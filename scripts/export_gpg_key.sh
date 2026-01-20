#!/bin/bash
# Export GPG public key for APT repository
#
# This script exports the GPG public key in a format suitable for
# distribution with the APT repository.
#
# Usage:
#   ./scripts/export_gpg_key.sh [key-id]
#
# If key-id is not provided, it will use the first available signing key.

set -euo pipefail

if [ $# -eq 0 ]; then
    # Get the first available signing key
    KEY_ID=$(gpg --list-secret-keys --keyid-format LONG | grep -E "^(sec|SEC)" | head -1 | awk '{print $2}' | cut -d'/' -f2)
    
    if [ -z "$KEY_ID" ]; then
        echo "Error: No GPG keys found. Please generate a key first:"
        echo "  ./scripts/generate_gpg_key.sh"
        exit 1
    fi
else
    KEY_ID="$1"
fi

echo "Exporting GPG public key: $KEY_ID"
echo ""

# Export public key
OUTPUT_FILE="public-key.gpg"
gpg --armor --export "$KEY_ID" > "$OUTPUT_FILE"

echo "✓ Public key exported to: $OUTPUT_FILE"
echo ""

# Show key information
echo "Key information:"
gpg --fingerprint "$KEY_ID" | grep -E "^(pub|      Key fingerprint)" | head -2
echo ""

echo "This key can be distributed with your APT repository."
echo "Users can import it with:"
echo "  curl -fsSL https://voldardard.github.io/mkv2cast/apt/public-key.gpg | sudo gpg --dearmor -o /etc/apt/keyrings/mkv2cast.gpg"
