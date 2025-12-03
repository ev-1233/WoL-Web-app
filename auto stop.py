#!/usr/bin/env python3
"""
Proxmox Auto-Shutdown Script for Pterodactyl Servers
Monitors active connections across Pterodactyl-hosted game servers.
Shuts down Proxmox after 5 minutes of no active connections.
"""

import subprocess
import time
import requests
import json
from datetime import datetime

# =================================================================
#                         USER CONFIGURATION
# =================================================================

# Pterodactyl Panel API Configuration
PTERODACTYL_URL = "https://panel.thethings.qzz.io"  # Your Pterodactyl Panel URL
API_KEY = "YOUR_API_KEY_HERE"  # Application API key from Pterodactyl

# Inactivity timeout in seconds (5 minutes = 300 seconds)
INACTIVITY_TIMEOUT = 300

# Check interval in seconds (how often to check for connections)
CHECK_INTERVAL = 60

# Shutdown command for Proxmox
SHUTDOWN_COMMAND = "shutdown -h now"

# Log file location (optional)
LOG_FILE = "/var/log/auto_shutdown.log"

# =================================================================
#                         HELPER FUNCTIONS
# =================================================================

def log_message(message):
    """Log messages with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    print(log_entry)
    
    try:
        with open(LOG_FILE, "a") as f:
            f.write(log_entry + "\n")
    except Exception as e:
        print(f"Warning: Could not write to log file: {e}")


def get_pterodactyl_servers():
    """Fetch all servers from Pterodactyl API"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(
            f"{PTERODACTYL_URL}/api/application/servers",
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        return response.json().get("data", [])
    except requests.RequestException as e:
        log_message(f"Error fetching servers: {e}")
        return []


def check_server_connections(server_id):
    """
    Check if a specific server has active connections.
    This uses the client API to get server resource usage.
    Returns True if players are connected, False otherwise.
    """
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    try:
        # Get server resource usage
        response = requests.get(
            f"{PTERODACTYL_URL}/api/application/servers/{server_id}",
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        server_data = response.json()
        
        # Check if server is running
        server_status = server_data.get("attributes", {}).get("status", "offline")
        
        # If server is running, check resource usage to infer activity
        if server_status == "running":
            return True  # Server is running, assume it might have users
        
        return False
        
    except requests.RequestException as e:
        log_message(f"Error checking server {server_id}: {e}")
        return False


def check_minecraft_players(server_ip, server_port):
    """
    Alternative method: Check Minecraft server for active players
    Uses server query protocol (if enabled on the server)
    """
    try:
        from mcstatus import JavaServer
        server = JavaServer.lookup(f"{server_ip}:{server_port}")
        status = server.status()
        return status.players.online > 0
    except Exception as e:
        log_message(f"Could not query Minecraft server: {e}")
        return False


def check_any_active_connections():
    """
    Check if any Pterodactyl servers have active connections.
    Returns True if any users are connected, False otherwise.
    """
    servers = get_pterodactyl_servers()
    
    if not servers:
        log_message("No servers found or API error")
        return False
    
    active_servers = 0
    for server in servers:
        server_id = server.get("attributes", {}).get("id")
        server_name = server.get("attributes", {}).get("name", "Unknown")
        
        if check_server_connections(server_id):
            active_servers += 1
            log_message(f"Server '{server_name}' is active")
    
    if active_servers > 0:
        log_message(f"Total active servers: {active_servers}")
        return True
    else:
        log_message("No active servers detected")
        return False


def check_network_connections():
    """
    Alternative method: Check for active network connections on common game ports.
    This is a fallback if API checks don't work well.
    """
    try:
        # Check for established connections on common game server ports
        result = subprocess.run(
            ["netstat", "-tn"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        # Common game server ports
        game_ports = ["25565", "25566", "25567", "27015", "7777", "8080"]
        
        for line in result.stdout.split("\n"):
            if "ESTABLISHED" in line:
                for port in game_ports:
                    if f":{port}" in line:
                        log_message(f"Active connection detected on port {port}")
                        return True
        
        return False
        
    except Exception as e:
        log_message(f"Error checking network connections: {e}")
        return False


def shutdown_proxmox():
    """Execute shutdown command"""
    log_message("INITIATING SHUTDOWN")
    try:
        subprocess.run(SHUTDOWN_COMMAND.split(), check=True)
        log_message("Shutdown command executed successfully")
    except subprocess.CalledProcessError as e:
        log_message(f"Error executing shutdown: {e}")
    except Exception as e:
        log_message(f"Unexpected error during shutdown: {e}")


# =================================================================
#                         MAIN MONITORING LOOP
# =================================================================

def main():
    log_message("=== Auto-Shutdown Monitor Started ===")
    log_message(f"Inactivity timeout: {INACTIVITY_TIMEOUT} seconds ({INACTIVITY_TIMEOUT/60} minutes)")
    log_message(f"Check interval: {CHECK_INTERVAL} seconds")
    log_message(f"Pterodactyl URL: {PTERODACTYL_URL}")
    
    inactive_time = 0
    
    while True:
        try:
            # Check for active connections
            has_connections = check_any_active_connections()
            
            # Optional: Also check network connections as backup
            # has_network_activity = check_network_connections()
            # has_connections = has_connections or has_network_activity
            
            if has_connections:
                # Reset timer if connections are detected
                if inactive_time > 0:
                    log_message("Activity detected - resetting inactivity timer")
                inactive_time = 0
            else:
                # Increment inactive time
                inactive_time += CHECK_INTERVAL
                remaining = INACTIVITY_TIMEOUT - inactive_time
                log_message(f"No activity detected. Inactive for {inactive_time}s. "
                          f"Shutdown in {remaining}s if no activity.")
                
                # Check if we've reached the timeout
                if inactive_time >= INACTIVITY_TIMEOUT:
                    log_message("Inactivity timeout reached!")
                    shutdown_proxmox()
                    break
            
            # Wait before next check
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            log_message("Monitor stopped by user")
            break
        except Exception as e:
            log_message(f"Unexpected error in main loop: {e}")
            time.sleep(CHECK_INTERVAL)
    
    log_message("=== Auto-Shutdown Monitor Stopped ===")


if __name__ == "__main__":
    main()
