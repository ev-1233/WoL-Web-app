import json
import os
import re

CONFIG_FILE = "WOL_Brige.config"

def validate_mac(mac):
    # simple regex for MAC address validation
    if re.match(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$", mac):
        return True
    return False

def load_current_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def main():
    print("====================================")
    print("      WOL Bridge Setup Script       ")
    print("====================================")
    
    current_config = load_current_config()
    
    # Defaults from current file or hardcoded fallbacks
    default_mac = current_config.get("WOL_MAC_ADDRESS", "")
    default_url = current_config.get("SITE_URL", "")
    default_wait = current_config.get("WAIT_TIME_SECONDS", 60)

    # 1. Get MAC Address
    while True:
        prompt_mac = f"Enter Server MAC Address (e.g., 00:11:22:33:44:55)"
        if default_mac:
            prompt_mac += f" [{default_mac}]"
        prompt_mac += ": "
        
        mac = input(prompt_mac).strip()
        
        if not mac and default_mac:
            mac = default_mac
            break
        
        if validate_mac(mac):
            break
        else:
            print("Invalid MAC address format. Please use XX:XX:XX:XX:XX:XX.")

    # 2. Get Site URL
    while True:
        prompt_url = "Enter Site URL"
        if default_url:
            prompt_url += f" [{default_url}]"
        prompt_url += ": "
        
        url_input = input(prompt_url).strip()
        
        if not url_input and default_url:
            url = default_url
            break
        elif url_input:
            url = url_input
            break
        else:
            print("Error: Site URL cannot be empty.")

    # 3. Get Wait Time
    while True:
        prompt_wait = f"Enter Wait Time in Seconds [{default_wait}]: "
        wait_input = input(prompt_wait).strip()
        
        if not wait_input:
            wait = default_wait
            try:
                wait = int(wait) # Ensure it's an int if it came from file
            except:
                wait = 60
            break
        elif wait_input.isdigit():
            wait = int(wait_input)
            break
        else:
            print("Please enter a valid integer number.")

    # Save Configuration
    new_config = {
        "WOL_MAC_ADDRESS": mac,
        "SITE_URL": url,
        "WAIT_TIME_SECONDS": wait
    }

    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(new_config, f, indent=4)
        print(f"\n[SUCCESS] Configuration saved to '{CONFIG_FILE}'.")
        print(f"Server MAC: {mac}")
        print(f"Redirect URL: {url}")
        print(f"Wait Time: {wait}s")
    except Exception as e:
        print(f"\n[ERROR] Could not save configuration: {e}")

if __name__ == "__main__":
    main()
