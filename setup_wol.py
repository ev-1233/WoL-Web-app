#!/usr/bin/env python3
"""
WOL Bridge Setup Script

This script creates and updates the configuration file (WOL_Brige.config) required
by the WOL Gateway Flask application. It prompts the user for:
  - Server MAC Address (for Wake-on-LAN)
  - Site URL (where to redirect after waking the server)
  - Wait Time (how long to wait before redirecting)
  - Port Number (which port Flask should run on)

The script validates all inputs and preserves existing configuration as defaults
when re-running the setup.

Additionally, this script automatically detects your Linux distribution and
installs required dependencies (Flask and wakeonlan) if they're missing.
"""

import json
import os
import re
import subprocess
import sys
import platform
import socket

# Configuration file path - must match the one used by wol_gatway.py
CONFIG_FILE = "WOL_Brige.config"

def detect_linux_distro():
    """
    Detects the Linux distribution and returns the package manager to use.
    
    Returns:
        tuple: (distro_name, package_manager) or (None, None) if unknown
               package_manager can be: 'apt', 'dnf', 'yum', 'pacman', 'zypper', 'apk'
    """
    # Check if we're on Linux
    if platform.system() != 'Linux':
        return (platform.system(), None)
    
    # Try to read /etc/os-release (most modern Linux distros)
    try:
        with open('/etc/os-release', 'r') as f:
            os_release = f.read().lower()
            
        # Detect distribution
        if 'ubuntu' in os_release or 'debian' in os_release or 'mint' in os_release:
            return ('Debian/Ubuntu', 'apt')
        elif 'fedora' in os_release:
            return ('Fedora', 'dnf')
        elif 'rhel' in os_release or 'red hat' in os_release or 'centos' in os_release:
            # Check if dnf or yum is available
            if subprocess.run(['which', 'dnf'], capture_output=True).returncode == 0:
                return ('RHEL/CentOS', 'dnf')
            else:
                return ('RHEL/CentOS', 'yum')
        elif 'arch' in os_release or 'manjaro' in os_release:
            return ('Arch Linux', 'pacman')
        elif 'opensuse' in os_release or 'suse' in os_release:
            return ('openSUSE', 'zypper')
        elif 'alpine' in os_release:
            return ('Alpine', 'apk')
        elif 'termux' in os_release:
            return ('Termux', 'pkg')
    except FileNotFoundError:
        pass
    
    # Fallback: Check which package manager is available
    package_managers = [
        ('apt-get', 'apt'),
        ('dnf', 'dnf'),
        ('yum', 'yum'),
        ('pacman', 'pacman'),
        ('zypper', 'zypper'),
        ('apk', 'apk'),
        ('pkg', 'pkg')  # Termux
    ]
    
    for cmd, pm in package_managers:
        if subprocess.run(['which', cmd], capture_output=True).returncode == 0:
            return ('Unknown Linux', pm)
    
    return ('Unknown', None)

def check_command_exists(command):
    """
    Check if a command exists on the system.
    
    Args:
        command (str): Command name to check
    
    Returns:
        bool: True if command exists, False otherwise
    """
    result = subprocess.run(['which', command], capture_output=True, text=True)
    return result.returncode == 0

def check_python_package(package_name):
    """
    Check if a Python package is installed.
    
    Args:
        package_name (str): Name of the Python package
    
    Returns:
        bool: True if package is installed, False otherwise
    """
    try:
        __import__(package_name)
        return True
    except ImportError:
        return False

def install_dependencies():
    """
    Automatically detects the system and installs required dependencies.
    
    Dependencies:
      - Flask (Python package)
      - wakeonlan (system command-line utility)
    
    Returns:
        bool: True if all dependencies are satisfied, False if installation failed
    """
    print("\n" + "="*50)
    print("      Checking Dependencies")
    print("="*50)
    
    # Detect Linux distribution
    distro, pkg_manager = detect_linux_distro()
    print(f"Detected OS: {distro}")
    
    if pkg_manager:
        print(f"Package Manager: {pkg_manager}")
    else:
        print("Warning: Could not detect package manager")
    
    # Track if we need sudo
    needs_sudo = os.geteuid() != 0  # True if not running as root
    
    # Check Flask
    print("\n[1/2] Checking Flask...")
    if check_python_package('flask'):
        print("  ✓ Flask is already installed")
    else:
        print("  ✗ Flask is not installed")
        print("  Installing Flask via pip3...")
        
        try:
            # Try user installation first (no sudo needed)
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '--user', 'flask'],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print("  ✓ Flask installed successfully")
            else:
                print(f"  ✗ Failed to install Flask: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"  ✗ Error installing Flask: {e}")
            return False
    
    # Check wakeonlan
    print("\n[2/2] Checking wakeonlan...")
    if check_command_exists('wakeonlan'):
        print("  ✓ wakeonlan is already installed")
    else:
        print("  ✗ wakeonlan is not installed")
        
        if not pkg_manager:
            print("  ✗ Cannot install wakeonlan: unknown package manager")
            print("  Please install wakeonlan manually for your system")
            return False
        
        # Build installation commands - some distros have different package names
        # Format: package_manager: [(package_name, [command]), ...]
        install_commands = {
            'apt': [('wakeonlan', ['apt-get', 'install', '-y', 'wakeonlan'])],
            'dnf': [
                ('wakeonlan', ['dnf', 'install', '-y', 'wakeonlan']),
                ('wol', ['dnf', 'install', '-y', 'wol'])  # Alternative on Fedora/RHEL
            ],
            'yum': [
                ('wakeonlan', ['yum', 'install', '-y', 'wakeonlan']),
                ('wol', ['yum', 'install', '-y', 'wol'])  # Alternative on RHEL/CentOS
            ],
            'pacman': [('wakeonlan', ['pacman', '-S', '--noconfirm', 'wakeonlan'])],
            'zypper': [('wakeonlan', ['zypper', '--non-interactive', 'install', 'wakeonlan'])],
            'apk': [('wakeonlan', ['apk', 'add', 'wakeonlan'])],
            'pkg': [('wakeonlan', ['pkg', 'install', '-y', 'wakeonlan'])]
        }
        
        if pkg_manager not in install_commands:
            print(f"  ✗ Don't know how to install with {pkg_manager}")
            print("  Please install wakeonlan manually")
            return False
        
        # Try each package option for this package manager
        installed = False
        for pkg_name, cmd in install_commands[pkg_manager]:
            # Add sudo if needed (except for Termux pkg)
            if needs_sudo and pkg_manager != 'pkg':
                full_cmd = ['sudo'] + cmd
            else:
                full_cmd = cmd
            
            print(f"  Trying to install '{pkg_name}': {' '.join(full_cmd)}")
            
            try:
                result = subprocess.run(full_cmd, capture_output=True, text=True)
                
                if result.returncode == 0 and check_command_exists('wakeonlan'):
                    print(f"  ✓ wakeonlan installed successfully (as '{pkg_name}' package)")
                    installed = True
                    break
                else:
                    print(f"  ✗ Package '{pkg_name}' not available or installation failed")
                    
            except Exception as e:
                print(f"  ✗ Error trying to install '{pkg_name}': {e}")
        
        # If none of the system packages worked, try pip as fallback
        if not installed:
            print("\n  System packages failed. Trying Python package 'wakeonlan'...")
            try:
                result = subprocess.run(
                    [sys.executable, '-m', 'pip', 'install', '--user', 'wakeonlan'],
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    # Check if the wakeonlan command is now available
                    # pip installs it to ~/.local/bin usually
                    if check_command_exists('wakeonlan'):
                        print("  ✓ wakeonlan installed successfully via pip")
                        installed = True
                    else:
                        print("  ✓ wakeonlan Python package installed")
                        print("  ⚠ Note: You may need to add ~/.local/bin to your PATH")
                        print("    Or use: python3 -m wakeonlan <MAC_ADDRESS>")
                        installed = True
                        
            except Exception as e:
                print(f"  ✗ Error installing wakeonlan via pip: {e}")
        
        if not installed:
            print("\n  ✗ Could not install wakeonlan automatically")
            print("\n  Manual installation options:")
            print("    1. Fedora/RHEL (with EPEL): sudo dnf install epel-release && sudo dnf install wol")
            print("    2. Python package: pip3 install --user wakeonlan")
            print("    3. Build from source: https://github.com/jpoliv/wakeonlan")
            return False
    
    print("\n" + "="*50)
    print("  ✓ All dependencies satisfied!")
    print("="*50 + "\n")
    return True

def validate_mac(mac):
    """
    Validates a MAC address format.
    
    Accepts formats like:
      - 00:11:22:33:44:55 (colon-separated)
      - 00-11-22-33-44-55 (dash-separated)
    
    Args:
        mac (str): The MAC address string to validate
    
    Returns:
        bool: True if the MAC address format is valid, False otherwise
    """
    # Regex pattern: 6 pairs of hex digits separated by : or -
    if re.match(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$", mac):
        return True
    return False

def load_current_config():
    """
    Attempts to load the existing configuration file.
    
    This allows the setup script to show current values as defaults when
    re-running the configuration. If the file doesn't exist or can't be
    parsed, returns an empty dictionary.
    
    Returns:
        dict: Configuration dictionary if file exists and is valid, empty dict otherwise
    """
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            # Silently fail if file is corrupted or invalid JSON
            pass
    return {}

def check_docker_available():
    """
    Check if Docker is installed and the daemon is running.
    
    Returns:
        bool: True if Docker is available and working, False otherwise
    """
    try:
        # Check if docker command exists
        result = subprocess.run(['docker', '--version'], capture_output=True, text=True)
        if result.returncode != 0:
            return False
        
        # Check if docker daemon is running by trying to list containers
        result = subprocess.run(['docker', 'ps'], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False

def get_local_ip():
    """
    Get the local IP address of this machine.
    
    Returns:
        str: Local IP address or 'localhost' if unable to determine
    """
    try:
        # Create a socket and connect to an external address (doesn't actually send data)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        # Use Google's DNS server to determine which interface would be used
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        # Fallback: try to get hostname IP
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return 'localhost'

def setup_with_docker():
    """
    Sets up and runs the WOL gateway using Docker.
    
    Returns:
        bool: True if successful, False otherwise
    """
    print("\n" + "="*50)
    print("      Docker Setup Mode")
    print("="*50)
    
    docker_dir = os.path.join(os.path.dirname(__file__), '.docker')
    
    if not os.path.exists(docker_dir):
        print("Error: .docker directory not found!")
        return False
    
    print("\nBuilding Docker image...")
    print("This may take a few minutes on first run...")
    print("You'll see Docker's build output below:\n")
    print("-" * 50)
    
    try:
        # Build the Docker image - show output to user so they see progress
        result = subprocess.run(
            ['docker', 'compose', 'up', '-d', '--build'],
            cwd=docker_dir
            # NOT capturing output so user sees real-time progress
        )
        
        print("-" * 50)
        
        if result.returncode == 0:
            # Check if container is actually running
            check_result = subprocess.run(
                ['docker', 'compose', 'ps', '-q'],
                cwd=docker_dir,
                capture_output=True,
                text=True
            )
            
            if check_result.returncode == 0 and check_result.stdout.strip():
                print("\n" + "="*50)
                print("  ✓ Docker container started successfully!")
                print("="*50)
                print("\nYour WOL Gateway is now running in Docker!")
                
                # Get the port from config
                try:
                    with open(CONFIG_FILE, 'r') as f:
                        config = json.load(f)
                        port = config.get('PORT', 500)
                except:
                    port = 500
                
                # Get local IP address
                local_ip = get_local_ip()
                
                print("\nAccess it at:")
                print(f"  - Local:   http://localhost:{port}/wake")
                print(f"  - Network: http://{local_ip}:{port}/wake")
                print("\nUseful commands:")
                print("  View logs:    cd .docker && docker compose logs -f")
                print("  Stop:         cd .docker && docker compose down")
                print("  Restart:      cd .docker && docker compose restart")
                print("  Rebuild:      cd .docker && docker compose up -d --build")
                return True
            else:
                print("\n✗ Container did not start properly")
                print("Run 'cd .docker && docker compose logs' to see errors")
                return False
        else:
            print("\n✗ Failed to start Docker container")
            print("Check the error messages above")
            return False
            
    except KeyboardInterrupt:
        print("\n\n⚠ Build cancelled by user")
        return False
    except Exception as e:
        print(f"\n✗ Error running Docker: {e}")
        return False

def main():
    print("====================================")
    print("      WOL Bridge Setup Script       ")
    print("====================================")
    
    # Check if Docker is available
    docker_available = check_docker_available()
    
    if docker_available:
        print("\n✓ Docker detected and running!")
        print("\n" + "="*50)
        print("  Deployment Options:")
        print("="*50)
        print("\n1. Docker (Recommended)")
        print("   - No dependency issues")
        print("   - Works on all Linux distributions")
        print("   - Easy to manage and update")
        print("   - Automatic restart on failure")
        print("\n2. Direct Installation")
        print("   - Installs dependencies on your system")
        print("   - May require troubleshooting")
        print("   - Good for development")
        
        choice = input("\nChoose deployment method [1/2] (default: 1): ").strip()
        
        if choice == '2':
            print("\n--- Direct Installation Mode ---")
        else:
            print("\n--- Docker Mode (Recommended) ---")
            # First, configure settings
            print("\nLet's configure your WOL Gateway settings first.\n")
    else:
        print("\n⚠ Docker not detected or not running.")
        print("For the best experience, install Docker Desktop or start the Docker daemon.")
        print("\nFalling back to direct installation mode...")
        choice = '2'
    
    print("\n====================================")
    print("      Configuration Setup           ")
    print("====================================\n")
    
    # Load any existing configuration to use as defaults
    current_config = load_current_config()
    
    # Extract defaults from current file or use hardcoded fallbacks
    default_mac = current_config.get("WOL_MAC_ADDRESS", "")
    default_url = current_config.get("SITE_URL", "")
    default_wait = current_config.get("WAIT_TIME_SECONDS")
    default_port = current_config.get("PORT", 5000)  # Default port is 5000

    # =================================================================
    # 1. Prompt for Server MAC Address
    # =================================================================
    # The MAC address is required for sending the Wake-on-LAN magic packet
    # to the target server's network interface card.
    while True:
        prompt_mac = f"Enter Server MAC Address (e.g., 00:11:22:33:44:55)"
        # Show current value in brackets if it exists
        if default_mac:
            prompt_mac += f" [{default_mac}]"
        prompt_mac += ": "
        
        mac = input(prompt_mac).strip()
        
        # If user presses Enter without input, use the default
        if not mac and default_mac:
            mac = default_mac
            break
        
        # Validate the MAC address format
        if validate_mac(mac):
            break
        else:
            print("Invalid MAC address format. Please use XX:XX:XX:XX:XX:XX.")

    # =================================================================
    # 2. Prompt for Site URL (Final Redirect Destination)
    # =================================================================
    # This is the URL where users will be redirected after the server wakes up.
    # Example: http://panel.yourdomain.com or http://192.168.1.100:8080
    while True:
        prompt_url = "Enter Site URL"
        if default_url:
            prompt_url += f" [{default_url}]"
        prompt_url += ": "
        
        url_input = input(prompt_url).strip()
        
        # Use default if user presses Enter without input
        if not url_input and default_url:
            url = default_url
            break
        elif url_input:
            url = url_input
            break
        else:
            # URL cannot be empty - keep prompting
            print("Error: Site URL cannot be empty.")

    # =================================================================
    # 3. Prompt for Wait Time (Server Boot Duration)
    # =================================================================
    # This is how long (in seconds) the waiting page will display before
    # automatically redirecting to the Site URL. Should be long enough for
    # your server to fully boot up and become accessible.
    while True:
        prompt_wait = "Enter Wait Time in Seconds"
        if default_wait is not None:
            prompt_wait += f" [{default_wait}]"
        prompt_wait += ": "

        wait_input = input(prompt_wait).strip()

        # Handle empty input (use default if available)
        if not wait_input:
            if default_wait is None:
                print("Wait time is required.")
                continue
            try:
                wait = int(default_wait)
            except Exception:
                print("Stored wait time is invalid; please enter a number.")
                continue
        else:
            # Parse user input as integer
            try:
                wait = int(wait_input)
            except ValueError:
                print("Please enter a valid integer number.")
                continue

        # Validate that wait time is positive
        if wait <= 0:
            print("Please enter a number greater than zero.")
            continue
        break

    # =================================================================
    # 4. Prompt for Flask Port Number
    # =================================================================
    # The port number that the Flask web server will listen on.
    # Common choices: 5000 (Flask default), 8080, 3000, or any available port.
    # Remember to configure your router's port forwarding to match this port.
    while True:
        prompt_port = "Enter Flask Port Number"
        if default_port is not None:
            prompt_port += f" [{default_port}]"
        prompt_port += " (1-65535): "

        port_input = input(prompt_port).strip()

        # Handle empty input (use default if available)
        if not port_input:
            if default_port is None:
                print("Port number is required.")
                continue
            try:
                port = int(default_port)
            except Exception:
                print("Stored port is invalid; please enter a number.")
                continue
        else:
            # Parse user input as integer
            try:
                port = int(port_input)
            except ValueError:
                print("Please enter a valid integer number.")
                continue

        # Validate port is within valid range (1-65535)
        if port <= 0 or port > 65535:
            print("Port must be between 1 and 65535.")
            continue
        break

    # =================================================================
    # Save Configuration to JSON File
    # =================================================================
    # Create the configuration dictionary with all collected values
    new_config = {
        "WOL_MAC_ADDRESS": mac,
        "SITE_URL": url,
        "WAIT_TIME_SECONDS": wait,
        "PORT": port
    }

    # Write the configuration to file with pretty formatting (indent=4)
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(new_config, f, indent=4)
        
        # Display success message with all configured values
        print(f"\n[SUCCESS] Configuration saved to '{CONFIG_FILE}'.")
        print(f"Server MAC: {mac}")
        print(f"Redirect URL: {url}")
        print(f"Wait Time: {wait}s")
        print(f"Port: {port}")
    except Exception as e:
        # Handle any file writing errors
        print(f"\n[ERROR] Could not save configuration: {e}")
        return
    
    # Now handle deployment based on chosen method
    if docker_available and choice != '2':
        # Docker mode
        print("\n" + "="*50)
        if not setup_with_docker():
            print("\n[WARNING] Docker setup failed.")
            print("You can try running manually:")
            print("  cd .docker && docker compose up -d")
    else:
        # Direct installation mode
        print("\n" + "="*50)
        print("      Installing Dependencies")
        print("="*50)
        print("\nThis script will check for required dependencies and install them if needed.")
        print("You may be prompted for your sudo password to install system packages.\n")
        
        user_input = input("Continue with dependency check? [Y/n]: ").strip().lower()
        if user_input and user_input not in ('y', 'yes'):
            print("Setup complete. Configuration saved.")
            print("Note: Dependencies were not installed. Run './start.sh' when ready.")
            return
        
        # Install dependencies
        if not install_dependencies():
            print("\n[WARNING] Some dependencies could not be installed automatically.")
            print("The configuration has been saved, but you may need to install dependencies manually.")
            print("\nYou can:")
            print("  1. Fix dependencies and run: ./start.sh")
            print("  2. Try Docker: cd .docker && docker compose up -d")
        else:
            print("\n" + "="*50)
            print("  ✓ Setup Complete!")
            print("="*50)
            print("\nTo start the WOL Gateway, run:")
            print("  ./start.sh")
            print("\nOr run manually:")
            print("  sudo python3 wol_gatway.py")

if __name__ == "__main__":
    main()
