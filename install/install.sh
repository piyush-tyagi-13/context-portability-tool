#!/usr/bin/env bash
# ctxkit installer
# Usage: curl -fsSL https://raw.githubusercontent.com/YOUR_USERNAME/context-portability-tool/main/install/install.sh | bash

set -euo pipefail

CTXKIT_VERSION="${CTXKIT_VERSION:-latest}"
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${CYAN}▸${NC} $*"; }
success() { echo -e "${GREEN}✓${NC} $*"; }
warn()    { echo -e "${YELLOW}!${NC} $*"; }
die()     { echo -e "${RED}✗${NC} $*" >&2; exit 1; }

echo ""
echo -e "${CYAN}ctxkit installer${NC}"
echo "────────────────────────────────"

# ── Python 3.11+ check ────────────────────────────────────────────────────────
PYTHON=""
for cmd in python3.13 python3.12 python3.11 python3; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print(sys.version_info[:2])" 2>/dev/null)
        if "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    die "Python 3.11+ required. Install from python.org or via Homebrew: brew install python@3.12"
fi
info "Python: $($PYTHON --version)"

# ── Install uv (fast, modern Python tool manager) ─────────────────────────────
if ! command -v uv &>/dev/null; then
    info "Installing uv (Python tool manager)…"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Add uv to PATH for this session
    export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
    if ! command -v uv &>/dev/null; then
        # uv not on PATH yet — restart shell will fix, but try common locations
        for p in "$HOME/.cargo/bin/uv" "$HOME/.local/bin/uv"; do
            [ -x "$p" ] && export PATH="$(dirname "$p"):$PATH" && break
        done
    fi
fi

if ! command -v uv &>/dev/null; then
    die "uv installed but not on PATH. Open a new terminal and run: uv tool install ctxkit"
fi
success "uv $(uv --version | cut -d' ' -f2)"

# ── Install ctxkit ────────────────────────────────────────────────────────────
info "Installing ctxkit${CTXKIT_VERSION:+ $CTXKIT_VERSION}…"
if [ "$CTXKIT_VERSION" = "latest" ]; then
    uv tool install ctxkit --quiet
else
    uv tool install "ctxkit==$CTXKIT_VERSION" --quiet
fi

# Ensure uv tool bin is on PATH permanently
UV_TOOL_BIN="$(uv tool dir)/bin"
SHELL_RC=""
case "$SHELL" in
    */zsh)  SHELL_RC="$HOME/.zshrc" ;;
    */bash) SHELL_RC="$HOME/.bashrc" ;;
esac

if [ -n "$SHELL_RC" ] && ! grep -q "uv tool" "$SHELL_RC" 2>/dev/null; then
    echo "" >> "$SHELL_RC"
    echo "# ctxkit / uv tools" >> "$SHELL_RC"
    echo 'export PATH="$(uv tool dir)/bin:$PATH"' >> "$SHELL_RC"
fi
export PATH="$UV_TOOL_BIN:$PATH"

# ── Verify ────────────────────────────────────────────────────────────────────
if ! command -v ctxkit &>/dev/null; then
    warn "ctxkit installed but 'ctxkit' not on PATH yet."
    warn "Run: source ~/.zshrc  (or open a new terminal)"
    echo ""
    echo "Then run: ctxkit init"
    exit 0
fi

success "ctxkit $(ctxkit --version 2>/dev/null || echo 'installed')"
echo ""
echo -e "  Run ${CYAN}ctxkit init${NC} to set up your config."
echo ""
