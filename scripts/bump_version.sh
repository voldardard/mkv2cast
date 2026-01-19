#!/bin/bash
# Usage: ./scripts/bump_version.sh 1.2.0
# Changes the version in the single source of truth: src/mkv2cast/__init__.py

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <new_version>"
    echo "Example: $0 1.2.0"
    echo "         $0 1.2.0b1"
    exit 1
fi

NEW_VERSION="$1"
INIT_FILE="src/mkv2cast/__init__.py"

if [ ! -f "$INIT_FILE" ]; then
    echo "Error: $INIT_FILE not found. Run from project root."
    exit 1
fi

# Get current version
CURRENT_VERSION=$(grep -Po '__version__ = "\K[^"]+' "$INIT_FILE")
echo "Current version: $CURRENT_VERSION"
echo "New version:     $NEW_VERSION"

# Update version
sed -i "s/__version__ = \"$CURRENT_VERSION\"/__version__ = \"$NEW_VERSION\"/" "$INIT_FILE"

# Verify
echo ""
echo "Updated $INIT_FILE:"
grep "__version__" "$INIT_FILE" | head -1

echo ""
echo "✓ Version changed to $NEW_VERSION"
echo ""
echo "Next steps:"
echo "  1. make translations     # Compile .mo files"
echo "  2. python -m build       # Build package"
echo "  3. git add -A && git commit -m 'Release v$NEW_VERSION'"
echo "  4. git tag v$NEW_VERSION"
echo "  5. git push origin <branch> --tags"
