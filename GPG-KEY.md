# GPG Public Key for APT Repository

This directory contains the GPG public key used to sign the mkv2cast APT repository.

## Key Information

- **Key ID**: `F9AEAE62C4BB2563`
- **Fingerprint**: `3672B070E65C0A26BB759759F9AEAE62C4BB2563`
- **Key Type**: RSA 4096 bits
- **Expiration**: 2028-01-20
- **Purpose**: APT repository signing
- **Email**: brugger.mathias@hotmail.com

## Files

- `public-key.gpg` - Public key in ASCII armor format (for distribution)
- `gpg-public-key-F9AEAE62C4BB2563.asc` - Public key with key ID in filename

Both files contain the same key. The `public-key.gpg` file is the one used by the APT repository.

## Verification

To verify the key fingerprint:

```bash
gpg --show-keys public-key.gpg | grep -A1 "pub"
```

Or:

```bash
gpg --fingerprint F9AEAE62C4BB2563
```

## Usage

Users can import this key to verify APT repository signatures:

```bash
curl -fsSL https://voldardard.github.io/mkv2cast/apt/public-key.gpg | sudo gpg --dearmor -o /etc/apt/keyrings/mkv2cast.gpg
```

## Security Note

⚠️ **Never commit private keys to this repository!**

Only the public key should be stored here. The private key must be:
- Stored securely (e.g., in GitHub Secrets)
- Never committed to version control
- Protected with a strong passphrase
