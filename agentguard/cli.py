"""Small CLI for day-1 checks: `python -m agentguard.cli check-rpc | keys <account> | demo`."""
from __future__ import annotations

import sys

from .config import load_settings
from .policy import Action, Policy, PolicyEngine, TxRequest, near_to_yocto
from .rpc import NearRpc, describe_key


def demo(policy_path: str) -> None:
    engine = PolicyEngine(Policy.from_toml(policy_path))
    agent = "agentguard-demo.testnet"
    cases = [
        ("pay API vendor 0.1 NEAR", TxRequest(agent, "api-vendor.testnet", [Action("Transfer", near_to_yocto(0.1))])),
        ("buy credits on whitelisted market", TxRequest(agent, "market.agentguard-demo.testnet",
                                                        [Action("FunctionCall", method="buy_credits")])),
        ("prompt-injected: send 3 NEAR to attacker", TxRequest(agent, "attacker.testnet", [Action("Transfer", near_to_yocto(3))])),
        ("prompt-injected: ft approve unlimited", TxRequest(agent, "usdc.fakes.testnet",
                                                            [Action("FunctionCall", method="ft_approve")])),
        ("prompt-injected: add a full-access key", TxRequest(agent, agent, [Action("AddKey")])),
        ("large vendor payment 1.5 NEAR", TxRequest(agent, "api-vendor.testnet", [Action("Transfer", near_to_yocto(1.5))])),
    ]
    for label, tx in cases:
        d = engine.evaluate(tx)
        if d.allowed:
            engine.record_signed(tx)
        print(f"{d.verdict.value:17} {label}\n{'':17} -> {'; '.join(d.reasons)}")


def main(argv: list[str]) -> int:
    s = load_settings()
    cmd = argv[1] if len(argv) > 1 else "demo"
    if cmd == "check-rpc":
        st = NearRpc(s.rpc_url).status()
        print(f"{st['chain_id']} block {st['sync_info']['latest_block_height']} via {s.rpc_url}")
    elif cmd == "keys":
        for k in NearRpc(s.rpc_url).view_access_key_list(argv[2]):
            print(describe_key(k))
    elif cmd == "demo":
        demo(s.policy_path)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
