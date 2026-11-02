"""Network configuration. Testnet only during the hackathon.

Secrets come from environment variables (or a local .env that is git-ignored);
they are never read from or written to the repository.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

NETWORKS = {
    "testnet": {
        "rpc_url": "https://rpc.testnet.near.org",
        "fallback_rpc_urls": ["https://test.rpc.fastnear.com"],
        "explorer_tx": "https://testnet.nearblocks.io/txns/{tx}",
        "explorer_account": "https://testnet.nearblocks.io/address/{account}",
        "faucet": "https://near-faucet.io/",
    },
}


def _load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class Settings:
    network: str
    rpc_url: str
    agent_account_id: str | None
    agent_private_key: str | None  # function-call key only (the agent's own process)
    gateway_private_key: str | None  # key the gateway signs with; never given to the agent
    policy_path: str
    audit_log: str
    approvals_path: str

    @property
    def explorer_tx(self) -> str:
        return NETWORKS[self.network]["explorer_tx"]


def _key_from(env_key: str, env_file: str) -> str | None:
    """A key comes from an env var, or from a JSON key file outside the repo
    (near-cli style: {"account_id", "public_key", "private_key"})."""
    if os.environ.get(env_key):
        return os.environ[env_key]
    path = os.path.expanduser(os.environ.get(env_file, ""))
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)["private_key"]
    return None


def load_settings() -> Settings:
    _load_dotenv()
    network = os.environ.get("NEAR_NETWORK", "testnet")
    if network != "testnet":
        raise RuntimeError("AgentGuard demo is testnet-only; set NEAR_NETWORK=testnet")
    return Settings(
        network=network,
        rpc_url=os.environ.get("NEAR_RPC_URL", NETWORKS[network]["rpc_url"]),
        agent_account_id=os.environ.get("AGENT_ACCOUNT_ID"),
        agent_private_key=_key_from("AGENT_PRIVATE_KEY", "AGENT_KEY_FILE"),
        gateway_private_key=_key_from("GATEWAY_PRIVATE_KEY", "GATEWAY_KEY_FILE"),
        policy_path=os.environ.get("AGENTGUARD_POLICY", "config/policy.example.toml"),
        audit_log=os.environ.get("AGENTGUARD_AUDIT_LOG", "data/audit.jsonl"),
        approvals_path=os.environ.get("AGENTGUARD_APPROVALS", "data/approvals.jsonl"),
    )
