#!/bin/bash

# 1. Import configuration
. "$HOME/.noaa-v2.conf"
. "$NOAA_HOME/scripts/common.sh"

# 2. Setup Variables
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUT_FILE="/srv/audio/meteor/test_record_${TIMESTAMP}"

# Hardware and Radio Parameters (Simulated for M2-4)
receiver="rtlsdr"
samplerate="1.024e6"
METEOR_FREQUENCY="137.9000"  # MHz
#METEOR_FREQUENCY="162.4750"  # MHz
DURATION=15

# --- DYNAMIC VARIABLE LOGIC (MIRRORED FROM RECEIVE_METEOR.SH) ---

# Set Gain and PPM flags based on receiver type
if [[ "$receiver" == "rtlsdr" ]]; then
    gain_option="--gain"
    ppm_correction="--ppm_correction"
    # Use your M2-4 specific gain from .conf
    GAIN=$METEOR_M2_4_GAIN
    # For RTL-SDR, your script uses the offset variable here
    FREQ_OFFSET_VAL=$METEOR_M2_4_FREQ_OFFSET 
else
    gain_option="--general_gain"
    FREQ_OFFSET_VAL=""
fi

# Determine if we use the Device ID string
if [[ "$USE_DEVICE_STRING" == "true" ]]; then
    sdr_id_option="--source_id"
    SDR_DEVICE_ID=$METEOR_M2_4_SDR_DEVICE_ID
else
    sdr_id_option=""
    SDR_DEVICE_ID=""
fi
#sdr_id_option="--source_id"
#SDR_DEVICE_ID="11"

# Bias-T logic based on .conf
if [ "$METEOR_M2_4_ENABLE_BIAS_TEE" == "-T" ]; then
    bias_tee_option="--bias"
else
    bias_tee_option=""
fi

log "Silencing secondary SDRs (Stopping OpenWebRX)..." "INFO"
#sudo systemctl stop openwebrx

# Standardize PPM value
ppm_value="0"

log "Starting Aligned Test: Freq=${METEOR_FREQUENCY}MHz, Gain=$GAIN, Device=$SDR_DEVICE_ID" "INFO"

# 3. Execute Aligned SatDump record command
# Follows the exact parameter order and structure of your production script
satdump record "${OUT_FILE}" \
    --source $receiver \
    --samplerate $samplerate \
    $ppm_correction $ppm_value $FREQ_OFFSET_VAL \
    --frequency "${METEOR_FREQUENCY}e6" \
    $sdr_id_option "$SDR_DEVICE_ID" \
    $gain_option "$GAIN" \
    $bias_tee_option \
    --baseband_format w16 \
    --timeout "$DURATION" >> $NOAA_LOG 2>&1
	
log "Meteor capture finished. Restoring OpenWebRX..." "INFO"
#sudo systemctl start openwebrx

# 4. Check results
if [ -f "${OUT_FILE}.wav" ]; then
    FILE_SIZE=$(du -h "${OUT_FILE}.wav" | cut -f1)
    log "Capture complete! File saved: ${OUT_FILE}.wav (Size: ${FILE_SIZE})" "INFO"
else
    log "Capture failed. Check $NOAA_LOG for the error." "ERROR"
fi
