#!/bin/bash
set -e

CONFIG_FILE="/home/admin/.noaa-v2.conf"
SATDUMP_CFG="/usr/share/satdump/satdump_cfg.json"

if [ -f "$CONFIG_FILE" ] && [ -f "$SATDUMP_CFG" ]; then
    LAT=$(grep -E '^LAT=' "$CONFIG_FILE" | cut -d'=' -f2 | tr -d '"' | tr -d "'")
    LON=$(grep -E '^LON=' "$CONFIG_FILE" | cut -d'=' -f2 | tr -d '"' | tr -d "'")

    if [ -n "$LAT" ] && [ -n "$LON" ]; then
        sed -i -E "s/\"lat0\": [-0-9.]+/\"lat0\": $LAT/g" "$SATDUMP_CFG"
        sed -i -E "s/\"lon0\": [-0-9.]+/\"lon0\": $LON/g" "$SATDUMP_CFG"
    fi
fi
