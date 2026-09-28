# File: station_bot.py | Version: 2026-04-26 01:30 ET
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

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)
bot.remove_command('help') 

# --- UTILITIES ---

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
    """Generic function to post HTML content to Blogger with a 'Jump Break' to prevent pagination issues."""
    service = get_blogger_service()
    if not service:
        return "⚠️ Blogger Auth Failed (Check token.json)"
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        html_body = '<div style="font-family: sans-serif; max-width: 900px; margin: auto; color: #333;">'
        
        if image_path and os.path.exists(image_path):
            img_bytes = resize_image_for_blogger(image_path)
            img_b64 = base64.b64encode(img_bytes).decode('utf-8')
            image_data_url = f"data:image/jpeg;base64,{img_b64}"
            img_filename = os.path.basename(image_path)
            
            # --- THE FIX: ADD A JUMP BREAK ---
            # We put the title and a small version of the image BEFORE the jump break.
            # The '' tag tells Blogger where to cut the post for the main page.
            
            html_body += (f'<h2 style="text-align: center; color: #2c3e50;">{sat_name} Capture</h2>'
                         f'<p style="text-align: center; color: #7f8c8d;">{now_str}</p>'
                         f''  # Blogger Jump Break
                         f'<div style="text-align: center; margin-top: 20px; margin-bottom: 25px;">'
                         f'<a href="{image_data_url}"><img src="{image_data_url}" style="max-width: 100%; border-radius: 12px; border: 1px solid #444; box-shadow: 0 4px 15px rgba(0,0,0,0.2);" /></a>'
                         f'<p style="margin-top: 10px; font-size: 0.9em; color: #555; font-family: monospace;">{img_filename}</p>'
                         f'</div>')
            
            if content and sat_name:
                html_body += f'<p style="text-align: center; color: #7f8c8d; margin-bottom: 30px;"><b>Station:</b> Westampton, NJ</p>'

        if content:
            clean_telemetry = content.replace("**", "")
            html_body += (
                f'<div style="background-color: #1e1e1e !important; color: #d4d4d4 !important; border-radius: 8px !important; '
                f'padding: 15px !important; font-family: Consolas, Monaco, monospace !important; white-space: pre !important; '
                f'font-size: 13px !important; text-align: left; border: 1px solid #333 !important; line-height: 1.5 !important;">'
                f'{clean_telemetry}</div>'
            )

        # Footer logic remains the same...
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

        post_body = {"kind": "blogger#post", "title": title, "content": html_body}
        service.posts().insert(blogId=BLOG_ID, body=post_body).execute()
        return "✅ Mirrored to Blogger"
    except Exception as e:
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

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}', flush=True)
    if not hourly_weather.is_running(): hourly_weather.start()
    
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
    """Scans /srv/images for the 2 most recent captures and pushes to Blogger."""
    if ctx.author.id != AUTHORIZED_USER_ID: return
    
    image_dir = "/srv/images"
    await ctx.send(f"🔍 Searching for the 2 most recent satellite captures in `{image_dir}`...")
    
    try:
        all_files = os.listdir(image_dir)
        # 1. Filter for your specific corrected image types
        corrected_files = [f for f in all_files if f.endswith("-221_corrected.jpg") or f.endswith("-MSA_corrected.jpg")]
        
        if not corrected_files:
            return await ctx.send(f"❌ No processed Meteor images found.")

        # 2. Sort all matching files by filename (since your files start with YYYYMMDD-HHMMSS)
        # Sorting descending [::-1] puts the absolute latest captures at the front
        latest_files = sorted(corrected_files, reverse=True)
        
        # 3. Take only the top 2
        targets = latest_files[:2]
        
        await ctx.send(f"✅ Identified {len(targets)} most recent images. Pushing to Blogger...")
        
        for index, filename in enumerate(targets):
            full_path = os.path.join(image_dir, filename)
            suffix = "221" if "221" in filename else "MSA"
            
            # Extract date (YYYYMMDD) and time (HHMM) for a precise title
            # Example filename: METEOR-M2-20260425-223015-221_corrected.jpg
            date_match = re.search(r'(\d{8})', filename)
            time_match = re.search(r'\d{8}-(\d{4})', filename)
            
            p_date = date_match.group(1) if date_match else "Unknown Date"
            p_time = f"{time_match.group(1)[:2]}:{time_match.group(1)[2:]}" if time_match else "Unknown Time"
            
            result = post_to_blogger(f"METEOR-M2 {suffix} Capture - {p_date} {p_time} EDT", "", full_path, "METEOR-M2")
            await ctx.send(f"📤 **[{index+1}/{len(targets)}]** `{filename}`: {result}")
            
            # 10-second gap to prevent Blogger display issues
            if index < len(targets) - 1:
                await asyncio.sleep(30)
                
        await ctx.send("🏁 **Sync of 2 latest images complete.**")
    except Exception as e:
        await ctx.send(f"❌ Error during scan: {str(e)}")

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
    

@bot.command()
async def cleanup(ctx):
    if ctx.author.id != AUTHORIZED_USER_ID: return
    target_dir = "/srv/audio/meteor"
    if not os.path.exists(target_dir): return await ctx.send("❌ Directory missing.")
    await ctx.send("🧹 **Cleaning Meteor audio files (>7 days)...**")
    os.system("find /srv/audio/meteor -type f -mtime +7 -delete")
    await ctx.send("✅ Cleanup Complete.")

@bot.command()
async def sync(ctx):
    if ctx.author.id != AUTHORIZED_USER_ID: return
    await ctx.send("🔄 **Running Master Panel Sync...**")
    try:
        output = subprocess.check_output("python3 /home/admin/raspberry-noaa-v2/scripts/panel_sync.py", shell=True, stderr=subprocess.STDOUT).decode('utf-8')
        trimmed = output[-1900:] if len(output) > 1900 else output
        await ctx.send(f"✅ **Sync Complete:**\n```text\n{trimmed}\n```")
    except: await ctx.send("❌ Sync Failed.")

@bot.command()
async def reboot(ctx):
    if ctx.author.id != AUTHORIZED_USER_ID: return
    await ctx.send("🔄 **Rebooting hardware...**")
    os.system("sudo reboot")

# --- CLI HANDLER ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--post-image", help="Path to satellite image for Blogger")
    parser.add_argument("--sat-name", help="Satellite name")
    parser.add_argument("--fail-alert", action="store_true", help="Trigger a failure post")
    parser.add_argument("--pass-info", help="Details about the failed pass")
    args, unknown = parser.parse_known_args()

    if args.fail_alert:
        res = post_to_blogger(f"Not Processed: {args.sat_name}", f"Status: Not processed\nDetails: {args.pass_info or 'Unknown Error'}", None, args.sat_name)
        print(res)
    elif args.post_image:
        res = post_to_blogger(f"{args.sat_name or 'Satellite'} Pass", "", args.post_image, args.sat_name)
        print(res)
    else:
        bot.run(TOKEN)
