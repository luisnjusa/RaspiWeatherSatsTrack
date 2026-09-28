#!/bin/bash
# Cleaned up Discord Push Script for Raspi-NOAA-v2

# 1. Import system settings and common functions
. "$HOME/.noaa-v2.conf"
. "$NOAA_HOME/scripts/common.sh"

# 2. Assign inputs and handle the argument shift
# receive_meteor.sh sends: $1=URL $2=Image $3=Message
if [[ $1 == http* ]]; then
    WEBHOOK=$1
    IMAGE=$2
    MESSAGE=$3
else
    # Manual test mode: $1=Message $2=Image
    MESSAGE=$1
    IMAGE=$2
    if [[ $IMAGE == *"METEOR"* ]]; then
        WEBHOOK=$DISCORD_METEOR_WEBHOOK
    else
        WEBHOOK=$DISCORD_NOAA_WEBHOOK
    fi
fi

# 3. Check that the image exists and the webhook is not empty
if [ -f "${IMAGE}" ] && [ ! -z "$WEBHOOK" ]; then 
  log "Sending $IMAGE to Discord" "INFO"
  
  # Use curl to upload. Note the ** around $MESSAGE to make it BOLD in Discord
  push_log=$(curl -s -H "Content-Type: multipart/form-data" \
             -F file=@"$IMAGE" \
             -F "payload_json={\"content\":\"**$MESSAGE**\"}" \
             "$WEBHOOK" 2>&1)
  log "${push_log}" "INFO"
else
  log "Skipping Discord push: Image not found or Webhook URL empty" "ERROR"
fi
 
# 5. Push the last 10 lines of the log to Discord as a file
#REAL_LOG="/var/log/raspberry-noaa-v2/output.log"

#if [ -f "$REAL_LOG" ]; then
#    # Create a small temp file for the log extract
#    tail -n 10 "$REAL_LOG" > /tmp/raspinoaa_log.txt
#    
#    # Send the log file as a second upload
#    curl -s -H "Content-Type: multipart/form-data" \
#         -F file=@"/tmp/raspinoaa_log.txt" \
#         -F "payload_json={\"content\":\"--- 🛰️ SYSTEM LOG EXTRACT ---\"}" \
#         "$WEBHOOK"
#         
    # Clean up the temp file
#    rm /tmp/raspinoaa_log.txt
#else
#    log "Log file $REAL_LOG not found" "ERROR"
#fi

