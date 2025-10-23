# Proxmox Boot Drive Backup System

## Overview

This system provides automated backup of Proxmox boot drives with cross-server storage and intelligent retention policies. It ensures that both Brain and Pinky servers have their boot drives backed up to the opposite server via NFS mounts.

## Network Configuration

- **Brain Server**: 10.0.1.1
  - Boot Drive: `/dev/sdb` (28.9GB USB)
  - Backup Destination: `/mnt/pve/nfs/BrainBackups/ProxmoxBootDrive/` (stored on Pinky)
  
- **Pinky Server**: 10.0.1.2  
  - Boot Drive: `/dev/sdb` (931GB SSD)
  - Backup Destination: `/mnt/nfs/PinkyBackups/ProxmoxBootDrive/` (stored on Brain)

- **Connection**: 10Gb direct backplane network
- **NFS Mounts**: Cross-server backup storage

## Backup Process

### How the Backup Script Works

The `BackupProxmoxBootDrive.py` script:

1. **Auto-detects the boot device** by finding the device mounted at `/`
2. **Determines backup destination** based on hostname (Brain → Pinky, Pinky → Brain)
3. **Creates compressed image** using `dd` and `gzip`
4. **Stores with timestamp** in format: `proxmox-boot-{hostname}-{YYYYMMDD_HHMMSS}.img.gz`
5. **Implements retention policy** automatically
6. **Logs all operations** to `/var/log/proxmox-backup/boot-drive-backup.log`

### Manual Backup Commands

```bash
# Run backup manually on Brain
python3 /path/to/Scripts/Proxmox/BackupProxmoxBootDrive.py

# Run backup manually on Pinky  
python3 /path/to/Scripts/Proxmox/BackupProxmoxBootDrive.py

# Dry run to see what would happen
python3 /path/to/Scripts/Proxmox/BackupProxmoxBootDrive.py --dry-run

# Verbose output
python3 /path/to/Scripts/Proxmox/BackupProxmoxBootDrive.py --verbose
```

### Automated Backup Schedule

**Cron Configuration:**
- **Brain**: Daily at 2:00 AM
- **Pinky**: Daily at 2:00 AM
- **Schedule**: `0 2 * * * /path/to/Scripts/Proxmox/BackupProxmoxBootDrive.py`

**Cron Setup Commands:**
```bash
# Add to Brain's crontab
echo "0 2 * * * /path/to/Scripts/Proxmox/BackupProxmoxBootDrive.py" | crontab -

# Add to Pinky's crontab  
echo "0 2 * * * /path/to/Scripts/Proxmox/BackupProxmoxBootDrive.py" | crontab -
```

### Retention Policy

- **Daily Backups**: Keep last 5 daily backups
- **Monthly Backups**: Keep last 12 monthly backups (automatically created on 1st of each month)
- **Automatic Cleanup**: Old backups are automatically deleted based on retention policy
- **Cross-Promotion**: Daily backups become monthly backups on the 1st of each month

### Where Backups Are Stored

**Brain Backups** (stored on Pinky):
- Location: `/mnt/pve/nfs/BrainBackups/ProxmoxBootDrive/`
- Format: `proxmox-boot-brain-YYYYMMDD_HHMMSS.img.gz`

**Pinky Backups** (stored on Brain):
- Location: `/mnt/nfs/PinkyBackups/ProxmoxBootDrive/`
- Format: `proxmox-boot-pinky-YYYYMMDD_HHMMSS.img.gz`

## Restore Procedures

### How to Restore from Image File

#### Step 1: Prepare the Target Drive

```bash
# Identify the target USB/SSD drive
lsblk

# Unmount any existing partitions on the target drive
umount /dev/sdX*  # Replace X with your target drive

# Wipe the target drive (optional but recommended)
dd if=/dev/zero of=/dev/sdX bs=1M count=100
```

#### Step 2: Restore the Image

```bash
# Method 1: Direct restore (if image is uncompressed)
dd if=proxmox-boot-brain-20241021_020000.img of=/dev/sdX bs=1M status=progress

# Method 2: Restore compressed image
gunzip -c proxmox-boot-brain-20241021_020000.img.gz | dd of=/dev/sdX bs=1M status=progress

# Method 3: Using zstd (if compressed with zstd)
zstd -dc proxmox-boot-brain-20241021_020000.img.zst | dd of=/dev/sdX bs=1M status=progress
```

#### Step 3: Verify the Restore

```bash
# Check filesystem integrity
fsck /dev/sdX1  # Check the root partition

# Mount and verify
mkdir /mnt/restore-test
mount /dev/sdX1 /mnt/restore-test
ls -la /mnt/restore-test/
umount /mnt/restore-test
```

#### Step 4: Boot from Restored Drive

1. **Shutdown the server**
2. **Replace the boot drive** with the restored drive
3. **Boot the server**
4. **Verify Proxmox is accessible** via web interface
5. **Check VM status** and storage mounts

### Emergency Recovery Procedures

#### If Boot Drive Fails Completely

1. **Access the server** via iDRAC or physical console
2. **Boot from Proxmox installation media**
3. **Mount the NFS backup location**:
   ```bash
   mkdir /mnt/backup
   mount -t nfs 10.0.1.1:/mnt/pve/Media/PinkyBackups /mnt/backup
   ```
4. **Restore the latest backup** to a new drive
5. **Replace the failed drive** and reboot

#### If NFS Mount is Unavailable

1. **Copy backup to local storage** first:
   ```bash
   cp /mnt/pve/nfs/BrainBackups/ProxmoxBootDrive/latest-backup.img.gz /tmp/
   ```
2. **Restore from local copy**:
   ```bash
   gunzip -c /tmp/latest-backup.img.gz | dd of=/dev/sdX bs=1M
   ```

## Physical Spare Drives

### Creating Spare USB Drives from Images

#### Method 1: Direct Clone from Backup

```bash
# Find the latest backup
ls -lt /mnt/pve/nfs/BrainBackups/ProxmoxBootDrive/ | head -1

# Restore to spare USB drive
gunzip -c proxmox-boot-brain-20241021_020000.img.gz | dd of=/dev/sdX bs=1M status=progress

# Verify the clone
fsck /dev/sdX1
```

#### Method 2: Clone from Running System

```bash
# Create image of current boot drive
dd if=/dev/sdb of=/tmp/current-boot.img bs=1M status=progress

# Compress the image
gzip /tmp/current-boot.img

# Restore to spare drive
gunzip -c /tmp/current-boot.img.gz | dd of=/dev/sdX bs=1M status=progress
```

### Labeling Convention

- **Brain Spare**: Label as "Brain-Spare-YYYYMMDD"
- **Pinky Spare**: Label as "Pinky-Spare-YYYYMMDD"
- **Use physical labels** on the USB drives
- **Store in labeled containers** for easy identification

### Where to Store Spares

- **Brain Spare**: Store on Pinky server (in `/mnt/BrainBackups/SpareDrives/`)
- **Pinky Spare**: Store on Brain server (in `/mnt/pve/Media/PinkyBackups/SpareDrives/`)
- **Keep spares updated** after significant configuration changes

### When to Update Spares

- **After major Proxmox updates**
- **After configuration changes** (network, storage, etc.)
- **Monthly** as part of maintenance
- **Before any major changes** to the system

## Troubleshooting

### Common Issues and Solutions

#### Issue: "Backup destination not accessible"

**Symptoms**: Script fails with NFS mount error

**Solutions**:
```bash
# Check NFS mount status
mount | grep nfs

# Remount NFS if needed
mount -a

# Check NFS server status
systemctl status nfs-server

# Test NFS connectivity
ping 10.0.1.1  # or 10.0.1.2
```

#### Issue: "Cannot write to backup destination"

**Symptoms**: Permission denied when writing to backup directory

**Solutions**:
```bash
# Check directory permissions
ls -la /mnt/pve/nfs/BrainBackups/

# Fix permissions if needed
chmod 755 /mnt/pve/nfs/BrainBackups/ProxmoxBootDrive/

# Check NFS export permissions on source server
cat /etc/exports
```

#### Issue: "Could not detect boot device"

**Symptoms**: Script cannot find the boot device

**Solutions**:
```bash
# Check what's mounted at root
df /

# Check available devices
lsblk

# Manually specify device in script if needed
```

#### Issue: "Backup file was not created"

**Symptoms**: Backup process completes but no file is created

**Solutions**:
```bash
# Check disk space on destination
df -h /mnt/pve/nfs/BrainBackups/

# Check for errors in log
tail -f /var/log/proxmox-backup/boot-drive-backup.log

# Test with smaller backup first
dd if=/dev/sdb bs=1M count=100 | gzip > /tmp/test-backup.img.gz
```

### How to Verify Backup Integrity

#### Check Backup File

```bash
# List backup files with details
ls -lh /mnt/pve/nfs/BrainBackups/ProxmoxBootDrive/

# Check file integrity
gunzip -t proxmox-boot-brain-20241021_020000.img.gz

# Get backup file size
du -h proxmox-boot-brain-20241021_020000.img.gz
```

#### Test Restore (Non-Destructive)

```bash
# Create a test restore to a spare drive
gunzip -c proxmox-boot-brain-20241021_020000.img.gz | dd of=/dev/sdX bs=1M

# Mount and verify filesystem
mkdir /mnt/test-restore
mount /dev/sdX1 /mnt/test-restore
ls -la /mnt/test-restore/
umount /mnt/test-restore
```

### How to Test Restores Without Disrupting Production

#### Method 1: Use Spare Hardware

1. **Use a separate server** or VM for testing
2. **Restore backup to test environment**
3. **Verify functionality** without affecting production
4. **Document any issues** found during testing

#### Method 2: Use Virtual Machine

1. **Create a VM** with similar disk configuration
2. **Restore backup to VM disk**
3. **Boot VM** and verify Proxmox functionality
4. **Test network and storage** connectivity

#### Method 3: Live Testing (Careful!)

1. **Create a complete backup** of current system first
2. **Restore to a spare drive** 
3. **Test boot from spare** in a safe environment
4. **Keep original drive** as fallback

## Monitoring and Maintenance

### Log Monitoring

```bash
# Check recent backup activity
tail -f /var/log/proxmox-backup/boot-drive-backup.log

# Check for errors
grep -i error /var/log/proxmox-backup/boot-drive-backup.log

# Check backup frequency
grep "Backup completed" /var/log/proxmox-backup/boot-drive-backup.log | tail -10
```

### Storage Monitoring

```bash
# Check backup storage usage
du -sh /mnt/pve/nfs/BrainBackups/ProxmoxBootDrive/
du -sh /mnt/nfs/PinkyBackups/ProxmoxBootDrive/

# Check available space
df -h /mnt/pve/nfs/BrainBackups/
df -h /mnt/nfs/PinkyBackups/
```

### Regular Maintenance Tasks

#### Weekly Tasks
- **Verify backup completion** from logs
- **Check storage space** on backup destinations
- **Test restore process** with latest backup
- **Update spare drives** if configuration changed

#### Monthly Tasks
- **Review retention policy** effectiveness
- **Clean up old test restores**
- **Update documentation** if procedures changed
- **Test emergency recovery** procedures

#### Quarterly Tasks
- **Full disaster recovery test**
- **Review and update backup procedures**
- **Check hardware health** of backup storage
- **Update spare drive inventory**

## Success Criteria

- ✅ **Daily backups** created automatically at 2:00 AM
- ✅ **Retention policy** working (5 daily + 12 monthly)
- ✅ **Cross-server storage** functioning properly
- ✅ **NFS mounts** stable and accessible
- ✅ **Backup integrity** verified regularly
- ✅ **Restore procedures** tested and documented
- ✅ **Spare drives** created and labeled
- ✅ **Emergency procedures** documented and tested

---

*Document created: October 21, 2025*  
*System: Brain (Dell PowerEdge R710) + Pinky Server*  
*Network: 10Gb backplane connection*  
*Backup Strategy: Cross-server NFS storage with intelligent retention*
