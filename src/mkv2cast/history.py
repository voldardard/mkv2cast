"""
History database for mkv2cast conversions.

Tracks all conversions with timestamps, durations, and results.
Uses SQLite as primary storage with JSONL fallback if SQLite is unavailable.
"""

import datetime
import json
import time
from pathlib import Path
from typing import Dict, List, Optional

# SQLite support (usually available, but check anyway)
try:
    import sqlite3
    SQLITE_AVAILABLE = True
except ImportError:
    SQLITE_AVAILABLE = False


class HistoryDB:
    """History storage with SQLite primary and JSONL text fallback."""

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self._use_sqlite = SQLITE_AVAILABLE

        if self._use_sqlite:
            self._db_path = state_dir / "history.db"
            self._init_sqlite()
        else:
            self._log_path = state_dir / "history.log"

    def _init_sqlite(self) -> None:
        """Initialize SQLite database."""
        conn = sqlite3.connect(str(self._db_path))
        conn.execute('''
            CREATE TABLE IF NOT EXISTS conversions (
                id INTEGER PRIMARY KEY,
                input_path TEXT NOT NULL,
                output_path TEXT,
                input_size INTEGER,
                output_size INTEGER,
                duration_ms INTEGER,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                backend TEXT,
                error_msg TEXT,
                encode_time_s REAL,
                integrity_time_s REAL
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_started ON conversions(started_at)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_status ON conversions(status)')
        conn.commit()
        conn.close()

    def record_start(self, input_path: Path, backend: str, input_size: int = 0) -> int:
        """Record conversion start, return entry ID."""
        started_at = datetime.datetime.now().isoformat()

        if self._use_sqlite:
            conn = sqlite3.connect(str(self._db_path))
            cur = conn.execute(
                '''INSERT INTO conversions (input_path, input_size, started_at, status, backend)
                   VALUES (?, ?, ?, ?, ?)''',
                (str(input_path), input_size, started_at, "running", backend)
            )
            entry_id = cur.lastrowid or 0
            conn.commit()
            conn.close()
            return entry_id
        else:
            # For JSONL, we use timestamp as pseudo-ID
            entry_id = int(time.time() * 1000)
            entry = {
                "id": entry_id,
                "input": str(input_path),
                "input_size": input_size,
                "started": started_at,
                "status": "running",
                "backend": backend
            }
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            return entry_id

    def record_finish(
        self,
        entry_id: int,
        output_path: Optional[Path],
        status: str,
        encode_time: float = 0,
        integrity_time: float = 0,
        output_size: int = 0,
        duration_ms: int = 0,
        error_msg: Optional[str] = None
    ) -> None:
        """Update entry with completion info."""
        finished_at = datetime.datetime.now().isoformat()

        if self._use_sqlite:
            conn = sqlite3.connect(str(self._db_path))
            conn.execute(
                '''UPDATE conversions SET
                   output_path=?, output_size=?, duration_ms=?, finished_at=?,
                   status=?, error_msg=?, encode_time_s=?, integrity_time_s=?
                   WHERE id=?''',
                (str(output_path) if output_path else None, output_size, duration_ms,
                 finished_at, status, error_msg, encode_time, integrity_time, entry_id)
            )
            conn.commit()
            conn.close()
        else:
            # For JSONL, append a new line with the update
            entry = {
                "id": entry_id,
                "output": str(output_path) if output_path else None,
                "output_size": output_size,
                "finished": finished_at,
                "status": status,
                "encode_time": encode_time,
                "integrity_time": integrity_time,
                "error_msg": error_msg
            }
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

    def record_skip(self, input_path: Path, reason: str, backend: str) -> None:
        """Record a skipped file."""
        now = datetime.datetime.now().isoformat()

        if self._use_sqlite:
            conn = sqlite3.connect(str(self._db_path))
            conn.execute(
                '''INSERT INTO conversions (input_path, started_at, finished_at, status, backend, error_msg)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (str(input_path), now, now, "skipped", backend, reason)
            )
            conn.commit()
            conn.close()
        else:
            entry = {
                "input": str(input_path),
                "started": now,
                "finished": now,
                "status": "skipped",
                "backend": backend,
                "reason": reason
            }
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

    def get_recent(self, limit: int = 20) -> List[dict]:
        """Get recent conversions."""
        if self._use_sqlite:
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                '''SELECT * FROM conversions ORDER BY started_at DESC LIMIT ?''',
                (limit,)
            )
            rows = [dict(row) for row in cur.fetchall()]
            conn.close()
            return rows
        else:
            # Read JSONL and get last N entries
            if not self._log_path.exists():
                return []
            entries = []
            with self._log_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            # Merge updates with starts (by id)
            merged: Dict[int, dict] = {}
            for e in entries:
                eid = e.get("id")
                if eid in merged:
                    merged[eid].update(e)
                else:
                    merged[eid] = e
            # Sort by started time descending
            result = sorted(merged.values(), key=lambda x: x.get("started", ""), reverse=True)
            return result[:limit]

    def get_stats(self) -> dict:
        """Get conversion statistics."""
        if self._use_sqlite:
            conn = sqlite3.connect(str(self._db_path))
            stats: dict = {}

            # Total counts by status
            cur = conn.execute('SELECT status, COUNT(*) FROM conversions GROUP BY status')
            stats["by_status"] = {row[0]: row[1] for row in cur.fetchall()}

            # Average encode time for successful conversions
            cur = conn.execute(
                'SELECT AVG(encode_time_s), SUM(encode_time_s) FROM conversions WHERE status="done" AND encode_time_s > 0'
            )
            row = cur.fetchone()
            stats["avg_encode_time"] = row[0] or 0
            stats["total_encode_time"] = row[1] or 0

            # Total size processed
            cur = conn.execute('SELECT SUM(input_size), SUM(output_size) FROM conversions WHERE status="done"')
            row = cur.fetchone()
            stats["total_input_size"] = row[0] or 0
            stats["total_output_size"] = row[1] or 0

            conn.close()
            return stats

        # Basic stats from JSONL (non-SQLite path)
        recent = self.get_recent(1000)
        result: dict = {"by_status": {}}
        for e in recent:
            s = e.get("status", "unknown")
            result["by_status"][s] = result["by_status"].get(s, 0) + 1

        done = [e for e in recent if e.get("status") == "done"]
        if done:
            times = [e.get("encode_time", 0) for e in done if e.get("encode_time")]
            result["avg_encode_time"] = sum(times) / len(times) if times else 0
            result["total_encode_time"] = sum(times)
        else:
            result["avg_encode_time"] = 0
            result["total_encode_time"] = 0

        result["total_input_size"] = sum(e.get("input_size", 0) for e in done)
        result["total_output_size"] = sum(e.get("output_size", 0) for e in done)
        return result

    def clean_old(self, days: int) -> int:
        """Remove entries older than N days. Returns count removed."""
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()

        if self._use_sqlite:
            conn = sqlite3.connect(str(self._db_path))
            cur = conn.execute('DELETE FROM conversions WHERE started_at < ?', (cutoff,))
            count = cur.rowcount
            conn.commit()
            conn.close()
            return count
        else:
            # For JSONL, rewrite file without old entries
            if not self._log_path.exists():
                return 0
            entries = []
            removed = 0
            with self._log_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            e = json.loads(line)
                            if e.get("started", "") >= cutoff:
                                entries.append(line)
                            else:
                                removed += 1
                        except json.JSONDecodeError:
                            pass
            with self._log_path.open("w", encoding="utf-8") as f:
                for line in entries:
                    f.write(line + "\n")
            return removed
