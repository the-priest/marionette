#!/bin/sh
# MARIONETTE — one-shot installer.
#
# Fresh install (one command, copy-paste):
#   curl -sL https://raw.githubusercontent.com/the-priest/marionette/main/install.sh | sh
#
# Re-running is safe — it updates the existing clone.
#
# Detects your OS / package manager and installs everything needed:
#   - git, python3, python3-pip
#   - pygame (via apt / dnf / pacman / etc, falls back to pip)
# Then creates:
#   - the `mari` command on your PATH
#   - an app-launcher entry with icon (Linux only)

REPO_URL="${MARIONETTE_REPO:-https://github.com/the-priest/marionette.git}"
INSTALL_DIR="${MARIONETTE_DIR:-$HOME/marionette}"
GAME_NAME="Marionette"
WRAPPER_CMD="mari"
EXEC_FILE="marionette.py"
DESKTOP_FILE="marionette.desktop"
APPDIR_NAME="marionette"

# ─── colors ──────────────────────────────────────────────────────────────────
if [ -t 1 ]; then
    CYAN='\033[36m'; YEL='\033[33m'; GRN='\033[32m'; RED='\033[31m'
    BOLD='\033[1m'; OFF='\033[0m'
else
    CYAN=''; YEL=''; GRN=''; RED=''; BOLD=''; OFF=''
fi
say()  { printf "${CYAN}==>${OFF} ${BOLD}%s${OFF}\n" "$*"; }
step() { printf "${YEL}[$1/$2]${OFF} %s\n" "$3"; }
ok()   { printf "    ${GRN}OK${OFF} %s\n" "$*"; }
warn() { printf "    ${YEL}!!${OFF} %s\n" "$*"; }
fail() { printf "    ${RED}XX${OFF} %s\n" "$*"; }

# ─── detect OS + package manager ────────────────────────────────────────────
detect_os() {
    OS="unknown"; PKG_MGR="unknown"; PYGAME_PKG=""; SUDO_PREFIX="sudo"
    if [ -n "$PREFIX" ] && [ -d "$PREFIX/var" ] && [ "$(uname -o 2>/dev/null)" = "Android" ]; then
        OS="termux"; PKG_MGR="pkg"; PYGAME_PKG="python-pygame"; SUDO_PREFIX=""
    elif [ "$(uname -s)" = "Darwin" ]; then
        OS="macos"; PKG_MGR="brew"; PYGAME_PKG=""
    elif [ -f /etc/os-release ]; then
        . /etc/os-release
        OS_ID="${ID:-unknown}"
        OS_LIKE="${ID_LIKE:-}"
        OS="linux-$OS_ID"
        case " $OS_ID $OS_LIKE " in
            *" debian "*|*" ubuntu "*|*" kali "*|*" linuxmint "*|*" pop "*|*" raspbian "*)
                PKG_MGR="apt"; PYGAME_PKG="python3-pygame" ;;
            *" fedora "*|*" rhel "*|*" centos "*|*" rocky "*)
                if command -v dnf >/dev/null 2>&1; then PKG_MGR="dnf"; else PKG_MGR="yum"; fi
                PYGAME_PKG="python3-pygame" ;;
            *" arch "*|*" manjaro "*|*" endeavouros "*)
                PKG_MGR="pacman"; PYGAME_PKG="python-pygame" ;;
            *" suse "*|*" opensuse "*|*" opensuse-tumbleweed "*|*" opensuse-leap "*)
                PKG_MGR="zypper"; PYGAME_PKG="python3-pygame" ;;
            *" alpine "*)
                PKG_MGR="apk"; PYGAME_PKG="py3-pygame" ;;
            *" void "*)
                PKG_MGR="xbps"; PYGAME_PKG="python3-pygame" ;;
            *" gentoo "*)
                PKG_MGR="emerge"; PYGAME_PKG="dev-python/pygame" ;;
        esac
    fi
}

pkg_install() {
    case "$PKG_MGR" in
        apt)      $SUDO_PREFIX apt-get update -qq; $SUDO_PREFIX apt-get install -y "$@" ;;
        dnf)      $SUDO_PREFIX dnf install -y "$@" ;;
        yum)      $SUDO_PREFIX yum install -y "$@" ;;
        pacman)   $SUDO_PREFIX pacman -S --noconfirm --needed "$@" ;;
        zypper)   $SUDO_PREFIX zypper install -y "$@" ;;
        apk)      $SUDO_PREFIX apk add --no-cache "$@" ;;
        xbps)     $SUDO_PREFIX xbps-install -Sy "$@" ;;
        emerge)   $SUDO_PREFIX emerge --quiet "$@" ;;
        pkg)      pkg install -y "$@" ;;
        brew)     brew install "$@" ;;
        *)        return 1 ;;
    esac
}

ensure_tool() {
    cmd="$1"; pkg="${2:-$1}"
    if command -v "$cmd" >/dev/null 2>&1; then
        ok "$cmd already installed"
        return 0
    fi
    if [ "$PKG_MGR" = "unknown" ]; then
        fail "$cmd not found and I don't recognise your package manager."
        printf "       Install $cmd manually then re-run.\n"
        exit 1
    fi
    printf "    installing $cmd via $PKG_MGR ...\n"
    pkg_install "$pkg" || { fail "failed to install $cmd"; exit 1; }
    ok "$cmd installed"
}

ensure_pygame() {
    if python3 -c "import pygame" >/dev/null 2>&1; then
        ok "pygame already present"
        return 0
    fi
    if [ -n "$PYGAME_PKG" ] && [ "$PKG_MGR" != "unknown" ]; then
        printf "    trying $PKG_MGR install $PYGAME_PKG ...\n"
        if pkg_install $PYGAME_PKG >/dev/null 2>&1; then
            if python3 -c "import pygame" >/dev/null 2>&1; then
                ok "pygame installed via $PKG_MGR"
                return 0
            fi
        fi
        warn "OS package didn't satisfy pygame; trying pip"
    fi
    for cmd in \
        "pip install --user pygame" \
        "pip3 install --user pygame" \
        "pip install --break-system-packages pygame" \
        "pip3 install --break-system-packages pygame" \
        "python3 -m pip install --user pygame"
    do
        printf "    trying: $cmd\n"
        if $cmd >/dev/null 2>&1; then
            if python3 -c "import pygame" >/dev/null 2>&1; then
                ok "pygame installed via pip"
                return 0
            fi
        fi
    done
    fail "couldn't install pygame automatically."
    printf "       Install it yourself, then re-run this script.\n"
    exit 1
}

# ─── start ───────────────────────────────────────────────────────────────────
detect_os
say "$GAME_NAME installer"
printf "    OS         : ${BOLD}$OS${OFF}\n"
printf "    pkg mgr    : ${BOLD}$PKG_MGR${OFF}\n"
printf "    repo       : $REPO_URL\n"
printf "    install to : $INSTALL_DIR\n"
echo

# 1. core tools
step 1 6 "checking core tools (git, python3, pip)"
ensure_tool git git
if ! command -v python3 >/dev/null 2>&1; then
    case "$PKG_MGR" in
        apt|dnf|yum|zypper|xbps|apk) ensure_tool python3 python3 ;;
        pacman) ensure_tool python3 python ;;
        pkg)    ensure_tool python3 python ;;
        brew)   ensure_tool python3 python ;;
        emerge) ensure_tool python3 dev-lang/python ;;
        *) fail "python3 missing and unknown package manager"; exit 1 ;;
    esac
else
    ok "python3 already installed ($(python3 --version 2>&1))"
fi
if ! python3 -m pip --version >/dev/null 2>&1; then
    case "$PKG_MGR" in
        apt|dnf|yum|zypper|xbps) ensure_tool pip3 python3-pip ;;
        pacman) ensure_tool pip3 python-pip ;;
        apk)    ensure_tool pip3 py3-pip ;;
        pkg)    ensure_tool pip3 python-pip ;;
        brew)   ok "pip ships with brew python" ;;
        *)      warn "pip missing; relying on OS pygame package" ;;
    esac
else
    ok "pip available"
fi

# 2. pygame
step 2 6 "checking pygame"
ensure_pygame

# 3. clone or pull
step 3 6 "fetching $GAME_NAME repo"
if [ -d "$INSTALL_DIR/.git" ]; then
    cd "$INSTALL_DIR"
    git fetch origin
    git reset --hard origin/main
    ok "updated existing clone"
else
    if [ -d "$INSTALL_DIR" ]; then
        fail "$INSTALL_DIR exists but isn't a git repo. Remove it and re-run."
        exit 1
    fi
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    ok "cloned to $INSTALL_DIR"
fi

# 4. wrapper command
step 4 6 "installing '$WRAPPER_CMD' command"
WRAPPER_BODY='#!/bin/sh
exec python3 "'"$INSTALL_DIR"'/'"$EXEC_FILE"'" "$@"
'
INSTALLED_AT=""
if [ "$SUDO_PREFIX" = "sudo" ] && command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    printf '%s' "$WRAPPER_BODY" | sudo tee /usr/local/bin/$WRAPPER_CMD >/dev/null
    sudo chmod +x /usr/local/bin/$WRAPPER_CMD
    INSTALLED_AT="/usr/local/bin/$WRAPPER_CMD"
else
    mkdir -p "$HOME/.local/bin"
    printf '%s' "$WRAPPER_BODY" > "$HOME/.local/bin/$WRAPPER_CMD"
    chmod +x "$HOME/.local/bin/$WRAPPER_CMD"
    INSTALLED_AT="$HOME/.local/bin/$WRAPPER_CMD"
    if ! echo ":$PATH:" | grep -q ":$HOME/.local/bin:"; then
        for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
            if [ -f "$rc" ] && ! grep -q '\.local/bin' "$rc"; then
                printf '\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$rc"
                warn "added ~/.local/bin to PATH in $(basename $rc) — restart your shell"
            fi
        done
    fi
fi
ok "installed at $INSTALLED_AT"

# 5. desktop entry + icon
step 5 6 "installing app launcher entry"
if [ "$OS" = "macos" ] || [ "$OS" = "termux" ]; then
    warn "skipping desktop entry — not supported on $OS"
else
    APP_DIR="$HOME/.local/share/applications"
    ICON_DIR="$HOME/.local/share/$APPDIR_NAME"
    mkdir -p "$APP_DIR" "$ICON_DIR"
    if [ -f "$INSTALL_DIR/icon.png" ]; then
        cp "$INSTALL_DIR/icon.png" "$ICON_DIR/icon.png"
    fi
    cat > "$APP_DIR/$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=$GAME_NAME
GenericName=Game
Comment=$GAME_NAME — a single-file Python game
Exec=python3 $INSTALL_DIR/$EXEC_FILE
Icon=$ICON_DIR/icon.png
Terminal=false
Categories=Game;ActionGame;ArcadeGame;
StartupWMClass=$GAME_NAME
EOF
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$APP_DIR" 2>/dev/null || true
    fi
    ok "$APP_DIR/$DESKTOP_FILE"
fi

# 6. done
step 6 6 "done"
echo
say "Success."
printf "    play from terminal     : ${BOLD}$WRAPPER_CMD${OFF}\n"
if [ "$OS" != "macos" ] && [ "$OS" != "termux" ]; then
    printf "    or                     : tap the ${BOLD}$GAME_NAME${OFF} icon in your app launcher\n"
fi
printf "    repo lives at          : $INSTALL_DIR\n"
printf "    re-run this script any time to update.\n"
echo
