"""
Tests for the history database module.
"""

from pathlib import Path


class TestHistoryDB:
    """Tests for HistoryDB class."""

    def test_init_creates_db(self, temp_state_dir):
        """Test that initialization creates database."""
        from mkv2cast.history import HistoryDB

        HistoryDB(temp_state_dir)

        # Should create either SQLite DB or JSONL file
        assert (temp_state_dir / "history.db").exists() or \
               (temp_state_dir / "history.log").exists()

    def test_record_start(self, temp_state_dir):
        """Test recording conversion start."""
        from mkv2cast.history import HistoryDB

        db = HistoryDB(temp_state_dir)

        entry_id = db.record_start(
            input_path=Path("/test/video.mkv"),
            backend="cpu",
            input_size=1000000
        )

        assert entry_id > 0

        # Verify it's recorded
        recent = db.get_recent(1)
        assert len(recent) == 1
        assert recent[0]["status"] == "running"

    def test_record_finish(self, temp_state_dir):
        """Test recording conversion finish."""
        from mkv2cast.history import HistoryDB

        db = HistoryDB(temp_state_dir)

        entry_id = db.record_start(
            input_path=Path("/test/video.mkv"),
            backend="cpu",
            input_size=1000000
        )

        db.record_finish(
            entry_id=entry_id,
            output_path=Path("/test/video.h264.cast.mkv"),
            status="done",
            encode_time=120.5,
            output_size=800000
        )

        recent = db.get_recent(1)
        assert len(recent) == 1
        assert recent[0]["status"] == "done"

    def test_record_skip(self, temp_state_dir):
        """Test recording skipped file."""
        from mkv2cast.history import HistoryDB

        db = HistoryDB(temp_state_dir)

        db.record_skip(
            input_path=Path("/test/video.mkv"),
            reason="output exists",
            backend="cpu"
        )

        recent = db.get_recent(1)
        assert len(recent) == 1
        assert recent[0]["status"] == "skipped"

    def test_get_recent_limit(self, temp_state_dir):
        """Test get_recent with limit."""
        from mkv2cast.history import HistoryDB

        db = HistoryDB(temp_state_dir)

        # Add multiple entries
        for i in range(10):
            db.record_skip(
                input_path=Path(f"/test/video{i}.mkv"),
                reason="test",
                backend="cpu"
            )

        recent = db.get_recent(5)
        assert len(recent) == 5

        recent = db.get_recent(20)
        assert len(recent) == 10

    def test_get_stats(self, temp_state_dir):
        """Test getting conversion statistics."""
        from mkv2cast.history import HistoryDB

        db = HistoryDB(temp_state_dir)

        # Add various conversions
        for i in range(3):
            entry_id = db.record_start(Path(f"/test/done{i}.mkv"), "cpu", 1000000)
            db.record_finish(entry_id, Path(f"/test/done{i}.cast.mkv"), "done",
                           encode_time=60, output_size=800000)

        for i in range(2):
            entry_id = db.record_start(Path(f"/test/fail{i}.mkv"), "cpu", 1000000)
            db.record_finish(entry_id, None, "failed", error_msg="test error")

        db.record_skip(Path("/test/skip.mkv"), "already exists", "cpu")

        stats = db.get_stats()

        assert "by_status" in stats
        assert stats["by_status"].get("done", 0) == 3
        assert stats["by_status"].get("failed", 0) == 2
        assert stats["by_status"].get("skipped", 0) == 1

    def test_clean_old(self, temp_state_dir):
        """Test cleaning old entries."""
        from mkv2cast.history import HistoryDB

        db = HistoryDB(temp_state_dir)

        # Add entries
        for i in range(5):
            db.record_skip(Path(f"/test/video{i}.mkv"), "test", "cpu")

        # Clean entries older than 0 days (all of them)
        db.clean_old(0)

        # Should have removed all entries
        recent = db.get_recent(10)
        assert len(recent) == 0


class TestHistoryDBFallback:
    """Tests for JSONL fallback behavior."""

    def test_jsonl_format(self, temp_state_dir, monkeypatch):
        """Test that JSONL format works."""
        # Force JSONL by patching SQLITE_AVAILABLE
        import mkv2cast.history
        monkeypatch.setattr(mkv2cast.history, "SQLITE_AVAILABLE", False)

        from mkv2cast.history import HistoryDB

        db = HistoryDB(temp_state_dir)

        entry_id = db.record_start(Path("/test/video.mkv"), "cpu", 1000000)
        db.record_finish(entry_id, Path("/test/video.cast.mkv"), "done")

        # Check JSONL file exists
        log_path = temp_state_dir / "history.log"
        assert log_path.exists()

        # Check content is JSON
        import json
        lines = log_path.read_text().strip().split("\n")
        for line in lines:
            json.loads(line)  # Should not raise
