#!/bin/bash
# Generate GPG key pair for APT repository signing
#
# This script generates a GPG key pair suitable for signing APT repositories.
# The key will be exported in a format ready for GitHub Secrets.
#
# Usage:
#   ./scripts/generate_gpg_key.sh [key-name] [email]
#
# Example:
#   ./scripts/generate_gpg_key.sh "mkv2cast APT Signing Key" "voldardard@example.com"

set -euo pipefail

KEY_NAME="${1:-mkv2cast APT Signing Key}"
EMAIL="${2:-voldardard@example.com}"
KEY_TYPE="RSA"
KEY_LENGTH="4096"
EXPIRE_DATE="2y"  # Key expires in 2 years

echo "══════════════════════════════════════════════════════"
echo "  GPG Key Generation for APT Repository Signing"
echo "══════════════════════════════════════════════════════"
echo ""
echo "Key Name: $KEY_NAME"
echo "Email: $EMAIL"
echo "Key Type: $KEY_TYPE"
echo "Key Length: $KEY_LENGTH bits"
echo "Expiration: $EXPIRE_DATE"
echo ""

# Check if GPG is installed
if ! command -v gpg &> /dev/null; then
    echo "Error: gpg is not installed. Please install it first:"
    echo "  sudo apt install gnupg"
    exit 1
fi

# Create temporary directory for key generation
TMP_DIR=$(mktemp -d)
trap "rm -rf $TMP_DIR" EXIT

# Create GPG batch file
BATCH_FILE="$TMP_DIR/gpg-batch.txt"
cat > "$BATCH_FILE" <<EOF
%no-protection
Key-Type: $KEY_TYPE
Key-Length: $KEY_LENGTH
Name-Real: $KEY_NAME
Name-Email: $EMAIL
Expire-Date: $EXPIRE_DATE
%commit
EOF

echo "→ Generating GPG key pair..."
gpg --batch --gen-key "$BATCH_FILE"

# Get the key ID
KEY_ID=$(gpg --list-secret-keys --keyid-format LONG | grep -E "^(sec|SEC)" | head -1 | awk '{print $2}' | cut -d'/' -f2)

if [ -z "$KEY_ID" ]; then
    echo "Error: Failed to generate or retrieve key ID"
    exit 1
fi

echo ""
echo "✓ Key generated successfully!"
echo "  Key ID: $KEY_ID"
echo ""

# Export private key (for GitHub Secrets)
echo "→ Exporting private key..."
PRIVATE_KEY_FILE="gpg-private-key-$KEY_ID.asc"
gpg --armor --export-secret-keys "$KEY_ID" > "$PRIVATE_KEY_FILE"
echo "  Private key saved to: $PRIVATE_KEY_FILE"
echo "  ⚠️  Keep this file secure! Add it to GitHub Secrets as GPG_PRIVATE_KEY"
echo ""

# Export public key
echo "→ Exporting public key..."
PUBLIC_KEY_FILE="gpg-public-key-$KEY_ID.asc"
gpg --armor --export "$KEY_ID" > "$PUBLIC_KEY_FILE"
echo "  Public key saved to: $PUBLIC_KEY_FILE"
echo ""

# Show key fingerprint
echo "→ Key fingerprint:"
gpg --fingerprint "$KEY_ID" | grep -E "^(pub|      Key fingerprint)" | head -2
echo ""

# Prompt for passphrase
echo "══════════════════════════════════════════════════════"
echo "  Next Steps:"
echo "══════════════════════════════════════════════════════"
echo ""
echo "1. Add the private key to GitHub Secrets:"
echo "   - Secret name: GPG_PRIVATE_KEY"
echo "   - Value: Contents of $PRIVATE_KEY_FILE"
echo ""
echo "2. Add a passphrase to GitHub Secrets (if you set one):"
echo "   - Secret name: GPG_PASSPHRASE"
echo "   - Value: Your GPG key passphrase"
echo ""
echo "3. Upload the public key to your repository:"
echo "   - Copy $PUBLIC_KEY_FILE to the apt-repo branch as public-key.gpg"
echo "   - Or publish it in GitHub Releases"
echo ""
echo "4. Verify the key fingerprint matches what you expect"
echo ""
echo "══════════════════════════════════════════════════════"
