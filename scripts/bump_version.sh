#!/bin/bash
# Usage: ./scripts/bump_version.sh 1.2.0
#        ./scripts/bump_version.sh 1.2.0-1  (patch release)
# Changes the version in the single source of truth: src/mkv2cast/__init__.py

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <new_version>"
    echo "Example: $0 1.2.0"
    echo "         $0 1.2.0-1  (patch release)"
    echo "         $0 1.2.0b1  (beta release)"
    exit 1
fi

NEW_VERSION="$1"
INIT_FILE="src/mkv2cast/__init__.py"

if [ ! -f "$INIT_FILE" ]; then
    echo "Error: $INIT_FILE not found. Run from project root."
    exit 1
fi

# Validate version format
# Accepts: X.Y.Z or X.Y.Z-N or X.Y.ZbetaN or X.Y.Z-alpha.N or X.Y.Z-rc.N
if ! echo "$NEW_VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+(-[0-9]+|(-(beta|alpha|rc)(\.[0-9]+)?)?)?$'; then
    echo "Error: Invalid version format: $NEW_VERSION"
    echo "Valid formats:"
    echo "  - X.Y.Z          (e.g., 1.2.0)"
    echo "  - X.Y.Z-N        (e.g., 1.2.0-1 for patch releases)"
    echo "  - X.Y.Z-beta.N   (e.g., 1.2.0-beta.1)"
    echo "  - X.Y.Z-alpha.N  (e.g., 1.2.0-alpha.1)"
    echo "  - X.Y.Z-rc.N     (e.g., 1.2.0-rc.1)"
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
