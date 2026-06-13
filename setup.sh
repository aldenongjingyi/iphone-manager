#!/usr/bin/env bash
# iPhone Manager — macOS setup script
# Run: bash setup.sh

set -e

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}▸${NC} $*"; }
warn()  { echo -e "${YELLOW}⚠${NC}  $*"; }
error() { echo -e "${RED}✗${NC}  $*"; }
step()  { echo -e "\n${BOLD}$*${NC}"; }

step "iPhone Manager — macOS Setup"
echo "This script installs all required dependencies."
echo

# ── 1. Check macOS ──────────────────────────────────────────────────
if [[ "$OSTYPE" != "darwin"* ]]; then
  error "This script is for macOS only. Use setup.bat on Windows."
  exit 1
fi

# ── 2. Check / install Homebrew ─────────────────────────────────────
step "1. Homebrew"
if command -v brew &>/dev/null; then
  info "Homebrew already installed ($(brew --version | head -1))"
else
  warn "Homebrew not found — installing…"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# ── 3. libimobiledevice ─────────────────────────────────────────────
step "2. libimobiledevice"
if command -v ideviceinfo &>/dev/null; then
  info "libimobiledevice already installed"
else
  info "Installing libimobiledevice…"
  brew install libimobiledevice
fi

# ── 4. Python 3 ─────────────────────────────────────────────────────
step "3. Python 3"
if command -v python3 &>/dev/null; then
  PY_VER=$(python3 --version)
  info "Python found: $PY_VER"
else
  info "Installing Python via Homebrew…"
  brew install python
fi

PYTHON=python3

# ── 5. Virtual environment ──────────────────────────────────────────
step "4. Python virtual environment"
VENV_DIR="$(dirname "$0")/.venv"

if [ -d "$VENV_DIR" ]; then
  info "Virtual environment already exists at .venv"
else
  info "Creating virtual environment…"
  $PYTHON -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

# ── 6. Python packages ──────────────────────────────────────────────
step "5. Python packages"
info "Installing / upgrading pip…"
pip install --upgrade pip --quiet

info "Installing requirements…"
pip install -r "$(dirname "$0")/requirements.txt"

# ── 7. Pairing daemon check ─────────────────────────────────────────
step "6. Checking usbmuxd"
if ! pgrep -x usbmuxd &>/dev/null; then
  warn "usbmuxd is not running. It starts automatically when you plug in a device."
  warn "If device detection fails, try: sudo brew services start usbmuxd"
fi

# ── Done ─────────────────────────────────────────────────────────────
echo
echo -e "${GREEN}${BOLD}Setup complete!${NC}"
echo
echo "To start iPhone Manager:"
echo "  source .venv/bin/activate"
echo "  python app.py"
echo
echo "Or use the convenience command:"
echo "  bash run.sh"
echo

# Create run.sh
cat > "$(dirname "$0")/run.sh" <<'RUNEOF'
#!/usr/bin/env bash
cd "$(dirname "$0")"
source .venv/bin/activate
python app.py
RUNEOF
chmod +x "$(dirname "$0")/run.sh"
info "Created run.sh"
