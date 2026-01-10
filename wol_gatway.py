#!/usr/bin/env python3
"""
Wake-on-LAN (WOL) Gateway - Flask Web Application

This application provides a web-based Wake-on-LAN gateway that:
  1. Receives HTTP requests at the /wake endpoint
  2. Sends a WOL magic packet to wake up a remote server
  3. Displays a waiting page while the server boots
  4. Automatically redirects to the target site once boot time elapses

Requirements:
  - Flask: pip install flask
  - wakeonlan utility: pkg install wakeonlan (Termux) or apt install wakeonlan (Linux)
  - WOL_Brige.config file created by setup_wol.py

Usage:
  python wol_gatway.py
  
Then access: http://<server-ip>:<port>/wake
"""

import subprocess
import time
import json
import os
from flask import Flask, redirect, Response

# =================================================================
#                         USER CONFIGURATION
# =================================================================

# Configuration file path - must be created by setup_wol.py first
CONFIG_FILE = "WOL_Brige.config"

def load_config():
    """
    Loads and validates the configuration from WOL_Brige.config.
    
    This function:
      1. Checks if the config file exists
      2. Parses the JSON content
      3. Validates that all required keys are present
      4. Validates each configuration value
      5. Returns a dictionary with validated config values
    
    Returns:
        dict: Validated configuration with keys: WOL_MAC_ADDRESS, SITE_URL,
              WAIT_TIME_SECONDS, PORT
    
    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid or missing required fields
    """
    # Define all required configuration keys
    required_keys = ("WOL_MAC_ADDRESS", "SITE_URL", "WAIT_TIME_SECONDS", "PORT")

    # Check if configuration file exists
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(
            f"Config file {CONFIG_FILE} is required. Run setup_wol.py to create it."
        )

    # Load and parse the JSON configuration file
    try:
        with open(CONFIG_FILE, 'r') as f:
            user_config = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Error parsing {CONFIG_FILE}: {e}") from e

    # Verify all required keys are present
    missing = [key for key in required_keys if key not in user_config]
    if missing:
        raise ValueError(f"Missing required config keys: {', '.join(missing)}")

    # Extract and validate MAC address
    mac = str(user_config["WOL_MAC_ADDRESS"]).strip()
    # Extract and validate site URL
    site = str(user_config["SITE_URL"]).strip()
    # Extract wait time (will validate as integer below)
    wait_raw = user_config["WAIT_TIME_SECONDS"]

    # Validate MAC address is not empty
    if not mac:
        raise ValueError("WOL_MAC_ADDRESS must be set in the config file.")
    
    # Validate site URL is not empty
    if not site:
        raise ValueError("SITE_URL must be set in the config file.")

    # Validate and convert wait time to integer
    try:
        wait = int(wait_raw)
    except (TypeError, ValueError) as e:
        raise ValueError("WAIT_TIME_SECONDS must be an integer.") from e

    # Ensure wait time is positive
    if wait <= 0:
        raise ValueError("WAIT_TIME_SECONDS must be greater than zero.")

    # Extract and validate port number
    port_raw = user_config["PORT"]
    try:
        port = int(port_raw)
    except (TypeError, ValueError) as e:
        raise ValueError("PORT must be an integer.") from e

    # Ensure port is within valid range (1-65535)
    if port <= 0 or port > 65535:
        raise ValueError("PORT must be between 1 and 65535.")

    # Log successful configuration load with timestamp
    print(f"[{time.strftime('%H:%M:%S')}] Loaded config from {CONFIG_FILE}")

    # Return validated configuration dictionary
    return {
        "WOL_MAC_ADDRESS": mac,
        "SITE_URL": site,
        "WAIT_TIME_SECONDS": wait,
        "PORT": port,
    }

# Load configuration at startup - will exit with error if config is invalid
config = load_config()

# Extract configuration values into module-level constants for easy access

# 1. MAC Address of the Server's Network Card (e.g., "00:1A:2B:3C:4D:5E")
#    This is the hardware address of the network interface to wake
WOL_MAC_ADDRESS = config["WOL_MAC_ADDRESS"]

# 2. The final URL of your site (e.g., "http://panel.yourdomain.com")
#    Users will be redirected here after the wait time elapses
SITE_URL = config["SITE_URL"]

# 3. Time (in seconds) to wait for the server to boot up
#    Should be long enough for the server to fully start and become accessible
WAIT_TIME_SECONDS = config["WAIT_TIME_SECONDS"]

# 4. Port for Flask to run on (e.g., 5000, 8080, 3000)
#    Remember to forward this port in your router if accessing externally
PORT = config["PORT"]

# =================================================================
#                     FLASK APPLICATION START
# =================================================================

# Initialize Flask application
app = Flask(__name__)

# =================================================================
#                    HTML WAITING PAGE TEMPLATE
# =================================================================
# This HTML page is displayed to users after triggering the WOL packet.
# Key features:
#   - Auto-refresh meta tag redirects to SITE_URL after WAIT_TIME_SECONDS
#   - CSS loading spinner animation for visual feedback
#   - Responsive design with centered container
#   - User-friendly messages explaining what's happening
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
    """
    Main endpoint that triggers Wake-on-LAN and displays the waiting page.
    
    When a user visits http://<server>:<port>/wake, this function:
      1. Sends a WOL magic packet to wake the sleeping server
      2. Returns an HTML page with auto-redirect after WAIT_TIME_SECONDS
    
    The magic packet is a special network message that tells the server's
    network card to power on the machine.
    
    Returns:
        Response: HTML waiting page (200) or error message (500)
    """
    
    # =================================================================
    # Step 1: Send the Wake-on-LAN Magic Packet
    # =================================================================
    # Uses the 'wakeonlan' command-line utility to send the magic packet
    try:
        # Execute: wakeonlan <MAC_ADDRESS>
        # check=True: raises CalledProcessError if command fails
        # capture_output=True: captures stdout/stderr for error reporting
        subprocess.run(['wakeonlan', WOL_MAC_ADDRESS], check=True, capture_output=True)
        print(f"[{time.strftime('%H:%M:%S')}] WOL Magic Packet sent to {WOL_MAC_ADDRESS}")
    
    except subprocess.CalledProcessError as e:
        # Command executed but failed (non-zero exit code)
        # This could happen if MAC address format is invalid
        error_message = f"WOL Error: Could not send packet. Check MAC address and 'wakeonlan' install: {e.stderr.decode()}"
        print(f"[{time.strftime('%H:%M:%S')}] {error_message}")
        return error_message, 500
    
    except FileNotFoundError:
        # The 'wakeonlan' command is not installed on the system
        # Installation varies by OS:
        #   - Termux: pkg install wakeonlan
        #   - Debian/Ubuntu: apt install wakeonlan
        #   - macOS: brew install wakeonlan
        error_message = "WOL Error: 'wakeonlan' command not found. Did you run 'pkg install wakeonlan' in Termux?"
        print(f"[{time.strftime('%H:%M:%S')}] {error_message}")
        return error_message, 500

    # =================================================================
    # Step 2: Return the HTML Waiting Page
    # =================================================================
    # The HTML page contains a meta refresh tag that will automatically
    # redirect the user's browser to SITE_URL after WAIT_TIME_SECONDS
    return Response(WAITING_PAGE_HTML, mimetype='text/html')

@app.route('/')
def home():
    """
    Root endpoint - informational page explaining how to use the gateway.
    
    This is displayed when users visit http://<server>:<port>/
    It provides instructions and a test link to the /wake endpoint.
    
    Returns:
        str: HTML content with usage instructions
    """
    
    # Construct the wake URL that users should access
    # Replace <Your-Public-IP-or-Domain> with your actual external address
    wake_link = f"http://<Your-Public-IP-or-Domain>/wake"
    
    return f"""
    <h1>WOL Gateway Running</h1>
    <p>The Python/Flask app is active on port 5000. </p>
    <p>To wake the server, please direct users to the <strong>/wake</strong> endpoint: <a href="/wake">Click here to test /wake</a></p>
    <p>Ensure your router's port forwarding is mapping your external access to this phone's IP on port 5000.</p>
    """

# =================================================================
#                     APPLICATION ENTRY POINT
# =================================================================
if __name__ == '__main__':
    # Start the Flask development server
    # host='0.0.0.0' - Binds to all network interfaces (allows external connections)
    #                  Change to '127.0.0.1' if only local access is needed
    # port=PORT - Uses the port specified in the config file
    # debug=False - Disables debug mode for production use
    #               Set to True during development for auto-reload and detailed errors
    
    print(f"[{time.strftime('%H:%M:%S')}] Flask App starting on http://0.0.0.0:{PORT}")
    print(f"[{time.strftime('%H:%M:%S')}] Waking MAC: {WOL_MAC_ADDRESS}, Redirect URL: {SITE_URL}")
    print(f"[{time.strftime('%H:%M:%S')}] Access the /wake endpoint to trigger WOL")
    
    app.run(host='0.0.0.0', port=PORT, debug=False)