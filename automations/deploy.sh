#!/bin/bash
# Deploy CJO automations to Hostinger VPS
# Usage: ./deploy.sh

set -e

VPS="${DEPLOY_HOST:?set DEPLOY_HOST=user@your-vps before deploying}"
REMOTE_DIR="/opt/cjo"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"
PARENT_DIR="$(dirname "$LOCAL_DIR")"

echo "=== CJO Automations Deploy ==="

# 1. Create remote directory structure
echo "[1] Creating remote directories..."
ssh "$VPS" "mkdir -p $REMOTE_DIR/automations $REMOTE_DIR/tools $REMOTE_DIR/prompts"

# 2. Copy automation scripts
echo "[2] Copying automation scripts..."
scp "$LOCAL_DIR"/*.py "$VPS:$REMOTE_DIR/automations/"
scp "$LOCAL_DIR"/schema.sql "$VPS:$REMOTE_DIR/automations/"
scp "$LOCAL_DIR"/requirements.txt "$VPS:$REMOTE_DIR/automations/"

# 3. Copy tools (etracker, ga4)
echo "[3] Copying tools..."
scp "$PARENT_DIR"/tools/etracker.py "$VPS:$REMOTE_DIR/tools/"
scp "$PARENT_DIR"/tools/ga4.py "$VPS:$REMOTE_DIR/tools/"
scp "$PARENT_DIR"/tools/__init__.py "$VPS:$REMOTE_DIR/tools/" 2>/dev/null || touch /tmp/__init__.py && scp /tmp/__init__.py "$VPS:$REMOTE_DIR/tools/"

# 4. Copy prompts (for Kai and Tessa analysis)
echo "[4] Copying prompts..."
scp "$PARENT_DIR"/prompts/kai.md "$VPS:$REMOTE_DIR/prompts/"
scp "$PARENT_DIR"/prompts/experimentation.md "$VPS:$REMOTE_DIR/prompts/"

# 5. Copy GA4 service account key
echo "[5] Copying GA4 key..."
scp "$PARENT_DIR"/GCP_KEY_REDACTED.json "$VPS:$REMOTE_DIR/ga4-key.json"

# 6. Copy .env if it exists locally (skip if already on VPS)
if [ -f "$LOCAL_DIR/.env" ]; then
    echo "[6] Copying .env..."
    scp "$LOCAL_DIR/.env" "$VPS:$REMOTE_DIR/automations/.env"
else
    echo "[6] No .env found locally — copy .env.template to VPS and fill in values"
    scp "$LOCAL_DIR/.env.template" "$VPS:$REMOTE_DIR/automations/.env.template"
fi

# 7. Install Python dependencies on VPS
echo "[7] Installing Python dependencies..."
ssh "$VPS" "cd $REMOTE_DIR && pip3 install -r automations/requirements.txt --quiet 2>&1 | tail -3"

# 8. Initialize database schema
echo "[8] Initializing database schema..."
ssh "$VPS" "cd $REMOTE_DIR/automations && python3 -c 'from db import init_schema; init_schema()'" 2>&1 || echo "  Schema init failed — check .env PostgreSQL credentials"

echo ""
echo "=== Deploy complete ==="
echo ""
echo "Next steps:"
echo "  1. SSH to VPS: ssh $VPS"
echo "  2. Edit .env:  nano $REMOTE_DIR/automations/.env"
echo "  3. Test cache:  cd $REMOTE_DIR/automations && python3 daily_cache.py"
echo "  4. Configure n8n workflows to trigger scripts on schedule"
echo ""
echo "n8n cron triggers (Execute Command node):"
echo "  Daily 06:00  → cd /opt/cjo/automations && python3 daily_cache.py"
echo "  Daily 06:30  → cd /opt/cjo/automations && python3 daily_anomaly.py"
echo "  Mon   07:00  → cd /opt/cjo/automations && python3 weekly_kai_report.py"
echo "  Daily 08:00  → cd /opt/cjo/automations && python3 daily_tessa_monitor.py"
