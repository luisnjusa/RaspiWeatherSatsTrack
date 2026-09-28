import os
import sqlite3
import sys
from datetime import datetime

# Configuration
DB_PATH = '/home/admin/raspberry-noaa-v2/db/panel.db'
IMAGES_PATH = '/srv/images'
OUTPUT_SQL = 'cleanup_orphans.sql'

def simulate_cleanup():
    print("--- RaspiNOAA V2 Orphan Cleanup Tool ---")
    
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get all records to check against disk
    # We need the ID to delete and the file_path to verify existence
    cursor.execute("SELECT id, file_path, pass_start FROM decoded_passes")
    all_entries = cursor.fetchall()
    total_records = len(all_entries)
    
    print(f"[*] Checking {total_records} database entries against disk...")

    sql_commands = []
    orphan_count = 0

    for i, (db_id, file_path, pass_start) in enumerate(all_entries, 1):
        # Update progress
        sys.stdout.write(f"\r[ ] Scanning {i}/{total_records}...")
        sys.stdout.flush()

        # Check for the base image file. 
        # Most entries use a .jpg extension for the primary reference.
        full_image_path = os.path.join(IMAGES_PATH, f"{file_path}-MSA_projected.jpg")
        
        # If the file doesn't exist, it's an orphan
        if not os.path.exists(full_image_path):
            # Also check if just a raw .jpg exists in case naming varies
            if not os.path.exists(os.path.join(IMAGES_PATH, f"{file_path}.jpg")):
                sys.stdout.write(f"\n    [!] ORPHAN FOUND: ID {db_id} ({file_path})\n")
                
                # Delete from both tables to keep the DB clean
                sql_commands.append(f"DELETE FROM decoded_passes WHERE id = {db_id};")
                sql_commands.append(f"DELETE FROM predict_passes WHERE pass_start = {pass_start};")
                orphan_count += 1

    print(f"\n\n[*] Cleanup analysis complete.")
    print(f"[*] Found {orphan_count} orphaned records.")

    if orphan_count > 0:
        with open(OUTPUT_SQL, 'w') as f:
            f.write("-- RaspiNOAA V2 Cleanup Script\n")
            f.write(f"-- Generated on: {datetime.now()}\n\n")
            f.write("BEGIN TRANSACTION;\n")
            for cmd in sql_commands:
                f.write(cmd + "\n")
            f.write("COMMIT;\n")
        print(f"[*] Cleanup SQL created: {OUTPUT_SQL}")
        print(f"[!] Review the file, then apply with: sqlite3 {DB_PATH} < {OUTPUT_SQL}")
    else:
        print("[*] No orphaned records found. Your database is healthy!")

    conn.close()

if __name__ == "__main__":
    simulate_cleanup()