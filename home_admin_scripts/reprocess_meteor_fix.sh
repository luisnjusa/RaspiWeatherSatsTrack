#!/bin/bash

# ==============================================================================
# Script: reprocess_meteor_fix.sh
# Purpose: Fully automated Meteor re-decoding with Hard-Link Map Fix,
#          180-degree Rotation, and Official Station Annotation.
# ==============================================================================

# --- 1. CONFIGURATION ---
INPUT_WAV="/srv/test/METEOR-M2-4-20260506-194734.wav"
OUTPUT_DIR="/srv/images/test"
TLE_FILE="/home/admin/raspberry-noaa-v2/tmp/orbit.tle"

# --- 2. THE MAP NUDGE (Adjust to align coastlines) ---
# If lines are too far East (right), use a negative number (e.g., -5).
# If lines are too far West (left), use a positive number (e.g., 5).
TIME_NUDGE=-5 

# --- 3. ENVIRONMENT ---
if [ -f "$HOME/.noaa-v2.conf" ]; then
    . "$HOME/.noaa-v2.conf"
    . "$NOAA_HOME/scripts/common.sh"
else
    echo "Error: .noaa-v2.conf not found."
    exit 1
fi

# --- 4. AUTOMATED METADATA EXTRACTION ---
FILE_NAME=$(basename "$INPUT_WAV")
DT_PART=$(echo "$FILE_NAME" | grep -oE '[0-9]{8}-[0-9]{6}')
D_STR=$(echo "$DT_PART" | cut -d'-' -f1)
T_STR=$(echo "$DT_PART" | cut -d'-' -f2)
BASE_EPOCH=$(date -u -d "${D_STR:0:4}-${D_STR:4:2}-${D_STR:6:2} ${T_STR:0:2}:${T_STR:2:2}:${T_STR:4:2}" +%s)

# Extract Satellite Digit (3 or 4)
SAT_NUM_DIGIT=$(echo "$FILE_NAME" | grep -oE 'M2-[0-9]' | cut -d'-' -f2)
export SAT_NAME="METEOR-M2 ${SAT_NUM_DIGIT}"

# --- 5. THE NUDGE & HARD LINK FIX ---
export EPOCH_START=$((BASE_EPOCH + TIME_NUDGE))
NUDGED_ISO=$(date -u -d "@$EPOCH_START" "+%Y%m%d_%H%M%S")

# Creating a Hard Link in /tmp so SatDump cannot resolve back to the old name
FORCED_WAV="/tmp/meteor_m2_${SAT_NUM_DIGIT}_${NUDGED_ISO}_utc.wav"
ln -f "$INPUT_WAV" "$FORCED_WAV"

# --- 6. EXPORT ANNOTATION METADATA ---
export PASS_DIRECTION="Southbound"
#export PASS_DIRECTION="Northbound"
export SAT_MAX_ELEVATION="47"
export CAPTURE_TIME="890"
export PASS_SIDE="W"
export START_DATE=$(date -u -d "@$EPOCH_START" "+%Y-%m-%d %H:%M:%S")
export FILENAME_BASE="TEST_NUDGE_${TIME_NUDGE}"
export SUN_ELEV=$(python3 "$NOAA_HOME/scripts/tools/sun.py" "$EPOCH_START")

gain_var="METEOR_${SAT_NUM_DIGIT}_GAIN"
export GAIN="${!gain_var}"

# --- 7. DYNAMIC MODE DETECTION ---
interleaving_var="METEOR_${SAT_NUM_DIGIT}_80K_INTERLEAVING"
mode="$([[ "${!interleaving_var}" == "true" ]] && echo "_80k" || echo "")"
SAT_TYPE="meteor_m2-x_lrpt${mode}"

# --- 8. EXECUTION ---
echo "Cleaning up $OUTPUT_DIR..."
rm -rf "${OUTPUT_DIR:?}"/*; 

echo "-------------------------------------------------------"
echo "Processing: $SAT_NAME (Mode: ${mode:-72k})"
echo "File Used:  $(basename $FORCED_WAV)"
echo "Epoch:      $EPOCH_START (Nudge: $TIME_NUDGE s)"
echo "Gain:       $GAIN"
echo "-------------------------------------------------------"

$SATDUMP "$SAT_TYPE" baseband "$FORCED_WAV" "$OUTPUT_DIR" \
    --samplerate 1.024e6 \
    --baseband_format w16 \
    --latitude "$LAT" --longitude "$LON" \
    --tle "$TLE_FILE" \
    --start_timestamp "$EPOCH_START" \
	--map_overlays --draw_cities --draw_shores_overlay \
    --no_settings --fill_missing --finish_processing

# --- 9. STEP 2: ROTATE & OFFICIAL ANNOTATION ---
echo "Applying Rotation and Official Annotation..."
cd "$OUTPUT_DIR/MSU-MR (Filled)" || exit

for i in *.png; do
    #if [[ "$i" == *"map"* ]]; then continue; fi
    if [[ "$i" == *"projected"* ]]; then continue; fi

    # A. Rotate 180 degrees ONLY if Southbound
    if [ "$PASS_DIRECTION" == "Southbound" ]; then
        echo "Rotating $i 180 degrees..."
        mogrify -rotate 180 "$i"
    fi

    # B. Official Annotation using station script
    log "Annotating $i using official script..." "INFO"
    ${IMAGE_PROC_DIR}/meteor_normalize_annotate.sh \
        "./$i" \
        "${OUTPUT_DIR}/${FILENAME_BASE}-${i%.png}.jpg" \
        "$METEOR_IMAGE_QUALITY"
done

# Cleanup the Hard Link
rm "$FORCED_WAV"

echo "-------------------------------------------------------"
echo "Reprocessing Complete. Final JPGs in $OUTPUT_DIR"
echo "-------------------------------------------------------"
