#!/bin/bash
# Usage: source scripts/parse_version.sh 1.1.1-1
# Sets BASE_VERSION and PATCH_NUMBER environment variables
#
# Examples:
#   1.1.1    → BASE_VERSION=1.1.1, PATCH_NUMBER=0
#   1.1.1-1  → BASE_VERSION=1.1.1, PATCH_NUMBER=1
#   1.1.1-2  → BASE_VERSION=1.1.1, PATCH_NUMBER=2

set -e

VERSION="${1:-}"

if [ -z "$VERSION" ]; then
    echo "Usage: source $0 <version>" >&2
    echo "Example: source $0 1.1.1-1" >&2
    exit 1
fi

# Extract base version (remove trailing -N if present)
BASE_VERSION=$(echo "$VERSION" | sed 's/-[0-9]*$//')

# Extract patch number (everything after the last -)
PATCH_NUMBER=$(echo "$VERSION" | sed -n 's/.*-\([0-9]*\)$/\1/p')
if [ -z "$PATCH_NUMBER" ]; then
    PATCH_NUMBER=0
fi

# Export variables for use in parent shell
export BASE_VERSION
export PATCH_NUMBER

# For non-source usage, print the values
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    echo "BASE_VERSION=$BASE_VERSION"
    echo "PATCH_NUMBER=$PATCH_NUMBER"
fi
