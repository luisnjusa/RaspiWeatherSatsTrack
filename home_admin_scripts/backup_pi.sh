#!/bin/bash

# Ensure the script is run as root to access system directories
if [ "$EUID" -ne 0 ]; then
  echo "❌ Please run this script with sudo."
  exit 1
fi

# --- CONFIGURATION ---
BACKUP_DIR="/home/admin/backups"
DATE=$(date +%Y%m%d_%H%M%S)
ARCHIVE_NAME="raspinoaa_backup_$DATE.tar.gz"
TEMP_DIR="/tmp/pi_backup_stage"

echo "🚀 Starting Raspberry Pi component backup process..."

# 1. Create clean working directories
mkdir -p "$BACKUP_DIR"
mkdir -p "$TEMP_DIR"

# --- STEP 1: Backup /home/admin scripts and python files ---
echo "📦 Staging /home/admin scripts and python files..."
mkdir -p "$TEMP_DIR/home_admin_scripts"
# Find and copy all .sh and .py files in /home/admin (excluding the backup dir itself)
find /home/admin -maxdepth 1 -type f \( -name "*.sh" -o -name "*.py" \) -exec cp {} "$TEMP_DIR/home_admin_scripts/" \;

# --- STEP 2: Backup raspberry-noaa-v2 ---
if [ -d "/home/admin/raspberry-noaa-v2" ]; then
    echo "📦 Staging raspberry-noaa-v2..."
    cp -r /home/admin/raspberry-noaa-v2 "$TEMP_DIR/"
else
    echo "⚠️ Warning: /home/admin/raspberry-noaa-v2 not found."
fi

# --- STEP 3: Backup Satdump configuration ---
if [ -d "/usr/share/satdump" ]; then
    echo "📦 Staging SatDump configurations..."
    cp -r /usr/share/satdump "$TEMP_DIR/satdump_usr_share"
else
    echo "⚠️ Warning: /usr/share/satdump not found."
fi

# --- STEP 4: Backup install_and_upgrade fix components ---
# Common locations modified by the installer fixes (like udev rules or systemd services)
echo "📦 Staging common install_and_upgrade fix components..."
mkdir -p "$TEMP_DIR/system_fixes"

# Backup udev rules if they exist (common for RTL-SDR / HackRF fixes)
if [ -d "/etc/udev/rules.d" ]; then
    mkdir -p "$TEMP_DIR/system_fixes/udev"
    cp /etc/udev/rules.d/*noaa* "$TEMP_DIR/system_fixes/udev/" 2>/dev/null || true
    cp /etc/udev/rules.d/*rtl* "$TEMP_DIR/system_fixes/udev/" 2>/dev/null || true
    cp /etc/udev/rules.d/*satdump* "$TEMP_DIR/system_fixes/udev/" 2>/dev/null || true
fi

# Backup custom systemd service files if they exist
if [ -d "/etc/systemd/system" ]; then
    mkdir -p "$TEMP_DIR/system_fixes/systemd"
    cp /etc/systemd/system/noaa* "$TEMP_DIR/system_fixes/systemd/" 2>/dev/null || true
    cp /etc/systemd/system/satdump* "$TEMP_DIR/system_fixes/systemd/" 2>/dev/null || true
fi

# --- STEP 5: Compress and Cleanup ---
echo "🗜️ Creating final compressed archive..."
tar -czf "$BACKUP_DIR/$ARCHIVE_NAME" -C "$TEMP_DIR" .

# Adjust permissions so the 'admin' user owns the final backup file
clear_admin_uid=$(id -u admin 2>/dev/null || echo 1000)
clear_admin_gid=$(id -g admin 2>/dev/null || echo 1000)
chown -R $clear_admin_uid:$clear_admin_gid "$BACKUP_DIR"

# Clean up staging area
rm -rf "$TEMP_DIR"

echo "------------------------------------------------"
echo "✅ Backup successfully created!"
echo "📁 Location: $BACKUP_DIR/$ARCHIVE_NAME"
echo "------------------------------------------------"
