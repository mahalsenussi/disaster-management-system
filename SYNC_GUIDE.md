# Disaster Management System - Remote Sync Guide

## Quick Sync Command

To sync your local changes to the remote server (10.1.30.100):

```bash
./sync_to_remote.sh
```

## What the Sync Script Does

1. **Tests SSH connection** - Ensures connectivity to remote server
2. **Creates backup** - Backs up the current remote deployment with timestamp
3. **Creates tarball** - Packages local project (excluding unnecessary files)
4. **Copies to remote** - Transfers tarball to remote server via SCP
5. **Extracts and updates** - Replaces remote deployment with new version
6. **Maintains configuration** - Preserves port settings (Engine on 5002)
7. **Updates dependencies** - Installs/updates Python requirements
8. **Restarts services** - Restarts both Public App and Engine Service
9. **Verifies deployment** - Checks service status and endpoints

## Files Excluded from Sync

- `.git/` - Git repository files
- `basic_flutter/` - Flutter mobile app
- `__pycache__/` - Python cache files
- `*.pyc` - Compiled Python files
- `database/*.db` - Local database files
- `*.log` - Log files
- `sync_to_remote.sh` - The sync script itself

## Service Configuration After Sync

- **Public App**: Port 5000 (managed by systemd)
- **Engine Service**: Port 5002 (manual start due to systemd issues)

## Access URLs After Sync

- **Public Dashboard**: http://10.1.30.100:5000
- **Engine Service**: http://10.1.30.100:5002

## Backup Management

Backups are created on the remote server in:
```
/home/mahmoud/disaster_management_backup_YYYYMMDD_HHMMSS/
```

To clean old backups (on remote server):
```bash
ssh mahmoud@10.1.30.100
cd /home/mahmoud
ls -la disaster_management_backup_*
# Remove old backups as needed
rm -rf disaster_management_backup_OLD_TIMESTAMP
```

## Troubleshooting

### Sync Fails
- Check SSH connection: `ssh mahmoud@10.1.30.100`
- Verify script permissions: `chmod +x sync_to_remote.sh`
- Check available disk space on remote server

### Services Don't Start After Sync
- Check Public App: `ssh mahmoud@10.1.30.100 'systemctl --user status disaster-public-app.service'`
- Check Engine Service: `ssh mahmoud@10.1.30.100 'ps aux | grep engine_service'`
- View Engine Service logs: `ssh mahmoud@10.1.30.100 'tail -f /tmp/engine_service.log'`

### Manual Service Restart
If you need to manually restart services after sync:

```bash
ssh mahmoud@10.1.30.100

# Restart Public App
systemctl --user restart disaster-public-app.service

# Restart Engine Service
pkill -f "engine_service/app.py"
cd /home/mahmoud/disaster_management/engine_service
nohup python3 app.py > /tmp/engine_service.log 2>&1 &
```

## Advanced Usage

### Sync Specific Files Only
Edit the `sync_to_remote.sh` script to modify the tar creation command to include only specific files.

### Skip Dependency Updates
Comment out the dependency installation steps in the script if you know requirements haven't changed.

### Custom Remote Directory
Modify the `REMOTE_DIR` variable at the top of the script if you want to deploy to a different location.

## Sync Script Location

The sync script is located at:
```
/home/mahmoud/v2/sync_to_remote.sh
```