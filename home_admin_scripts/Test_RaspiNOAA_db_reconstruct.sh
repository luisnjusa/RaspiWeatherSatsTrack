import os
import sqlite3
import re
import time
from datetime import datetime

# Paths
IMAGE_DIR = "/srv/images"
DB_PATH = "/home/admin/raspberry-noaa-v2/db/panel.db"
LOG_FILE = "/home/admin/reconstruct_scan.log"

def parse_metadata(filename):
    match = re.search(r'(\d{8})-(\d{6})', filename)
    if match:
        dt_str = f"{match.group(1)}{match.group(2)}"
        try:
            dt_obj = datetime.strptime(dt_str, '%Y%m%d%H%M%S')
            return int(dt_obj.timestamp()), dt_obj.strftime('%Y-%m-%d %H:%M')
        except: pass
    return None, "Unknown"

def cautious_sync():
    print("Starting Cautious Scan (Batch of 100)...")
    
    files = os.listdir(IMAGE_DIR)
    new_found = 0
    processed = 0

    for img_file in files:
        # stop after 100 to prevent system exhaustion
        if new_found >= 100: 
            print("\nReached batch limit (100). Stopping to keep system stable.")
            break
            
        if not img_file.lower().endswith(('.jpg', '.png')):
            continue

        processed += 1
        # Short sleep to let OpenWebRX and Xorg breathe
        time.sleep(0.1) 

        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM decoded_passes WHERE file_path = ?", (img_file,))
            missing = cursor.fetchone() is None
            conn.close()

            if missing:
                ts, dt_readable = parse_metadata(img_file)
                with open(LOG_FILE, "a") as f:
                    f.write(f"FOUND: {img_file} | {dt_readable}\n")
                print(f"[{new_found+1}] Detected: {img_file[:30]}...", end='\r')
                new_found += 1
                
        except Exception as e:
            print(f"\nError: {e}")

    print(f"\nScan finished. Found {new_found} new entries in this batch.")

if __name__ == "__main__":
    cautious_sync()
