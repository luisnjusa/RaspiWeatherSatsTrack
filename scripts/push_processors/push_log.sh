#!/bin/bash
# Push a single log file to Discord after a pass completes

# 1. Import system settings and common functions
. "$HOME/.noaa-v2.conf"
. "$NOAA_HOME/scripts/common.sh"

# 2. Assign Webhook (passed from receive_meteor.sh)
WEBHOOK=$1
REAL_LOG="/var/log/raspberry-noaa-v2/output.log"

if [ -f "$REAL_LOG" ]; then
    log "Preparing final pass log for Discord..." "INFO"
    
    # Grab the last 30 lines
    tail -n 30 "$REAL_LOG" > /tmp/raspinoaa_log.txt
    
    # Send to Discord
    # We use -s (silent) to keep the terminal output clean
    curl -s -H "Content-Type: multipart/form-data" \
         -F file=@"/tmp/raspinoaa_log.txt" \
         -F "payload_json={\"content\":\"--- 🛰️ FINAL PASS LOG EXTRACT ---\"}" \
         "$WEBHOOK"
         
    rm /tmp/raspinoaa_log.txt
    log "Final log push complete." "INFO"
else
    log "Log file $REAL_LOG not found. Skipping Discord log push." "ERROR"
fi
