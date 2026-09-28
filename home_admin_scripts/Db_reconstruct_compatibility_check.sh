import sqlite3
import os
import re
from datetime import datetime

DB_PATH = "/home/admin/raspberry-noaa-v2/db/panel.db"
IMAGE_DIR = "/srv/images"

def parse_metadata(filename):
    match = re.search(r'(\d{8})-(\d{6})', filename)
    if match:
        dt_str = f"{match.group(1)}{match.group(2)}"
        try:
            dt_obj = datetime.strptime(dt_str, '%Y%m%d%H%M%S')
            return int(dt_obj.timestamp()), dt_obj.strftime('%Y-%m-%d %H:%M')
        except: pass
    return None, "Unknown"

def check_db_alignment():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Inspect the Table Schema (Columns and Types)
    print("--- 1. TABLE STRUCTURE ---")
    cursor.execute("PRAGMA table_info(decoded_passes)")
    columns = cursor.fetchall()
    for col in columns:
        print(f"Column: {col[1]} | Type: {col[2]}")

    # 2. Grab an existing record for comparison
    print("\n--- 2. EXISTING DATA EXAMPLE (FROM MARCH BACKUP) ---")
    cursor.execute("SELECT * FROM decoded_passes LIMIT 1")
    row = cursor.fetchone()
    if row:
        # Map values to column names for clarity
        col_names = [description[0] for description in cursor.description]
        for name, value in zip(col_names, row):
            print(f"{name}: {value} (Type: {type(value).__name__})")
    else:
        print("No existing records found to compare.")

    # 3. Preview of New Data to be inserted
    print("\n--- 3. PROPOSED DATA PREVIEW (FOR APRIL/MAY) ---")
    # Grab one file from your log example
    sample_file = "METEOR-M2-3-20260414-142832-321_corrected.jpg"
    ts, readable = parse_metadata(sample_file)
    is_noaa = 1 if "NOAA" in sample_file.upper() else 0
    sat_type = 1 if is_noaa else 2
    
    proposed_data = {
        "pass_start": ts,
        "file_path": sample_file,
        "daylight_pass": 1,
        "is_noaa": is_noaa,
        "sat_type": sat_type,
        "img_count": 1
    }
    
    for key, val in proposed_data.items():
        print(f"Target Column: {key} | Value: {val} (Type: {type(val).__name__})")

    conn.close()

if __name__ == "__main__":
    check_db_alignment()
