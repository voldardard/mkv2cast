#!/bin/bash
# mkv2cast uninstaller
# Copyright (C) 2024-2026 voldardard
# License: GPL-3.0
#
# This script removes mkv2cast from ~/.local/

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Installation paths
PREFIX="${HOME}/.local"
BIN_DIR="${PREFIX}/bin"
MAN_DIR="${PREFIX}/share/man/man1"
BASH_COMPLETION_DIR="${PREFIX}/share/bash-completion/completions"
ZSH_COMPLETION_DIR="${PREFIX}/share/zsh/site-functions"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"

# XDG directories (data)
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/mkv2cast"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/mkv2cast"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/mkv2cast"

print_header() {
    echo -e "${BOLD}${CYAN}"
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║           mkv2cast - Uninstallation                      ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_step() {
    echo -e "${BLUE}==>${NC} ${BOLD}$1${NC}"
}

print_success() {
    echo -e "  ${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "  ${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "  ${CYAN}ℹ${NC} $1"
}

remove_file() {
    local file="$1"
    if [[ -f "$file" ]]; then
        rm -f "$file"
        print_success "Removed: $file"
    else
        print_info "Not found: $file"
    fi
}

remove_dir() {
    local dir="$1"
    if [[ -d "$dir" ]]; then
        rm -rf "$dir"
        print_success "Removed: $dir"
    else
        print_info "Not found: $dir"
    fi
}

# Uninstall main components
uninstall_main() {
    print_step "Removing mkv2cast..."
    
    # Remove binary
    remove_file "${BIN_DIR}/mkv2cast"
    
    # Remove man page
    remove_file "${MAN_DIR}/mkv2cast.1"
    remove_file "${MAN_DIR}/mkv2cast.1.gz"
    
    # Remove completions
    remove_file "${BASH_COMPLETION_DIR}/mkv2cast"
    remove_file "${ZSH_COMPLETION_DIR}/_mkv2cast"
    
    echo ""
}

# Uninstall systemd timer
uninstall_systemd() {
    print_step "Removing systemd timer..."
    
    # Disable timer first
    if command -v systemctl &> /dev/null; then
        systemctl --user stop mkv2cast-cleanup.timer 2>/dev/null || true
        systemctl --user disable mkv2cast-cleanup.timer 2>/dev/null || true
    fi
    
    remove_file "${SYSTEMD_USER_DIR}/mkv2cast-cleanup.service"
    remove_file "${SYSTEMD_USER_DIR}/mkv2cast-cleanup.timer"
    
    # Reload systemd
    if command -v systemctl &> /dev/null; then
        systemctl --user daemon-reload 2>/dev/null || true
    fi
    
    echo ""
}

# Remove user data (optional)
remove_user_data() {
    print_step "Removing user data..."
    
    echo -e "  ${YELLOW}This will remove:${NC}"
    echo -e "    - Configuration: ${CONFIG_DIR}"
    echo -e "    - History/Logs:  ${STATE_DIR}"
    echo -e "    - Cache/Temp:    ${CACHE_DIR}"
    echo ""
    
    read -p "  Remove all user data? [y/N] " -n 1 -r
    echo ""
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        remove_dir "${CONFIG_DIR}"
        remove_dir "${STATE_DIR}"
        remove_dir "${CACHE_DIR}"
    else
        print_info "User data preserved"
    fi
    
    echo ""
}

# Main uninstallation
main() {
    print_header
    
    # Parse arguments
    REMOVE_DATA=false
    FORCE=false
    
    for arg in "$@"; do
        case $arg in
            --purge)
                REMOVE_DATA=true
                ;;
            --force|-f)
                FORCE=true
                ;;
            --help|-h)
                echo "Usage: $0 [options]"
                echo ""
                echo "Options:"
                echo "  --purge       Also remove configuration, history, and cache"
                echo "  --force, -f   Don't ask for confirmation"
                echo "  --help, -h    Show this help message"
                exit 0
                ;;
        esac
    done
    
    # Confirm uninstallation
    if [[ "$FORCE" != true ]]; then
        read -p "Are you sure you want to uninstall mkv2cast? [y/N] " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Uninstallation cancelled."
            exit 0
        fi
        echo ""
    fi
    
    uninstall_main
    uninstall_systemd
    
    if [[ "$REMOVE_DATA" == true ]]; then
        if [[ "$FORCE" == true ]]; then
            print_step "Removing user data (--purge)..."
            remove_dir "${CONFIG_DIR}"
            remove_dir "${STATE_DIR}"
            remove_dir "${CACHE_DIR}"
            echo ""
        else
            remove_user_data
        fi
    else
        print_info "User data preserved in:"
        print_info "  Config:  ${CONFIG_DIR}"
        print_info "  State:   ${STATE_DIR}"
        print_info "  Cache:   ${CACHE_DIR}"
        print_info "Use --purge to remove all data"
        echo ""
    fi
    
    echo -e "${BOLD}${GREEN}mkv2cast has been uninstalled.${NC}"
    echo ""
    
    # Update man database
    if command -v mandb &> /dev/null; then
        mandb -q "${PREFIX}/share/man" 2>/dev/null || true
    fi
}

main "$@"
