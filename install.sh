#!/bin/bash
# mkv2cast installer
# Copyright (C) 2024-2026 voldardard
# License: GPL-3.0
#
# Usage:
#   # Installation utilisateur (recommandée)
#   curl -fsSL https://raw.githubusercontent.com/voldardard/mkv2cast/main/install.sh | bash
#
#   # Installation système (nécessite sudo)
#   curl -fsSL https://raw.githubusercontent.com/voldardard/mkv2cast/main/install.sh | sudo bash -s -- --system
#
#   # Mise à jour
#   curl -fsSL https://raw.githubusercontent.com/voldardard/mkv2cast/main/install.sh | bash -s -- --update
#
#   # Désinstallation
#   curl -fsSL https://raw.githubusercontent.com/voldardard/mkv2cast/main/install.sh | bash -s -- --uninstall

set -e

# ==================== Configuration ====================
VERSION="1.0.0"
REPO_URL="https://github.com/voldardard/mkv2cast"
RAW_URL="https://raw.githubusercontent.com/voldardard/mkv2cast/main"
ARCHIVE_URL="https://github.com/voldardard/mkv2cast/archive/refs/heads/main.tar.gz"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'
BOLD='\033[1m'

# ==================== Helper Functions ====================
print_header() {
    echo -e "${BOLD}${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║              mkv2cast - Installation Script                  ║"
    echo "║    Smart MKV to Chromecast-compatible converter              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
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

print_error() {
    echo -e "  ${RED}✗${NC} $1"
}

print_info() {
    echo -e "  ${CYAN}ℹ${NC} $1"
}

die() {
    print_error "$1"
    cleanup_tmp
    exit 1
}

# ==================== Path Configuration ====================
# User installation paths
USER_BIN_DIR="$HOME/.local/bin"
USER_MAN_DIR="$HOME/.local/share/man/man1"
USER_BASH_COMPLETION_DIR="$HOME/.local/share/bash-completion/completions"
USER_ZSH_COMPLETION_DIR="$HOME/.local/share/zsh/site-functions"
USER_SYSTEMD_DIR="$HOME/.config/systemd/user"
USER_CONFIG_DIR="$HOME/.config/mkv2cast"

# System installation paths
SYSTEM_BIN_DIR="/usr/local/bin"
SYSTEM_MAN_DIR="/usr/local/share/man/man1"
SYSTEM_BASH_COMPLETION_DIR="/etc/bash_completion.d"
SYSTEM_ZSH_COMPLETION_DIR="/usr/local/share/zsh/site-functions"
SYSTEM_SYSTEMD_DIR="/etc/systemd/system"
SYSTEM_CONFIG_DIR="/etc/mkv2cast"

# Temporary directory
TMP_DIR=""

# ==================== Arguments ====================
MODE="user"  # user, system
ACTION="install"  # install, update, uninstall
INSTALL_SYSTEMD=false
MODIFY_RC=true
LOCAL_INSTALL=false  # true if running from cloned repo

# ==================== Parse Arguments ====================
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --user)
                MODE="user"
                shift
                ;;
            --system)
                MODE="system"
                shift
                ;;
            --update)
                ACTION="update"
                shift
                ;;
            --uninstall)
                ACTION="uninstall"
                shift
                ;;
            --with-systemd)
                INSTALL_SYSTEMD=true
                shift
                ;;
            --no-modify-rc)
                MODIFY_RC=false
                shift
                ;;
            --local)
                LOCAL_INSTALL=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                print_warning "Unknown option: $1"
                shift
                ;;
        esac
    done
}

show_help() {
    cat << EOF
mkv2cast installer v${VERSION}

Usage:
  # One-liner installation (recommended)
  curl -fsSL ${RAW_URL}/install.sh | bash

  # With options
  curl -fsSL ${RAW_URL}/install.sh | bash -s -- [OPTIONS]

  # Local installation (from cloned repo)
  ./install.sh [OPTIONS]

Options:
  --user            Install for current user only (default)
                    Location: ~/.local/bin
  
  --system          Install system-wide (requires sudo)
                    Location: /usr/local/bin
  
  --update          Update existing installation
  
  --uninstall       Remove mkv2cast
  
  --with-systemd    Install systemd timer for automatic cleanup
  
  --no-modify-rc    Don't modify .bashrc/.zshrc
  
  -h, --help        Show this help message

Examples:
  # User installation
  curl -fsSL ${RAW_URL}/install.sh | bash

  # System-wide installation
  curl -fsSL ${RAW_URL}/install.sh | sudo bash -s -- --system

  # Update existing installation
  curl -fsSL ${RAW_URL}/install.sh | bash -s -- --update

  # Uninstall
  curl -fsSL ${RAW_URL}/install.sh | bash -s -- --uninstall

More info: ${REPO_URL}
EOF
}

# ==================== Detection Functions ====================
detect_shell() {
    # Detect current user's shell
    if [[ -n "$SHELL" ]]; then
        case "$SHELL" in
            */zsh)  echo "zsh" ;;
            */bash) echo "bash" ;;
            */fish) echo "fish" ;;
            *)      echo "bash" ;;  # Default
        esac
    else
        echo "bash"
    fi
}

get_rc_file() {
    local shell="$1"
    case "$shell" in
        zsh)
            if [[ -f "$HOME/.zshrc" ]]; then
                echo "$HOME/.zshrc"
            else
                echo "$HOME/.zshrc"
            fi
            ;;
        bash)
            if [[ -f "$HOME/.bashrc" ]]; then
                echo "$HOME/.bashrc"
            elif [[ -f "$HOME/.bash_profile" ]]; then
                echo "$HOME/.bash_profile"
            else
                echo "$HOME/.bashrc"
            fi
            ;;
        fish)
            echo "$HOME/.config/fish/config.fish"
            ;;
        *)
            echo "$HOME/.bashrc"
            ;;
    esac
}

is_in_path() {
    local dir="$1"
    [[ ":$PATH:" == *":$dir:"* ]]
}

detect_existing_install() {
    # Check for existing installation
    if [[ -x "$USER_BIN_DIR/mkv2cast" ]]; then
        echo "user"
        return 0
    elif [[ -x "$SYSTEM_BIN_DIR/mkv2cast" ]]; then
        echo "system"
        return 0
    fi
    echo "none"
    return 1
}

get_installed_version() {
    local install_type="$1"
    local bin_path
    
    if [[ "$install_type" == "user" ]]; then
        bin_path="$USER_BIN_DIR/mkv2cast"
    else
        bin_path="$SYSTEM_BIN_DIR/mkv2cast"
    fi
    
    if [[ -x "$bin_path" ]]; then
        "$bin_path" --version 2>/dev/null | head -1 | awk '{print $2}' || echo "unknown"
    else
        echo "none"
    fi
}

# ==================== Requirement Checks ====================
check_requirements() {
    print_step "Checking requirements..."
    
    local missing=0
    
    # Check Python 3
    if command -v python3 &> /dev/null; then
        local py_version
        py_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        print_success "Python 3: $py_version"
    else
        print_error "Python 3: NOT FOUND"
        print_info "Install with: sudo pacman -S python (Arch) or sudo apt install python3 (Debian)"
        missing=1
    fi
    
    # Check ffmpeg
    if command -v ffmpeg &> /dev/null; then
        print_success "ffmpeg: found"
    else
        print_error "ffmpeg: NOT FOUND"
        print_info "Install with: sudo pacman -S ffmpeg (Arch) or sudo apt install ffmpeg (Debian)"
        missing=1
    fi
    
    # Check ffprobe
    if command -v ffprobe &> /dev/null; then
        print_success "ffprobe: found"
    else
        print_error "ffprobe: NOT FOUND"
        missing=1
    fi
    
    # Check curl or wget (for downloading)
    if ! $LOCAL_INSTALL; then
        if command -v curl &> /dev/null; then
            print_success "curl: found"
        elif command -v wget &> /dev/null; then
            print_success "wget: found"
        else
            print_error "curl or wget: NOT FOUND (required for download)"
            missing=1
        fi
    fi
    
    if [[ $missing -eq 1 ]]; then
        echo ""
        die "Missing required dependencies. Please install them and try again."
    fi
    
    echo ""
}

check_sudo_if_needed() {
    if [[ "$MODE" == "system" ]]; then
        if [[ $EUID -ne 0 ]]; then
            die "System-wide installation requires root privileges. Run with sudo."
        fi
        print_info "Running in system mode (root)"
    fi
}

# ==================== Download Functions ====================
create_tmp_dir() {
    TMP_DIR=$(mktemp -d -t mkv2cast-install.XXXXXX)
    print_info "Created temporary directory: $TMP_DIR"
}

cleanup_tmp() {
    if [[ -n "$TMP_DIR" && -d "$TMP_DIR" ]]; then
        rm -rf "$TMP_DIR"
    fi
}

# Set trap to cleanup on exit
trap cleanup_tmp EXIT

download_files() {
    print_step "Downloading mkv2cast..."
    
    create_tmp_dir
    cd "$TMP_DIR"
    
    # Try git clone first
    if command -v git &> /dev/null; then
        print_info "Using git clone..."
        if git clone --depth 1 "$REPO_URL.git" mkv2cast 2>/dev/null; then
            print_success "Downloaded via git"
            cd mkv2cast
            return 0
        fi
    fi
    
    # Fallback to curl/wget with tar
    print_info "Using curl/wget to download archive..."
    
    if command -v curl &> /dev/null; then
        curl -fsSL "$ARCHIVE_URL" -o mkv2cast.tar.gz || die "Failed to download archive"
    elif command -v wget &> /dev/null; then
        wget -q "$ARCHIVE_URL" -O mkv2cast.tar.gz || die "Failed to download archive"
    else
        die "Neither curl nor wget available"
    fi
    
    tar -xzf mkv2cast.tar.gz || die "Failed to extract archive"
    cd mkv2cast-main
    print_success "Downloaded and extracted"
}

get_source_dir() {
    if $LOCAL_INSTALL; then
        # Running from local clone
        local script_dir
        script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        echo "$script_dir"
    else
        # Running from curl, files are in TMP_DIR
        echo "$TMP_DIR/mkv2cast" 2>/dev/null || echo "$TMP_DIR/mkv2cast-main"
    fi
}

# ==================== Installation Functions ====================
set_paths() {
    if [[ "$MODE" == "system" ]]; then
        BIN_DIR="$SYSTEM_BIN_DIR"
        MAN_DIR="$SYSTEM_MAN_DIR"
        BASH_COMPLETION_DIR="$SYSTEM_BASH_COMPLETION_DIR"
        ZSH_COMPLETION_DIR="$SYSTEM_ZSH_COMPLETION_DIR"
        SYSTEMD_DIR="$SYSTEM_SYSTEMD_DIR"
        CONFIG_DIR="$SYSTEM_CONFIG_DIR"
    else
        BIN_DIR="$USER_BIN_DIR"
        MAN_DIR="$USER_MAN_DIR"
        BASH_COMPLETION_DIR="$USER_BASH_COMPLETION_DIR"
        ZSH_COMPLETION_DIR="$USER_ZSH_COMPLETION_DIR"
        SYSTEMD_DIR="$USER_SYSTEMD_DIR"
        CONFIG_DIR="$USER_CONFIG_DIR"
    fi
}

create_directories() {
    print_step "Creating directories..."
    
    mkdir -p "$BIN_DIR"
    print_success "Binary: $BIN_DIR"
    
    mkdir -p "$MAN_DIR"
    print_success "Man pages: $MAN_DIR"
    
    mkdir -p "$BASH_COMPLETION_DIR"
    print_success "Bash completion: $BASH_COMPLETION_DIR"
    
    mkdir -p "$ZSH_COMPLETION_DIR"
    print_success "Zsh completion: $ZSH_COMPLETION_DIR"
    
    if $INSTALL_SYSTEMD; then
        mkdir -p "$SYSTEMD_DIR"
        print_success "Systemd: $SYSTEMD_DIR"
    fi
    
    echo ""
}

install_script() {
    local src_dir="$1"
    print_step "Installing mkv2cast..."
    
    if [[ -f "$src_dir/mkv2cast.py" ]]; then
        cp "$src_dir/mkv2cast.py" "$BIN_DIR/mkv2cast"
        chmod +x "$BIN_DIR/mkv2cast"
        print_success "Installed: $BIN_DIR/mkv2cast"
    else
        die "mkv2cast.py not found in source directory"
    fi
    
    echo ""
}

install_manpage() {
    local src_dir="$1"
    print_step "Installing man page..."
    
    if [[ -f "$src_dir/man/mkv2cast.1" ]]; then
        cp "$src_dir/man/mkv2cast.1" "$MAN_DIR/"
        
        # Compress if gzip available
        if command -v gzip &> /dev/null; then
            gzip -f "$MAN_DIR/mkv2cast.1"
            print_success "Installed: $MAN_DIR/mkv2cast.1.gz"
        else
            print_success "Installed: $MAN_DIR/mkv2cast.1"
        fi
        
        # Update man database if available
        if command -v mandb &> /dev/null; then
            if [[ "$MODE" == "system" ]]; then
                mandb -q 2>/dev/null || true
            else
                mandb -q "$HOME/.local/share/man" 2>/dev/null || true
            fi
        fi
    else
        print_warning "Man page not found, skipping"
    fi
    
    echo ""
}

install_completions() {
    local src_dir="$1"
    print_step "Installing shell completions..."
    
    # Bash completion
    if [[ -f "$src_dir/completions/mkv2cast.bash" ]]; then
        cp "$src_dir/completions/mkv2cast.bash" "$BASH_COMPLETION_DIR/mkv2cast"
        print_success "Bash: $BASH_COMPLETION_DIR/mkv2cast"
    else
        print_warning "Bash completion not found"
    fi
    
    # Zsh completion
    if [[ -f "$src_dir/completions/_mkv2cast" ]]; then
        cp "$src_dir/completions/_mkv2cast" "$ZSH_COMPLETION_DIR/"
        print_success "Zsh: $ZSH_COMPLETION_DIR/_mkv2cast"
    else
        print_warning "Zsh completion not found"
    fi
    
    echo ""
}

install_systemd() {
    local src_dir="$1"
    
    if ! $INSTALL_SYSTEMD; then
        return
    fi
    
    print_step "Installing systemd timer..."
    
    if [[ -f "$src_dir/systemd/mkv2cast-cleanup.service" ]]; then
        cp "$src_dir/systemd/mkv2cast-cleanup.service" "$SYSTEMD_DIR/"
        print_success "Service: $SYSTEMD_DIR/mkv2cast-cleanup.service"
    fi
    
    if [[ -f "$src_dir/systemd/mkv2cast-cleanup.timer" ]]; then
        cp "$src_dir/systemd/mkv2cast-cleanup.timer" "$SYSTEMD_DIR/"
        print_success "Timer: $SYSTEMD_DIR/mkv2cast-cleanup.timer"
    fi
    
    # Enable timer
    if command -v systemctl &> /dev/null; then
        if [[ "$MODE" == "system" ]]; then
            systemctl daemon-reload 2>/dev/null || true
            systemctl enable mkv2cast-cleanup.timer 2>/dev/null || true
        else
            systemctl --user daemon-reload 2>/dev/null || true
            systemctl --user enable mkv2cast-cleanup.timer 2>/dev/null || true
        fi
        print_success "Timer enabled"
    fi
    
    echo ""
}

install_uninstaller() {
    local src_dir="$1"
    print_step "Installing uninstaller..."
    
    if [[ -f "$src_dir/uninstall.sh" ]]; then
        cp "$src_dir/uninstall.sh" "$BIN_DIR/mkv2cast-uninstall"
        chmod +x "$BIN_DIR/mkv2cast-uninstall"
        print_success "Installed: $BIN_DIR/mkv2cast-uninstall"
    fi
    
    echo ""
}

# ==================== Shell Configuration ====================
configure_path() {
    if [[ "$MODE" == "system" ]]; then
        # System paths are usually already in PATH
        return
    fi
    
    if is_in_path "$BIN_DIR"; then
        print_info "$BIN_DIR is already in PATH"
        return
    fi
    
    if ! $MODIFY_RC; then
        print_warning "$BIN_DIR is not in PATH"
        print_info "Add manually: export PATH=\"$BIN_DIR:\$PATH\""
        return
    fi
    
    print_step "Configuring PATH..."
    
    local shell
    shell=$(detect_shell)
    local rc_file
    rc_file=$(get_rc_file "$shell")
    
    local path_line="export PATH=\"$BIN_DIR:\$PATH\""
    local marker="# mkv2cast PATH"
    
    # Check if already configured
    if grep -q "mkv2cast" "$rc_file" 2>/dev/null; then
        print_info "PATH already configured in $rc_file"
        return
    fi
    
    # Add to rc file
    echo "" >> "$rc_file"
    echo "$marker" >> "$rc_file"
    echo "$path_line" >> "$rc_file"
    
    print_success "Added to $rc_file:"
    print_info "$path_line"
    
    echo ""
}

configure_completions() {
    if [[ "$MODE" == "system" ]]; then
        # System completions are loaded automatically
        return
    fi
    
    if ! $MODIFY_RC; then
        return
    fi
    
    local shell
    shell=$(detect_shell)
    local rc_file
    rc_file=$(get_rc_file "$shell")
    
    case "$shell" in
        zsh)
            # Check if fpath is already configured
            if ! grep -q "mkv2cast.*fpath" "$rc_file" 2>/dev/null; then
                local fpath_line="fpath=($ZSH_COMPLETION_DIR \$fpath)"
                local marker="# mkv2cast completions"
                
                # Add before compinit if possible, or at the end
                if ! grep -q "$marker" "$rc_file" 2>/dev/null; then
                    echo "" >> "$rc_file"
                    echo "$marker" >> "$rc_file"
                    echo "$fpath_line" >> "$rc_file"
                    print_success "Added Zsh completion path to $rc_file"
                fi
            fi
            ;;
        bash)
            # Bash completions in ~/.local/share/bash-completion/completions/ 
            # are usually auto-loaded by bash-completion package
            local completion_source="[[ -f $BASH_COMPLETION_DIR/mkv2cast ]] && source $BASH_COMPLETION_DIR/mkv2cast"
            local marker="# mkv2cast completions"
            
            if ! grep -q "mkv2cast" "$rc_file" 2>/dev/null || ! grep -q "completion" "$rc_file" 2>/dev/null; then
                # Check if bash-completion is already handling it
                if [[ -d "/usr/share/bash-completion" ]] || [[ -d "$HOME/.local/share/bash-completion" ]]; then
                    print_info "Bash completion should be auto-loaded"
                else
                    echo "" >> "$rc_file"
                    echo "$marker" >> "$rc_file"
                    echo "$completion_source" >> "$rc_file"
                    print_success "Added Bash completion to $rc_file"
                fi
            fi
            ;;
    esac
}

configure_manpath() {
    if [[ "$MODE" == "system" ]]; then
        return
    fi
    
    if ! $MODIFY_RC; then
        return
    fi
    
    local shell
    shell=$(detect_shell)
    local rc_file
    rc_file=$(get_rc_file "$shell")
    
    local man_dir="$HOME/.local/share/man"
    local manpath_line="export MANPATH=\"$man_dir:\$MANPATH\""
    
    # Check if already configured
    if grep -q "MANPATH.*\.local/share/man" "$rc_file" 2>/dev/null; then
        return
    fi
    
    echo "$manpath_line" >> "$rc_file"
    print_info "Added MANPATH to $rc_file"
}

# ==================== Uninstall Functions ====================
do_uninstall() {
    print_step "Uninstalling mkv2cast..."
    
    local existing
    existing=$(detect_existing_install)
    
    if [[ "$existing" == "none" ]]; then
        print_warning "mkv2cast is not installed"
        exit 0
    fi
    
    # Determine paths based on installation type
    if [[ "$existing" == "system" ]]; then
        if [[ $EUID -ne 0 ]]; then
            die "System installation requires root to uninstall. Run with sudo."
        fi
        set_paths  # This will use system paths since we're root
        MODE="system"
    else
        MODE="user"
    fi
    set_paths
    
    echo ""
    print_info "Found $existing installation"
    echo ""
    
    # Remove files
    local files_to_remove=(
        "$BIN_DIR/mkv2cast"
        "$BIN_DIR/mkv2cast-uninstall"
        "$MAN_DIR/mkv2cast.1"
        "$MAN_DIR/mkv2cast.1.gz"
        "$BASH_COMPLETION_DIR/mkv2cast"
        "$ZSH_COMPLETION_DIR/_mkv2cast"
        "$SYSTEMD_DIR/mkv2cast-cleanup.service"
        "$SYSTEMD_DIR/mkv2cast-cleanup.timer"
    )
    
    for file in "${files_to_remove[@]}"; do
        if [[ -f "$file" ]]; then
            rm -f "$file"
            print_success "Removed: $file"
        fi
    done
    
    # Disable systemd timer if exists
    if command -v systemctl &> /dev/null; then
        if [[ "$MODE" == "system" ]]; then
            systemctl stop mkv2cast-cleanup.timer 2>/dev/null || true
            systemctl disable mkv2cast-cleanup.timer 2>/dev/null || true
            systemctl daemon-reload 2>/dev/null || true
        else
            systemctl --user stop mkv2cast-cleanup.timer 2>/dev/null || true
            systemctl --user disable mkv2cast-cleanup.timer 2>/dev/null || true
            systemctl --user daemon-reload 2>/dev/null || true
        fi
    fi
    
    echo ""
    print_info "User data preserved in:"
    print_info "  Config: $USER_CONFIG_DIR"
    print_info "  State:  \$XDG_STATE_HOME/mkv2cast"
    print_info "  Cache:  \$XDG_CACHE_HOME/mkv2cast"
    echo ""
    echo -e "${GREEN}${BOLD}mkv2cast has been uninstalled.${NC}"
    echo ""
}

# ==================== Update Functions ====================
do_update() {
    print_step "Checking for updates..."
    
    local existing
    existing=$(detect_existing_install)
    
    if [[ "$existing" == "none" ]]; then
        print_info "No existing installation found. Performing fresh install..."
        ACTION="install"
        do_install
        return
    fi
    
    local current_version
    current_version=$(get_installed_version "$existing")
    print_info "Current version: $current_version"
    print_info "Installation type: $existing"
    
    # Set mode based on existing installation
    MODE="$existing"
    
    if [[ "$MODE" == "system" && $EUID -ne 0 ]]; then
        die "System installation requires root to update. Run with sudo."
    fi
    
    echo ""
    
    # Proceed with installation (will overwrite existing files)
    do_install
}

# ==================== Main Install Function ====================
do_install() {
    local src_dir
    
    # Download files if not local
    if ! $LOCAL_INSTALL; then
        download_files
        src_dir=$(get_source_dir)
        # After download, cd back and use the downloaded directory
        if [[ -d "$TMP_DIR/mkv2cast" ]]; then
            src_dir="$TMP_DIR/mkv2cast"
        elif [[ -d "$TMP_DIR/mkv2cast-main" ]]; then
            src_dir="$TMP_DIR/mkv2cast-main"
        fi
    else
        src_dir=$(get_source_dir)
    fi
    
    print_info "Source: $src_dir"
    echo ""
    
    # Verify source directory
    if [[ ! -f "$src_dir/mkv2cast.py" ]]; then
        die "Invalid source directory: mkv2cast.py not found"
    fi
    
    set_paths
    create_directories
    install_script "$src_dir"
    install_manpage "$src_dir"
    install_completions "$src_dir"
    install_systemd "$src_dir"
    install_uninstaller "$src_dir"
    
    # Configure shell
    if [[ "$MODE" == "user" ]]; then
        configure_path
        configure_completions
        configure_manpath
    fi
    
    # Print success message
    print_success_message
}

print_success_message() {
    local shell
    shell=$(detect_shell)
    local rc_file
    rc_file=$(get_rc_file "$shell")
    
    echo ""
    echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║              Installation Complete!                          ║${NC}"
    echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    if [[ "$MODE" == "user" ]]; then
        echo -e "${BOLD}To start using mkv2cast:${NC}"
        echo ""
        
        if ! is_in_path "$BIN_DIR"; then
            echo -e "  ${YELLOW}1.${NC} Reload your shell configuration:"
            echo -e "     ${CYAN}source $rc_file${NC}"
            echo ""
            echo -e "  ${YELLOW}2.${NC} Or open a new terminal"
            echo ""
        fi
        
        echo -e "${BOLD}Verify installation:${NC}"
        echo -e "  ${CYAN}mkv2cast --version${NC}"
        echo -e "  ${CYAN}mkv2cast --check-requirements${NC}"
        echo -e "  ${CYAN}man mkv2cast${NC}"
        echo ""
        
        echo -e "${BOLD}Quick start:${NC}"
        echo -e "  ${CYAN}cd /path/to/videos${NC}"
        echo -e "  ${CYAN}mkv2cast${NC}"
        echo ""
        
        echo -e "${BOLD}Update later with:${NC}"
        echo -e "  ${CYAN}curl -fsSL ${RAW_URL}/install.sh | bash -s -- --update${NC}"
        echo ""
        
        echo -e "${BOLD}Uninstall with:${NC}"
        echo -e "  ${CYAN}mkv2cast-uninstall${NC}"
        echo -e "  ${CYAN}# or: curl -fsSL ${RAW_URL}/install.sh | bash -s -- --uninstall${NC}"
        echo ""
        
        echo -e "${BOLD}Optional: Install recommended Python packages:${NC}"
        echo -e "  ${CYAN}# Arch Linux:${NC}"
        echo -e "  ${CYAN}sudo pacman -S python-rich python-tomli${NC}"
        echo -e "  ${CYAN}# Debian/Ubuntu:${NC}"
        echo -e "  ${CYAN}pip install --user rich tomli${NC}"
    else
        echo -e "${BOLD}System-wide installation complete.${NC}"
        echo ""
        echo -e "  ${CYAN}mkv2cast --version${NC}"
        echo -e "  ${CYAN}mkv2cast --check-requirements${NC}"
        echo ""
        
        echo -e "${BOLD}Update with:${NC}"
        echo -e "  ${CYAN}curl -fsSL ${RAW_URL}/install.sh | sudo bash -s -- --system --update${NC}"
    fi
    
    echo ""
    echo -e "${MAGENTA}Documentation: ${REPO_URL}${NC}"
    echo ""
}

# ==================== Main ====================
main() {
    print_header
    parse_args "$@"
    
    # Detect if running from local clone
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
    if [[ -f "$script_dir/mkv2cast.py" ]]; then
        LOCAL_INSTALL=true
    fi
    
    # Execute action
    case "$ACTION" in
        install)
            check_sudo_if_needed
            check_requirements
            do_install
            ;;
        update)
            check_sudo_if_needed
            check_requirements
            do_update
            ;;
        uninstall)
            do_uninstall
            ;;
        *)
            die "Unknown action: $ACTION"
            ;;
    esac
}

main "$@"
