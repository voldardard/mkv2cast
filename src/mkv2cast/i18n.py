"""
Internationalization (i18n) support for mkv2cast.

Uses Python's gettext module for translations.
Supports: English (en), French (fr), Spanish (es), Italian (it), German (de)
"""

import gettext
import locale
import os
from pathlib import Path
from typing import Callable, Optional

# Global translation function
_current_translation: Optional[Callable[[str], str]] = None

# Supported languages
SUPPORTED_LANGUAGES = ["en", "fr", "es", "it", "de"]
DEFAULT_LANGUAGE = "en"


def get_locales_dir() -> Path:
    """Get the locales directory path."""
    return Path(__file__).parent / "locales"


def detect_system_language() -> str:
    """
    Detect the system language from environment.
    Returns language code (e.g., 'fr', 'en', 'es').
    """
    # Check environment variables in order of priority
    for env_var in ["MKV2CAST_LANG", "LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"]:
        lang = os.environ.get(env_var, "")
        if lang:
            # Extract language code (e.g., 'fr_FR.UTF-8' -> 'fr')
            lang_code = lang.split("_")[0].split(".")[0].lower()
            if lang_code in SUPPORTED_LANGUAGES:
                return lang_code

    # Try locale module (use newer API to avoid deprecation warning)
    try:
        # Try getlocale first (Python 3.11+)
        loc = locale.getlocale()[0]
        if loc:
            lang_code = loc.split("_")[0].lower()
            if lang_code in SUPPORTED_LANGUAGES:
                return lang_code
    except Exception:
        pass

    return DEFAULT_LANGUAGE


def setup_i18n(lang: Optional[str] = None) -> Callable[[str], str]:
    """
    Configure internationalization and return the translation function.

    Args:
        lang: Language code (e.g., 'fr', 'en'). If None, auto-detect from system.

    Returns:
        Translation function that takes a string and returns translated string.
    """
    global _current_translation

    if lang is None:
        lang = detect_system_language()

    # Normalize language code
    lang = lang.lower().split("_")[0].split(".")[0]

    if lang not in SUPPORTED_LANGUAGES:
        lang = DEFAULT_LANGUAGE

    locales_dir = get_locales_dir()

    try:
        translation = gettext.translation(
            "mkv2cast",
            localedir=locales_dir,
            languages=[lang, DEFAULT_LANGUAGE],
            fallback=True
        )
        _current_translation = translation.gettext
    except Exception:
        # Fallback to identity function
        def identity_fn(x: str) -> str:
            return x
        _current_translation = identity_fn

    return _current_translation if _current_translation else (lambda x: x)


def _(message: str) -> str:
    """
    Translate a message.

    This is the main translation function. Import and use as:
        from mkv2cast.i18n import _
        print(_("Processing file..."))

    Args:
        message: The message to translate (in English).

    Returns:
        Translated message, or original if no translation found.
    """
    global _current_translation

    if _current_translation is None:
        setup_i18n()

    return _current_translation(message) if _current_translation else message


def get_current_language() -> str:
    """Get the currently configured language code."""
    return detect_system_language()


def ngettext(singular: str, plural: str, n: int) -> str:
    """
    Translate a message with singular/plural forms.

    Args:
        singular: Singular form of the message.
        plural: Plural form of the message.
        n: Count to determine which form to use.

    Returns:
        Appropriate translated form based on count.
    """
    # Simple implementation - for full support, use gettext.ngettext
    if n == 1:
        return _(singular)
    return _(plural)


# Translation strings catalog
# These are the strings that need translation in the application
TRANSLATION_CATALOG = [
    # General
    "Processing file: {filename}",
    "Conversion complete",
    "Conversion failed",
    "Skipped: {reason}",
    "No MKV files to process.",
    "Backend selected: {backend}",

    # Progress
    "Checking integrity...",
    "Encoding...",
    "Waiting for file stability...",
    "Done",
    "Failed",
    "Skipped",

    # Summary
    "Summary",
    "Total files seen",
    "Transcoded OK",
    "Skipped",
    "Failed",
    "Interrupted",
    "Total time",

    # Notifications
    "mkv2cast - Conversion Complete",
    "Successfully converted {count} file(s)",
    "mkv2cast - Conversion Failed",
    "Failed to convert {count} file(s)",

    # Errors
    "File not found: {path}",
    "Integrity check failed",
    "Output already exists",
    "ffmpeg error (rc={rc})",

    # Help texts
    "Smart MKV to Chromecast-compatible converter with hardware acceleration",
    "Process all MKV files in current directory",
    "Process single file",
    "Enable debug output",
    "Dry run - show commands without executing",
]
