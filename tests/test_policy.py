from agentguard.policy import Action, Policy, PolicyEngine, TxRequest, Verdict, near_to_yocto

AGENT = "agentguard-demo.testnet"


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


def engine(clock=None):
    return PolicyEngine(Policy.from_toml("config/policy.example.toml"), clock=clock or Clock())


def transfer(to, near):
    return TxRequest(AGENT, to, [Action("Transfer", near_to_yocto(near))])


def call(contract, method, deposit=0.0):
    return TxRequest(AGENT, contract, [Action("FunctionCall", near_to_yocto(deposit), method=method)])


def test_small_payment_to_allowlisted_vendor_is_allowed():
    assert engine().evaluate(transfer("agentguard-vendor.testnet", 0.1)).verdict is Verdict.ALLOW


def test_transfer_to_unknown_recipient_is_denied():
    d = engine().evaluate(transfer("agentguard-attacker.testnet", 0.01))
    assert d.verdict is Verdict.DENY and "allowlist" in d.reasons[0]


def test_approve_like_methods_are_denied_even_on_whitelisted_contract():
    assert engine().evaluate(call("usdc.fakes.testnet", "ft_approve")).verdict is Verdict.DENY


def test_unlisted_method_and_contract_denied():
    e = engine()
    assert e.evaluate(call("usdc.fakes.testnet", "mint")).verdict is Verdict.DENY
    assert e.evaluate(call("random.testnet", "do_stuff")).verdict is Verdict.DENY


def test_key_management_actions_denied():
    assert engine().evaluate(TxRequest(AGENT, AGENT, [Action("AddKey")])).verdict is Verdict.DENY


def test_over_per_tx_limit_requires_approval_and_hard_cap_denies():
    e = engine()
    assert e.evaluate(transfer("agentguard-vendor.testnet", 1.0)).verdict is Verdict.REQUIRE_APPROVAL
    assert e.evaluate(transfer("agentguard-vendor.testnet", 6.0)).verdict is Verdict.DENY


def test_daily_limit_rolls_over_after_24h():
    clock = Clock()
    e = engine(clock)
    for _ in range(4):
        tx = transfer("agentguard-vendor.testnet", 0.5)
        assert e.evaluate(tx).verdict is Verdict.ALLOW
        e.record_signed(tx)
        clock.t += 120
    assert e.evaluate(transfer("agentguard-vendor.testnet", 0.1)).verdict is Verdict.REQUIRE_APPROVAL
    clock.t += 86_401
    assert e.evaluate(transfer("agentguard-vendor.testnet", 0.1)).verdict is Verdict.ALLOW


def test_rate_limit():
    e = engine()
    for _ in range(5):
        tx = transfer("agentguard-vendor.testnet", 0.01)
        assert e.evaluate(tx).allowed
        e.record_signed(tx)
    d = e.evaluate(transfer("agentguard-vendor.testnet", 0.01))
    assert d.verdict is Verdict.DENY and "rate limit" in d.reasons[0]


def test_policy_prefix_rewrites_demo_accounts():
    p = Policy.from_toml("config/policy.example.toml", "ag1234")
    assert "ag1234-vendor.testnet" in p.recipient_allowlist
    assert "ag1234-vendor.testnet" in p.contract_methods
    assert "usdc.fakes.testnet" in p.contract_methods
