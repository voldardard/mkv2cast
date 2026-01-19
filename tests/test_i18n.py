"""
Tests for the internationalization module.
"""



class TestI18nSetup:
    """Tests for i18n setup and configuration."""

    def test_setup_i18n_returns_function(self):
        """Test that setup_i18n returns a callable."""
        from mkv2cast.i18n import setup_i18n

        translate = setup_i18n("en")
        assert callable(translate)

    def test_setup_i18n_default_language(self, monkeypatch):
        """Test default language detection."""
        from mkv2cast.i18n import setup_i18n

        # Clear language environment
        for var in ["MKV2CAST_LANG", "LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"]:
            monkeypatch.delenv(var, raising=False)

        # Should fall back to 'en'
        translate = setup_i18n()
        assert callable(translate)

    def test_setup_i18n_env_override(self, monkeypatch):
        """Test MKV2CAST_LANG environment variable."""
        from mkv2cast.i18n import detect_system_language

        monkeypatch.setenv("MKV2CAST_LANG", "fr")

        lang = detect_system_language()
        assert lang == "fr"

    def test_setup_i18n_lang_fallback(self, monkeypatch):
        """Test LANG environment fallback."""
        from mkv2cast.i18n import detect_system_language

        monkeypatch.delenv("MKV2CAST_LANG", raising=False)
        monkeypatch.delenv("LANGUAGE", raising=False)
        monkeypatch.delenv("LC_ALL", raising=False)
        monkeypatch.delenv("LC_MESSAGES", raising=False)
        monkeypatch.setenv("LANG", "de_DE.UTF-8")

        lang = detect_system_language()
        assert lang == "de"


class TestTranslationFunction:
    """Tests for the _ translation function."""

    def test_translation_function_identity(self):
        """Test that _ returns string if no translation."""
        from mkv2cast.i18n import _, setup_i18n

        # Setup English (messages are in English)
        setup_i18n("en")

        result = _("Summary")
        assert result == "Summary"  # Should return same string

    def test_translation_function_without_setup(self):
        """Test that _ works even without explicit setup."""
        from mkv2cast.i18n import _

        # Should not raise
        result = _("Test message")
        assert isinstance(result, str)

    def test_translation_preserves_unknown(self):
        """Test that unknown strings are returned unchanged."""
        from mkv2cast.i18n import _, setup_i18n

        setup_i18n("fr")

        # A string that's not in the translation catalog
        unknown = "This string is not translated xyz123"
        result = _(unknown)
        assert result == unknown


class TestSupportedLanguages:
    """Tests for supported languages."""

    def test_supported_languages_list(self):
        """Test that supported languages are defined."""
        from mkv2cast.i18n import SUPPORTED_LANGUAGES

        assert "en" in SUPPORTED_LANGUAGES
        assert "fr" in SUPPORTED_LANGUAGES
        assert "es" in SUPPORTED_LANGUAGES
        assert "it" in SUPPORTED_LANGUAGES
        assert "de" in SUPPORTED_LANGUAGES

    def test_unsupported_language_fallback(self):
        """Test that unsupported language falls back to English."""
        from mkv2cast.i18n import _, setup_i18n

        # Use an unsupported language
        setup_i18n("xx")

        # Should still work
        result = _("Summary")
        assert isinstance(result, str)


class TestLocaleFiles:
    """Tests for locale file existence."""

    def test_locales_dir_exists(self):
        """Test that locales directory exists."""
        from mkv2cast.i18n import get_locales_dir

        locales_dir = get_locales_dir()
        assert locales_dir.exists()

    def test_language_dirs_exist(self):
        """Test that language directories exist."""
        from mkv2cast.i18n import SUPPORTED_LANGUAGES, get_locales_dir

        locales_dir = get_locales_dir()

        for lang in SUPPORTED_LANGUAGES:
            lang_dir = locales_dir / lang
            assert lang_dir.exists(), f"Missing language directory: {lang}"

    def test_po_files_exist(self):
        """Test that .po files exist for each language."""
        from mkv2cast.i18n import SUPPORTED_LANGUAGES, get_locales_dir

        locales_dir = get_locales_dir()

        for lang in SUPPORTED_LANGUAGES:
            po_file = locales_dir / lang / "LC_MESSAGES" / "mkv2cast.po"
            assert po_file.exists(), f"Missing PO file: {po_file}"


class TestNgettext:
    """Tests for plural form handling."""

    def test_ngettext_singular(self):
        """Test singular form."""
        from mkv2cast.i18n import ngettext, setup_i18n

        setup_i18n("en")

        result = ngettext("1 file", "{n} files", 1)
        assert "1" in result or "file" in result.lower()

    def test_ngettext_plural(self):
        """Test plural form."""
        from mkv2cast.i18n import ngettext, setup_i18n

        setup_i18n("en")

        result = ngettext("1 file", "{n} files", 5)
        assert "files" in result.lower() or "5" in result


class TestLanguageDetection:
    """Tests for system language detection."""

    def test_detect_language_from_mkv2cast_lang(self, monkeypatch):
        """Test MKV2CAST_LANG has highest priority."""
        from mkv2cast.i18n import detect_system_language

        monkeypatch.setenv("MKV2CAST_LANG", "it")
        monkeypatch.setenv("LANG", "en_US.UTF-8")

        lang = detect_system_language()
        assert lang == "it"

    def test_detect_language_normalizes(self, monkeypatch):
        """Test language code normalization."""
        from mkv2cast.i18n import detect_system_language

        monkeypatch.setenv("MKV2CAST_LANG", "fr_FR.UTF-8")

        lang = detect_system_language()
        assert lang == "fr"

    def test_detect_language_unsupported_fallback(self, monkeypatch):
        """Test fallback for unsupported language."""
        import locale

        from mkv2cast.i18n import DEFAULT_LANGUAGE, detect_system_language

        # Clear all language vars except one unsupported
        for var in ["MKV2CAST_LANG", "LANGUAGE", "LC_ALL", "LC_MESSAGES"]:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("LANG", "xx_XX.UTF-8")  # Unsupported

        # Also mock locale.getlocale to return unsupported locale
        monkeypatch.setattr(locale, "getlocale", lambda: ("xx_XX", "UTF-8"))

        lang = detect_system_language()
        assert lang == DEFAULT_LANGUAGE
