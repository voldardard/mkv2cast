# Package Signing Guide

This document explains how to set up GPG signing for the mkv2cast APT repository.

## Overview

The APT repository uses GPG signing to ensure package integrity and authenticity. The signing process:

1. Signs the `Release` file (which contains checksums of all metadata)
2. Generates `Release.gpg` (detached signature) and `InRelease` (inline signed)
3. Distributes the public key for users to verify signatures

## Prerequisites

- GPG installed on your system
- Access to GitHub repository secrets

## Setup Instructions

### 1. Generate GPG Key Pair

Use the provided script to generate a GPG key pair:

```bash
./scripts/generate_gpg_key.sh "mkv2cast APT Signing Key" "your-email@example.com"
```

This will create:
- `gpg-private-key-<KEY_ID>.asc` - Private key (for GitHub Secrets)
- `gpg-public-key-<KEY_ID>.asc` - Public key (for distribution)

**Important**: Store the private key securely. Never commit it to the repository.

### 2. Configure GitHub Secrets

Add the following secrets to your GitHub repository:

1. Go to **Settings** → **Secrets and variables** → **Actions**
2. Add a new secret:
   - **Name**: `GPG_PRIVATE_KEY`
   - **Value**: Contents of `gpg-private-key-<KEY_ID>.asc`
3. Add another secret (if you set a passphrase):
   - **Name**: `GPG_PASSPHRASE`
   - **Value**: Your GPG key passphrase (leave empty if no passphrase)

### 3. Upload Public Key

The public key needs to be available in the APT repository:

**Option A: Automatic (Recommended)**
- The GitHub Actions workflow will automatically export and publish the public key
- It will be available at: `https://voldardard.github.io/mkv2cast/apt/public-key.gpg`

**Option B: Manual**
- Export the public key: `./scripts/export_gpg_key.sh`
- Copy `public-key.gpg` to the `apt-repo` branch in the repository

### 4. Verify Setup

After the next release, verify that:

1. The `Release.gpg` and `InRelease` files are generated
2. The public key is available at the repository URL
3. Users can install packages using the signed repository

## Testing Locally

You can test the signing process locally:

```bash
# Import your private key
gpg --import gpg-private-key-<KEY_ID>.asc

# Generate Release file (from workflow)
cd dists/stable
# ... generate Release file ...

# Sign Release file
gpg --sign --detach-sign --armor --output Release.gpg Release
gpg --clearsign --output InRelease Release

# Verify signature
gpg --verify Release.gpg Release
```

## Key Management

### Viewing Key Information

```bash
# List keys
gpg --list-secret-keys

# Show key fingerprint
gpg --fingerprint <KEY_ID>
```

### Rotating Keys

If you need to rotate the signing key:

1. Generate a new key pair
2. Update GitHub Secrets with the new private key
3. Upload the new public key to the repository
4. Update documentation with the new key fingerprint
5. Revoke the old key if necessary

### Key Expiration

The default key expiration is set to 2 years. To extend:

```bash
gpg --edit-key <KEY_ID>
# In GPG prompt:
expire
# Enter new expiration date
save
```

Then re-export and update GitHub Secrets.

## Troubleshooting

### Workflow fails with "No GPG key found"

- Verify `GPG_PRIVATE_KEY` secret is set correctly
- Check that the key was imported successfully in the workflow logs
- Ensure the key format is correct (armored ASCII)

### Signature verification fails

- Verify the public key matches the private key
- Check that `Release.gpg` and `InRelease` are generated
- Ensure the public key is accessible at the repository URL

### Users can't verify signatures

- Verify the public key is available at the expected URL
- Check that users are using the correct keyring path
- Ensure the `signed-by` option is correctly configured

## Security Best Practices

1. **Use a strong passphrase** for the GPG key
2. **Store private keys securely** - never commit them to the repository
3. **Rotate keys periodically** - especially if compromised
4. **Verify key fingerprints** before trusting a key
5. **Use HTTPS** for serving the repository
6. **Monitor for key expiration** and renew before expiration

## References

- [Debian SecureApt](https://www.debian.org/doc/manuals/debian-handbook/sect.package-authentication.en.html)
- [APT Repository Signing](https://wiki.debian.org/SecureApt)
- [GitHub Actions Secrets](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
