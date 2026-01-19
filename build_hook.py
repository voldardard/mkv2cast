"""Build hook for compiling .po files to .mo files during package build."""

import subprocess
from pathlib import Path


def compile_translations():
    """Compile all .po files to .mo files."""
    locales_dir = Path(__file__).parent / "src" / "mkv2cast" / "locales"

    if not locales_dir.exists():
        print(f"Locales directory not found: {locales_dir}")
        return

    for lang_dir in locales_dir.iterdir():
        if not lang_dir.is_dir():
            continue

        po_file = lang_dir / "LC_MESSAGES" / "mkv2cast.po"
        mo_file = lang_dir / "LC_MESSAGES" / "mkv2cast.mo"

        if po_file.exists():
            try:
                subprocess.run(
                    ["msgfmt", "-o", str(mo_file), str(po_file)],
                    check=True,
                    capture_output=True
                )
                print(f"Compiled {po_file.name} -> {mo_file.name} for {lang_dir.name}")
            except FileNotFoundError:
                print(f"Warning: msgfmt not found, skipping {po_file}")
            except subprocess.CalledProcessError as e:
                print(f"Error compiling {po_file}: {e}")


if __name__ == "__main__":
    compile_translations()
