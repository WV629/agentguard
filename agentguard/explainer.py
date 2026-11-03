"""Plain-language summary of a tx request + policy decision (rule-based; an LLM can be swapped in via explain_llm hook)."""
from __future__ import annotations

from .policy import YOCTO, Decision, TxRequest


def explain(tx: TxRequest, d: Decision) -> str:
    parts = []
    for a in tx.actions:
        if a.kind == "Transfer":
            parts.append(f"send {int(a.deposit_yocto) / YOCTO:g} NEAR to {tx.receiver_id}")
        elif a.kind == "FunctionCall":
            parts.append(f"call {a.method}() on {tx.receiver_id}")
        else:
            parts.append(f"perform {a.kind} on {tx.receiver_id}")
    what = " and ".join(parts) or "do nothing"
    verdict = {"ALLOW": "Approved automatically", "REQUIRE_APPROVAL": "Held for human approval",
               "DENY": "Blocked"}.get(d.verdict.value, d.verdict.value)
    why = "; ".join(d.reasons)
    intent = f' Agent said: "{tx.intent}".' if tx.intent else ""
    return f"{tx.signer_id} wants to {what}.{intent} {verdict}: {why}"
