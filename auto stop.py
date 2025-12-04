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
from datetime import datetime, time as dt_time

# =================================================================
#                         USER CONFIGURATION
# =================================================================

# Pterodactyl Panel API Configuration
PTERODACTYL_URL = "https://panel.thethings.qzz.io"  # Your Pterodactyl Panel URL
API_KEY = "ptla_vXHi5hrHcUosQbB68PTGULuVEFmlnSZsBx6GFsTkqgz"  # Application API key from Pterodactyl

# Server IPs and Ports to monitor (from your setup)
MONITOR_IPS = ["192.168.86.45"]  # Internal IP of your game servers
MONITOR_PORTS = ["25565", "24454", "8100", "19132", "8080", "2022"]  # Game servers + web panel ports

# Game server VM SSH details (to check connections remotely)
GAME_SERVER_VM_IP = "192.168.86.45"
GAME_SERVER_VM_USER = "ev"  # Non-root user on game server VM

# Minecraft server log path (adjust if needed)
MINECRAFT_LOG_PATH = "/var/lib/pterodactyl/volumes/9ba78b05-6302-4952-b337-b9719fcdfbdd/logs/latest.log"

# Inactivity timeout in seconds (5 minutes = 300 seconds)
INACTIVITY_TIMEOUT = 300

# Check interval in seconds (how often to check for connections)
CHECK_INTERVAL = 60

# Shutdown command for Proxmox
SHUTDOWN_COMMAND = "shutdown -h now"

# SSL verification (set to False if using self-signed certificate)
VERIFY_SSL = False

# Log file location (optional)
LOG_FILE = "./auto_shutdown.log"

# =================================================================
#                         HELPER FUNCTIONS
# =================================================================

def is_within_monitoring_hours():
    """
    Check if current time is within monitoring hours.
    Weekdays (Mon-Fri): 22:00-15:00 (10 PM to 3 PM next day)
    Weekends (Sat-Sun): 21:30-07:30 (9:30 PM to 7:30 AM next day)
    Returns True if within monitoring hours, False otherwise.
    """
    now = datetime.now()
    current_time = now.time()
    current_day = now.weekday()  # Monday=0, Sunday=6
    
    # Check if it's a weekday (Monday-Friday: 0-4)
    if current_day < 5:  # Weekday
        start_time = dt_time(22, 0)  # 10 PM
        end_time = dt_time(15, 0)    # 3 PM
    else:  # Weekend (Saturday-Sunday: 5-6)
        start_time = dt_time(21, 30)  # 9:30 PM
        end_time = dt_time(7, 30)     # 7:30 AM
    
    # Handle overnight monitoring (start > end means it crosses midnight)
    if start_time > end_time:
        # We're in monitoring window if current time is after start OR before end
        in_monitoring_window = current_time >= start_time or current_time <= end_time
    else:
        # Normal case: monitoring window within same day
        in_monitoring_window = start_time <= current_time <= end_time
    
    return in_monitoring_window


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
            timeout=10,
            verify=VERIFY_SSL
        )
        response.raise_for_status()
        return response.json().get("data", [])
    except requests.RequestException as e:
        log_message(f"Error fetching servers: {e}")
        return []


def check_server_connections(server_id):
    """
    Check if a specific server has active connections.
    Returns True if server is running (players might be connected), False otherwise.
    Note: This doesn't give exact player count, just checks if server is online.
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
            timeout=10,
            verify=VERIFY_SSL
        )
        response.raise_for_status()
        server_data = response.json()
        
        # Check if server is running
        server_status = server_data.get("attributes", {}).get("status", "offline")
        
        # Only count as active if server is actually running
        if server_status == "running":
            return True
        
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
    Check for active network connections on the game server VM.
    SSHs into the VM and checks for connections to monitored ports.
    """
    try:
        # SSH into game server VM and check for established connections
        ssh_command = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=5",
            f"{GAME_SERVER_VM_USER}@{GAME_SERVER_VM_IP}",
            "ss -tn"
        ]
        
        result = subprocess.run(
            ssh_command,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            log_message(f"Error connecting to game server VM: {result.stderr}")
            return False
        
        connections_found = []
        
        for line in result.stdout.split("\n"):
            if "ESTAB" in line:
                # Check if line contains any of our monitored ports
                for port in MONITOR_PORTS:
                    # Look for the port in the local address column
                    if f":{port}" in line:
                        connections_found.append(f"port {port}")
                        log_message(f"Active connection detected on port {port}")
        
        if connections_found:
            log_message(f"Total active connections: {len(connections_found)}")
            return True
        
        return False
        
    except Exception as e:
        log_message(f"Error checking network connections: {e}")
        return False


def check_game_servers_running():
    """
    Check if Minecraft servers are empty by looking at recent log messages.
    Looks for EmptyServerStopper messages indicating server is empty.
    If the message appears in last 30 lines, server is empty and can shutdown.
    """
    try:
        # SSH into game server VM and check last 30 lines of Minecraft log
        ssh_command = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=5",
            f"{GAME_SERVER_VM_USER}@{GAME_SERVER_VM_IP}",
            f"tail -n 30 {MINECRAFT_LOG_PATH} 2>/dev/null || echo 'LOG_NOT_FOUND'"
        ]
        
        result = subprocess.run(
            ssh_command,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0 or "LOG_NOT_FOUND" in result.stdout:
            log_message(f"Could not read Minecraft log at {MINECRAFT_LOG_PATH}")
            # If we can't read the log, fall back to checking processes
            return check_java_processes()
        
        log_output = result.stdout
        
        # Look for the EmptyServerStopper message in recent logs
        if "Server empty -> shutdown" in log_output:
            log_message("Minecraft server is EMPTY (EmptyServerStopper detected)")
            return False  # Server is empty, safe to shutdown
        else:
            log_message("Minecraft server has players or recently active")
            return True  # Server has players or was recently used
        
    except Exception as e:
        log_message(f"Error checking Minecraft server logs: {e}")
        return check_java_processes()  # Fallback


def check_java_processes():
    """
    Fallback: Check if Java processes are running.
    """
    try:
        ssh_command = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=5",
            f"{GAME_SERVER_VM_USER}@{GAME_SERVER_VM_IP}",
            "ps aux | grep -E 'java' | grep -v grep"
        ]
        
        result = subprocess.run(
            ssh_command,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0 and result.stdout.strip():
            log_message("Java processes running")
            return True
        else:
            log_message("No Java processes running")
            return False
        
    except Exception as e:
        log_message(f"Error checking Java processes: {e}")
        return False


def shutdown_proxmox():
    """Execute Proxmox shutdown"""
    log_message("INITIATING PROXMOX SHUTDOWN")
    print("\n" + "="*50)
    print("    SHUTTING DOWN PROXMOX")
    print("="*50 + "\n")
    try:
        subprocess.run(["shutdown", "-h", "now"], check=True)
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
    log_message(f"Monitoring IPs: {', '.join(MONITOR_IPS)}")
    log_message(f"Monitoring Ports: {', '.join(MONITOR_PORTS)}")
    log_message("Monitoring Hours - Weekdays: 22:00-15:00, Weekends: 21:30-07:30")
    
    # Check and display current monitoring status
    if is_within_monitoring_hours():
        log_message("✓ Script is RUNNING - within monitoring hours")
    else:
        now = datetime.now()
        current_day = "Weekday" if now.weekday() < 5 else "Weekend"
        log_message(f"⏸ Script is PAUSED - outside monitoring hours ({current_day}: {now.strftime('%H:%M')})")
    
    inactive_time = 0
    
    while True:
        try:
            # Check if we're within monitoring hours
            if not is_within_monitoring_hours():
                now = datetime.now()
                current_day = "Weekday" if now.weekday() < 5 else "Weekend"
                log_message(f"Outside monitoring hours ({current_day}: {now.strftime('%H:%M')}). Resetting timer and waiting...")
                inactive_time = 0  # Reset timer when outside monitoring hours
                time.sleep(CHECK_INTERVAL)
                continue
            
            # Check for active network connections (primary method)
            has_connections = check_network_connections()
            
            # Also check if game servers are running (not sleeping)
            servers_running = check_game_servers_running()
            
            # Optional: Also check Pterodactyl API if needed
            # api_activity = check_any_active_connections()
            
            # Keep system alive if connections OR servers running
            has_activity = has_connections or servers_running
            
            if has_activity:
                # Reset timer if connections are detected
                if inactive_time > 0:
                    log_message("Activity detected - resetting inactivity timer")
                    print("\nNO SHUTDOWN")
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
