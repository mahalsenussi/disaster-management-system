#!/bin/bash

# Service setup script for Disaster Management System
# This script creates and starts systemd services on the remote server

REMOTE_HOST="10.1.30.100"
REMOTE_USER="mahmoud"
REMOTE_PASSWORD="loraly"
REMOTE_DIR="/home/mahmoud/disaster_management"

echo "=== Setting up systemd services ==="
echo "Target: $REMOTE_USER@$REMOTE_HOST"
echo ""

# Function to run SSH command with sudo
run_ssh_sudo() {
    local cmd=$1
    ssh -o StrictHostKeyChecking=no $REMOTE_USER@$REMOTE_HOST "echo '$REMOTE_PASSWORD' | sudo -S $cmd"
}

echo "Step 1: Creating systemd service for Public App..."
run_ssh_sudo "tee /etc/systemd/system/disaster-public-app.service > /dev/null << 'EOF'
[Unit]
Description=Disaster Management Public App
After=network.target

[Service]
Type=simple
User=$REMOTE_USER
WorkingDirectory=$REMOTE_DIR/public_app
Environment=\"DATABASE=database/disaster.db\"
Environment=\"ENGINE_API_URL=http://localhost:5001/route\"
ExecStart=/usr/bin/python3 $REMOTE_DIR/public_app/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF"

echo "Step 2: Creating systemd service for Engine Service..."
run_ssh_sudo "tee /etc/systemd/system/disaster-engine-service.service > /dev/null << 'EOF'
[Unit]
Description=Disaster Management Engine Service
After=network.target

[Service]
Type=simple
User=$REMOTE_USER
WorkingDirectory=$REMOTE_DIR/engine_service
Environment=\"OSRM_URL=http://router.project-osrm.org\"
Environment=\"FALLBACK_ENABLED=true\"
ExecStart=/usr/bin/python3 $REMOTE_DIR/engine_service/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF"

echo "Step 3: Reloading systemd daemon..."
run_ssh_sudo "systemctl daemon-reload"

echo "Step 4: Enabling services..."
run_ssh_sudo "systemctl enable disaster-public-app.service"
run_ssh_sudo "systemctl enable disaster-engine-service.service"

echo "Step 5: Starting services..."
run_ssh_sudo "systemctl start disaster-public-app.service"
run_ssh_sudo "systemctl start disaster-engine-service.service"

echo ""
echo "=== Service Setup Complete ==="
echo "Checking service status..."
run_ssh_sudo "systemctl status disaster-public-app.service --no-pager"
echo "---"
run_ssh_sudo "systemctl status disaster-engine-service.service --no-pager"

echo ""
echo "Services are now running on remote server:"
echo "- Public App: http://$REMOTE_HOST:5000"
echo "- Engine Service: http://$REMOTE_HOST:5001"