"""Append-only JSONL audit log and a file-backed human approval queue."""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict
from typing import Any

from .policy import Decision, TxRequest


def tx_to_dict(tx: TxRequest) -> dict[str, Any]:
    d = asdict(tx)
    for a in d["actions"]:
        a["deposit_yocto"] = str(a["deposit_yocto"])  # keep yocto exact in JSON
    return d


class AuditLog:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def write(self, event: str, tx: TxRequest, decision: Decision | None = None, **extra: Any) -> dict:
        rec = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event": event,
            "tx": tx_to_dict(tx),
            **({"verdict": decision.verdict.value, "reasons": decision.reasons} if decision else {}),
            **extra,
        }
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    def read(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]


class ApprovalQueue:
    """Pending transactions waiting for a human. One JSON record per line;
    a later record with the same id and a status overrides the earlier one."""

    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def _append(self, rec: dict) -> None:
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def add(self, tx: TxRequest, decision: Decision) -> str:
        rid = uuid.uuid4().hex[:12]
        self._append({"id": rid, "status": "pending", "tx": tx_to_dict(tx), "reasons": decision.reasons})
        return rid

    def set_status(self, rid: str, status: str, **extra: Any) -> None:
        self._append({"id": rid, "status": status, **extra})

    def all(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        rec = json.loads(line)
                        out.setdefault(rec["id"], {}).update(rec)
        return out

    def pending(self) -> dict[str, dict]:
        return {k: v for k, v in self.all().items() if v["status"] == "pending"}
