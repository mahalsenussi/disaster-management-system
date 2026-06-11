#!/bin/bash

# Deployment script for Disaster Management System
# This script copies the project to remote server and sets up systemd services
# 
# PREREQUISITE: Set up SSH keys for passwordless authentication:
# 1. ssh-keygen -t rsa (if you don't have keys)
# 2. ssh-copy-id mahmoud@10.1.30.100
# 3. Enter password: loraly

REMOTE_HOST="10.1.30.100"
REMOTE_USER="mahmoud"
REMOTE_PASSWORD="loraly"
REMOTE_DIR="/home/mahmoud/disaster_management"

echo "=== Disaster Management System Deployment ==="
echo "Target: $REMOTE_USER@$REMOTE_HOST"
echo "Remote directory: $REMOTE_DIR"
echo ""

# Check SSH connection
echo "Testing SSH connection..."
if ! ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 $REMOTE_USER@$REMOTE_HOST "echo 'Connection successful'" 2>/dev/null; then
    echo "Error: Cannot connect to remote server."
    echo "Please set up SSH keys for passwordless authentication:"
    echo "  1. ssh-keygen -t rsa"
    echo "  2. ssh-copy-id $REMOTE_USER@$REMOTE_HOST"
    echo "  3. Enter password when prompted"
    exit 1
fi

# Function to run SSH command
run_ssh() {
    ssh -o StrictHostKeyChecking=no $REMOTE_USER@$REMOTE_HOST "$1"
}

# Function to run SSH command with sudo
run_ssh_sudo() {
    local cmd=$1
    ssh -o StrictHostKeyChecking=no $REMOTE_USER@$REMOTE_HOST "echo '$REMOTE_PASSWORD' | sudo -S $cmd"
}

echo "Step 1: Creating remote directory..."
run_ssh "mkdir -p $REMOTE_DIR"

echo "Step 2: Copying project files to remote server..."
# Create a temporary tarball excluding unnecessary files
tar -czf /tmp/disaster_management.tar.gz \
    --exclude='.git' \
    --exclude='basic_flutter' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='database/*.db' \
    -C /home/mahmoud v2

# Copy tarball to remote server
scp -o StrictHostKeyChecking=no /tmp/disaster_management.tar.gz $REMOTE_USER@$REMOTE_HOST:/tmp/

# Extract on remote server
run_ssh "cd /home/mahmoud && rm -rf $REMOTE_DIR && mkdir -p $REMOTE_DIR && tar -xzf /tmp/disaster_management.tar.gz && mv v2/* $REMOTE_DIR/ && rm -rf v2 /tmp/disaster_management.tar.gz"

# Clean up local tarball
rm -f /tmp/disaster_management.tar.gz

echo "Step 3: Installing Python dependencies..."
run_ssh "cd $REMOTE_DIR && pip3 install -r public_app/requirements.txt"
run_ssh "cd $REMOTE_DIR && pip3 install -r engine_service/requirements.txt"

echo "Step 4: Creating systemd service for Public App..."
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

echo "Step 5: Creating systemd service for Engine Service..."
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

echo "Step 6: Reloading systemd daemon..."
run_ssh_sudo "systemctl daemon-reload"

echo "Step 7: Enabling services..."
run_ssh_sudo "systemctl enable disaster-public-app.service"
run_ssh_sudo "systemctl enable disaster-engine-service.service"

echo "Step 8: Starting services..."
run_ssh_sudo "systemctl start disaster-public-app.service"
run_ssh_sudo "systemctl start disaster-engine-service.service"

echo ""
echo "=== Deployment Complete ==="
echo "Checking service status..."
run_ssh_sudo "systemctl status disaster-public-app.service --no-pager"
run_ssh_sudo "systemctl status disaster-engine-service.service --no-pager"

echo ""
echo "Services are now running on remote server:"
echo "- Public App: http://$REMOTE_HOST:5000"
echo "- Engine Service: http://$REMOTE_HOST:5001"