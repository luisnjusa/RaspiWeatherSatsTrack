import os
import sqlite3
import sys
from datetime import datetime

# Configuration
DB_PATH = '/home/admin/raspberry-noaa-v2/db/panel.db'
THUMB_PATH = '/srv/images/thumb'
OUTPUT_SQL = 'full_reconstruction.sql'

def get_metadata_from_filename(filename):
    try:
        # Expected: METEOR-M2-3-20260502-141022-website-thumbnail.jpg
        base_path = filename.replace('-website-thumbnail.jpg', '')
        parts = base_path.split('-')
        
        # Satellite formatting: "METEOR-M2 3"
        sat_name = f"{parts[0]}-{parts[1]} {parts[2]}"
        
        # Parse the local time from filename to get the Epoch
        # Per your DB sample, 14:10:22 local matches 14:10:22 UTC epoch numbers
        dt = datetime.strptime(f"{parts[3]}{parts[4]}", "%Y%m%d%H%M%S")
        epoch_start = int(dt.timestamp())
        epoch_end = epoch_start + 900 # 15 minute duration per your sample
        
        # AM = Southbound, PM = Northbound
        direction = "Southbound" if dt.hour < 12 else "Northbound"
        
        return {
            "epoch_start": epoch_start,
            "epoch_end": epoch_end,
            "sat_name": sat_name,
            "direction": direction,
            "base_path": base_path
        }
    except (IndexError, ValueError):
        return None

def rebuild():
    print("--- Starting Final DB Reconstruction ---")
    
    if not os.path.exists(DB_PATH):
        print(f"ERROR: DB not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Scan for Meteor thumbnails
    thumb_files = sorted([f for f in os.listdir(THUMB_PATH) if f.startswith('METEOR') and f.endswith('-website-thumbnail.jpg')])
    
    sql_commands = []
    found_count = 0

    for thumb in thumb_files:
        meta = get_metadata_from_filename(thumb)
        if not meta: continue

        # Check if already present to prevent primary key errors
        cursor.execute("SELECT pass_start FROM predict_passes WHERE pass_start = ?", (meta['epoch_start'],))
        if not cursor.fetchone():
            # 1. predict_passes mapping
            pred_sql = (f"INSERT INTO predict_passes (sat_name, pass_start, pass_end, max_elev, is_active, direction, at_job_id) "
                        f"VALUES ('{meta['sat_name']}', {meta['epoch_start']}, {meta['epoch_end']}, 90, 1, '{meta['direction']}', 0);")
            
            # 2. decoded_passes mapping
            deco_sql = (f"INSERT INTO decoded_passes (pass_start, file_path, daylight_pass, is_noaa, sat_type, "
                        f"has_spectrogram, has_pristine, gain, has_polar_az_el, has_polar_direction, has_histogram) "
                        f"VALUES ({meta['epoch_start']}, '{meta['base_path']}', 1, 0, 0, 0, 0, 44.5, 0, 0, 0);")
            
            sql_commands.append(pred_sql)
            sql_commands.append(deco_sql)
            found_count += 1
            sys.stdout.write(f"\r[+] Queuing: {meta['base_path']} ({meta['direction']})")
            sys.stdout.flush()

    with open(OUTPUT_SQL, 'w') as f:
        f.write("-- RaspiNOAA V2 Full Reconstruction - Final Schema Match\n")
        f.write("BEGIN TRANSACTION;\n")
        for cmd in sql_commands:
            f.write(cmd + "\n")
        f.write("COMMIT;\n")

    conn.close()
    print(f"\n\n[*] Success! Found {found_count} missing captures.")
    print(f"[*] To apply changes: sqlite3 {DB_PATH} < {OUTPUT_SQL}")

if __name__ == "__main__":
    rebuild()