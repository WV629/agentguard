"""Minimal FastAPI approval panel: pending queue (with plain-language explanation) + audit log.
Run: python -m agentguard.panel  -> http://127.0.0.1:8808  (testnet only)"""
from __future__ import annotations

import html

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse

from .audit import ApprovalQueue, AuditLog
from .config import load_settings
from .explainer import explain
from .policy import Action, Decision, TxRequest, Verdict

app = FastAPI(title="AgentGuard approval panel")


def rec_to_tx(rec: dict) -> TxRequest:
    t = rec["tx"]
    return TxRequest(t["signer_id"], t["receiver_id"],
                     [Action(a["kind"], int(a["deposit_yocto"]), a.get("method"), a.get("args"), a.get("gas", 30 * 10**12))
                      for a in t["actions"]], t.get("intent", ""))


def pending_explained(queue: ApprovalQueue) -> list[dict]:
    out = []
    for rid, rec in queue.pending().items():
        tx = rec_to_tx(rec)
        out.append({"id": rid, "explain": explain(tx, Decision(Verdict.REQUIRE_APPROVAL, rec["reasons"]))})
    return out


@app.get("/api/pending")
def api_pending():
    return pending_explained(ApprovalQueue(load_settings().approvals_path))


@app.get("/api/audit")
def api_audit():
    return AuditLog(load_settings().audit_log).read()


@app.post("/approve/{rid}")
def approve(rid: str):
    from .cli import build_gateway
    build_gateway(load_settings()).approve(rid)
    return RedirectResponse("/", status_code=303)


@app.post("/reject/{rid}")
def reject(rid: str):
    ApprovalQueue(load_settings().approvals_path).set_status(rid, "rejected", by="human")
    return RedirectResponse("/", status_code=303)


@app.get("/", response_class=HTMLResponse)
def index():
    s = load_settings()
    rows = "".join(
        f"<li>{html.escape(p['explain'])}<form method=post action=/approve/{p['id']} style=display:inline><button>Approve</button></form>"
        f"<form method=post action=/reject/{p['id']} style=display:inline><button>Reject</button></form></li>"
        for p in pending_explained(ApprovalQueue(s.approvals_path))) or "<li>nothing pending</li>"
    log = "".join(f"<tr><td>{r['ts']}</td><td>{r['event']}</td><td>{html.escape(r['tx']['receiver_id'])}</td>"
                  f"<td>{html.escape('; '.join(r.get('reasons', [])))}</td></tr>"
                  for r in reversed(AuditLog(s.audit_log).read()[-30:]))
    return (f"<h1>AgentGuard (testnet)</h1><h2>Pending approvals</h2><ul>{rows}</ul>"
            f"<h2>Audit log</h2><table border=1 cellpadding=4><tr><th>time</th><th>event</th><th>to</th><th>reasons</th></tr>{log}</table>")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8808)
