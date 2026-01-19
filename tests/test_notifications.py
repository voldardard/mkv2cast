"""
Tests for the notifications module.
"""

import shutil

import pytest


class TestNotificationSupport:
    """Tests for notification capability detection."""

    def test_check_notification_support(self):
        """Test notification support detection."""
        from mkv2cast.notifications import check_notification_support

        support = check_notification_support()

        assert "notify_send" in support
        assert "plyer" in support
        assert "any" in support
        assert isinstance(support["notify_send"], bool)
        assert isinstance(support["plyer"], bool)
        assert isinstance(support["any"], bool)

    def test_has_notify_send(self):
        """Test notify-send detection."""
        from mkv2cast.notifications import NOTIFY_SEND_AVAILABLE

        has_notify_send = shutil.which("notify-send") is not None
        assert NOTIFY_SEND_AVAILABLE == has_notify_send


class TestSendNotification:
    """Tests for send_notification function."""

    def test_send_notification_no_backend(self, monkeypatch):
        """Test notification when no backend available."""
        import mkv2cast.notifications

        monkeypatch.setattr(mkv2cast.notifications, "NOTIFY_SEND_AVAILABLE", False)
        monkeypatch.setattr(mkv2cast.notifications, "PLYER_AVAILABLE", False)

        from mkv2cast.notifications import send_notification

        result = send_notification("Test", "Message")
        assert result is False

    @pytest.mark.skipif(not shutil.which("notify-send"), reason="notify-send not available")
    def test_send_notification_with_notify_send(self):
        """Test notification with notify-send (if available)."""
        from mkv2cast.notifications import send_notification

        # This may or may not succeed depending on D-Bus availability
        result = send_notification("mkv2cast Test", "Test message", timeout=1)
        # Just test it doesn't crash - result depends on system
        assert isinstance(result, bool)


class TestNotificationHelpers:
    """Tests for notification helper functions."""

    def test_notify_success_message(self, monkeypatch):
        """Test success notification message formatting."""
        import mkv2cast.notifications

        # Mock send_notification to capture args
        captured = []

        def mock_send(title, message, **kwargs):
            captured.append((title, message, kwargs))
            return True

        monkeypatch.setattr(mkv2cast.notifications, "send_notification", mock_send)

        from mkv2cast.notifications import notify_success

        notify_success(3, "01:30:00")

        assert len(captured) == 1
        title, message, _ = captured[0]
        assert "Complete" in title or "terminée" in title.lower()
        assert "3" in message

    def test_notify_failure_message(self, monkeypatch):
        """Test failure notification message formatting."""
        import mkv2cast.notifications

        captured = []

        def mock_send(title, message, **kwargs):
            captured.append((title, message, kwargs))
            return True

        monkeypatch.setattr(mkv2cast.notifications, "send_notification", mock_send)

        from mkv2cast.notifications import notify_failure

        notify_failure(2, "ffmpeg error")

        assert len(captured) == 1
        title, message, kwargs = captured[0]
        assert "Failed" in title or "Échec" in title or "failed" in title.lower()
        assert kwargs.get("urgency") == "critical"

    def test_notify_partial_message(self, monkeypatch):
        """Test partial success notification."""
        import mkv2cast.notifications

        captured = []

        def mock_send(title, message, **kwargs):
            captured.append((title, message, kwargs))
            return True

        monkeypatch.setattr(mkv2cast.notifications, "send_notification", mock_send)

        from mkv2cast.notifications import notify_partial

        notify_partial(5, 2, 3, "02:00:00")

        assert len(captured) == 1
        title, message, _ = captured[0]
        assert "5" in message  # converted count
        assert "2" in message  # failed count
        assert "3" in message  # skipped count

    def test_notify_interrupted_message(self, monkeypatch):
        """Test interrupted notification."""
        import mkv2cast.notifications

        captured = []

        def mock_send(title, message, **kwargs):
            captured.append((title, message, kwargs))
            return True

        monkeypatch.setattr(mkv2cast.notifications, "send_notification", mock_send)

        from mkv2cast.notifications import notify_interrupted

        notify_interrupted()

        assert len(captured) == 1
        title, message, _ = captured[0]
        assert "Interrupt" in title or "Interrompu" in title


class TestNotificationUrgency:
    """Tests for notification urgency levels."""

    def test_success_urgency(self, monkeypatch):
        """Test that success uses normal urgency."""
        import mkv2cast.notifications

        captured = []

        def mock_send(title, message, **kwargs):
            captured.append(kwargs)
            return True

        monkeypatch.setattr(mkv2cast.notifications, "send_notification", mock_send)

        from mkv2cast.notifications import notify_success

        notify_success(1, "00:05:00")

        assert captured[0].get("urgency") == "normal"

    def test_failure_urgency(self, monkeypatch):
        """Test that failure uses critical urgency."""
        import mkv2cast.notifications

        captured = []

        def mock_send(title, message, **kwargs):
            captured.append(kwargs)
            return True

        monkeypatch.setattr(mkv2cast.notifications, "send_notification", mock_send)

        from mkv2cast.notifications import notify_failure

        notify_failure(1)

        assert captured[0].get("urgency") == "critical"
