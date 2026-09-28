# File: station_bot.py | Version: 2026-06-10 01:52pm EDT
import asyncio
import re # Add this to your imports at the top of the file
import sqlite3
import sys
import os
import glob
import argparse

# Ensure the bot uses the virtual environment where libraries are installed
venv_site_packages = '/home/admin/bot_env/lib/python3.11/site-packages'
if venv_site_packages not in sys.path:
    sys.path.append(venv_site_packages)

import discord
from discord.ext import commands, tasks 
import subprocess
import time
import csv
import requests 
import json
import base64
import io
from datetime import datetime, time as clock_time, timezone, timedelta

# --- BLOGGER & IMAGE IMPORTS ---
try:
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from PIL import Image
    BLOGGER_ENABLED = True
except ImportError:
    BLOGGER_ENABLED = False

LOG_FILE = "/home/admin/station_weather_log.csv"

# --- CONFIGURATION ---
TOKEN = 'MTQ4MjU2NTAwODI2NDEzODc4Mg.GQYR5L.vnNlRJXpGThOUJGBtSJYePaYowCx5aNm6vChdo'
AUTHORIZED_USER_ID = 794776141059719168 
G_CHANNEL_ID = 1480692274760388764 # general
CHANNEL_ID = 1483239063656988814 # weather_reports
ALERTS_CHANNEL_ID = 1514502390902952066 # NWS alerts
BLOG_ID = '191709493093871402'
SCOPES = ['https://www.googleapis.com/auth/blogger']
TOKEN_PATH = '/home/admin/token.json'

# Station Coordinates
LAT = 40.02
LON = -74.80

WEATHER_ICONS = {
    0: "☀️ Clear", 1: "🌤️ Mostly Clear", 2: "⛅ Partly Cloudy", 3: "☁️ Overcast",
    45: "🌫️ Fog", 48: "🌫️ Freezing Fog", 51: "🌦️ Light Drizzle", 61: "🌧️ Light Rain",
    63: "🌧️ Rain", 71: "🌨️ Light Snow", 95: "⛈️ Thunderstorm"
}
# Add under WEATHER_ICONS
ACTIVE_ALERTS = set()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)
bot.remove_command('help') 

# --- UTILITIES ---

def get_nws_alerts(force_all=False):
    """Fetches active weather alerts from NWS and converts temperatures to metric."""
    url = f"https://api.weather.gov/alerts/active?point={LAT},{LON}"
    headers = {"User-Agent": "StationBot/1.0 (discord_weather_bot)"}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if "features" not in data or not data["features"]:
            return [], []

        new_alerts = []
        current_alert_ids = set()

        for feature in data["features"]:
            props = feature["properties"]
            alert_id = props.get("id")
            current_alert_ids.add(alert_id)

            if alert_id not in ACTIVE_ALERTS or force_all:
                event = props.get("event", "Unknown Alert")
                severity = props.get("severity", "Unknown")
                headline = props.get("headline", "No details provided.")
                desc = props.get("description", "")
                
                # Convert any NWS Fahrenheit text to Metric (Celsius)
                def f_to_c(match):
                    f_temp = float(match.group(1))
                    c_temp = (f_temp - 32) * 5/9
                    return f"{c_temp:.1f}°C ({f_temp:.1f}°F)"
                
                # Regex to catch "32 degrees", "32 F", "32 degrees Fahrenheit"
                desc = re.sub(r'(-?\d{1,3})\s*(?:degrees? Fahrenheit|degrees? F|degrees?|F\b)', f_to_c, desc, flags=re.IGNORECASE)
                
                # Truncate to stay safely under Discord's 2000 character limit
                desc = desc[:1000] + ("...\n[Message truncated]" if len(desc) > 1000 else "")

                msg = (
                    f"🚨 **WEATHER ALERT: {event}** 🚨\n"
                    f"**Severity:** {severity}\n"
                    f"**Headline:** {headline}\n\n"
                    f"**Details:** {desc}\n"
                )
                new_alerts.append((alert_id, msg))
        
        return new_alerts, list(current_alert_ids)
    except Exception as e:
        print(f"NWS API Error: {e}")
        return [], []

def get_upcoming_pass_info():
    """Queries the local Raspi-NOAA database for the next TWO scheduled passes with E/W side calculation."""
    db_path = '/home/admin/raspberry-noaa-v2/db/panel.db'
    try:
        if not os.path.exists(db_path): return ""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # We query azimuth_at_max to determine if the pass is East (<180) or West (>180)
        query = """
            SELECT sat_name, pass_start, max_elev, azimuth_at_max 
            FROM predict_passes 
            WHERE pass_start > strftime('%s', 'now') 
            ORDER BY pass_start ASC 
            LIMIT 2
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()

        if rows:
            pass_strings = []
            for row in rows:
                sat, start_val, elev, az_max = row
                
                # Logic: Azimuth < 180 is East, Azimuth >= 180 is West
                side = "E" if az_max < 180 else "W"
                
                try:
                    # Convert Unix Epoch to UTC object
                    dt_utc = datetime.fromtimestamp(int(start_val), tz=timezone.utc)
                    
                    # Convert to EDT (UTC-4)
                    edt_offset = timezone(timedelta(hours=-4))
                    dt_edt = dt_utc.astimezone(edt_offset)
                    
                    local_str = dt_edt.strftime('%b %d at %H:%M EDT')
                    utc_str = dt_utc.strftime('%H:%M UTC')
                    
                    # Format with the calculated side (e.g., 81° E)
                    pass_strings.append(f"{sat}: {local_str} ({utc_str}) | Elev: {elev}° {side}")
                except Exception as e:
                    pass_strings.append(f"{sat}: {start_val} ({side})")
            
            return " <br> ".join(pass_strings)
            
        return "No further passes currently scheduled."
    except Exception as e:
        print(f"Database read error: {e}")
        return ""

def get_blogger_service():
    """Authenticates and returns the Blogger service object."""
    if not BLOGGER_ENABLED or not os.path.exists(TOKEN_PATH):
        return None
    try:
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(TOKEN_PATH, 'w') as token_file:
                    token_file.write(creds.to_json())
            except:
                return None
        if not creds or not creds.valid:
            return None
        return build('blogger', 'v3', credentials=creds, static_discovery=False)
    except:
        return None

def resize_image_for_blogger(image_path, max_kb=800):
    """Resizes large satellite images to fit Blogger API limits."""
    try:
        with Image.open(image_path) as img:
            if img.mode in ("RGBA", "P"): img = img.convert("RGB")
            quality = 80
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=quality)
            while img_byte_arr.tell() > max_kb * 1024 and img.width > 400:
                img = img.resize((int(img.width * 0.80), int(img.height * 0.80)), Image.Resampling.LANCZOS)
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='JPEG', quality=quality)
            return img_byte_arr.getvalue()
    except Exception as e:
        print(f"Resize failed: {e}")
        with open(image_path, "rb") as f: return f.read()

def post_to_blogger(title, content, image_path=None, sat_name=None):
    """
    Consolidated function to post to Blogger.
    Handles single images, bundles (via HTML content), and station telemetry.
    """
    service = get_blogger_service()
    if not service:
        return "⚠️ Blogger Auth Failed (Check token.json)"
        
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        # Wrapper for consistent styling across all post types
        html_body = '<div style="font-family: sans-serif; max-width: 900px; margin: auto; color: #333;">'
        
        # --- CASE 1: SINGLE IMAGE POST (Standard /postblog or CLI) ---
        if image_path and os.path.exists(image_path):
            img_bytes = resize_image_for_blogger(image_path)
            img_b64 = base64.b64encode(img_bytes).decode('utf-8')
            image_data_url = f"data:image/jpeg;base64,{img_b64}"
            img_filename = os.path.basename(image_path)
            
            html_body += (f'<h2 style="text-align: center; color: #2c3e50;">{sat_name} Capture</h2>'
                         f'<p style="text-align: center; color: #7f8c8d;">{now_str}</p>'
                         f''  # Blogger Jump Break (Separator)
                         f'<div style="text-align: center; margin-top: 20px; margin-bottom: 25px;">'
                         f'<a href="{image_data_url}"><img src="{image_data_url}" style="max-width: 100%; border-radius: 12px; border: 1px solid #444; box-shadow: 0 4px 15px rgba(0,0,0,0.2);" /></a>'
                         f'<p style="margin-top: 10px; font-size: 0.9em; color: #555; font-family: monospace;">{img_filename}</p>'
                         f'</div>')
            
            if content and sat_name:
                html_body += f'<p style="text-align: center; color: #7f8c8d; margin-bottom: 30px;"><b>Station:</b> Westampton, NJ</p>'

        # --- CASE 2: BUNDLED POST (Multi-image from receive_meteor.sh) ---
        elif content and "data:image" in content:
            # When bundling, the images are already in the 'content' as HTML
            html_body += (f'<h2 style="text-align: center; color: #2c3e50;">{sat_name}</h2>'
                         f'<p style="text-align: center; color: #7f8c8d;">{now_str}</p>'
                         f''  # Blogger Jump Break
                         f'{content}')
            # We "empty" content here so the telemetry section below uses fresh data
            content = get_weather_report() 

        # --- TELEMETRY SECTION (Applied to all posts if content exists) ---
        if content:
            # Clean up Discord markdown if present
            clean_telemetry = content.replace("**", "")
            html_body += (
                f'<div style="background-color: #1e1e1e !important; color: #d4d4d4 !important; border-radius: 8px !important; '
                f'padding: 15px !important; font-family: Consolas, Monaco, monospace !important; white-space: pre !important; '
                f'font-size: 13px !important; text-align: left; border: 1px solid #333 !important; line-height: 1.5 !important;">'
                f'{clean_telemetry}</div>'
            )

        # --- GLOBAL FOOTER: UPCOMING PASSES ---
        next_passes = get_upcoming_pass_info()
        html_body += (
            f'<footer style="margin-top: 30px; text-align: center; border-top: 1px solid #444; padding-top: 15px;">'
            f'<div style="display: inline-block; background-color: #2d2d2d; color: #00d4ff; border: 1px solid #00d4ff; '
            f'padding: 12px 25px; border-radius: 15px; font-family: sans-serif; box-shadow: 0 2px 8px rgba(0,0,0,0.3); font-size: 0.9em; line-height: 1.6;">'
            f'<span style="color: #fff; font-weight: bold; display: block; margin-bottom: 5px;">🛰️ UPCOMING PASSES:</span>'
            f'{next_passes}</div>'
            f'<p style="font-style: italic; color: #777; font-size: 0.75em; margin-top: 15px;">'
            f'AUTOMATED STATION DATA GENERATED BY RASPINOAA SERVICE</p>'
            f'</footer></div>'
        )

        # EXECUTE POST
        post_data = {"kind": "blogger#post", "title": title, "content": html_body}
        service.posts().insert(blogId=BLOG_ID, body=post_data).execute()
        return "✅ Mirrored to Blogger"
        
    except Exception as e:
        # Check for size-related errors specifically
        if "Request contains an invalid argument" in str(e):
            return "❌ Blogger Error: Post size too large (Image resizing may have failed)"
        return f"❌ Blogger Error: {str(e)}"

# --- WEATHER LOGIC ---

def get_weather_report():
    """Fetches weather with detailed error reporting and retry logic (Metric focus)."""
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}"
           f"&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,"
           f"wind_direction_10m,wind_gusts_10m,apparent_temperature,dew_point_2m,"
           f"pressure_msl,cloud_cover_low,cloud_cover_mid,cloud_cover_high")
    
    for attempt in range(2):
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status() 
            data = response.json()
            curr = data['current']
            
            # Metric Units
            temp_c = curr['temperature_2m']
            feels_c = curr['apparent_temperature']
            dew_c = curr['dew_point_2m']
            hum = curr['relative_humidity_2m']
            wind_kmh = curr['wind_speed_10m']
            wind_gst_kmh = curr['wind_gusts_10m']
            wind_dir = curr['wind_direction_10m']
            press_hpa = curr['pressure_msl']
            cloud_low, cloud_mid, cloud_high = curr['cloud_cover_low'], curr['cloud_cover_mid'], curr['cloud_cover_high']
            code = curr['weather_code']
            
            # Conversions for Imperial Display
            temp_f = (temp_c * 9/5) + 32
            feels_f = (feels_c * 9/5) + 32
            dew_f = (dew_c * 9/5) + 32
            wind_mph = wind_kmh * 0.621371
            wind_gst_mph = wind_gst_kmh * 0.621371
            press_inHg = press_hpa * 0.02953 
            
            # csv logging
            with open(LOG_FILE, mode='a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                                 temp_c, feels_c, dew_c, hum, wind_kmh, wind_gst_kmh, 
                                 wind_dir, press_hpa, cloud_low, cloud_mid, cloud_high, code])
            
            icon = WEATHER_ICONS.get(code, "🌡️")
            now = datetime.now().strftime("%H:%M")
            dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
            compass = dirs[int((wind_dir + 22.5) / 45) % 8]

            return (
                f"📊 **Station Weather Report** ({now})\n"
                f"--------------------------\n"
                f"Condition: **{icon}**\n"
                f"Temp: **{temp_c}°C** ({temp_f:.1f}°F)\n"
                f"Feels like: **{feels_c}°C** ({feels_f:.1f}°F)\n"
                f"Dew point: **{dew_c}°C** ({dew_f:.1f}°F)\n"
                f"Humidity: **{hum}%**\n"
                f"Barometer: **{press_hpa:.1f} hPa** ({press_inHg:.2f} inHg)\n"
                f"Wind: **{wind_kmh} km/h** ({wind_mph:.1f} mph) from **{compass}**\n"
                f"Wind Gusts: **{wind_gst_kmh} km/h** ({wind_gst_mph:.1f} mph)\n"
                f"--------------------------\n"
                f"☁️ **Cloud Cover:**\n"
                f"Low: **{cloud_low}%** | Mid: **{cloud_mid}%** | High: **{cloud_high}%**\n"
                f"*(Low <2km/6.5k ft | Mid 2-6km/20k ft | High >6km/20k ft)*"
            )
        except Exception as e:
            if attempt == 0:
                time.sleep(5)
                continue
            return f"❌ **Weather API Error:** {str(e)}"

# --- TASKS & COMMANDS ---

top_of_every_hour = [clock_time(hour=h, minute=5) for h in range(24)]

@tasks.loop(time=top_of_every_hour)
async def hourly_weather():
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        report = get_weather_report()
        await channel.send(report)
        post_to_blogger(f"Hourly Weather Update - {datetime.now().strftime('%H:%M')}", report)
        
@tasks.loop(minutes=10)
async def alert_checker():
    global ACTIVE_ALERTS
    channel = bot.get_channel(ALERTS_CHANNEL_ID)
    if not channel: return
    
    new_alerts, current_ids = get_nws_alerts()
    
    # If there are new alerts to send out
    if new_alerts:
        total_count = len(new_alerts)
        
        # If there's a multi-alert event, send a summary line first
        if total_count > 1:
            await channel.send(f"⚠️ **Notice:** {total_count} NEW active weather alerts detected for the station area.")
        
        # Loop through and transmit every alert found
        for alert_id, msg in new_alerts:
            await channel.send(msg)
    
    # Update the tracking list to clear out expired alerts
    ACTIVE_ALERTS.clear()
    ACTIVE_ALERTS.update(current_ids)

@bot.command()
async def alerts(ctx):
    if ctx.author.id != AUTHORIZED_USER_ID: return
    await ctx.send("🔍 Checking for active weather alerts...")
    
    # force_all=True ensures it prints the alert even if it was already sent automatically
    alerts_found, current_ids = get_nws_alerts(force_all=True)
    
    if not alerts_found:
        await ctx.send("✅ No active weather alerts for the station area.")
    else:
        total_count = len(alerts_found)
        
        # Dynamically switch wording depending on single or multiple alerts
        if total_count == 1:
            await ctx.send(f"🚨 **1 Active Weather Alert Found:**")
        else:
            await ctx.send(f"🚨 **Found {total_count} Active Weather Alerts:**")
            
        # Display each active alert distinctly
        for alert_id, msg in alerts_found:
            await ctx.send(msg)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}', flush=True)
    if not hourly_weather.is_running(): hourly_weather.start()
    
    # Add this line below your hourly_weather start command
    if not alert_checker.is_running(): alert_checker.start()
    
    channel = bot.get_channel(G_CHANNEL_ID)
    if channel:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await channel.send(f"✅ **Bot Service Online**\n"
                           f"Connection established to Discord.\n"
                           f"🕒 **Time:** {current_time}")

@bot.command(aliases=['?'])
async def help(ctx):
    if ctx.author.id != AUTHORIZED_USER_ID: return
    help_text = (
        "🛠️ **Station Bot Command Manual**\n"
        "**`/weather`** - Fetches weather & mirrors to Blogger.\n"
        "**`/alerts`** - Fetches weather alerts from NWS.\n"
        "**`/postblog`** - Scans /srv/images for today's captures & pushes.\n"
        "**`/radio`** - Restart OpenWebRX.\n"
        "**`/radiostop`** - Stop OpenWebRX.\n"
        "**`/status`** - System health (CPU/Disk/Time).\n"
        "**`/schedule`** - Lists upcoming satellite passes.\n"
        "**`/top`** - Memory usage.\n"
        "**`/cleanup`** - Deletes old Meteor audio (>7 days).\n"
        "**`/sync`** - Runs RaspiNOAA Master Panel Sync.\n"
        "**`/reboot`** - Safely restarts the Raspberry Pi."
    )
    await ctx.send(help_text)

@bot.command()
async def weather(ctx):
    if ctx.author.id != AUTHORIZED_USER_ID: return
    report = get_weather_report()
    await ctx.send(report)
    await ctx.send("🔄 *Mirroring telemetry to Blogger...*")
    result = post_to_blogger(f"Manual Weather Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}", report)
    await ctx.send(result)

@bot.command()
async def postblog(ctx):
    """Scans /srv/images for the 2 most recent captures and bundles them into ONE Blogger post."""
    if ctx.author.id != AUTHORIZED_USER_ID: return
    
    image_dir = "/srv/images"
    await ctx.send(f"🔍 Searching for images to bundle in `{image_dir}`...")
    
    try:
        all_files = os.listdir(image_dir)
        #corrected_files = [f for f in all_files if f.endswith("-221_corrected.jpg") or f.endswith("-MSA_corrected.jpg")]
        # Updated to match both SatDump 1.2.1 and 1.2.2+ naming conventions
        corrected_files = [f for f in all_files if any(x in f for x in ["221_False_Color_corrected.jpg", "MSA_corrected.jpg"])]
        
        if not corrected_files:
            return await ctx.send(f"❌ No processed Meteor images found.")

        # Sort by file modification time (mtime) to get the absolute latest
        corrected_files.sort(key=lambda x: os.path.getmtime(os.path.join(image_dir, x)), reverse=True)
        
        targets = corrected_files[:2]
        
        # --- TITLE FIX LOGIC ---
        # Look for the date-time string (e.g., 20260502-141022) in the newest filename
        match = re.search(r'(\d{8}-\d{6})', targets[0])
        if match:
            raw_ts = match.group(1)
            # Parse the string and format it nicely
            capture_dt = datetime.strptime(raw_ts, "%Y%m%d-%H%M%S")
            title_time = capture_dt.strftime("%Y-%m-%d %H:%M")
        else:
            # Fallback to current time if regex fails
            title_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        bundle_html = ""
        await ctx.send(f"📦 Bundling {len(targets)} images from {title_time}...")

        for filename in targets:
            full_path = os.path.join(image_dir, filename)
            img_bytes = resize_image_for_blogger(full_path)
            img_b64 = base64.b64encode(img_bytes).decode('utf-8')
            
            bundle_html += (f'<div style="text-align: center; margin-bottom: 25px;">'
                           f'<img src="data:image/jpeg;base64,{img_b64}" style="max-width: 100%; border-radius: 12px; border: 1px solid #444;" />'
                           f'<p style="font-size: 0.8em; color: #777;">{filename}</p></div>')

        # Create ONE post with the bundled HTML and the extracted capture time
        result = post_to_blogger(f"METEOR-M2 Bundled Capture - {title_time} EDT", bundle_html, None, "METEOR-M2")
        
        await ctx.send(f"📤 {result}")
    except Exception as e:
        await ctx.send(f"❌ Error during bundle: {str(e)}")

@bot.command()
async def status(ctx):
    if ctx.author.id != AUTHORIZED_USER_ID: return
    temp_raw = os.popen("vcgencmd measure_temp").read().strip().split('=')[1]
    disk_raw = os.popen("df -h / | awk 'NR==2 {print $4}'").read().strip()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await ctx.send(f"🛰️ **Station Health Report**\n🕒 Time: {current_time}\n🌡️ CPU Temp: {temp_raw}\n💾 Available Storage: {disk_raw}")

@bot.command()
async def schedule(ctx):
    if ctx.author.id != AUTHORIZED_USER_ID: return
    try:
        atq_output = subprocess.check_output("atq | sort -k 6n -k 3M -k 4n -k 5", shell=True).decode('utf-8')
        response = f"📅 **Schedule:**\n```\n{atq_output or 'No passes scheduled.'}\n```"
    except: response = "❌ Error reading schedule."
    await ctx.send(response)

@bot.command()
async def top(ctx):
    if ctx.author.id != AUTHORIZED_USER_ID: return
    output = subprocess.check_output("ps -eo comm,pmem,pcpu --sort=-pmem | head -n 6", shell=True).decode('utf-8')
    await ctx.send(f"📋 **Top Usage**\n```\n{output}```")
    
@bot.command()
async def radio(ctx):
    if ctx.author.id != AUTHORIZED_USER_ID: return
    status_msg = await ctx.send("🔄 **Initiating OpenWebRX reset...** Please wait.")
    try:
        output = subprocess.run(["sudo", "systemctl", "restart", "openwebrx"], check=True)
        #await ctx.send(f"✅ Radio services have been reset.")
        await status_msg.edit(content="✅ **Radio services have been reset.**")
    
    except subprocess.CalledProcessError as e:
        await ctx.send(f"❌ Failed to reset radio: {e}")
    except Exception as e:
        await ctx.send(f"⚠️ An unexpected error occurred: {e}")
        
@bot.command()
async def radiostop(ctx):
    if ctx.author.id != AUTHORIZED_USER_ID: return
    status_msg = await ctx.send("🔄 **Stopping OpenWebRX ...** Please wait.")
    try:
        output = subprocess.run(["sudo", "systemctl", "stop", "openwebrx"], check=True)
        #await ctx.send(f"✅ Radio services have been reset.")
        await status_msg.edit(content="✅ **Radio services have been stopped.**")
    
    except subprocess.CalledProcessError as e:
        await ctx.send(f"❌ Failed to stop radio: {e}")
    except Exception as e:
        await ctx.send(f"⚠️ An unexpected error occurred: {e}")
    
# --- ADD THIS CLASS ABOVE THE CLEANUP COMMAND ---
class ConfirmCleanup(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30.0)
        self.value = None

    @discord.ui.button(label="Confirm Deletion", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.stop()
        await interaction.response.defer() # Acknowledge the click

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.stop()
        await interaction.response.defer()

@bot.command()
async def cleanup(ctx):
    if ctx.author.id != AUTHORIZED_USER_ID: return
    target_dir = "/srv/audio/meteor"
    
    if not os.path.exists(target_dir): 
        return await ctx.send("❌ Directory missing.")
    
    # Create the confirmation view
    view = ConfirmCleanup()
    msg = await ctx.send("⚠️ **Are you sure?** This will delete Meteor audio files older than 14 days and all 0-byte files.", view=view)

    # Wait for the user to interact
    await view.wait()

    if view.value is None:
        await msg.edit(content="⏳ **Cleanup timed out.** No files were deleted.", view=None)
    elif view.value:
        await msg.edit(content="🧹 **Cleaning Meteor audio files (Old or Empty)...**", view=None)
        
        # Logic: Delete if (older than 14 days) OR (size is 0)
        cmd = f"find {target_dir} -type f \( -mtime +14 -o -size 0 \) -delete"
        os.system(cmd)
        
        await ctx.send("✅ Cleanup Complete.")
    else:
        await msg.edit(content="❌ **Cleanup cancelled.**", view=None)
    
#@bot.command()
#async def cleanup(ctx):
#    if ctx.author.id != AUTHORIZED_USER_ID: return
#    target_dir = "/srv/audio/meteor"
#   
#    if not os.path.exists(target_dir): 
#        return await ctx.send("❌ Directory missing.")
#    
#    await ctx.send("🧹 **Cleaning Meteor audio files (Old or Empty)...**")
#    
#    # Combined into one efficient 'find' call
#    # Logic: Delete if (older than 14 days) OR (size is 0)
#    cmd = f"find {target_dir} -type f \( -mtime +14 -o -size 0 \) -delete"
#    os.system(cmd)
#    
#    await ctx.send("✅ Cleanup Complete.")

@bot.command()
async def sync(ctx):
    if ctx.author.id != AUTHORIZED_USER_ID: return
    await ctx.send("🔄 **This option is under construction...**")

@bot.command()
async def reboot(ctx):
    if ctx.author.id != AUTHORIZED_USER_ID: return
    await ctx.send("🔄 **Rebooting hardware...**")
    # Give the bot 2 seconds to ensure the Discord API receives the message
    await asyncio.sleep(2)
    os.system("sudo reboot")

# --- UPDATED CLI HANDLER FOR STATION_BOT.PY ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--post-image", help="Path to satellite image for Blogger")
    parser.add_argument("--post-bundle", help="Space-separated paths for multiple images")
    parser.add_argument("--sat-name", help="Satellite name")
    parser.add_argument("--fail-alert", action="store_true", help="Trigger a failure post")
    parser.add_argument("--pass-info", help="Details about the failed pass")
    args, unknown = parser.parse_known_args()

    if args.fail_alert:
        res = post_to_blogger(f"Not Processed: {args.sat_name}", f"Status: Not processed\nDetails: {args.pass_info or 'Unknown Error'}", None, args.sat_name)
        print(res)
    elif args.post_bundle:
        # --- BUNDLE LOGIC ---
        image_list = args.post_bundle.split()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        title = f"{args.sat_name or 'Meteor'} Pass - {now_str}"
        
        bundle_html = ""
        for img_path in image_list:
            if os.path.exists(img_path):
                print(f"📦 Adding to bundle: {os.path.basename(img_path)}")
                img_bytes = resize_image_for_blogger(img_path)
                img_b64 = base64.b64encode(img_bytes).decode('utf-8')
                # Use a cleaner wrapper for multiple images
                bundle_html += f'<div style="text-align: center; margin-bottom: 30px;"><img src="data:image/jpeg;base64,{img_b64}" style="max-width: 100%; border-radius: 12px; border: 1px solid #444; box-shadow: 0 4px 8px rgba(0,0,0,0.5);" /></div>'
        
        # We pass the bundled HTML directly as the 'content' 
        # and set image_path to None so the function uses our custom HTML
        res = post_to_blogger(title, bundle_html, None, args.sat_name)
        print(res)
    elif args.post_image:
        res = post_to_blogger(f"{args.sat_name or 'Satellite'} Pass", "", args.post_image, args.sat_name)
        print(res)
    else:
        bot.run(TOKEN)

