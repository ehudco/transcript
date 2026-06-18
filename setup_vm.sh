#!/bin/bash
set -e

REPO_URL="https://github.com/ehudco/transcript.git"
USERNAME=$(whoami)
HOME_DIR="/home/$USERNAME"
REPO_DIR="$HOME_DIR/transcript"

echo "=== [1/6] Installing system dependencies ==="
sudo apt-get update -q
sudo apt-get install -y -q python3-pip python3-venv git

echo "=== [2/6] Cloning repo ==="
if [ -d "$REPO_DIR" ]; then
    echo "Repo already exists — pulling latest"
    git -C "$REPO_DIR" pull
else
    git clone "$REPO_URL" "$REPO_DIR"
fi

echo "=== [3/6] Installing Python dependencies ==="
python3 -m venv "$REPO_DIR/venv"
"$REPO_DIR/venv/bin/pip" install -q -r "$REPO_DIR/requirements.txt"

echo "=== [4/6] Creating worker.conf ==="
if [ ! -f "$HOME_DIR/worker.conf" ]; then
    cat > "$HOME_DIR/worker.conf" << 'EOF'
ENABLED=true
DOWNLOAD_ONLY=false
TEST_MODE=false
EOF
    echo "Created $HOME_DIR/worker.conf"
else
    echo "worker.conf already exists — skipping"
fi

echo "=== [5/6] Creating start_worker.sh ==="
cat > "$REPO_DIR/start_worker.sh" << EOF
#!/bin/bash
set -a
source $HOME_DIR/worker.conf
set +a

if [ "\$ENABLED" != "true" ]; then
    echo "Worker disabled in worker.conf — exiting"
    exit 0
fi
exec $REPO_DIR/venv/bin/python $REPO_DIR/worker.py
EOF
chmod +x "$REPO_DIR/start_worker.sh"

echo "=== [6/6] Installing systemd service ==="
sudo tee /etc/systemd/system/worker.service > /dev/null << EOF
[Unit]
Description=Transcription Worker
After=network.target

[Service]
User=$USERNAME
WorkingDirectory=$REPO_DIR
EnvironmentFile=$HOME_DIR/worker.conf
ExecStart=$REPO_DIR/start_worker.sh
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable worker
sudo systemctl start worker

echo ""
echo "=== Setup complete ==="
echo "Worker status:"
sudo systemctl status worker --no-pager
echo ""
echo "To follow logs: sudo journalctl -u worker -f"
