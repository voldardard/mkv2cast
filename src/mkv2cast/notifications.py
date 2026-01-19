"""
Desktop notification support for mkv2cast.

Sends system notifications when conversions complete.
Uses notify-send (libnotify) as primary method with plyer as fallback.
"""

import shutil
import subprocess
from typing import Literal, Optional

from mkv2cast.i18n import _


# Check for notification capabilities
def _has_notify_send() -> bool:
    """Check if notify-send is available."""
    return shutil.which("notify-send") is not None


def _has_plyer() -> bool:
    """Check if plyer is available."""
    try:
        from plyer import notification  # noqa: F401
        return True
    except ImportError:
        return False


NOTIFY_SEND_AVAILABLE = _has_notify_send()
PLYER_AVAILABLE = _has_plyer()


def send_notification(
    title: str,
    message: str,
    urgency: Literal["low", "normal", "critical"] = "normal",
    icon: str = "video-x-generic",
    timeout: int = 10
) -> bool:
    """
    Send a desktop notification.

    Tries notify-send first (Linux standard), then falls back to plyer
    if available.

    Args:
        title: Notification title.
        message: Notification body text.
        urgency: Urgency level - "low", "normal", or "critical".
        icon: Icon name (XDG icon spec) or path.
        timeout: Notification timeout in seconds.

    Returns:
        True if notification was sent successfully, False otherwise.
    """
    # Try notify-send first (Linux standard via libnotify)
    if NOTIFY_SEND_AVAILABLE:
        try:
            cmd = [
                "notify-send",
                "--urgency", urgency,
                "--app-name", "mkv2cast",
                "--icon", icon,
                "--expire-time", str(timeout * 1000),  # Convert to ms
                title,
                message
            ]
            subprocess.run(cmd, check=True, capture_output=True, timeout=5)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass

    # Fallback to plyer
    if PLYER_AVAILABLE:
        try:
            from plyer import notification
            notification.notify(
                title=title,
                message=message,
                app_name="mkv2cast",
                app_icon=icon if icon.startswith("/") else None,
                timeout=timeout
            )
            return True
        except Exception:
            pass

    return False


def notify_success(converted_count: int, total_time: str) -> bool:
    """
    Send a success notification.

    Args:
        converted_count: Number of files successfully converted.
        total_time: Total processing time as formatted string.

    Returns:
        True if notification sent successfully.
    """
    title = _("mkv2cast - Conversion Complete")

    if converted_count == 1:
        message = _("Successfully converted 1 file in {time}").format(time=total_time)
    else:
        message = _("Successfully converted {count} files in {time}").format(
            count=converted_count,
            time=total_time
        )

    return send_notification(
        title=title,
        message=message,
        urgency="normal",
        icon="dialog-information"
    )


def notify_failure(failed_count: int, error_summary: Optional[str] = None) -> bool:
    """
    Send a failure notification.

    Args:
        failed_count: Number of files that failed.
        error_summary: Optional brief error description.

    Returns:
        True if notification sent successfully.
    """
    title = _("mkv2cast - Conversion Failed")

    if failed_count == 1:
        message = _("Failed to convert 1 file")
    else:
        message = _("Failed to convert {count} files").format(count=failed_count)

    if error_summary:
        message += f"\n{error_summary}"

    return send_notification(
        title=title,
        message=message,
        urgency="critical",
        icon="dialog-error"
    )


def notify_partial(ok_count: int, failed_count: int, skipped_count: int, total_time: str) -> bool:
    """
    Send a notification for partial success (some files converted, some failed/skipped).

    Args:
        ok_count: Number of successful conversions.
        failed_count: Number of failed conversions.
        skipped_count: Number of skipped files.
        total_time: Total processing time as formatted string.

    Returns:
        True if notification sent successfully.
    """
    title = _("mkv2cast - Processing Complete")

    parts = []
    if ok_count > 0:
        parts.append(_("{count} converted").format(count=ok_count))
    if failed_count > 0:
        parts.append(_("{count} failed").format(count=failed_count))
    if skipped_count > 0:
        parts.append(_("{count} skipped").format(count=skipped_count))

    message = ", ".join(parts)
    message += f" ({total_time})"

    urgency: Literal["low", "normal", "critical"] = "normal" if failed_count == 0 else "critical"
    icon = "dialog-information" if failed_count == 0 else "dialog-warning"

    return send_notification(
        title=title,
        message=message,
        urgency=urgency,
        icon=icon
    )


def notify_interrupted() -> bool:
    """Send a notification when processing was interrupted by the user."""
    return send_notification(
        title=_("mkv2cast - Interrupted"),
        message=_("Processing was interrupted by user"),
        urgency="normal",
        icon="dialog-warning"
    )


def check_notification_support() -> dict:
    """
    Check available notification methods.

    Returns:
        Dict with 'notify_send' and 'plyer' boolean keys indicating availability.
    """
    return {
        "notify_send": NOTIFY_SEND_AVAILABLE,
        "plyer": PLYER_AVAILABLE,
        "any": NOTIFY_SEND_AVAILABLE or PLYER_AVAILABLE,
    }
