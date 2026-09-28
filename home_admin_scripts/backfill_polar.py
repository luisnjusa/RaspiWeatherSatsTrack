import sqlite3
import subprocess
import os
import urllib.request

# Configuration
DB_PATH = '/home/admin/raspberry-noaa-v2/db/panel.db'
SCRIPTS_DIR = '/home/admin/raspberry-noaa-v2/scripts/image_processors'
TEMP_TLE = '/tmp/standard_format.tle'
IMAGE_DIR = '/srv/images'
THUMB_DIR = '/srv/images/thumb'
LAT, LON = "40.02", "-74.80"

# NORAD IDs for Meteor satellites
SAT_MAPPING = {
    "METEOR-M2 3": "57166",
    "METEOR-M2 4": "59051",
    "METEOR-M2-3": "57166",
    "METEOR-M2-4": "59051"
}

def get_live_tle(norad_id):
    """Fetches a perfectly formatted 3-line TLE from CelesTrak"""
    url = f"https://celestrak.org/NORAD/elements/gp.php?CATNR={norad_id}&FORMAT=TLE"
    try:
        with urllib.request.urlopen(url) as response:
            data = response.read().decode('utf-8').splitlines()
            if len(data) >= 3:
                # Ensure we have the Name, Line 1, and Line 2
                tle_formatted = f"{data[0].strip()}\n{data[1]}\n{data[2]}\n"
                with open(TEMP_TLE, 'w') as f:
                    f.write(tle_formatted)
                return data[0].strip()
    except Exception as e:
        print(f"      [!] TLE Download failed: {e}")
    return None

def run_fix():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    query = "SELECT d.pass_start, p.sat_name, p.direction, d.file_path FROM decoded_passes d JOIN predict_passes p ON d.pass_start = p.pass_start WHERE d.pass_start >= 1777816037"
    cursor.execute(query)
    passes = cursor.fetchall()

    print(f"[*] Starting reconstruction for {len(passes)} passes...")

    for start_time, sat_name, direction, file_path in passes:
        azel_path = f"{IMAGE_DIR}/{file_path}-polar-azel.jpg"
        dir_path = f"{IMAGE_DIR}/{file_path}-polar-direction.png"
        
        if os.path.exists(azel_path):
            continue

        norad_id = SAT_MAPPING.get(sat_name)
        if not norad_id:
            continue

        print(f"[!] Processing {file_path}...")
        tle_name = get_live_tle(norad_id)
        
        if tle_name:
            end_time = start_time + 900
            # Run Az/El
            subprocess.run(["python3", f"{SCRIPTS_DIR}/polar_plot.py", tle_name, TEMP_TLE, str(start_time), str(end_time), LAT, LON, "10", direction, azel_path, "azel"])
            # Run Direction
            subprocess.run(["python3", f"{SCRIPTS_DIR}/polar_plot.py", tle_name, TEMP_TLE, str(start_time), str(end_time), LAT, LON, "10", direction, dir_path, "direction"])
            # Thumbnails
            subprocess.run([f"{SCRIPTS_DIR}/thumbnail.sh", "300", azel_path, f"{THUMB_DIR}/{file_path}-polar-azel.jpg"])
            subprocess.run([f"{SCRIPTS_DIR}/thumbnail.sh", "300", dir_path, f"{THUMB_DIR}/{file_path}-polar-direction.png"])
        else:
            print(f"    [FAIL] Could not get TLE for {sat_name}")

    conn.close()

if __name__ == "__main__":
    run_fix()
