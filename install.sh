#!/usr/bin/env bash
# =============================================================================
#  AI Video Remake API — 1-Click Contabo Install
#  Run as root on a fresh Ubuntu 22.04 / Debian 12 VPS:
#    curl -fsSL https://raw.githubusercontent.com/shakapakalo/AI-Video-Remake/main/install.sh | bash
# =============================================================================
set -euo pipefail

REPO_URL="https://github.com/shakapakalo/AI-Video-Remake.git"
INSTALL_DIR="/opt/ai-video-remake"
SERVICE_NAME="ai-video-remake"
PYTHON_BIN="python3"
PORT="${PORT:-3100}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[INSTALL]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}   $*"; }
err()  { echo -e "${RED}[ERROR]${NC}  $*"; exit 1; }

# ── Root check ────────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && err "Run as root: sudo bash install.sh"

log "Starting AI Video Remake installation..."

# ── System packages ───────────────────────────────────────────────────────────
log "Updating system packages..."
apt-get update -qq
apt-get install -y -qq \
    python3 python3-pip python3-venv \
    ffmpeg \
    git curl wget \
    build-essential libssl-dev \
    chromium-browser || \
apt-get install -y -qq chromium 2>/dev/null || \
warn "Chromium install failed — voiceover Playwright fallback won't work (yt-dlp fallback still available)"

# ── yt-dlp ───────────────────────────────────────────────────────────────────
log "Installing yt-dlp..."
curl -fsSL "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp" \
    -o /usr/local/bin/yt-dlp
chmod +x /usr/local/bin/yt-dlp

# ── Clone repo ────────────────────────────────────────────────────────────────
log "Cloning repository..."
if [[ -d "$INSTALL_DIR" ]]; then
    warn "$INSTALL_DIR already exists — pulling latest instead of cloning"
    git -C "$INSTALL_DIR" pull --ff-only
else
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

# ── Python virtual environment ────────────────────────────────────────────────
log "Setting up Python virtual environment..."
cd "$INSTALL_DIR"
$PYTHON_BIN -m venv venv
source venv/bin/activate

pip install --upgrade pip -q
pip install -r python-api/requirements.txt -q

# ── Playwright browsers (for voiceover extraction) ───────────────────────────
log "Installing Playwright browsers (optional — for voiceover extraction)..."
pip install playwright -q
python3 -m playwright install chromium 2>/dev/null || \
    warn "Playwright browser install failed — yt-dlp subtitle fallback will be used"

# ── Storage directories ───────────────────────────────────────────────────────
log "Creating storage directories..."
mkdir -p "$INSTALL_DIR/python-api/storage/"{images,videos,final,sounds}

# ── systemd service ───────────────────────────────────────────────────────────
log "Installing systemd service..."
cat > /etc/systemd/system/${SERVICE_NAME}.service <<EOF
[Unit]
Description=AI Video Remake API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}/python-api
Environment=PORT=${PORT}
ExecStart=${INSTALL_DIR}/venv/bin/python app.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

# ── Verify ────────────────────────────────────────────────────────────────────
log "Waiting for API to start..."
sleep 4
if curl -sf "http://localhost:${PORT}/api/healthz" > /dev/null; then
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  Installation complete!${NC}"
    echo -e "${GREEN}  API running at: http://$(hostname -I | awk '{print $1}'):${PORT}/api${NC}"
    echo -e "${GREEN}  Health: http://$(hostname -I | awk '{print $1}'):${PORT}/api/healthz${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
else
    warn "API did not respond on port ${PORT}. Check logs:"
    echo "  journalctl -u ${SERVICE_NAME} -n 50"
fi

echo ""
echo "Useful commands:"
echo "  systemctl status ${SERVICE_NAME}     # check running status"
echo "  journalctl -u ${SERVICE_NAME} -f     # live logs"
echo "  systemctl restart ${SERVICE_NAME}    # restart"
echo "  bash ${INSTALL_DIR}/update.sh        # update from GitHub"
