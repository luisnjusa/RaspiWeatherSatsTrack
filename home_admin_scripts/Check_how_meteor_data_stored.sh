import sqlite3
import os

DB_PATH = "/home/admin/raspberry-noaa-v2/db/panel.db"

def check_meteor_template():
    if not os.path.exists(DB_PATH):
        print("Database not found!")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("--- SEARCHING FOR EXISTING METEOR RECORD ---")
    # Query specifically for a file containing 'METEOR'
    cursor.execute("SELECT * FROM decoded_passes WHERE file_path LIKE '%METEOR%' LIMIT 1")
    row = cursor.fetchone()
    
    if row:
        col_names = [description[0] for description in cursor.description]
        print(f"Match found: {row[col_names.index('file_path')]}\n")
        for name, value in zip(col_names, row):
            print(f"{name}: {value} (Type: {type(value).__name__})")
    else:
        print("No Meteor records found in the March backup. This implies all Meteor data was lost.")
        print("We will proceed using the standard RaspiNOAA convention (sat_type: 2).")

    conn.close()

if __name__ == "__main__":
    check_meteor_template()
