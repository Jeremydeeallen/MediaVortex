#!/usr/bin/env python3
"""
Proxmox Boot Drive Backup Setup Script

This script helps set up the backup directories and cron jobs for
the Proxmox boot drive backup system.

Usage:
    python3 SetupProxmoxBackup.py [--install-cron] [--dry-run]

Author: MediaVortex Automation
"""

import os
import sys
import subprocess
import socket
import argparse
from pathlib import Path

class ProxmoxBackupSetup:
    def __init__(self, install_cron=False, dry_run=False):
        self.install_cron = install_cron
        self.dry_run = dry_run
        self.hostname = socket.gethostname().lower()
        self.script_dir = Path(__file__).parent
        self.backup_script = self.script_dir / "BackupProxmoxBootDrive.py"
        
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
        
    def _run_command(self, command, check=True):
        """Run a shell command and return the result"""
        if self.dry_run:
            print(f"DRY RUN: {command}")
            return "DRY RUN"
            
        print(f"Running: {command}")
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
            print(f"Command failed: {command}")
            print(f"Error: {e.stderr}")
            if check:
                raise
            return None
            
    def _get_backup_config(self):
        """Get backup configuration for current host"""
        if self.hostname not in self.network_config:
            print(f"Error: Unknown hostname: {self.hostname}")
            print("Expected 'brain' or 'pinky'")
            sys.exit(1)
            
        return self.network_config[self.hostname]
        
    def setup_directories(self):
        """Create backup directories"""
        config = self._get_backup_config()
        backup_dest = config['backup_dest']
        target_server = config['target_server']
        
        print(f"Setting up backup directories for {self.hostname}")
        print(f"Backup destination: {backup_dest}")
        print(f"Target server: {target_server}")
        
        # Create backup directory
        self._run_command(f"mkdir -p {backup_dest}")
        
        # Set permissions
        self._run_command(f"chmod 755 {backup_dest}")
        
        # Create log directory
        self._run_command("mkdir -p /var/log/proxmox-backup")
        self._run_command("chmod 755 /var/log/proxmox-backup")
        
        print("Directories created successfully")
        
    def setup_cron(self):
        """Set up cron job for automated backups"""
        if not self.install_cron:
            print("Skipping cron setup (use --install-cron to enable)")
            return
            
        print("Setting up cron job for automated backups...")
        
        # Check if script exists
        if not self.backup_script.exists():
            print(f"Error: Backup script not found at {self.backup_script}")
            sys.exit(1)
            
        # Make script executable
        self._run_command(f"chmod +x {self.backup_script}")
        
        # Create cron entry
        cron_entry = f"0 2 * * * {self.backup_script}"
        
        # Check if cron entry already exists
        result = self._run_command("crontab -l", check=False)
        if result and cron_entry in result:
            print("Cron entry already exists")
            return
            
        # Add cron entry
        if result:
            # Append to existing crontab
            new_crontab = result + "\n" + cron_entry + "\n"
            self._run_command(f"echo '{new_crontab}' | crontab -")
        else:
            # Create new crontab
            self._run_command(f"echo '{cron_entry}' | crontab -")
            
        print("Cron job installed successfully")
        print(f"Backup will run daily at 2:00 AM")
        
    def verify_setup(self):
        """Verify the setup is working"""
        print("Verifying setup...")
        
        config = self._get_backup_config()
        backup_dest = config['backup_dest']
        
        # Check if backup directory exists
        if os.path.exists(backup_dest):
            print(f"✓ Backup directory exists: {backup_dest}")
        else:
            print(f"✗ Backup directory missing: {backup_dest}")
            
        # Check if script is executable
        if self.backup_script.exists() and os.access(self.backup_script, os.X_OK):
            print(f"✓ Backup script is executable: {self.backup_script}")
        else:
            print(f"✗ Backup script not found or not executable: {self.backup_script}")
            
        # Check NFS mount
        if os.path.exists(backup_dest):
            try:
                # Test write access
                test_file = os.path.join(backup_dest, '.write_test')
                with open(test_file, 'w') as f:
                    f.write('test')
                os.remove(test_file)
                print(f"✓ NFS mount is writable: {backup_dest}")
            except Exception as e:
                print(f"✗ NFS mount not writable: {e}")
        else:
            print(f"✗ NFS mount not accessible: {backup_dest}")
            
        # Check cron job
        if self.install_cron:
            result = self._run_command("crontab -l", check=False)
            if result and str(self.backup_script) in result:
                print("✓ Cron job is installed")
            else:
                print("✗ Cron job not found")
        else:
            print("ℹ Cron job not installed (use --install-cron to enable)")
            
    def run_setup(self):
        """Run the complete setup process"""
        print(f"Setting up Proxmox boot drive backup for {self.hostname}")
        print("=" * 50)
        
        # Setup directories
        self.setup_directories()
        print()
        
        # Setup cron if requested
        if self.install_cron:
            self.setup_cron()
            print()
            
        # Verify setup
        self.verify_setup()
        print()
        
        print("Setup completed!")
        print()
        print("Next steps:")
        print("1. Test the backup script manually:")
        print(f"   python3 {self.backup_script} --dry-run")
        print()
        print("2. Run a real backup:")
        print(f"   python3 {self.backup_script}")
        print()
        if not self.install_cron:
            print("3. Install cron job for automation:")
            print(f"   python3 {__file__} --install-cron")

def main():
    parser = argparse.ArgumentParser(description='Setup Proxmox boot drive backup system')
    parser.add_argument('--install-cron', action='store_true',
                       help='Install cron job for automated backups')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without executing')
    
    args = parser.parse_args()
    
    setup = ProxmoxBackupSetup(install_cron=args.install_cron, dry_run=args.dry_run)
    
    try:
        setup.run_setup()
    except KeyboardInterrupt:
        print("\nSetup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Setup failed with error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
