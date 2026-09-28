# File: station_bot.py | Version: 2026-04-06 21:55
import sys
import os
import glob

# Ensure the bot uses the virtual environment where you just installed the libraries
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
from datetime import datetime, time as clock_time

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
bot.remove_command('help') # Removes the default discord help menu

# --- BLOGGER UTILITIES ---

def get_blogger_service():
    """Authenticates and returns the Blogger service object with forced token refresh logic."""
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

def post_to_blogger(title, content):
    """Generic function to post HTML content to Blogger in the terminal-style box."""
    service = get_blogger_service()
    if not service:
        return "⚠️ Blogger Auth Failed (Check token.json)"
    
    try:
        # Wrap content in the terminal-style box and strip Discord bolding
        clean_text = content.replace("**", "")
        html_body = (
            f'<div style="background-color: #1e1e1e !important; color: #d4d4d4 !important; border-radius: 8px !important; '
            f'padding: 15px !important; font-family: Consolas, Monaco, monospace !important; white-space: pre !important; '
            f'font-size: 13px !important; text-align: left; border: 1px solid #333 !important; line-height: 1.5 !important;">'
            f'{clean_text}</div>'
        )

        post_body = {"kind": "blogger#post", "title": title, "content": html_body}
        service.posts().insert(blogId=BLOG_ID, body=post_body).execute()
        return "✅ Mirrored to Blogger"
    except Exception as e:
        return f"❌ Blogger Error: {str(e)}"

# --- WEATHER LOGIC ---

def get_weather_report():
    """Fetches weather and returns a formatted string with Metric units."""
    try:
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}"
               f"&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,"
               f"wind_direction_10m,wind_gusts_10m,apparent_temperature,dew_point_2m,"
               f"pressure_msl,cloud_cover_low,cloud_cover_mid,cloud_cover_high")
        
        response = requests.get(url, timeout=10)
        data = response.json()
        
        curr = data['current']
        temp_c = curr['temperature_2m']
        feels_c = curr['apparent_temperature']
        dew_c = curr['dew_point_2m']
        hum = curr['relative_humidity_2m']
        wind_kmh = curr['wind_speed_10m']
        wind_gst_kmh = curr['wind_gusts_10m']
        wind_dir = curr['wind_direction_10m']
        press_hpa = curr['pressure_msl']
        cloud_low = curr['cloud_cover_low']
        cloud_mid = curr['cloud_cover_mid']
        cloud_high = curr['cloud_cover_high']
        code = curr['weather_code']
        
        # conversions
        temp_f = (temp_c * 9/5) + 32
        feels_f = (feels_c * 9/5) + 32
        dew_f = (dew_c * 9/5) + 32
        wind_mph = wind_kmh * 0.621371
        wind_gst_mph = wind_gst_kmh * 0.621371
        press_inHg = press_hpa * 0.02953 
        
        # csv logging
        file_exists = os.path.isfile(LOG_FILE)
        with open(LOG_FILE, mode='a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['Timestamp', 'Temp_C', 'Feels_C', 'Dew_C', 'Humidity', 
                                 'Wind_kmh', 'Gusts_kmh', 'Direction', 'Pressure_hPa', 
                                 'Cloud_L', 'Cloud_M', 'Cloud_H', 'Code'])
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
    except:
        return "❌ Unexpected Weather Error."

# --- TASKS ---

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
                           f"Connection to Discord established.\n"
                           f"🕒 **Time:** {current_time}\n"
                           f"All station services active.")

# --- COMMANDS ---

@bot.command(aliases=['?'])
async def help(ctx):
    if ctx.author.id != AUTHORIZED_USER_ID: return
    help_text = (
        "🛠️ **Station Bot Command Manual** 🛠️\n"
        "---------------------------------\n"
        "**`/status`** - Shows system time, CPU temp, and available storage.\n"
        "**`/weather`** - Fetches the weather & posts to Blogger.\n"
        "**`/schedule`** - Lists upcoming scheduled satellite passes.\n"
        "**`/top`** - Shows the top memory-consuming processes.\n"
        "**`/cleanup`** - Deletes 0-byte and old Meteor audio files.\n"
        "**`/sync`** - Runs the master web panel sync script.\n"
        "**`/reboot`** - Safely restarts the Raspberry Pi.\n"
        "**`/help`** or **`/?`** - Displays this menu."
    )
    await ctx.send(help_text)

@bot.command()
async def status(ctx):
    if ctx.author.id != AUTHORIZED_USER_ID: return
    temp_raw = os.popen("vcgencmd measure_temp").read().strip() 
    disk_raw = os.popen("df -h / | awk 'NR==2 {print $4}'").read().strip()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    response = (
        f"🛰️ **Station Health Report**\n"
        f"--------------------------\n"
        f"🕒 **System Time:** {current_time}\n"
        f"🌡️ **CPU Temp:** {temp_raw.split('=')[1] if '=' in temp_raw else 'N/A'}\n"
        f"💾 **Available Storage:** {disk_raw}"
    )
    await ctx.send(response)

@bot.command()
async def weather(ctx):
    if ctx.author.id != AUTHORIZED_USER_ID: return
    report = get_weather_report()
    await ctx.send(report)
    await ctx.send("🔄 *Mirroring telemetry to Blogger...*")
    result = post_to_blogger(f"Manual Weather Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}", report)
    await ctx.send(result)

@bot.command()
async def schedule(ctx):
    if ctx.author.id != AUTHORIZED_USER_ID: return
    try:
        atq_output = subprocess.check_output("atq | sort -k 6n -k 3M -k 4n -k 5", shell=True).decode('utf-8')
        response = f"📅 **Schedule:**\n```\n{atq_output}\n```" if atq_output.strip() else "📅 No passes scheduled."
    except:
        response = "❌ Error reading schedule."
    await ctx.send(response)

@bot.command()
async def top(ctx):
    if ctx.author.id != AUTHORIZED_USER_ID: return
    cmd = "ps -eo comm,pmem,pcpu --sort=-pmem | head -n 6"
    output = subprocess.check_output(cmd, shell=True).decode('utf-8')
    await ctx.send(f"📋 **Top Usage**\n```\n{output}```")

@bot.command()
async def cleanup(ctx):
    if ctx.author.id != AUTHORIZED_USER_ID: return
    target_dir = "/srv/audio/meteor"
    if not os.path.exists(target_dir):
        return await ctx.send("❌ Target directory missing.")
    await ctx.send("🧹 **Starting Meteor Audio Cleanup...**")
    os.system("find /srv/audio/meteor -type f -mtime +7 -delete")
    await ctx.send("✅ Cleanup Complete.")
        
@bot.command()
async def sync(ctx):
    if ctx.author.id != AUTHORIZED_USER_ID: return
    await ctx.send("🔄 **Running Master Panel Sync...**")
    try:
        output = subprocess.check_output("python3 /home/admin/raspberry-noaa-v2/scripts/panel_sync.py", shell=True, stderr=subprocess.STDOUT).decode('utf-8')
        # Safety: Trim output to fit Discord's 2000 char limit
        trimmed_output = output[-1900:] if len(output) > 1900 else output
        await ctx.send(f"✅ **Sync Complete:**\n```text\n{trimmed_output}\n```")
    except:
        await ctx.send("❌ Sync Failed.")

@bot.command()
async def reboot(ctx):
    if ctx.author.id != AUTHORIZED_USER_ID: return
    await ctx.send("🔄 **Rebooting...**")
    os.system("sudo reboot")

bot.run(TOKEN)
