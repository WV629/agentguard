"""Signs and sends a TxRequest on NEAR testnet with py-near.

Only Transfer and FunctionCall actions are ever built here: key management,
deploy, stake and delete actions have no code path at all, so the gateway
cannot be talked into signing them even if the policy were misconfigured.
"""
from __future__ import annotations

import asyncio
import json

from py_near.account import Account
from py_near import transactions

from .policy import TxRequest

SIGNABLE = {"Transfer", "FunctionCall"}


def _actions(tx: TxRequest) -> list:
    out = []
    for a in tx.actions:
        if a.kind == "Transfer":
            out.append(transactions.create_transfer_action(a.deposit_yocto))
        elif a.kind == "FunctionCall":
            args = json.dumps(a.args or {}).encode()
            out.append(transactions.create_function_call_action(a.method or "", args, a.gas, a.deposit_yocto))
        else:
            raise ValueError(f"signer refuses action kind {a.kind}")
    return out


async def _send(rpc_url: str, signer_id: str, private_key: str, tx: TxRequest) -> str:
    acc = Account(signer_id, private_key, rpc_url)
    await acc.startup()
    try:
        res = await acc.sign_and_submit_tx(tx.receiver_id, _actions(tx))
        if isinstance(res.status, dict) and "Failure" in res.status:
            raise RuntimeError(f"tx {res.transaction.hash} failed on chain: {res.status['Failure']}")
        return res.transaction.hash
    finally:
        await acc.shutdown()


def sign_and_send(rpc_url: str, private_key: str, tx: TxRequest) -> str:
    """Returns the transaction hash once the tx is executed on chain."""
    return asyncio.run(_send(rpc_url, tx.signer_id, private_key, tx))


async def _add_fc_key(rpc_url, account_id, private_key, public_key, receiver_id, methods, allowance) -> str:
    acc = Account(account_id, private_key, rpc_url)
    await acc.startup()
    try:
        res = await acc.add_public_key(public_key, receiver_id, methods, allowance)
        return res.transaction.hash
    finally:
        await acc.shutdown()


def add_function_call_key(rpc_url: str, account_id: str, private_key: str, public_key: str,
                          receiver_id: str, methods: list[str], allowance_yocto: int) -> str:
    """Owner-side provisioning: add a Function-Call key for the agent process."""
    return asyncio.run(_add_fc_key(rpc_url, account_id, private_key, public_key, receiver_id, methods, allowance_yocto))
