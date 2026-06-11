#!/bin/bash

# Disaster Management System - Remote Sync Script
# This script syncs the local project to the remote server and restarts services

REMOTE_HOST="10.1.30.100"
REMOTE_USER="mahmoud"
REMOTE_DIR="/home/mahmoud/disaster_management"

echo "=== Disaster Management System - Remote Sync ==="
echo "Local: /home/mahmoud/v2"
echo "Remote: $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR"
echo ""

# Check SSH connection
echo "Testing SSH connection..."
if ! ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 $REMOTE_USER@$REMOTE_HOST "echo 'Connection successful'" 2>/dev/null; then
    echo "Error: Cannot connect to remote server."
    exit 1
fi

echo "✓ SSH connection successful"
echo ""

# Step 1: Create backup of remote deployment
echo "Step 1: Creating backup of remote deployment..."
ssh $REMOTE_USER@$REMOTE_HOST "cd /home/mahmoud && cp -r disaster_management disaster_management_backup_$(date +%Y%m%d_%H%M%S) 2>/dev/null || echo 'No existing deployment to backup'"
echo "✓ Backup created"
echo ""

# Step 2: Create tarball of local project
echo "Step 2: Creating tarball of local project..."
tar -czf /tmp/disaster_management_sync.tar.gz \
    --exclude='.git' \
    --exclude='basic_flutter' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='database/*.db' \
    --exclude='.DS_Store' \
    --exclude='*.log' \
    --exclude='sync_to_remote.sh' \
    -C /home/mahmoud v2

if [ $? -eq 0 ]; then
    echo "✓ Tarball created successfully"
else
    echo "✗ Failed to create tarball"
    exit 1
fi
echo ""

# Step 3: Copy tarball to remote server
echo "Step 3: Copying tarball to remote server..."
scp -o StrictHostKeyChecking=no /tmp/disaster_management_sync.tar.gz $REMOTE_USER@$REMOTE_HOST:/tmp/

if [ $? -eq 0 ]; then
    echo "✓ Tarball copied successfully"
else
    echo "✗ Failed to copy tarball"
    exit 1
fi
echo ""

# Step 4: Extract and update on remote server
echo "Step 4: Extracting and updating on remote server..."
ssh $REMOTE_USER@$REMOTE_HOST << 'ENDSSH'
cd /home/mahmoud
# Remove old deployment
rm -rf disaster_management
# Create new directory
mkdir -p disaster_management
# Extract new deployment
tar -xzf /tmp/disaster_management_sync.tar.gz
# Move files to correct location
mv v2/* disaster_management/
# Cleanup
rm -rf v2 /tmp/disaster_management_sync.tar.gz
echo "✓ Remote deployment updated"
ENDSSH

echo ""

# Step 5: Update Engine Service port configuration (maintain port 5002)
echo "Step 5: Maintaining port configuration..."
ssh $REMOTE_USER@$REMOTE_HOST "sed -i 's/port=5001/port=5002/g' $REMOTE_DIR/engine_service/app.py"
ssh $REMOTE_USER@$REMOTE_HOST "sed -i \"s|'http://localhost:5001/route'|'http://localhost:5002/route'|g\" $REMOTE_DIR/public_app/app.py"
echo "✓ Port configuration maintained (Engine on 5002)"
echo ""

# Step 6: Install/update Python dependencies
echo "Step 6: Updating Python dependencies..."
ssh $REMOTE_USER@$REMOTE_HOST "cd $REMOTE_DIR && pip3 install -r public_app/requirements.txt -q"
ssh $REMOTE_USER@$REMOTE_HOST "cd $REMOTE_DIR && pip3 install -r engine_service/requirements.txt -q"
echo "✓ Dependencies updated"
echo ""

# Step 7: Restart Public App (systemd)
echo "Step 7: Restarting Public App..."
ssh $REMOTE_USER@$REMOTE_HOST "systemctl --user restart disaster-public-app.service"
echo "✓ Public App restarted"
echo ""

# Step 8: Restart Engine Service (manual)
echo "Step 8: Restarting Engine Service..."
ssh $REMOTE_USER@$REMOTE_HOST << 'ENDSSH'
# Kill existing engine service
pkill -f "engine_service/app.py"
# Wait a moment
sleep 2
# Start engine service
cd /home/mahmoud/disaster_management/engine_service
nohup python3 app.py > /tmp/engine_service.log 2>&1 &
echo "✓ Engine Service restarted"
ENDSSH

echo ""

# Step 9: Wait for services to start
echo "Step 9: Waiting for services to start..."
sleep 5
echo "✓ Services should be ready"
echo ""

# Step 10: Verify services
echo "Step 10: Verifying services..."
echo "Public App status:"
ssh $REMOTE_USER@$REMOTE_HOST "systemctl --user status disaster-public-app.service --no-pager | head -10"

echo ""
echo "Engine Service status:"
ssh $REMOTE_USER@$REMOTE_HOST "ps aux | grep 'engine_service/app.py' | grep -v grep || echo 'Engine service not found in process list'"

echo ""
echo "Port status:"
ssh $REMOTE_USER@$REMOTE_HOST "netstat -tlnp 2>/dev/null | grep -E ':(5000|5002)' || ss -tlnp 2>/dev/null | grep -E ':(5000|5002)'"

echo ""

# Cleanup local tarball
rm -f /tmp/disaster_management_sync.tar.gz

echo "=== SYNC COMPLETE ==="
echo "✓ Project synced to remote server"
echo "✓ Services restarted"
echo ""
echo "Access URLs:"
echo "• Public Dashboard: http://$REMOTE_HOST:5000"
echo "• Engine Service: http://$REMOTE_HOST:5002"
echo ""
echo "Backup created on remote server in: /home/mahmoud/disaster_management_backup_*"