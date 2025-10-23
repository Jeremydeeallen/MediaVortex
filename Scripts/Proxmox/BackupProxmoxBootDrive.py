#!/usr/bin/env python3
"""
Proxmox Boot Drive Backup Script

This script creates compressed backups of Proxmox boot drives and stores them
on the opposite server via NFS mounts. It implements a retention policy of
5 daily backups and 12 monthly backups.

Usage:
    python3 BackupProxmoxBootDrive.py [--dry-run] [--verbose]

Author: MediaVortex Automation
"""

import os
import sys
import subprocess
import shutil
import gzip
import logging
import argparse
import socket
import datetime
import glob
from pathlib import Path

class ProxmoxBootDriveBackup:
    def __init__(self, dry_run=False, verbose=False):
        self.dry_run = dry_run
        self.verbose = verbose
        self.hostname = socket.gethostname().lower()
        self.logger = self._setup_logging()
        
        # Network configuration
        self.network_config = {
            'brain': {
                'backup_dest': '/mnt/pve/nfs/BrainBackups/ProxmoxBootDrive',
                'target_server': 'Pinky'
            },
            'pinky': {
                'backup_dest': '/mnt/nfs/PinkyBackups/ProxmoxBootDrive', 
                'target_server': 'Brain'
            }
        }
        
        # Retention policy
        self.retention_daily = 5
        self.retention_monthly = 12
        
    def _setup_logging(self):
        """Setup logging configuration"""
        log_dir = Path('/var/log/proxmox-backup')
        log_dir.mkdir(exist_ok=True)
        
        logger = logging.getLogger('ProxmoxBootDriveBackup')
        logger.setLevel(logging.INFO)
        
        # File handler
        fh = logging.FileHandler(log_dir / 'boot-drive-backup.log')
        fh.setLevel(logging.INFO)
        
        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        
        logger.addHandler(fh)
        logger.addHandler(ch)
        
        return logger
        
    def _run_command(self, command, check=True):
        """Run a shell command and return the result"""
        if self.dry_run:
            self.logger.info(f"DRY RUN: {command}")
            return "DRY RUN"
            
        if self.verbose:
            self.logger.info(f"Running: {command}")
            
        try:
            result = subprocess.run(
                command, 
                shell=True, 
                capture_output=True, 
                text=True, 
                check=check
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Command failed: {command}")
            self.logger.error(f"Error: {e.stderr}")
            if check:
                raise
            return None
            
    def _get_boot_device(self):
        """Detect the boot device by finding the device mounted at /"""
        try:
            # Find the device mounted at root
            result = self._run_command("df / | tail -1 | awk '{print $1}'")
            if result and result.startswith('/dev/'):
                # Get the actual device (remove partition number)
                device = result.rstrip('0123456789')
                self.logger.info(f"Detected boot device: {device}")
                return device
            else:
                raise Exception("Could not detect boot device")
        except Exception as e:
            self.logger.error(f"Failed to detect boot device: {e}")
            sys.exit(1)
            
    def _get_device_size(self, device):
        """Get the size of the device in bytes"""
        try:
            result = self._run_command(f"blockdev --getsize64 {device}")
            return int(result)
        except Exception as e:
            self.logger.error(f"Failed to get device size: {e}")
            return None
            
    def _create_backup_filename(self):
        """Create timestamped backup filename"""
        now = datetime.datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        return f"proxmox-boot-{self.hostname}-{timestamp}.img.gz"
        
    def _get_backup_config(self):
        """Get backup configuration for current host"""
        if self.hostname not in self.network_config:
            self.logger.error(f"Unknown hostname: {self.hostname}")
            self.logger.error("Expected 'brain' or 'pinky'")
            sys.exit(1)
            
        return self.network_config[self.hostname]
        
    def _ensure_backup_directory(self, backup_dest):
        """Ensure backup directory exists"""
        if not os.path.exists(backup_dest):
            self.logger.info(f"Creating backup directory: {backup_dest}")
            self._run_command(f"mkdir -p {backup_dest}")
            
    def _check_nfs_mount(self, backup_dest):
        """Check if NFS mount is accessible"""
        if not os.path.exists(backup_dest):
            self.logger.error(f"Backup destination not accessible: {backup_dest}")
            self.logger.error("Check NFS mount status")
            return False
            
        # Test write access
        test_file = os.path.join(backup_dest, '.write_test')
        try:
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            return True
        except Exception as e:
            self.logger.error(f"Cannot write to backup destination: {e}")
            return False
            
    def _create_backup(self, device, backup_dest):
        """Create the actual backup"""
        backup_file = os.path.join(backup_dest, self._create_backup_filename())
        
        self.logger.info(f"Starting backup of {device} to {backup_file}")
        
        # Get device size for progress tracking
        device_size = self._get_device_size(device)
        if device_size:
            self.logger.info(f"Device size: {device_size / (1024**3):.2f} GB")
            
        # Create backup using dd and gzip
        backup_cmd = f"dd if={device} bs=1M | gzip > {backup_file}"
        
        self.logger.info("Starting backup process...")
        start_time = datetime.datetime.now()
        
        try:
            self._run_command(backup_cmd)
            end_time = datetime.datetime.now()
            duration = end_time - start_time
            
            # Verify backup file
            if os.path.exists(backup_file):
                backup_size = os.path.getsize(backup_file)
                self.logger.info(f"Backup completed successfully")
                self.logger.info(f"Backup file: {backup_file}")
                self.logger.info(f"Backup size: {backup_size / (1024**3):.2f} GB")
                self.logger.info(f"Duration: {duration}")
                return backup_file
            else:
                self.logger.error("Backup file was not created")
                return None
                
        except Exception as e:
            self.logger.error(f"Backup failed: {e}")
            return None
            
    def _cleanup_old_backups(self, backup_dest):
        """Clean up old backups based on retention policy"""
        self.logger.info("Cleaning up old backups...")
        
        # Get all backup files
        backup_pattern = os.path.join(backup_dest, f"proxmox-boot-{self.hostname}-*.img.gz")
        backup_files = glob.glob(backup_pattern)
        backup_files.sort(key=os.path.getmtime, reverse=True)
        
        if len(backup_files) <= self.retention_daily:
            self.logger.info("No cleanup needed - within daily retention limit")
            return
            
        # Separate daily and monthly backups
        now = datetime.datetime.now()
        daily_backups = []
        monthly_backups = []
        
        for backup_file in backup_files:
            # Extract date from filename
            filename = os.path.basename(backup_file)
            try:
                date_str = filename.split('-')[-1].replace('.img.gz', '')
                backup_date = datetime.datetime.strptime(date_str, "%Y%m%d_%H%M%S")
                
                # Check if it's a monthly backup (1st of month)
                if backup_date.day == 1:
                    monthly_backups.append(backup_file)
                else:
                    daily_backups.append(backup_file)
            except Exception as e:
                self.logger.warning(f"Could not parse date from {filename}: {e}")
                continue
                
        # Keep only the required number of daily backups
        if len(daily_backups) > self.retention_daily:
            files_to_delete = daily_backups[self.retention_daily:]
            for file_to_delete in files_to_delete:
                self.logger.info(f"Deleting old daily backup: {file_to_delete}")
                if not self.dry_run:
                    os.remove(file_to_delete)
                    
        # Keep only the required number of monthly backups
        if len(monthly_backups) > self.retention_monthly:
            files_to_delete = monthly_backups[self.retention_monthly:]
            for file_to_delete in files_to_delete:
                self.logger.info(f"Deleting old monthly backup: {file_to_delete}")
                if not self.dry_run:
                    os.remove(file_to_delete)
                    
        self.logger.info("Backup cleanup completed")
        
    def run_backup(self):
        """Main backup process"""
        self.logger.info(f"Starting Proxmox boot drive backup on {self.hostname}")
        
        # Get configuration
        config = self._get_backup_config()
        backup_dest = config['backup_dest']
        target_server = config['target_server']
        
        self.logger.info(f"Backing up to {target_server} at {backup_dest}")
        
        # Check NFS mount
        if not self._check_nfs_mount(backup_dest):
            self.logger.error("NFS mount check failed")
            sys.exit(1)
            
        # Ensure backup directory exists
        self._ensure_backup_directory(backup_dest)
        
        # Detect boot device
        device = self._get_boot_device()
        
        # Create backup
        backup_file = self._create_backup(device, backup_dest)
        if not backup_file:
            self.logger.error("Backup creation failed")
            sys.exit(1)
            
        # Clean up old backups
        self._cleanup_old_backups(backup_dest)
        
        self.logger.info("Backup completed successfully")
        return True

def main():
    parser = argparse.ArgumentParser(description='Backup Proxmox boot drive')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be done without executing')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose output')
    
    args = parser.parse_args()
    
    backup = ProxmoxBootDriveBackup(dry_run=args.dry_run, verbose=args.verbose)
    
    try:
        success = backup.run_backup()
        if success:
            print("Backup completed successfully")
            sys.exit(0)
        else:
            print("Backup failed")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\nBackup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Backup failed with error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
