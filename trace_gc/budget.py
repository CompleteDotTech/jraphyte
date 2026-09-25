"""Shared, persistent, monotonic per-run budgets across services and retries."""
from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Any, Mapping
from .canonical import dumps, loads
from .errors import ContractError, require

RESOURCES = {"retrieval_requests","model_calls","retries","solver_expansions","review_actions","request_bytes"}

class RunBudget:
    def __init__(self, path: str | Path, run_id: str, limits: Mapping[str,int]):
        require(bool(run_id) and set(limits) == RESOURCES,"BUDGET_CONFIG","all resource limits required")
        require(all(type(x) is int and x >= 0 for x in limits.values()),"BUDGET_CONFIG","nonnegative integer limits")
        self.path, self.run_id = str(path), run_id
        self.db = sqlite3.connect(self.path, isolation_level=None, timeout=10, check_same_thread=False)
        import threading
        self._lock = threading.RLock()
        try:
            self.db.execute("CREATE TABLE IF NOT EXISTS trace_budgets (run_id TEXT PRIMARY KEY, limits TEXT NOT NULL, used TEXT NOT NULL)")
            with self._lock:
                self.db.execute("BEGIN IMMEDIATE")
                self.db.execute("INSERT OR IGNORE INTO trace_budgets VALUES (?,?,?)",(run_id,dumps(dict(limits)),dumps({k:0 for k in limits})))
                current = self.db.execute("SELECT limits FROM trace_budgets WHERE run_id=?",(run_id,)).fetchone()
                require(loads(current[0]) == dict(limits),"BUDGET_CONFIG_CHANGED","cannot reset an existing run's limits")
                self.db.execute("COMMIT")
        except BaseException:
            try:
                if self.db.in_transaction:self.db.execute("ROLLBACK")
            finally:
                self.db.close()
            raise

    def consume(self, resource: str, amount: int = 1) -> dict[str,int]:
        return self.consume_many({resource:amount})

    def consume_many(self, requests: Mapping[str,int]) -> dict[str,int]:
        require(set(requests) <= RESOURCES and all(type(v) is int and v >= 0 for v in requests.values()),
                "BUDGET_REQUEST","invalid resource or amount")
        with self._lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                limit_text, used_text = self.db.execute("SELECT limits,used FROM trace_budgets WHERE run_id=?",(self.run_id,)).fetchone()
                limits, used = loads(limit_text), loads(used_text)
                require(all(used[k]+v <= limits[k] for k,v in requests.items()),"RUN_BUDGET_EXHAUSTED","shared run cap reached")
                for key,value in requests.items():used[key] += value
                self.db.execute("UPDATE trace_budgets SET used=? WHERE run_id=?",(dumps(used),self.run_id))
                self.db.execute("COMMIT")
                return dict(used)
            except BaseException:
                if self.db.in_transaction:self.db.execute("ROLLBACK")
                raise

    def snapshot(self) -> dict[str,Any]:
        with self._lock:
            row=self.db.execute("SELECT limits,used FROM trace_budgets WHERE run_id=?",(self.run_id,)).fetchone()
            return {"run_id":self.run_id,"limits":loads(row[0]),"used":loads(row[1])}

    def close(self) -> None:
        self.db.close()

    def __enter__(self):return self
    def __exit__(self,*args):self.close()
