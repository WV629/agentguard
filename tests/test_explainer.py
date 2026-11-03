from agentguard.explainer import explain
from agentguard.policy import Action, Policy, PolicyEngine, TxRequest, near_to_yocto


def test_explain_blocked():
    e = PolicyEngine(Policy.from_toml("config/policy.example.toml"))
    tx = TxRequest("a.testnet", "agentguard-attacker.testnet", [Action("Transfer", near_to_yocto(3))], "move funds")
    s = explain(tx, e.evaluate(tx))
    assert "send 3 NEAR" in s and "Blocked" in s and "move funds" in s
