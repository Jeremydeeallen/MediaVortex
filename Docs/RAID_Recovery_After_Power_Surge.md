# RAID Recovery After Power Surge - Dell PowerEdge R710

## Problem Summary
After a power surge, the Proxmox server "Brain" (Dell PowerEdge R710) experienced:
- RAID controller misreading 8TB drives as 1.9TB drives
- 29.1TB RAID 5 array showing as only 3.8TB total
- XFS filesystem corruption on the media volume
- Boot timeout errors for device UUID `9f4df46e-c716-4a27-9e12-ce665`
- Proxmox unable to mount `/mnt/pve/Media`

## Root Cause Analysis
1. **Power surge damage** to RAID controller configuration
2. **Controller BIOS disabled** - causing drive capacity misdetection
3. **XFS filesystem corruption** from the power surge
4. **UUID mismatch** after disk cloning recovery

## Hardware Configuration
- **Server**: Dell PowerEdge R710
- **RAID Controller**: PERC H700 Integrated
- **Storage**: 29.1TB RAID 5 array (4x 8TB Hitachi HUA72302 drives)
- **Filesystem**: XFS on `/dev/sda1`
- **Mount Point**: `/mnt/pve/Media`

## Recovery Steps

### Step 1: RAID Controller Diagnosis
1. **Access iDRAC** web interface
2. **Navigate to RAID controller BIOS** during boot
3. **Check Physical Disk Management** - drives showing as 1.9TB instead of 8TB
4. **Verify Virtual Disk Management** - array showing as 3.8TB instead of 29.1TB

### Step 2: RAID Controller Fix
1. **Navigate to Controller Management tab**
2. **Enable "Enable controller BIOS"** (was unchecked)
3. **Apply settings** and reboot
4. **Verify drive detection** - should now show correct 8TB drive sizes
5. **Confirm 29.1TB virtual disk** is detected properly

### Step 3: Filesystem Recovery
1. **Boot into Proxmox** (ignore timeout errors)
2. **Check device status**:
   ```bash
   lsblk
   blkid /dev/sda1
   ```
3. **Attempt XFS repair**:
   ```bash
   xfs_repair /dev/sda1
   ```
4. **Force repair if needed**:
   ```bash
   xfs_repair -L /dev/sda1
   ```

### Step 4: Mount and Verify
1. **Test manual mount**:
   ```bash
   mount /dev/sda1 /mnt/pve/Media
   df -h | grep Media
   ```
2. **Verify data integrity**:
   ```bash
   ls -la /mnt/pve/Media/
   ```
3. **Test Proxmox services**:
   ```bash
   systemctl status mnt-pve-Media.mount
   ```

### Step 5: Final Verification
1. **Reboot server** to test automatic mounting
2. **Verify no boot timeout errors**
3. **Confirm Proxmox can access media volume**
4. **Test VM access to media storage**

### Step 6: NFS Services Recovery
1. **Check NFS server status**:
   ```bash
   systemctl status nfs-server
   ```
2. **Start NFS services** (they failed due to Media mount dependency):
   ```bash
   systemctl start nfs-server
   systemctl status nfs-server
   ```
3. **Verify NFS exports**:
   ```bash
   exportfs -v
   ```
4. **Test NFS mount access**:
   ```bash
   ls -la /mnt/pve/nfs/BrainBackups/
   ```

## Key Commands Used

### RAID Controller Access
- **iDRAC web interface**: Access during boot
- **PERC H700 BIOS**: Navigate to Controller Management
- **Enable controller BIOS**: Check the setting and apply

### Filesystem Recovery
```bash
# Check device status
lsblk
blkid /dev/sda1

# XFS repair
xfs_repair /dev/sda1
xfs_repair -L /dev/sda1  # Force repair if needed

# Test mount
mount /dev/sda1 /mnt/pve/Media
df -h | grep Media
```

### Verification
```bash
# Check filesystem
xfs_info /dev/sda1

# Verify data access
ls -la /mnt/pve/Media/

# Check Proxmox services
systemctl status mnt-pve-Media.mount

# Restart NFS services
systemctl start nfs-server
systemctl status nfs-server

# Test NFS exports
exportfs -v
```

## Prevention Measures

### Hardware Protection
- **UPS system** to prevent power surge damage
- **Surge protectors** for all equipment
- **Regular hardware health checks**

### Data Protection
- **Regular backups** of media data
- **RAID monitoring** to catch issues early
- **Filesystem health monitoring**

### Documentation
- **Record RAID configurations** and settings
- **Document UUID mappings** for storage
- **Maintain recovery procedures**

## Lessons Learned

1. **Power surges can corrupt RAID controller settings** - not just data
2. **Controller BIOS settings** can affect drive detection
3. **XFS repair tools** are effective for filesystem recovery
4. **Large filesystems** (29TB) require significant repair time
5. **iDRAC access** is crucial for hardware troubleshooting

## Recovery Time
- **RAID controller fix**: ~30 minutes
- **XFS repair**: ~2-4 hours for 29TB
- **Total recovery time**: ~4-6 hours

## Success Criteria
- ✅ 29.1TB RAID 5 array detected correctly
- ✅ XFS filesystem repaired and mountable
- ✅ Proxmox can access media volume
- ✅ No boot timeout errors
- ✅ All media data accessible
- ✅ NFS services running and accessible
- ✅ All network shares functional

## Future Improvements
1. **Implement UPS system** for power protection
2. **Set up RAID monitoring** alerts
3. **Create automated backup procedures**
4. **Document all RAID configurations**
5. **Test recovery procedures** regularly

---
*Document created: [Current Date]*  
*Server: Brain (Dell PowerEdge R710)*  
*RAID Controller: PERC H700 Integrated*  
*Storage: 29.1TB RAID 5 (4x 8TB Hitachi HUA72302)*
