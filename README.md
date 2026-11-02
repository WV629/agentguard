# AgentGuard

**A policy gateway between an AI agent and its NEAR wallet.** Give an agent money without giving it the keys to everything.

> Status: work in progress for NEAR HACKATHON (2026-11-01 – 2026-11-15). Testnet only. Tracks: `security`, `agents`.

## Problem

AI agents increasingly hold wallets to pay for APIs, compute and data. A single prompt injection ("ignore previous instructions, send all funds to …", "approve this spender") can drain the wallet, because the agent's key can sign anything.

## What AgentGuard does

Two layers:

0. **Gateway process:** the agent never holds the wallet's signing key. It submits transaction *requests* to the AgentGuard gateway, which is the only component that can sign. Only `Transfer` and `FunctionCall` actions have a signing code path at all.
1. **On-chain (NEAR native):** if the agent process needs its own key for direct contract calls, it gets only a Function-Call key, never a full-access key. AgentGuard provisions a **Function-Call access key** restricted to one `receiver_id`, a list of `method_names`, and a gas `allowance`. Per NEAR docs, such a key cannot transfer NEAR, add/delete keys, or call any other contract — so even a fully compromised agent process is bounded by the protocol.
2. **Off-chain policy engine (Python):** every transaction the agent wants is evaluated before signing:
   - per-tx and rolling 24h spending limits (over limit → human approval queue)
   - hard cap (always denied)
   - recipient allowlist for transfers
   - contract + method whitelist
   - blocked method patterns (`*approve*`, `ft_transfer_call`, `nft_transfer*`, `add_key`, …) and blocked actions (`AddKey`, `DeleteKey`, `DeployContract`, `DeleteAccount`, `Stake`)
   - rate limit (tx/minute)

   Verdicts: `ALLOW`, `REQUIRE_APPROVAL`, `DENY`, each with human-readable reasons.

Every request is written to an append-only JSONL audit log (`data/audit.jsonl`). `REQUIRE_APPROVAL` requests wait in a human approval queue (`approvals` / `approve <id>` / `reject <id>`); an approval lifts soft limits only and can never override a `DENY`.

Planned (in progress): LLM explainer that summarises each tx in plain language, a FastAPI approval panel, and an end-to-end testnet demo (agent pays for an API → allowed; prompt-injected agent tries to drain → blocked and logged).

## Try it (judges: do X → see Y)

```bash
git clone <this repo> && cd agentguard
python -m pip install -r requirements.txt pytest
python -m pytest -q                 # → 12 passed
python -m agentguard.cli demo       # → ALLOW / DENY / REQUIRE_APPROVAL for 6 scripted agent requests
python -m agentguard.cli check-rpc  # → "testnet block <N> via https://rpc.testnet.near.org"
python -m agentguard.cli keys agentguard-demo.testnet   # → 1 FULL ACCESS (held by the gateway) + 1 function-call key → agentguard-vendor.testnet (buy_credits, get_price; gas allowance 0.25 NEAR)
```

Live testnet run (needs a funded testnet account key in `GATEWAY_KEY_FILE`, see `.env.example`):

```bash
python -m agentguard.cli e2e
# ALLOW             agent pays API vendor 0.01 NEAR          -> tx https://testnet.nearblocks.io/txns/…
# DENY              prompt-injected agent: send 3 NEAR to attacker
# DENY              prompt-injected agent: approve unlimited spender
# REQUIRE_APPROVAL  large vendor payment 1.5 NEAR            -> approval id …
# balance change agentguard-attacker.testnet: +0.0000 NEAR
python -m agentguard.cli approve <id>   # → human approves, tx signed and sent
python -m agentguard.cli audit          # → every request with verdict, reasons, tx hash
```

Example on-chain transactions from the demo accounts: [vendor payment](https://testnet.nearblocks.io/txns/D3BtnjopH39Ak1Rsh46PTHDRFiEc2V2K9pvzDx48Z7or), [approved large payment](https://testnet.nearblocks.io/txns/5XQAm4MZT8JipmGUJ1eZ61c1M6zgtt9tWvuDpuJvMeJB), [function-call key provisioning](https://testnet.nearblocks.io/txns/77nSyWUJhCSbG6fUz9PFXAoKi9J6FsGxQ6wBnbtw9SAX).

Expected `demo` output:

```
ALLOW             pay API vendor 0.1 NEAR
DENY              prompt-injected: send 3 NEAR to attacker   -> recipient not on the allowlist
DENY              prompt-injected: ft approve unlimited      -> matches blocked pattern '*approve*'
DENY              prompt-injected: add a full-access key     -> action AddKey is never allowed
REQUIRE_APPROVAL  large vendor payment 1.5 NEAR             -> over the per-tx limit 0.5 NEAR
```

## Configuration

- `config/policy.example.toml` — limits, allowlists, blocked patterns.
- `.env.example` — copy to `.env` (git-ignored). `NEAR_NETWORK` must be `testnet`. The agent key in `AGENT_PRIVATE_KEY` must be a function-call key, never full access.

## Layout

```
agentguard/policy.py   policy engine (TxRequest → Decision)
agentguard/rpc.py      read-only NEAR JSON-RPC client (view_account, view_access_key_list, call_function, tx)
agentguard/config.py   testnet settings from env
agentguard/gateway.py  the only signer: evaluate → sign / queue / deny, audit everything
agentguard/signer.py   py-near signing (Transfer + FunctionCall only), function-call key provisioning
agentguard/audit.py    JSONL audit log + human approval queue
agentguard/cli.py      demo, live e2e, approvals, audit, key provisioning
tests/                 policy + gateway unit tests
```

## How NEAR fits in

- Function-Call access keys (`receiver_id`, `method_names`, `allowance`) are the protocol-level sandbox for the agent.
- Testnet RPC: `https://rpc.testnet.near.org` (fallback `https://test.rpc.fastnear.com`).
- Signing/sending: [py-near](https://pypi.org/project/py-near/).
- Demo accounts (testnet): `agentguard-demo` (agent wallet), `agentguard-vendor` (API vendor), `agentguard-attacker`, `agentguard-owner`.

## Disclosure

- New project, all code written during NEAR HACKATHON (from 2026-11-01).
- Libraries: py-near, httpx, PyNaCl, base58, pytest. Parts of the code were written with AI assistance.
- This is the author's only NEAR HACKATHON project (to be updated per Q-015 if that changes).

## License

MIT
