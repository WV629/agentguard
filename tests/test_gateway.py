from agentguard.audit import ApprovalQueue, AuditLog
from agentguard.gateway import Gateway
from agentguard.policy import Action, Policy, PolicyEngine, TxRequest, Verdict, near_to_yocto

AGENT = "agentguard-demo.testnet"


def gw(tmp_path, sent):
    def sender(tx):
        sent.append(tx)
        return f"HASH{len(sent)}"
    return Gateway(PolicyEngine(Policy.from_toml("config/policy.example.toml")), sender,
                   AuditLog(str(tmp_path / "audit.jsonl")), ApprovalQueue(str(tmp_path / "appr.jsonl")))


def t(to, near):
    return TxRequest(AGENT, to, [Action("Transfer", near_to_yocto(near))])


def test_allowed_is_signed_and_logged(tmp_path):
    sent = []
    g = gw(tmp_path, sent)
    out = g.submit(t("agentguard-vendor.testnet", 0.01))
    assert out.tx_hash == "HASH1" and len(sent) == 1
    assert g.audit.read()[-1]["event"] == "signed"


def test_denied_is_never_signed(tmp_path):
    sent = []
    g = gw(tmp_path, sent)
    out = g.submit(t("agentguard-attacker.testnet", 3))
    assert out.decision.verdict is Verdict.DENY and not sent
    assert g.audit.read()[-1]["event"] == "denied"


def test_over_limit_waits_for_human_then_sends(tmp_path):
    sent = []
    g = gw(tmp_path, sent)
    out = g.submit(t("agentguard-vendor.testnet", 1.5))
    assert out.decision.verdict is Verdict.REQUIRE_APPROVAL and not sent
    assert out.approval_id in g.approvals.pending()
    done = g.approve(out.approval_id)
    assert done.tx_hash and len(sent) == 1 and not g.approvals.pending()


def test_approval_cannot_override_a_deny(tmp_path):
    sent = []
    g = gw(tmp_path, sent)
    out = g.submit(t("agentguard-vendor.testnet", 1.5))
    g.engine.policy.recipient_allowlist.clear()  # policy tightened while tx was waiting
    res = g.approve(out.approval_id)
    assert res.decision.verdict is Verdict.DENY and not sent


def test_rejected_is_never_sent(tmp_path):
    sent = []
    g = gw(tmp_path, sent)
    out = g.submit(t("agentguard-vendor.testnet", 1.5))
    g.reject(out.approval_id)
    assert not sent and not g.approvals.pending()


def test_audit_log_is_append_only_and_ordered(tmp_path):
    sent = []
    g = gw(tmp_path, sent)
    g.submit(t("agentguard-vendor.testnet", 0.01))
    g.submit(t("agentguard-attacker.testnet", 3))
    ev = [r["event"] for r in g.audit.read()]
    assert ev == ["signed", "denied"]
