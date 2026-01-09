import subprocess
import time
import json
import os
from flask import Flask, redirect, Response

# =================================================================
#                         USER CONFIGURATION
# =================================================================

CONFIG_FILE = "WOL_Brige.config"

def load_config():
    defaults = {
        "WOL_MAC_ADDRESS": "8C:EC:4B:CE:2D:B7",
        "SITE_URL": "https://panel.thethings.qzz.io",
        "WAIT_TIME_SECONDS": 60
    }
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                user_config = json.load(f)
                # Update defaults with user config, ignoring keys that might not exist in defaults if desired, 
                # but here we just update.
                defaults.update(user_config)
                print(f"[{time.strftime('%H:%M:%S')}] Loaded config from {CONFIG_FILE}")
        except json.JSONDecodeError as e:
            print(f"[{time.strftime('%H:%M:%S')}] Error parsing {CONFIG_FILE}: {e}. Using defaults.")
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] Error loading {CONFIG_FILE}: {e}. Using defaults.")
    else:
        print(f"[{time.strftime('%H:%M:%S')}] Config file {CONFIG_FILE} not found. Creating with defaults.")
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(defaults, f, indent=4)
        except Exception as e:
             print(f"[{time.strftime('%H:%M:%S')}] Could not create {CONFIG_FILE}: {e}")

    return defaults

config = load_config()

# 1. MAC Address of the Server's Network Card (e.g., "00:1A:2B:3C:4D:5E")
WOL_MAC_ADDRESS = config["WOL_MAC_ADDRESS"]

# 2. The final URL of your site (e.g., "http://panel.yourdomain.com")
SITE_URL = config["SITE_URL"]

# 3. Time (in seconds) to wait for the server to boot up
WAIT_TIME_SECONDS = int(config["WAIT_TIME_SECONDS"]) 

# =================================================================
#                     FLASK APPLICATION START
# =================================================================

app = Flask(__name__)

# --- HTML Response for the Waiting Page ---
# This page is served to the user while the server boots. 
# The <meta http-equiv="refresh"> tag handles the automatic redirection.
WAITING_PAGE_HTML = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Server Starting...</title>
    <meta http-equiv="refresh" content="{WAIT_TIME_SECONDS};url={SITE_URL}">
    <style>
        body {{ font-family: sans-serif; text-align: center; margin-top: 50px; background-color: #f0f0f0; }}
        .container {{ background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); display: inline-block; }}
        h1 {{ color: #333; }}
        .loader {{ border: 8px solid #f3f3f3; border-top: 8px solid #3498db; border-radius: 50%; width: 50px; height: 50px; animation: spin 2s linear infinite; margin: 20px auto; }}
        @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 Starting Server...</h1>
        <div class="loader"></div>
        <p>Sending Wake-on-LAN signal. Please wait approximately <strong>{WAIT_TIME_SECONDS} seconds</strong>.</p>
        <p>You will be automatically redirected to your Pterodactyl Panel.</p>
        <p>If the page fails to load, the server may still be booting. Please try refreshing.</p>
    </div>
</body>
</html>
"""

@app.route('/wake', methods=['GET'])
def wake_server_and_redirect():
    """Triggers the WOL Magic Packet and serves the waiting page."""
    
    # 1. Send the Wake-on-LAN Packet using the command-line utility
    try:
        # 'check=True' raises an error if the command fails
        subprocess.run(['wakeonlan', WOL_MAC_ADDRESS], check=True, capture_output=True)
        print(f"[{time.strftime('%H:%M:%S')}] WOL Magic Packet sent to {WOL_MAC_ADDRESS}")
    
    except subprocess.CalledProcessError as e:
        error_message = f"WOL Error: Could not send packet. Check MAC address and 'wakeonlan' install: {e.stderr.decode()}"
        print(f"[{time.strftime('%H:%M:%S')}] {error_message}")
        return error_message, 500
    
    except FileNotFoundError:
        error_message = "WOL Error: 'wakeonlan' command not found. Did you run 'pkg install wakeonlan' in Termux?"
        print(f"[{time.strftime('%H:%M:%S')}] {error_message}")
        return error_message, 500

    # 2. Return the waiting page (the user's browser handles the redirection)
    return Response(WAITING_PAGE_HTML, mimetype='text/html')

@app.route('/')
def home():
    """Simple home page to instruct the user to use the correct /wake endpoint."""
    
    # This URL is what the user must access to start the process
    wake_link = f"http://<Your-Public-IP-or-Domain>/wake"
    
    return f"""
    <h1>WOL Gateway Running</h1>
    <p>The Python/Flask app is active on port 5000. </p>
    <p>To wake the server, please direct users to the <strong>/wake</strong> endpoint: <a href="/wake">Click here to test /wake</a></p>
    <p>Ensure your router's port forwarding is mapping your external access to this phone's IP on port 5000.</p>
    """

if __name__ == '__main__':
    # 'host=0.0.0.0' allows connections from any device on your local network.
    # 'port=5000' is the default Flask port, which your router must forward to.
    print(f"[{time.strftime('%H:%M:%S')}] Flask App starting on http://0.0.0.0:5000")
    print(f"[{time.strftime('%H:%M:%S')}] Waking MAC: {WOL_MAC_ADDRESS}, Redirect URL: {SITE_URL}")
    app.run(host='0.0.0.0', port=5000, debug=False)