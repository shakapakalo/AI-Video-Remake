#!/usr/bin/env bash
# =============================================================================
#  AI Video Remake API — 1-Click Update from GitHub
#  Run on your Contabo VPS:
#    bash /opt/ai-video-remake/update.sh
#  OR pull and run directly:
#    curl -fsSL https://raw.githubusercontent.com/YOUR_USER/YOUR_REPO/main/update.sh | bash
# =============================================================================
set -euo pipefail

INSTALL_DIR="/opt/ai-video-remake"
SERVICE_NAME="ai-video-remake"
PORT="${PORT:-3100}"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${GREEN}[UPDATE]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}   $*"; }
err()  { echo -e "${RED}[ERROR]${NC}  $*"; exit 1; }

[[ $EUID -ne 0 ]] && err "Run as root: sudo bash update.sh"
[[ ! -d "$INSTALL_DIR" ]] && err "$INSTALL_DIR not found. Run install.sh first."

cd "$INSTALL_DIR"

# ── Pull latest code ──────────────────────────────────────────────────────────
log "Pulling latest code from GitHub..."
git fetch origin
BEFORE=$(git rev-parse HEAD)
git pull --ff-only origin main
AFTER=$(git rev-parse HEAD)

if [[ "$BEFORE" == "$AFTER" ]]; then
    log "Already up to date ($(git log -1 --format='%h %s'))"
else
    log "Updated: $(git log --oneline ${BEFORE}..${AFTER} | wc -l) new commit(s)"
    git log --oneline "${BEFORE}..${AFTER}"
fi

# ── Update yt-dlp ─────────────────────────────────────────────────────────────
log "Updating yt-dlp..."
yt-dlp -U 2>/dev/null || curl -fsSL \
    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp" \
    -o /usr/local/bin/yt-dlp && chmod +x /usr/local/bin/yt-dlp

# ── Update Python dependencies ────────────────────────────────────────────────
log "Installing/updating Python dependencies..."
source venv/bin/activate
pip install --upgrade pip -q
pip install -r python-api/requirements.txt -q

# ── Ensure storage directories exist ─────────────────────────────────────────
mkdir -p "$INSTALL_DIR/python-api/storage/"{images,videos,final,sounds}

# ── Restart service ───────────────────────────────────────────────────────────
log "Restarting service..."
systemctl restart "${SERVICE_NAME}"

# ── Verify ────────────────────────────────────────────────────────────────────
log "Waiting for API to come back online..."
sleep 4
if curl -sf "http://localhost:${PORT}/api/healthz" > /dev/null; then
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  Update complete!${NC}"
    echo -e "${GREEN}  API running at: http://$(hostname -I | awk '{print $1}'):${PORT}/api${NC}"
    echo -e "${GREEN}  Version: $(git log -1 --format='%h — %s')${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
else
    warn "API did not respond after restart. Check logs:"
    echo "  journalctl -u ${SERVICE_NAME} -n 50"
fi
