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
import socket
from datetime import datetime, timedelta
from flask import Flask, redirect, Response, request, session

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
              SITE_URL, WAIT_TIME_SECONDS (max timeout), IP_ADDRESS (optional)
    
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
            raise ValueError(
                "No servers configured. Please run 'python3 setup_wol.py' to configure at least one server."
            )
        
        # Validate each server
        for idx, server in enumerate(servers):
            required_keys = ("NAME", "WOL_MAC_ADDRESS", "BROADCAST_ADDRESS", "SITE_URL")
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
            
            # Set default wait time if not provided (used as max timeout for pings)
            if "WAIT_TIME_SECONDS" not in server:
                server["WAIT_TIME_SECONDS"] = 60
            else:
                try:
                    wait = int(server["WAIT_TIME_SECONDS"])
                    if wait <= 0:
                        raise ValueError(f"Server #{idx+1}: WAIT_TIME_SECONDS must be greater than zero.")
                except (TypeError, ValueError) as e:
                    raise ValueError(f"Server #{idx+1}: WAIT_TIME_SECONDS must be a positive integer.") from e
            
            # Validate IP address if provided (optional field for TCP port checking)
            if "IP_ADDRESS" in server and server["IP_ADDRESS"]:
                ip_addr = server["IP_ADDRESS"].strip()
                if ip_addr:
                    server["IP_ADDRESS"] = ip_addr
                else:
                    server["IP_ADDRESS"] = None
            else:
                server["IP_ADDRESS"] = None
            
            # Set default port for TCP port checking (SSH port 22)
            if "CHECK_PORT" not in server:
                server["CHECK_PORT"] = 22
            else:
                try:
                    port = int(server["CHECK_PORT"])
                    if port <= 0 or port > 65535:
                        raise ValueError(f"Server #{idx+1}: CHECK_PORT must be between 1 and 65535.")
                except (TypeError, ValueError) as e:
                    raise ValueError(f"Server #{idx+1}: CHECK_PORT must be a valid port number.") from e
            
            # Set default values for optional fields (locked and pin)
            if "locked" not in server:
                server["locked"] = False
            if "pin" not in server:
                server["pin"] = ""
            
            # Initialize startup_times tracking (list of past startup durations)
            if "startup_times" not in server:
                server["startup_times"] = []
            elif not isinstance(server["startup_times"], list):
                server["startup_times"] = []
        
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

# Configure session to use cookies
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True if using HTTPS
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)

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
#                    SERVER UNLOCK TRACKING
# =================================================================

def is_server_unlocked(server_id):
    """
    Check if a server is unlocked for the current client session.
    
    Args:
        server_id (int): The index of the server
    
    Returns:
        bool: True if server is unlocked or lock expired, False otherwise
    """
    if 'unlocked_servers' not in session:
        return False
    
    unlocked = session['unlocked_servers']
    server_key = str(server_id)
    
    if server_key not in unlocked:
        return False
    
    # Check if unlock has expired (24 hours)
    unlock_time = unlocked[server_key]
    expiry_time = datetime.fromisoformat(unlock_time) + timedelta(hours=24)
    
    if datetime.now() >= expiry_time:
        # Expired - remove from session
        del unlocked[server_key]
        session.modified = True
        return False
    
    return True

def unlock_server(server_id):
    """
    Mark a server as unlocked for the current client session.
    
    Args:
        server_id (int): The index of the server to unlock
    """
    session.permanent = True
    
    if 'unlocked_servers' not in session:
        session['unlocked_servers'] = {}
    
    session['unlocked_servers'][str(server_id)] = datetime.now().isoformat()
    session.modified = True

# =================================================================
#                    HTML WAITING PAGE TEMPLATE
# =================================================================
# This function generates HTML pages dynamically for each server

def generate_pin_entry_page(server_name, server_id, error_message=None):
    """
    Generates a PIN entry page for locked servers.
    
    Args:
        server_name (str): Name of the server requiring PIN
        server_id (int): ID of the server
        error_message (str, optional): Error message to display
    
    Returns:
        str: HTML content for the PIN entry page
    """
    error_html = ""
    if error_message:
        error_html = f'<div class="error-message">{error_message}</div>'
    
    return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Enter PIN - {server_name}</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        :root {{
            --bg-color: #f0f0f0;
            --card-bg: #ffffff;
            --text-color: #333333;
            --heading-color: #2c3e50;
            --button-bg: #3498db;
            --button-hover: #2980b9;
            --border-color: #e0e0e0;
            --error-bg: #e74c3c;
            --shadow: rgba(0,0,0,0.1);
        }}
        [data-theme="dark"] {{
            --bg-color: #1a1a1a;
            --card-bg: #2d2d2d;
            --text-color: #e0e0e0;
            --heading-color: #e0e0e0;
            --button-bg: #3498db;
            --button-hover: #2980b9;
            --border-color: #404040;
            --error-bg: #c0392b;
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
        .container {{ 
            background: var(--card-bg); 
            padding: 40px; 
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
        .lock-icon {{
            font-size: 48px;
            color: var(--heading-color);
            margin-bottom: 20px;
        }}
        .form-group {{
            margin: 20px 0;
        }}
        input[type="password"] {{
            width: 100%;
            padding: 15px;
            font-size: 24px;
            text-align: center;
            border: 2px solid var(--border-color);
            border-radius: 5px;
            background: var(--card-bg);
            color: var(--text-color);
            letter-spacing: 8px;
        }}
        input[type="password"]:focus {{
            outline: none;
            border-color: var(--button-bg);
        }}
        .button {{ 
            background-color: var(--button-bg); 
            color: white; 
            padding: 15px 40px; 
            text-align: center; 
            text-decoration: none; 
            display: inline-block; 
            font-size: 16px; 
            margin: 20px 5px; 
            cursor: pointer; 
            border: none; 
            border-radius: 5px;
            transition: background-color 0.3s;
        }}
        .button:hover {{ background-color: var(--button-hover); }}
        .button.cancel {{ background-color: #95a5a6; }}
        .button.cancel:hover {{ background-color: #7f8c8d; }}
        .error-message {{
            background-color: var(--error-bg);
            color: white;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }}
        .help-text {{
            color: var(--text-color);
            font-size: 14px;
            margin-top: 10px;
            opacity: 0.7;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="lock-icon"><i class="fas fa-lock"></i></div>
        <h1>{server_name}</h1>
        {error_html}
        <p class="help-text">This server is locked. Please enter the PIN to unlock it.</p>
        <form method="POST" action="/wake/{server_id}">
            <div class="form-group">
                <input type="password" name="pin" id="pin" placeholder="Enter PIN" 
                       maxlength="10" pattern="[0-9]*" inputmode="numeric" 
                       autocomplete="off" required autofocus>
            </div>
            <button type="submit" class="button">Unlock</button>
            <a href="/" class="button cancel">Cancel</a>
        </form>
    </div>
    <script>
        const savedTheme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-theme', savedTheme);
    </script>
</body>
</html>
    """

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
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        :root {{
            --bg-color: #f0f0f0;
            --card-bg: #ffffff;
            --text-color: #333333;
            --heading-color: #2c3e50;
            --server-name-color: #3498db;
            --loader-bg: #f3f3f3;
            --loader-top: #3498db;
            --shadow: rgba(0,0,0,0.1);
        }}
        [data-theme="dark"] {{
            --bg-color: #1a1a1a;
            --card-bg: #2d2d2d;
            --text-color: #e0e0e0;
            --heading-color: #e0e0e0;
            --server-name-color: #5dade2;
            --loader-bg: #404040;
            --loader-top: #3498db;
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
        .container {{ 
            background: var(--card-bg); 
            padding: 30px; 
            border-radius: 10px; 
            box-shadow: 0 4px 8px var(--shadow); 
            display: inline-block;
            min-width: 400px;
            transition: background-color 0.3s;
        }}
        .start-icon {{
            font-size: 48px;
            color: var(--server-name-color);
            margin-bottom: 20px;
        }}
        h1 {{ 
            color: var(--heading-color); 
            margin: 20px 0;
        }}
        .server-name {{ color: var(--server-name-color); }}
        .loader {{ 
            border: 8px solid var(--loader-bg); 
            border-top: 8px solid var(--loader-top); 
            border-radius: 50%; 
            width: 50px; 
            height: 50px; 
            animation: spin 2s linear infinite; 
            margin: 20px auto; 
        }}
        @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
        p {{
            color: var(--text-color);
            line-height: 1.6;
        }}
        strong {{
            color: var(--heading-color);
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="start-icon"><i class="fas fa-power-off"></i></div>
        <h1>Starting <span class="server-name">{server_name}</span></h1>
        <div class="loader"></div>
        <p>Sending Wake-on-LAN signal. Please wait approximately <strong>{wait_time} seconds</strong>.</p>
        <p>You will be automatically redirected to your server.</p>
        <p>If the page fails to load, the server may still be booting. Please try refreshing.</p>
    </div>
    <script>
        const savedTheme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-theme', savedTheme);
    </script>
</body>
</html>
"""

def generate_ping_waiting_page(server_name, site_url, estimated_time, server_id):
    """
    Generates a waiting page that pings the server until it responds.
    
    Args:
        server_name (str): Name of the server being woken
        site_url (str): URL to redirect to when server is online
        estimated_time (int): Estimated seconds based on historical average (0 if no history)
        server_id (int): Server index for ping status endpoint
    
    Returns:
        str: HTML content for the ping-based waiting page
    """
    return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Starting {server_name}...</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        :root {{
            --bg-color: #f0f0f0;
            --card-bg: #ffffff;
            --text-color: #333333;
            --heading-color: #2c3e50;
            --server-name-color: #3498db;
            --loader-bg: #f3f3f3;
            --loader-top: #3498db;
            --success-color: #27ae60;
            --shadow: rgba(0,0,0,0.1);
        }}
        [data-theme="dark"] {{
            --bg-color: #1a1a1a;
            --card-bg: #2d2d2d;
            --text-color: #e0e0e0;
            --heading-color: #e0e0e0;
            --server-name-color: #5dade2;
            --loader-bg: #404040;
            --loader-top: #3498db;
            --success-color: #2ecc71;
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
        .container {{ 
            background: var(--card-bg); 
            padding: 30px; 
            border-radius: 10px; 
            box-shadow: 0 4px 8px var(--shadow); 
            display: inline-block;
            min-width: 400px;
            transition: background-color 0.3s;
        }}
        .start-icon {{
            font-size: 48px;
            color: var(--server-name-color);
            margin-bottom: 20px;
            transition: color 0.3s;
        }}
        .start-icon.success {{
            color: var(--success-color);
        }}
        h1 {{ 
            color: var(--heading-color); 
            margin: 20px 0;
        }}
        .server-name {{ color: var(--server-name-color); }}
        .loader {{ 
            border: 8px solid var(--loader-bg); 
            border-top: 8px solid var(--loader-top); 
            border-radius: 50%; 
            width: 50px; 
            height: 50px; 
            animation: spin 2s linear infinite; 
            margin: 20px auto; 
        }}
        @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
        p {{
            color: var(--text-color);
            line-height: 1.6;
        }}
        strong {{
            color: var(--heading-color);
        }}
        .status {{
            margin: 20px 0;
            padding: 10px;
            border-radius: 5px;
            background: var(--loader-bg);
        }}
        .status.online {{
            background: var(--success-color);
            color: white;
        }}
        .progress {{
            margin: 15px 0;
            font-size: 14px;
            color: var(--text-color);
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="start-icon" id="icon"><i class="fas fa-power-off"></i></div>
        <h1>Starting <span class="server-name">{server_name}</span></h1>
        <div class="loader" id="loader"></div>
        <div class="status" id="status">Sending Wake-on-LAN signal...</div>
        <p class="progress" id="progress">Waiting for server to respond...</p>
        <p id="info">Pinging server every 2 seconds. {'Estimated time: <strong>' + str(estimated_time) + ' seconds</strong>' if estimated_time > 0 else 'No estimated time available yet'}.</p>
    </div>
    <script>
        const savedTheme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-theme', savedTheme);
        
        const estimatedTime = {estimated_time};
        const serverId = {server_id};
        const siteUrl = "{site_url}";
        let elapsedTime = 0;
        let pingInterval;
        let hasLoggedStartup = false;
        
        function updateStatus(message, isOnline = false) {{
            const statusEl = document.getElementById('status');
            statusEl.textContent = message;
            if (isOnline) {{
                statusEl.classList.add('online');
                document.getElementById('icon').classList.add('success');
                document.getElementById('icon').innerHTML = '<i class="fas fa-check-circle"></i>';
                document.getElementById('loader').style.display = 'none';
            }}
        }}
        
        function updateProgress() {{
            const progressEl = document.getElementById('progress');
            if (estimatedTime > 0) {{
                progressEl.textContent = `Time elapsed: ${{elapsedTime}}s (estimated: ${{estimatedTime}}s)`;
            }} else {{
                progressEl.textContent = `Time elapsed: ${{elapsedTime}}s`;
            }}
        }}
        
        function checkServerStatus() {{
            fetch(`/ping_status/${{serverId}}?elapsed=${{elapsedTime}}`)
                .then(response => response.json())
                .then(data => {{
                    if (data.online) {{
                        // Server is online!
                        clearInterval(pingInterval);
                        updateStatus('Server is online! Redirecting...', true);
                        setTimeout(() => {{
                            window.location.href = data.redirect_url;
                        }}, 1500);
                    }} else if (data.no_ip) {{
                        // No IP configured, shouldn't happen but fallback anyway
                        clearInterval(pingInterval);
                        updateStatus('Redirecting...');
                        setTimeout(() => {{
                            window.location.href = data.redirect_url;
                        }}, 2000);
                    }} else {{
                        elapsedTime += 2;
                        updateProgress();
                    }}
                }})
                .catch(error => {{
                    console.error('Ping check failed:', error);
                    elapsedTime += 2;
                    updateProgress();
                }});
        }}
        
        // Start checking immediately
        updateProgress();
        checkServerStatus();
        
        // Then check every 2 seconds
        pingInterval = setInterval(checkServerStatus, 2000);
    </script>
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

def log_startup_time(server_id, startup_seconds):
    """
    Logs a server's startup time and updates the config file with rolling average.
    Keeps last 10 startup times for calculating average.
    
    Args:
        server_id (int): Server index
        startup_seconds (int): Time in seconds it took for server to respond
    """
    try:
        # Load current config
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        
        servers = config.get('SERVERS', [])
        if server_id < 0 or server_id >= len(servers):
            return
        
        server = servers[server_id]
        
        # Initialize or get existing startup times
        if 'startup_times' not in server:
            server['startup_times'] = []
        
        # Add new time
        server['startup_times'].append(startup_seconds)
        
        # Keep only last 10 entries
        if len(server['startup_times']) > 10:
            server['startup_times'] = server['startup_times'][-10:]
        
        # Calculate average
        avg_time = sum(server['startup_times']) // len(server['startup_times'])
        
        # Save updated config
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        
        print(f"[{time.strftime('%H:%M:%S')}] Server '{server['NAME']}' startup time: {startup_seconds}s (avg: {avg_time}s)")
        
        # Update the in-memory SERVERS list
        SERVERS[server_id]['startup_times'] = server['startup_times']
        
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] Error logging startup time: {e}")

@app.route('/ping_status/<server_id>')
def ping_status(server_id):
    """
    Endpoint to check if a server is responding via TCP port check.
    Returns JSON with status and logs startup time when server comes online.
    
    Args:
        server_id (str): The index (0-based) of the server to check
    
    Returns:
        JSON: {"online": true/false, "redirect_url": "...", "startup_time": seconds}
    """
    try:
        idx = int(server_id)
        if idx < 0 or idx >= len(SERVERS):
            return {"error": "Invalid server ID"}, 400
    except ValueError:
        return {"error": "Server ID must be a number"}, 400
    
    server = SERVERS[idx]
    ip_address = server.get("IP_ADDRESS")
    check_port = server.get("CHECK_PORT", 22)
    site_url = server["SITE_URL"]
    
    # Ensure site_url has a proper scheme
    if not site_url.startswith(('http://', 'https://')):
        site_url = 'http://' + site_url
    
    if not ip_address:
        # No IP configured, can't check port
        return {"online": False, "no_ip": True, "redirect_url": site_url}
    
    # Check if port is open (TCP connection test)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((ip_address, check_port))
        sock.close()
        
        online = (result == 0)
        
        # If server just came online, check if we should log the startup time
        if online:
            startup_time = request.args.get('elapsed', type=int)
            if startup_time:
                # Log this startup time
                log_startup_time(idx, startup_time)
        
        return {"online": online, "redirect_url": site_url}
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] Port check error for {ip_address}:{check_port}: {e}")
        return {"online": False, "error": str(e), "redirect_url": site_url}

@app.route('/wake/<server_id>', methods=['GET', 'POST'])
def wake_server_and_redirect(server_id):
    """
    Endpoint that triggers Wake-on-LAN for a specific server and displays the waiting page.
    
    When a user visits http://<server>:<port>/wake/<server_id>, this function:
      1. Finds the server configuration by ID (0-based index)
      2. If server is locked, prompts for PIN (GET) or validates PIN (POST)
      3. Sends a WOL magic packet to wake the sleeping server
      4. Returns an HTML page with auto-redirect after server's wait time
    
    Args:
        server_id (str): The index (0-based) of the server to wake
    
    Returns:
        Response: HTML waiting page (200), PIN entry page, or error message (400/500)
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
    
    # Ensure site_url has a proper scheme (http:// or https://)
    if not site_url.startswith(('http://', 'https://')):
        site_url = 'http://' + site_url
    
    wait_time = server["WAIT_TIME_SECONDS"]
    is_locked = server.get("locked", False)
    server_pin = server.get("pin", "")
    
    # Check if server is locked and requires PIN
    if is_locked and server_pin:
        # Check if server is already unlocked in this session
        unlocked = is_server_unlocked(idx)
        print(f"[{time.strftime('%H:%M:%S')}] Server {idx} locked={is_locked}, unlocked_in_session={unlocked}, method={request.method}")
        
        if not unlocked:
            if request.method == 'GET':
                # Show PIN entry page
                return Response(generate_pin_entry_page(server_name, idx), mimetype='text/html')
            elif request.method == 'POST':
                # Validate PIN
                entered_pin = request.form.get('pin', '').strip()
                if entered_pin != server_pin:
                    # Incorrect PIN - show error
                    return Response(
                        generate_pin_entry_page(server_name, idx, "Incorrect PIN. Please try again."),
                        mimetype='text/html'
                    ), 401
                # PIN is correct, unlock the server for 24 hours and redirect to home
                unlock_server(idx)
                print(f"[{time.strftime('%H:%M:%S')}] Server {idx} unlocked successfully")
                return redirect('/')
        # Server is unlocked in session, proceed to wake it
        print(f"[{time.strftime('%H:%M:%S')}] Server {idx} already unlocked, proceeding to wake")
    
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
    ip_address = server.get("IP_ADDRESS")
    
    if ip_address:
        # Use ping-based waiting page that actively checks if server is online
        # Calculate estimated time from historical data
        startup_times = server.get("startup_times", [])
        if startup_times:
            estimated_time = sum(startup_times) // len(startup_times)
        else:
            estimated_time = 0  # No history yet
        return Response(generate_ping_waiting_page(server_name, site_url, estimated_time, idx), mimetype='text/html')
    else:
        # Use traditional time-based waiting page
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
        is_locked = server.get("locked", False)
        server_is_unlocked = is_server_unlocked(idx)
        
        if is_locked and not server_is_unlocked:
            # Server is locked - show grey button with padlock
            button_class = "button locked"
            button_text = '<i class="fas fa-lock"></i> Locked'
        else:
            # Server is unlocked or not locked - show normal button
            button_class = "button"
            button_text = "Start Server"
        
        server_buttons_html += f"""
        <div class="server-card">
            <h2>{server_name}</h2>
            <a href="/wake/{idx}" class="{button_class}">{button_text}</a>
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
        .button.locked {{
            background-color: #95a5a6;
            color: #ffffff;
            opacity: 0.7;
        }}
        .button.locked:hover {{
            background-color: #7f8c8d;
            opacity: 0.85;
        }}
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
        <h1><i class="fas fa-server"></i> Server Gateway</h1>
        {server_buttons_html}
        <div style="margin-top: 25px; padding-top: 20px; border-top: 1px solid var(--border-color);">
            <a href="/admin" class="button admin"><i class="fas fa-cog"></i> Admin Panel</a>
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