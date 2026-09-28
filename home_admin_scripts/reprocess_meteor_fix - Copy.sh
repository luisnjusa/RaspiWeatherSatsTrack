#!/bin/bash

# --- CONFIGURATION ---
INPUT_WAV="/srv/audio/meteor/meteor_m2_4_20260503_191209.wav"
OUTPUT_DIR="/srv/images/test"
SAT_TYPE="meteor_m2-x_lrpt"
# MANUALLY DEFINING THE TLE FOR THIS TEST
TLE_FILE="/home/admin/raspberry-noaa-v2/tmp/orbit.tle"

# --- ENVIRONMENT ---
if [ -f "$HOME/.noaa-v2.conf" ]; then
    . "$HOME/.noaa-v2.conf"
    . "$NOAA_HOME/scripts/common.sh"
else
    echo "Error: .noaa-v2.conf not found."
    exit 1
fi

# MANUALLY DEFINING THE CORRECT 19:12:09 UTC TIMESTAMP
PASS_TIMESTAMP="1777835529"

# Match the samplerate for your RTL-SDR
SAMPLERATE="1.024e6"

# --- STEP 0: CLEANUP ---
echo "Cleaning up $OUTPUT_DIR..."
# Removes all files and subdirectories inside the test folder safely
rm -rf "${OUTPUT_DIR:?}"/*; 
echo "Reprocessing baseband: $INPUT_WAV"
echo "Using coordinates: Lat $LAT, Lon $LON"
echo "Using TLE: $TLE_FILE"
echo "Using timestamp: $PASS_TIMESTAMP"

# --- THE FIX: ADDING TLE AND COORDINATES ---
$SATDUMP $SAT_TYPE baseband "$INPUT_WAV" "$OUTPUT_DIR" \
    --samplerate $SAMPLERATE \
    --baseband_format w16 \
    --latitude "$LAT" \
    --longitude "$LON" \
    --altitude "${ALT:-0}" \
    --tle "$TLE_FILE" \
    --start_timestamp "$PASS_TIMESTAMP" \
    --fill_missing \
    --finish_processing
    
    #--timestamp "$PASS_TIMESTAMP" \
    
    #--projection_type mercator \

echo "Done. Check $OUTPUT_DIR for the corrected composites."
