# File: auth_blogger.py | Version: 2026-04-07 02:30
import os
import sys

# Ensure we use the virtual environment libraries
sys.path.append('/home/admin/bot_env/lib/python3.11/site-packages')

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
except ImportError:
    print("❌ Error: Google Auth libraries not found in /home/admin/bot_env/")
    print("Run: /home/admin/bot_env/bin/pip install google-auth-oauthlib google-api-python-client")
    sys.exit(1)

# Scopes must match the bot's SCOPES exactly
SCOPES = ['https://www.googleapis.com/auth/blogger']
CLIENT_SECRET_FILE = '/home/admin/credentials.json'
TOKEN_FILE = '/home/admin/token.json'

def main():
    print("--- 🛰️ Forced Blogger Auth Utility (Headless/Pi Fix) ---")
    
    # 1. Check for credentials.json
    if not os.path.exists(CLIENT_SECRET_FILE):
        print(f"❌ CRITICAL ERROR: {CLIENT_SECRET_FILE} not found.")
        print("Please upload your credentials.json to /home/admin/")
        return

    # 2. Clean start
    if os.path.exists(TOKEN_FILE):
        print(f"🗑️ Removing old token at {TOKEN_FILE}...")
        os.remove(TOKEN_FILE)

    # 3. Start the OAuth flow
    try:
        print("🔑 Starting authentication flow...")
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
        
        # We use open_browser=False for Headless/SSH environments
        # This prevents the Pi from trying to open a text-browser like 'links'
        print("\n" + "="*60)
        print("🌐 HEADLESS AUTHENTICATION STEP:")
        print("1. Copy the URL that will appear below.")
        print("2. Paste it into the browser on YOUR PERSONAL COMPUTER.")
        print("3. Sign in and check the 'Manage Blogger' permission box.")
        print("4. After signing in, your browser will show 'Unable to connect' or 'Site can't be reached' at localhost.")
        print("5. COPY the ENTIRE URL from your browser's address bar (it starts with http://localhost...)")
        print("6. Paste that URL back here in the terminal.")
        print("="*60 + "\n")
        
        creds = flow.run_local_server(
            port=0, 
            prompt='consent', 
            access_type='offline',
            open_browser=False  # THIS IS THE FIX
        )
        
        # 4. Save the credentials
        print(f"\n💾 Saving new token to {TOKEN_FILE}...")
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
            
        # 5. Verification
        if creds.refresh_token:
            print("✅ SUCCESS: Long-term Refresh Token obtained.")
        else:
            print("⚠️ WARNING: No refresh token found. Re-run and check 'Consent'.")

        print(f"\n✨ Final Step: Run 'sudo chmod 644 {TOKEN_FILE}'")
        print("Then: 'sudo systemctl restart station_bot.service'")

    except Exception as e:
        print(f"\n❌ AUTHENTICATION FAILED: {str(e)}")

if __name__ == '__main__':
    main()
