import discord
from discord.ext import commands, tasks 
import subprocess
import os
import time
import csv
import requests 
from datetime import datetime, time as clock_time

LOG_FILE = "/home/admin/station_weather_log.csv"

# --- CONFIGURATION ---
TOKEN = 'MTQ4MjU2NTAwODI2NDEzODc4Mg.GQYR5L.vnNlRJXpGThOUJGBtSJYePaYowCx5aNm6vChdo'
AUTHORIZED_USER_ID = 794776141059719168 
G_CHANNEL_ID = 1480692274760388764 # general
CHANNEL_ID = 1483239063656988814 # weather_reports

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

def get_weather_report():
    """Fetches weather and returns a formatted string with both Metric and Imperial units."""
    try:
        # Updated URL with new parameters: apparent_temperature, dew_point_2m, pressure_msl, cloud_cover_low/mid/high
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
        
        # --- CONVERSIONS ---
        temp_f = (temp_c * 9/5) + 32
        feels_f = (feels_c * 9/5) + 32
        dew_f = (dew_c * 9/5) + 32
        wind_mph = wind_kmh * 0.621371
        wind_gst_mph = wind_gst_kmh * 0.621371
        press_inHg = press_hpa * 0.02953  # Convert hPa/mb to inches of Mercury
        
        # --- LOGGING TO CSV (Updated with new columns) ---
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
    except requests.exceptions.RequestException:
        return f"⚠️ **Weather API Error:** Service timed out or unreachable."
    except Exception as e:
        return f"❌ **Unexpected Error:** {e}"

# Create a list of times representing the top of every hour (00:00, 01:00, etc.)
top_of_every_hour = [clock_time(hour=h, minute=5) for h in range(24)]

#@tasks.loop(minutes=60) 
@tasks.loop(time=top_of_every_hour)
async def hourly_weather():
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        await channel.send(get_weather_report())

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    if not hourly_weather.is_running():
        hourly_weather.start()
    
    channel = bot.get_channel(G_CHANNEL_ID)
    if channel:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await channel.send(f"✅ **Bot Service Online**\n"
                           f"Connection to Discord established.\n"
                           f"🕒 **Time:** {current_time}\n"
                           f"All station services active.")

@bot.command(aliases=['?'])
async def help(ctx):
    """Displays the custom help menu."""
    if ctx.author.id != AUTHORIZED_USER_ID: return
    
    help_text = (
        "🛠️ **Station Bot Command Manual** 🛠️\n"
        "---------------------------------\n"
        "**`/status`** - Shows system time, CPU temp, and available storage.\n"
        "**`/weather`** - Fetches the current local weather report.\n"
        "**`/schedule`** - Lists upcoming scheduled satellite passes.\n"
        "**`/top`** - Shows the top memory-consuming processes.\n"
        "**`/cleanup`** - Deletes 0-byte and old (>7 days) meteor audio files.\n"
        "**`/sync`** - Runs the master web panel sync to fix missing thumbnails.\n"
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
    await ctx.send(get_weather_report())

@bot.command()
async def schedule(ctx):
    if ctx.author.id != AUTHORIZED_USER_ID: return
    try:
        atq_output = subprocess.check_output("atq | sort -k 6n -k 3M -k 4n -k 5", shell=True).decode('utf-8')
        response = f"📅 **Schedule:**\n```\n{atq_output}\n```" if atq_output.strip() else "📅 No passes scheduled."
    except Exception as e:
        response = f"❌ Error: {e}"
    await ctx.send(response)

@bot.command()
async def top(ctx):
    if ctx.author.id != AUTHORIZED_USER_ID: return
    try:
        cmd = "ps -eo comm,pmem,pcpu --sort=-pmem | head -n 6"
        output = subprocess.check_output(cmd, shell=True).decode('utf-8')
        await ctx.send(f"📋 **Top Usage**\n```\n{output}```")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

@bot.command()
async def cleanup(ctx):
    """Deletes 0-byte files and files older than 7 days in the meteor audio folder."""
    if ctx.author.id != AUTHORIZED_USER_ID: return
    
    target_dir = "/srv/audio/meteor"
    if not os.path.exists(target_dir):
        return await ctx.send(f"❌ Error: Directory `{target_dir}` not found.")

    await ctx.send("🧹 **Starting Meteor Audio Cleanup...**")
    deleted_empty = deleted_old = freed_space = 0
    seven_days_ago = time.time() - (7 * 86400) 

    try:
        for filename in os.listdir(target_dir):
            filepath = os.path.join(target_dir, filename)
            if os.path.isfile(filepath):
                file_size = os.path.getsize(filepath)
                file_mtime = os.path.getmtime(filepath)

                if file_size == 0 or file_mtime < seven_days_ago:
                    os.remove(filepath)
                    if file_size == 0: deleted_empty += 1
                    else: 
                        deleted_old += 1
                        freed_space += file_size
                    
        freed_mb = freed_space / (1024 * 1024)
        await ctx.send(f"✅ **Cleanup Complete!**\nTarget: `{target_dir}`\n"
                       f"🗑️ Empty Files: **{deleted_empty}**\n🕰️ Old Files: **{deleted_old}**\n"
                       f"💾 Freed: **{freed_mb:.2f} MB**")
    except Exception as e:
        await ctx.send(f"❌ **Error:** {e}")
        
@bot.command()
async def sync(ctx):
    """Runs the master web panel sync python script."""
    if ctx.author.id != AUTHORIZED_USER_ID: return
    
    await ctx.send("🔄 **Running Master Panel Sync... this may take a moment.**")
    try:
        output = subprocess.check_output("python3 /home/admin/raspberry-noaa-v2/scripts/panel_sync.py", shell=True, stderr=subprocess.STDOUT).decode('utf-8')
        if len(output) > 1900:
            output = output[-1900:]
        await ctx.send(f"✅ **Sync Complete:**\n```text\n{output}\n```")
    except subprocess.CalledProcessError as e:
        await ctx.send(f"❌ **Sync Failed:**\n```text\n{e.output.decode('utf-8')}\n```")

@bot.command()
async def reboot(ctx):
    if ctx.author.id != AUTHORIZED_USER_ID: return
    await ctx.send("🔄 **Rebooting the hardware...**")
    os.system("sudo reboot")

bot.run(TOKEN)
