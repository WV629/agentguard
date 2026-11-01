"""AgentGuard policy engine.

Every transaction an agent wants to sign is described as a TxRequest and run
through PolicyEngine.evaluate(), which returns one of:

  ALLOW            sign and send
  REQUIRE_APPROVAL park in the human approval queue (over a soft limit)
  DENY             never sign (blocked method/action, unknown target, hard cap, rate limit)

This is the off-chain layer. The on-chain layer is NEAR's native
Function-Call access key (receiver_id + method_names + gas allowance), which
AgentGuard provisions for the agent so that even a bypassed gateway cannot
transfer NEAR or call other contracts.
"""
from __future__ import annotations

import fnmatch
import time
import tomllib
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

YOCTO = 10**24


def near_to_yocto(near: float) -> int:
    return int(round(near * YOCTO))


class Verdict(str, Enum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


@dataclass
class Action:
    kind: str                     # "Transfer" | "FunctionCall" | "AddKey" | ...
    deposit_yocto: int = 0        # attached NEAR (transfer amount or call deposit)
    method: str | None = None     # for FunctionCall
    args: dict | None = None
    gas: int = 30 * 10**12


@dataclass
class TxRequest:
    signer_id: str
    receiver_id: str
    actions: list[Action]
    intent: str = ""              # the agent's stated reason, shown to humans

    @property
    def total_deposit_yocto(self) -> int:
        return sum(a.deposit_yocto for a in self.actions)


@dataclass
class Decision:
    verdict: Verdict
    reasons: list[str] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.verdict is Verdict.ALLOW


@dataclass
class Policy:
    per_tx_max_yocto: int
    daily_max_yocto: int
    hard_deny_yocto: int
    max_tx_per_minute: int
    recipient_allowlist: set[str]
    contract_methods: dict[str, list[str]]
    blocked_methods: list[str]
    blocked_actions: set[str]

    @classmethod
    def from_toml(cls, path: str) -> "Policy":
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
        lim = raw.get("limits", {})
        return cls(
            per_tx_max_yocto=near_to_yocto(lim.get("per_tx_max_near", 0.5)),
            daily_max_yocto=near_to_yocto(lim.get("daily_max_near", 2.0)),
            hard_deny_yocto=near_to_yocto(lim.get("hard_deny_near", 5.0)),
            max_tx_per_minute=int(lim.get("max_tx_per_minute", 5)),
            recipient_allowlist=set(raw.get("recipients", {}).get("allowlist", [])),
            contract_methods={k: list(v) for k, v in raw.get("contracts", {}).items()},
            blocked_methods=list(raw.get("blocked", {}).get("methods", [])),
            blocked_actions=set(raw.get("blocked", {}).get("actions", [])),
        )


class PolicyEngine:
    def __init__(self, policy: Policy, clock=time.time):
        self.policy = policy
        self.clock = clock
        self._spend: deque[tuple[float, int]] = deque()   # (ts, yocto) of signed txs
        self._sent: deque[float] = deque()                # ts of signed txs

    # -- bookkeeping -------------------------------------------------------
    def _prune(self, now: float) -> None:
        while self._spend and now - self._spend[0][0] > 86_400:
            self._spend.popleft()
        while self._sent and now - self._sent[0] > 60:
            self._sent.popleft()

    def spent_24h_yocto(self) -> int:
        self._prune(self.clock())
        return sum(v for _, v in self._spend)

    def record_signed(self, tx: TxRequest) -> None:
        now = self.clock()
        self._spend.append((now, tx.total_deposit_yocto))
        self._sent.append(now)

    # -- evaluation --------------------------------------------------------
    def _method_blocked(self, method: str) -> str | None:
        for pat in self.policy.blocked_methods:
            if fnmatch.fnmatchcase(method, pat):
                return pat
        return None

    def evaluate(self, tx: TxRequest) -> Decision:
        p = self.policy
        now = self.clock()
        self._prune(now)
        deny: list[str] = []
        approve: list[str] = []

        if not tx.actions:
            deny.append("empty transaction")

        for a in tx.actions:
            if a.kind in p.blocked_actions:
                deny.append(f"action {a.kind} is never allowed for an agent key")
            elif a.kind == "Transfer":
                if tx.receiver_id not in p.recipient_allowlist:
                    deny.append(f"recipient {tx.receiver_id} is not on the allowlist")
            elif a.kind == "FunctionCall":
                method = a.method or ""
                pat = self._method_blocked(method)
                allowed = p.contract_methods.get(tx.receiver_id)
                if pat:
                    deny.append(f"method {method} matches blocked pattern '{pat}'")
                elif allowed is None:
                    deny.append(f"contract {tx.receiver_id} is not whitelisted")
                elif "*" not in allowed and method not in allowed:
                    deny.append(f"method {method} is not allowed on {tx.receiver_id}")
            else:
                deny.append(f"unknown action kind {a.kind}")

        total = tx.total_deposit_yocto
        if total > p.hard_deny_yocto:
            deny.append(f"amount {total / YOCTO:g} NEAR exceeds hard cap {p.hard_deny_yocto / YOCTO:g} NEAR")
        if len(self._sent) >= p.max_tx_per_minute:
            deny.append(f"rate limit: {p.max_tx_per_minute} tx/minute reached")

        if deny:
            return Decision(Verdict.DENY, deny)

        if total > p.per_tx_max_yocto:
            approve.append(f"amount {total / YOCTO:g} NEAR is over the per-tx limit {p.per_tx_max_yocto / YOCTO:g} NEAR")
        spent = sum(v for _, v in self._spend)
        if spent + total > p.daily_max_yocto:
            approve.append(
                f"24h spend would reach {(spent + total) / YOCTO:g} NEAR, over the daily limit {p.daily_max_yocto / YOCTO:g} NEAR"
            )
        if approve:
            return Decision(Verdict.REQUIRE_APPROVAL, approve)
        return Decision(Verdict.ALLOW, ["within policy"])
