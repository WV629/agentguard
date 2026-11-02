"""The gateway: the only component that holds a signing key.

agent -> Gateway.submit(TxRequest) -> PolicyEngine.evaluate
   ALLOW            -> sign & send on testnet, log tx hash
   REQUIRE_APPROVAL -> park in the approval queue, a human approves/rejects later
   DENY             -> never signed, logged with reasons
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .audit import ApprovalQueue, AuditLog
from .policy import Action, Decision, PolicyEngine, TxRequest, Verdict

Sender = Callable[[TxRequest], str]  # returns tx hash


@dataclass
class Outcome:
    decision: Decision
    tx_hash: str | None = None
    approval_id: str | None = None
    error: str | None = None


class Gateway:
    def __init__(self, engine: PolicyEngine, sender: Sender, audit: AuditLog, approvals: ApprovalQueue):
        self.engine = engine
        self.sender = sender
        self.audit = audit
        self.approvals = approvals

    def _send(self, tx: TxRequest, decision: Decision, event: str) -> Outcome:
        try:
            h = self.sender(tx)
        except Exception as exc:  # network / chain failure: log, never retry silently
            self.audit.write("send_failed", tx, decision, error=str(exc))
            return Outcome(decision, error=str(exc))
        self.engine.record_signed(tx)
        self.audit.write(event, tx, decision, tx_hash=h)
        return Outcome(decision, tx_hash=h)

    def submit(self, tx: TxRequest) -> Outcome:
        d = self.engine.evaluate(tx)
        if d.verdict is Verdict.ALLOW:
            return self._send(tx, d, "signed")
        if d.verdict is Verdict.REQUIRE_APPROVAL:
            rid = self.approvals.add(tx, d)
            self.audit.write("queued_for_approval", tx, d, approval_id=rid)
            return Outcome(d, approval_id=rid)
        self.audit.write("denied", tx, d)
        return Outcome(d)

    def approve(self, rid: str, approver: str = "human") -> Outcome:
        rec = self.approvals.pending().get(rid)
        if rec is None:
            raise KeyError(f"no pending approval {rid}")
        t = rec["tx"]
        tx = TxRequest(t["signer_id"], t["receiver_id"],
                       [Action(a["kind"], int(a["deposit_yocto"]), a.get("method"), a.get("args"), a.get("gas", 30 * 10**12))
                        for a in t["actions"]], t.get("intent", ""))
        # Re-check the hard rules: approval lifts soft limits only, never a DENY.
        d = self.engine.evaluate(tx)
        if d.verdict is Verdict.DENY:
            self.approvals.set_status(rid, "rejected", by="policy", reasons=d.reasons)
            self.audit.write("approval_blocked", tx, d, approval_id=rid)
            return Outcome(d, approval_id=rid)
        out = self._send(tx, Decision(Verdict.ALLOW, [f"approved by {approver}"] + rec.get("reasons", [])), "signed_after_approval")
        self.approvals.set_status(rid, "sent" if out.tx_hash else "failed", by=approver, tx_hash=out.tx_hash)
        out.approval_id = rid
        return out

    def reject(self, rid: str, approver: str = "human") -> None:
        self.approvals.set_status(rid, "rejected", by=approver)
