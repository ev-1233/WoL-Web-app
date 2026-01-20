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
import secrets
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
        dict: Validated configuration with keys: PORT, SERVERS (array)
              Each server has: NAME, WOL_MAC_ADDRESS, BROADCAST_ADDRESS, 
              SITE_URL, WAIT_TIME_SECONDS
    
    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid or missing required fields
    """
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

    # Check if this is the new format (with SERVERS array) or old format
    if "SERVERS" in user_config:
        # New multi-server format
        servers = user_config.get("SERVERS", [])
        
        if not servers or not isinstance(servers, list):
            raise ValueError("SERVERS must be a non-empty array.")
        
        # Validate each server
        for idx, server in enumerate(servers):
            required_keys = ("NAME", "WOL_MAC_ADDRESS", "BROADCAST_ADDRESS", "SITE_URL", "WAIT_TIME_SECONDS")
            missing = [key for key in required_keys if key not in server]
            if missing:
                raise ValueError(f"Server #{idx+1} missing required keys: {', '.join(missing)}")
            
            # Validate each field
            if not server["NAME"].strip():
                raise ValueError(f"Server #{idx+1}: NAME must not be empty.")
            if not server["WOL_MAC_ADDRESS"].strip():
                raise ValueError(f"Server #{idx+1}: WOL_MAC_ADDRESS must not be empty.")
            if not server["BROADCAST_ADDRESS"].strip():
                raise ValueError(f"Server #{idx+1}: BROADCAST_ADDRESS must not be empty.")
            if not server["SITE_URL"].strip():
                raise ValueError(f"Server #{idx+1}: SITE_URL must not be empty.")
            
            try:
                wait = int(server["WAIT_TIME_SECONDS"])
                if wait <= 0:
                    raise ValueError(f"Server #{idx+1}: WAIT_TIME_SECONDS must be greater than zero.")
            except (TypeError, ValueError) as e:
                raise ValueError(f"Server #{idx+1}: WAIT_TIME_SECONDS must be a positive integer.") from e
        
        # Extract and validate port number
        port_raw = user_config.get("PORT")
        try:
            port = int(port_raw)
        except (TypeError, ValueError) as e:
            raise ValueError("PORT must be an integer.") from e

        # Ensure port is within valid range (1-65535)
        if port <= 0 or port > 65535:
            raise ValueError("PORT must be between 1 and 65535.")
        
        print(f"[{time.strftime('%H:%M:%S')}] Loaded config from {CONFIG_FILE}")
        print(f"[{time.strftime('%H:%M:%S')}] Found {len(servers)} server(s)")
        
        return {
            "PORT": port,
            "SERVERS": servers
        }
    
    else:
        # Old single-server format - migrate to new format
        print(f"[{time.strftime('%H:%M:%S')}] Warning: Old config format detected. Please run setup_wol.py to update.")
        required_keys = ("WOL_MAC_ADDRESS", "BROADCAST_ADDRESS", "SITE_URL", "WAIT_TIME_SECONDS", "PORT")
        missing = [key for key in required_keys if key not in user_config]
        if missing:
            raise ValueError(f"Missing required config keys: {', '.join(missing)}")
        
        # Create a single server entry
        servers = [{
            "NAME": "Default Server",
            "WOL_MAC_ADDRESS": str(user_config["WOL_MAC_ADDRESS"]).strip(),
            "BROADCAST_ADDRESS": str(user_config["BROADCAST_ADDRESS"]).strip(),
            "SITE_URL": str(user_config["SITE_URL"]).strip(),
            "WAIT_TIME_SECONDS": int(user_config["WAIT_TIME_SECONDS"])
        }]
        
        port = int(user_config["PORT"])
        
        print(f"[{time.strftime('%H:%M:%S')}] Loaded legacy config from {CONFIG_FILE}")
        
        return {
            "PORT": port,
            "SERVERS": servers
        }

# Load configuration at startup - will exit with error if config is invalid
config = load_config()

# Extract configuration values into module-level constants for easy access

# Port for Flask to run on (e.g., 5000, 8080, 3000)
# Remember to forward this port in your router if accessing externally
PORT = config["PORT"]

# Array of server configurations
# Each server has: NAME, WOL_MAC_ADDRESS, BROADCAST_ADDRESS, SITE_URL, WAIT_TIME_SECONDS
SERVERS = config["SERVERS"]

# =================================================================
#                     FLASK APPLICATION START
# =================================================================

# Initialize Flask application
app = Flask(__name__)

# Set session secret key for admin panel
app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))

# Import and register admin panel if enabled
try:
    from admin_panel import admin_bp, load_admin_config
    admin_config = load_admin_config()
    if admin_config.get('admin_enabled', False):
        app.register_blueprint(admin_bp)
        print(f"[{time.strftime('%H:%M:%S')}] Admin panel enabled at /admin")
except ImportError:
    print(f"[{time.strftime('%H:%M:%S')}] Admin panel module not found")
except Exception as e:
    print(f"[{time.strftime('%H:%M:%S')}] Error loading admin panel: {e}")

# =================================================================
#                    HTML WAITING PAGE TEMPLATE
# =================================================================
# This function generates HTML pages dynamically for each server

def generate_waiting_page(server_name, site_url, wait_time):
    """
    Generates a waiting page HTML for a specific server.
    
    Args:
        server_name (str): Name of the server being woken
        site_url (str): URL to redirect to after wait time
        wait_time (int): Seconds to wait before redirecting
    
    Returns:
        str: HTML content for the waiting page
    """
    return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Starting {server_name}...</title>
    <meta http-equiv="refresh" content="{wait_time};url={site_url}">
    <style>
        body {{ font-family: sans-serif; text-align: center; margin-top: 50px; background-color: #f0f0f0; }}
        .container {{ background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); display: inline-block; }}
        h1 {{ color: #333; }}
        .server-name {{ color: #3498db; }}
        .loader {{ border: 8px solid #f3f3f3; border-top: 8px solid #3498db; border-radius: 50%; width: 50px; height: 50px; animation: spin 2s linear infinite; margin: 20px auto; }}
        @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 Starting <span class="server-name">{server_name}</span>...</h1>
        <div class="loader"></div>
        <p>Sending Wake-on-LAN signal. Please wait approximately <strong>{wait_time} seconds</strong>.</p>
        <p>You will be automatically redirected to your server.</p>
        <p>If the page fails to load, the server may still be booting. Please try refreshing.</p>
    </div>
</body>
</html>
"""

def find_wakeonlan_command():
    """
    Finds the wakeonlan command in various possible locations.
    
    When running with sudo, the PATH may not include user's local bin directories,
    so we need to check multiple possible locations.
    
    Returns:
        str or None: Full path to wakeonlan command, or None if not found
    """
    # Possible locations for wakeonlan command
    possible_paths = [
        'wakeonlan',  # Try PATH first
        '/usr/bin/wakeonlan',
        '/usr/local/bin/wakeonlan',
        '/bin/wakeonlan',
    ]
    
    # Also check user's local bin (get the actual user even when running with sudo)
    if 'SUDO_USER' in os.environ:
        # Running with sudo, get the real user's home directory
        sudo_user = os.environ['SUDO_USER']
        user_local_bin = f'/home/{sudo_user}/.local/bin/wakeonlan'
        possible_paths.insert(1, user_local_bin)
    else:
        # Not running with sudo, check current user's local bin
        user_home = os.path.expanduser('~')
        user_local_bin = os.path.join(user_home, '.local', 'bin', 'wakeonlan')
        possible_paths.insert(1, user_local_bin)
    
    # Try each path
    for cmd_path in possible_paths:
        try:
            # Check if it's just a command name (try 'which')
            if '/' not in cmd_path:
                result = subprocess.run(['which', cmd_path], capture_output=True, text=True)
                if result.returncode == 0:
                    return cmd_path
            # Check if it's a full path that exists
            elif os.path.isfile(cmd_path) and os.access(cmd_path, os.X_OK):
                return cmd_path
        except Exception:
            continue
    
    return None

@app.route('/wake/<server_id>', methods=['GET'])
def wake_server_and_redirect(server_id):
    """
    Endpoint that triggers Wake-on-LAN for a specific server and displays the waiting page.
    
    When a user visits http://<server>:<port>/wake/<server_id>, this function:
      1. Finds the server configuration by ID (0-based index)
      2. Sends a WOL magic packet to wake the sleeping server
      3. Returns an HTML page with auto-redirect after server's wait time
    
    Args:
        server_id (str): The index (0-based) of the server to wake
    
    Returns:
        Response: HTML waiting page (200) or error message (400/500)
    """
    
    # Validate server_id
    try:
        idx = int(server_id)
        if idx < 0 or idx >= len(SERVERS):
            return f"Error: Invalid server ID. Must be between 0 and {len(SERVERS)-1}.", 400
    except ValueError:
        return "Error: Server ID must be a number.", 400
    
    # Get the server configuration
    server = SERVERS[idx]
    server_name = server["NAME"]
    mac_address = server["WOL_MAC_ADDRESS"]
    broadcast_address = server["BROADCAST_ADDRESS"]
    site_url = server["SITE_URL"]
    wait_time = server["WAIT_TIME_SECONDS"]
    
    # =================================================================
    # Step 1: Send the Wake-on-LAN Magic Packet
    # =================================================================
    # Find the wakeonlan command (may be in different locations)
    wakeonlan_cmd = find_wakeonlan_command()
    
    if not wakeonlan_cmd:
        error_message = "WOL Error: 'wakeonlan' command not found. Please install it:\n"
        error_message += "  Debian/Ubuntu: sudo apt-get install wakeonlan\n"
        error_message += "  Fedora/RHEL: sudo dnf install wol\n"
        error_message += "  Or via pip: pip3 install --user wakeonlan"
        print(f"[{time.strftime('%H:%M:%S')}] {error_message}")
        return error_message, 500
    
    # Uses the 'wakeonlan' command-line utility to send the magic packet
    try:
        # Execute: wakeonlan -i <BROADCAST_ADDRESS> <MAC_ADDRESS>
        # -i flag specifies the broadcast address to send the packet to
        # check=True: raises CalledProcessError if command fails
        # capture_output=True: captures stdout/stderr for error reporting
        subprocess.run([wakeonlan_cmd, '-i', broadcast_address, mac_address], check=True, capture_output=True)
        print(f"[{time.strftime('%H:%M:%S')}] WOL packet sent to '{server_name}' ({mac_address}) via {broadcast_address} using {wakeonlan_cmd}")
    
    except subprocess.CalledProcessError as e:
        # Command executed but failed (non-zero exit code)
        # This could happen if MAC address format is invalid
        error_message = f"WOL Error: Could not send packet. Check MAC address: {e.stderr.decode()}"
        print(f"[{time.strftime('%H:%M:%S')}] {error_message}")
        return error_message, 500
    
    except Exception as e:
        # Any other error (shouldn't happen since we checked for command existence)
        error_message = f"WOL Error: Unexpected error: {str(e)}"
        print(f"[{time.strftime('%H:%M:%S')}] {error_message}")
        return error_message, 500

    # =================================================================
    # Step 2: Return the HTML Waiting Page
    # =================================================================
    # The HTML page contains a meta refresh tag that will automatically
    # redirect the user's browser to site_url after wait_time seconds
    return Response(generate_waiting_page(server_name, site_url, wait_time), mimetype='text/html')

@app.route('/')
def home():
    """
    Root endpoint - landing page with buttons to start servers.
    
    This is displayed when users visit http://<server>:<port>/
    It provides a button for each configured server.
    
    Returns:
        Response: HTML landing page
    """
    
    # Generate HTML for server buttons
    server_buttons_html = ""
    for idx, server in enumerate(SERVERS):
        server_name = server["NAME"]
        wait_time = server["WAIT_TIME_SECONDS"]
        server_buttons_html += f"""
        <div class="server-card">
            <h2>{server_name}</h2>
            <a href="/wake/{idx}" class="button">Start Server</a>
            <p class="server-info">Wait time: ~{wait_time} seconds</p>
        </div>
        """
    
    landing_page_html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Server Gateway</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        :root {{
            --bg-color: #f0f0f0;
            --card-bg: #ffffff;
            --text-color: #333333;
            --heading-color: #2c3e50;
            --button-bg: #3498db;
            --button-hover: #2980b9;
            --admin-button-bg: #9b59b6;
            --admin-button-hover: #8e44ad;
            --border-color: #e0e0e0;
            --server-card-bg: #f9f9f9;
            --shadow: rgba(0,0,0,0.1);
        }}
        [data-theme="dark"] {{
            --bg-color: #1a1a1a;
            --card-bg: #2d2d2d;
            --text-color: #e0e0e0;
            --heading-color: #e0e0e0;
            --button-bg: #3498db;
            --button-hover: #2980b9;
            --admin-button-bg: #9b59b6;
            --admin-button-hover: #8e44ad;
            --border-color: #404040;
            --server-card-bg: #3d3d3d;
            --shadow: rgba(0,0,0,0.3);
        }}
        body {{ 
            font-family: sans-serif; 
            text-align: center; 
            margin-top: 50px; 
            background-color: var(--bg-color);
            color: var(--text-color);
            transition: background-color 0.3s, color 0.3s;
        }}
        .theme-toggle {{
            position: fixed;
            top: 20px;
            left: 20px;
            background: none;
            border: none;
            font-size: 28px;
            cursor: pointer;
            z-index: 1000;
            color: var(--text-color);
            opacity: 0.7;
            transition: opacity 0.3s;
        }}
        .theme-toggle:hover {{
            opacity: 1;
        }}
        .container {{ 
            background: var(--card-bg); 
            padding: 30px; 
            border-radius: 10px; 
            box-shadow: 0 4px 8px var(--shadow); 
            display: inline-block; 
            min-width: 400px;
            transition: background-color 0.3s;
        }}
        h1 {{ 
            color: var(--heading-color); 
            margin-bottom: 30px;
        }}
        .server-card {{ 
            background: var(--server-card-bg); 
            padding: 20px; 
            margin: 15px 0; 
            border-radius: 8px; 
            border: 1px solid var(--border-color);
            transition: background-color 0.3s;
        }}
        .server-card h2 {{ 
            color: var(--heading-color); 
            margin: 0 0 15px 0; 
            font-size: 20px; 
        }}
        .button {{ 
            background-color: var(--button-bg); 
            color: white; 
            padding: 12px 28px; 
            text-align: center; 
            text-decoration: none; 
            display: inline-block; 
            font-size: 16px; 
            margin: 10px 2px; 
            cursor: pointer; 
            border: none; 
            border-radius: 5px;
            transition: background-color 0.3s;
        }}
        .button:hover {{ background-color: var(--button-hover); }}
        .button.admin {{ 
            background-color: var(--admin-button-bg); 
            margin-top: 20px;
        }}
        .button.admin:hover {{ background-color: var(--admin-button-hover); }}
        .server-info {{ 
            color: var(--text-color); 
            font-size: 13px; 
            margin: 10px 0 0 0;
            opacity: 0.7;
        }}
        .footer {{ 
            color: var(--text-color); 
            font-size: 12px; 
            margin-top: 30px;
            opacity: 0.6;
        }}
    </style>
</head>
<body>
    <button class="theme-toggle" onclick="toggleTheme()" title="Toggle dark mode"><i class="fas fa-moon"></i></button>
    <div class="container">
        <h1>🖥️ Server Gateway</h1>
        {server_buttons_html}
        <div style="margin-top: 25px; padding-top: 20px; border-top: 1px solid var(--border-color);">
            <a href="/admin" class="button admin">⚙️ Admin Panel</a>
        </div>
        <p class="footer">
            {len(SERVERS)} server{'s' if len(SERVERS) != 1 else ''} configured
        </p>
    </div>
    <script>
        function toggleTheme() {{
            const html = document.documentElement;
            const currentTheme = html.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            html.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeIcon();
        }}
        function updateThemeIcon() {{
            const theme = document.documentElement.getAttribute('data-theme');
            const toggle = document.querySelector('.theme-toggle i');
            toggle.className = theme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
        }}
        const savedTheme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-theme', savedTheme);
        updateThemeIcon();
    </script>
</body>
</html>
    """
    
    return Response(landing_page_html, mimetype='text/html')


@app.route('/health')
def health_check():
    """
    Health check endpoint for Docker and monitoring.
    
    Returns:
        Response: JSON response with status
    """
    return {"status": "ok", "servers": len(SERVERS)}, 200

# =================================================================
#                     APPLICATION ENTRY POINT
# =================================================================
if __name__ == '__main__':
    # Start the Flask development server
    # host='0.0.0.0' - Binds to all network interfaces (allows external connections)
    #                  Change to '127.0.0.1' if only local access is needed
    # port=PORT - Uses the port specified in the config file
    # debug - Controlled by FLASK_ENV environment variable
    #         Only enables if FLASK_ENV=development
    #         Defaults to False (production-safe)
    
    # Check environment variable for debug mode (safe default)
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    
    print(f"[{time.strftime('%H:%M:%S')}] Flask App starting on http://0.0.0.0:{PORT}")
    print(f"[{time.strftime('%H:%M:%S')}] Debug mode: {debug_mode}")
    print(f"[{time.strftime('%H:%M:%S')}] Configured {len(SERVERS)} server(s):")
    for idx, server in enumerate(SERVERS):
        print(f"[{time.strftime('%H:%M:%S')}]   {idx}. {server['NAME']} - MAC: {server['WOL_MAC_ADDRESS']}")
    print(f"[{time.strftime('%H:%M:%S')}] Access the root page to see all servers")
    
    app.run(host='0.0.0.0', port=PORT, debug=debug_mode, use_reloader=debug_mode)