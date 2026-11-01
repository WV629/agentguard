"""Minimal read-only NEAR JSON-RPC client (view calls, access keys, tx status).

Signing and sending go through py-near (see signer.py, day 2+). Keeping reads
on plain JSON-RPC makes the policy checks independent of the signing library.
"""
from __future__ import annotations

import base64
import json
from typing import Any

import httpx


class NearRpc:
    def __init__(self, url: str, timeout: float = 15.0):
        self.url = url
        self._client = httpx.Client(timeout=timeout)

    def _call(self, method: str, params: Any) -> Any:
        resp = self._client.post(
            self.url, json={"jsonrpc": "2.0", "id": "agentguard", "method": method, "params": params}
        )
        resp.raise_for_status()
        body = resp.json()
        if "error" in body:
            raise RuntimeError(f"RPC error: {body['error']}")
        return body["result"]

    def status(self) -> dict:
        return self._call("status", [])

    def view_account(self, account_id: str) -> dict:
        return self._call("query", {"request_type": "view_account", "finality": "final", "account_id": account_id})

    def view_access_key_list(self, account_id: str) -> list[dict]:
        res = self._call(
            "query", {"request_type": "view_access_key_list", "finality": "final", "account_id": account_id}
        )
        return res["keys"]

    def view_function(self, contract_id: str, method: str, args: dict | None = None) -> Any:
        res = self._call(
            "query",
            {
                "request_type": "call_function",
                "finality": "final",
                "account_id": contract_id,
                "method_name": method,
                "args_base64": base64.b64encode(json.dumps(args or {}).encode()).decode(),
            },
        )
        raw = bytes(res["result"])
        return json.loads(raw) if raw else None

    def tx_status(self, tx_hash: str, sender_id: str) -> dict:
        return self._call("tx", {"tx_hash": tx_hash, "sender_account_id": sender_id, "wait_until": "FINAL"})


def describe_key(key: dict) -> str:
    """Human-readable summary of an access key's on-chain permission."""
    perm = key["access_key"]["permission"]
    if perm == "FullAccess":
        return f"{key['public_key'][:16]}… FULL ACCESS"
    fc = perm["FunctionCall"]
    methods = ", ".join(fc.get("method_names") or []) or "any method"
    allowance = fc.get("allowance")
    allow = "unlimited gas" if allowance is None else f"gas allowance {int(allowance) / 1e24:.4f} NEAR"
    return f"{key['public_key'][:16]}… function-call → {fc['receiver_id']} ({methods}; {allow})"
