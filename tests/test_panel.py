from fastapi.testclient import TestClient
from agentguard import panel
from agentguard.audit import ApprovalQueue
from agentguard.policy import Action, Decision, TxRequest, Verdict


def test_pending_explained(tmp_path, monkeypatch):
    q = ApprovalQueue(str(tmp_path / "a.jsonl"))
    q.add(TxRequest("a.testnet", "v.testnet", [Action("Transfer", 10**24)], "buy"), Decision(Verdict.REQUIRE_APPROVAL, ["over per-tx"]))
    r = panel.pending_explained(q)
    assert len(r) == 1 and "Held for human approval" in r[0]["explain"]
