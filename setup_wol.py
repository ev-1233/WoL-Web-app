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

try:
    from version import __version__, __github_repo__
except ImportError:
    __version__ = "1.0.0"
    __github_repo__ = "yourusername/wol-gateway"

# Configuration file path - must match the one used by wol_gatway.py
CONFIG_FILE = "WOL_Brige.config"

def is_running_in_docker():
    """
    Detect if the script is running inside a Docker container.
    
    Returns:
        bool: True if running in Docker, False otherwise
    """
    # Check for .dockerenv file (most common indicator)
    if os.path.exists('/.dockerenv'):
        return True
    
    # Check cgroup for docker
    try:
        with open('/proc/1/cgroup', 'r') as f:
            return 'docker' in f.read() or 'containerd' in f.read()
    except:
        pass
    
    # Check for container environment variable
    if os.environ.get('CONTAINER') or os.environ.get('DOCKER_CONTAINER'):
        return True
    
    return False

def check_for_updates():
    """
    Check if a newer version is available on GitHub.
    Displays a message if an update is found, but doesn't auto-update.
    
    Returns:
        bool: True if update is available, False otherwise
    """
    try:
        import urllib.request
        import json as json_lib
        
        # GitHub API endpoint for latest release
        api_url = f"https://api.github.com/repos/{__github_repo__}/releases/latest"
        
        # Set a short timeout to avoid hanging
        req = urllib.request.Request(api_url)
        req.add_header('User-Agent', 'WOL-Gateway-Update-Checker')
        
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json_lib.loads(response.read().decode())
            latest_version = data['tag_name'].lstrip('v')
            
            # Compare versions (simple string comparison works for semantic versioning)
            if latest_version != __version__:
                print("\n" + "="*60)
                print("🔔  UPDATE AVAILABLE!")
                print("="*60)
                print(f"  Current version: {__version__}")
                print(f"  Latest version:  {latest_version}")
                print(f"\n  Download: https://github.com/{__github_repo__}/releases/latest")
                print("="*60 + "\n")
                return True
    except Exception as e:
        # Silently fail - don't interrupt setup if update check fails
        pass
    
    return False

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
            return ('Debian/Ubuntu', 'aabout:blank#blockedpt')
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
    Check if a command exists on the system .
    
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
    # Skip dependency installation if running inside Docker - everything is pre-installed
    if is_running_in_docker():
        print("\n" + "="*50)
        print("      Running in Docker Container")
        print("="*50)
        print("✓ Dependencies pre-installed in container")
        print("="*50 + "\n")
        return True
    
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

def check_docker_installed():
    """
    Check if Docker is installed (command exists).
    
    Returns:
        bool: True if Docker is installed, False otherwise
    """
    try:
        result = subprocess.run(['docker', '--version'], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False

def check_docker_running():
    """
    Check if Docker daemon is running.
    
    Returns:
        bool: True if Docker daemon is running, False otherwise
    """
    try:
        result = subprocess.run(['docker', 'ps'], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False

def check_docker_available():
    """
    Check if Docker is installed and the daemon is running.
    
    Returns:
        bool: True if Docker is available and working, False otherwise
    """
    return check_docker_installed() and check_docker_running()

def install_docker():
    """
    Install Docker based on detected Linux distribution.
    
    Returns:
        bool: True if installation was successful, False otherwise
    """
    print("\n" + "="*50)
    print("      Docker Installation")
    print("="*50)
    
    distro, pkg_manager = detect_linux_distro()
    
    if platform.system() != 'Linux':
        print(f"\nAutomated Docker installation is only available for Linux.")
        print(f"Please install Docker Desktop manually from: https://docs.docker.com/get-docker/")
        return False
    
    print(f"\nDetected: {distro}")
    print("\nThis will install Docker on your system.")
    
    # Check if running as root
    needs_sudo = os.geteuid() != 0
    
    try:
        # Use official Docker installation script (works for most distros)
        print("\nDownloading Docker installation script...")
        print("This will use Docker's official installation script from get.docker.com\n")
        
        # Download and run the Docker installation script
        install_cmd = 'curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh'
        
        if needs_sudo:
            full_cmd = ['sudo', 'sh', '-c', install_cmd]
        else:
            full_cmd = ['sh', '-c', install_cmd]
        
        result = subprocess.run(full_cmd)
        
        if result.returncode != 0:
            print("\n✗ Docker installation failed")
            return False
        
        # Add current user to docker group (if not root)
        if needs_sudo:
            try:
                username = os.environ.get('USER', os.environ.get('SUDO_USER', ''))
                if username:
                    print(f"\nAdding user '{username}' to docker group...")
                    subprocess.run(['sudo', 'usermod', '-aG', 'docker', username])
                    print("\n⚠ Note: You may need to log out and back in for group changes to take effect.")
            except Exception as e:
                print(f"\nWarning: Could not add user to docker group: {e}")
        
        # Clean up installation script
        try:
            if os.path.exists('get-docker.sh'):
                os.remove('get-docker.sh')
        except:
            pass
        
        print("\n✓ Docker installed successfully!")
        return True
        
    except KeyboardInterrupt:
        print("\n\n⚠ Installation cancelled by user")
        return False
    except Exception as e:
        print(f"\n✗ Error during installation: {e}")
        print("\nPlease install Docker manually:")
        print("  https://docs.docker.com/engine/install/")
        return False

def detect_docker_installation_type():
    """
    Detect how Docker is installed on the system.
    
    Returns:
        str: 'desktop', 'engine', 'snap', 'manual', or 'unknown'
    """
    # Check for Docker Desktop user service (most reliable method)
    try:
        result = subprocess.run(['systemctl', '--user', 'list-unit-files', 'docker-desktop.service'], 
                              capture_output=True, text=True)
        if 'docker-desktop.service' in result.stdout:
            return 'desktop'
    except:
        pass
    
    # Check for Docker Desktop directory
    docker_desktop_dirs = [
        os.path.expanduser('~/.docker/desktop'),
        '/opt/docker-desktop'
    ]
    for dir_path in docker_desktop_dirs:
        if os.path.exists(dir_path):
            return 'desktop'
    
    # Check for Docker Desktop command
    if check_command_exists('docker-desktop'):
        return 'desktop'
    
    # Check if installed via snap
    try:
        result = subprocess.run(['snap', 'list', 'docker'], capture_output=True, text=True)
        if result.returncode == 0 and 'docker' in result.stdout:
            return 'snap'
    except:
        pass
    
    # Check if systemd service exists (Docker Engine)
    try:
        result = subprocess.run(['systemctl', 'list-unit-files', 'docker.service'], 
                              capture_output=True, text=True)
        if 'docker.service' in result.stdout:
            return 'engine'
    except:
        pass
    
    # Check if dockerd exists (manual installation)
    if check_command_exists('dockerd'):
        return 'manual'
    
    return 'unknown'

def start_docker():
    """
    Start the Docker daemon, handling different installation methods.
    
    Returns:
        bool: True if Docker was started successfully, False otherwise
    """
    print("\n" + "="*50)
    print("      Starting Docker")
    print("="*50)
    
    needs_sudo = os.geteuid() != 0
    install_type = detect_docker_installation_type()
    
    print(f"\nDetected Docker installation type: {install_type}")
    
    try:
        import time
        
        # Handle Docker Desktop
        if install_type == 'desktop':
            print("\nDocker Desktop detected.")
            print("Starting Docker Desktop as user service...\n")
            
            # Try to start Docker Desktop using systemctl --user
            cmd = ['systemctl', '--user', 'start', 'docker-desktop']
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                print("Waiting for Docker Desktop to start...")
                time.sleep(8)  # Docker Desktop takes longer to start
                
                # Verify it's running
                if check_docker_running():
                    print("\n✓ Docker Desktop started successfully!")
                    
                    # Enable Docker Desktop to start on login
                    enable_cmd = ['systemctl', '--user', 'enable', 'docker-desktop']
                    enable_result = subprocess.run(enable_cmd, capture_output=True, text=True)
                    if enable_result.returncode == 0:
                        print("✓ Docker Desktop configured to start on login")
                    return True
                else:
                    print("\n⚠ Docker Desktop service started but daemon not responding yet")
                    print("It may still be starting up. Waiting a bit longer...")
                    time.sleep(5)
                    
                    if check_docker_running():
                        print("✓ Docker Desktop is now running!")
                        return True
                    else:
                        print("\n✗ Docker Desktop did not start properly")
                        print("Try starting it manually from your applications menu")
                        return False
            else:
                print(f"\n✗ Failed to start Docker Desktop: {result.stderr}")
                print("\nYou can try starting it manually:")
                print("  systemctl --user start docker-desktop")
                print("  Or from your applications menu")
                return False
        
        # Handle Snap installation
        elif install_type == 'snap':
            print("\nDocker installed via Snap detected.")
            print("Starting Docker via Snap...\n")
            
            cmd = ['snap', 'start', 'docker']
            if needs_sudo:
                cmd = ['sudo'] + cmd
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0 or 'is not' in result.stderr:
                # Snap might say it's already started
                time.sleep(3)
                if check_docker_running():
                    print("\n✓ Docker started successfully!")
                    return True
                else:
                    print("\n✗ Docker service started but daemon not responding")
                    print("\nTry running: sudo snap restart docker")
                    return False
            else:
                print(f"\n✗ Failed to start Docker: {result.stderr}")
                return False
        
        # Handle Docker Engine (systemd)
        elif install_type == 'engine':
            print("\nDocker Engine detected. Starting via systemd...\n")
            
            cmd = ['systemctl', 'start', 'docker']
            if needs_sudo:
                cmd = ['sudo'] + cmd
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                print("Waiting for Docker to start...")
                time.sleep(3)
                
                if check_docker_running():
                    print("\n✓ Docker started successfully!")
                    
                    # Enable Docker to start on boot
                    enable_cmd = ['systemctl', 'enable', 'docker']
                    if needs_sudo:
                        enable_cmd = ['sudo'] + enable_cmd
                    subprocess.run(enable_cmd, capture_output=True)
                    print("✓ Docker configured to start on boot")
                    return True
                else:
                    print("\n✗ Docker service started but daemon not responding")
                    return False
            else:
                print(f"\n✗ Failed to start Docker: {result.stderr}")
                return False
        
        # Handle manual installation
        elif install_type == 'manual':
            print("\nManual Docker installation detected.")
            print("\nTo start Docker manually, you need to run:")
            print("  sudo dockerd")
            print("\nThis should be run in a separate terminal and left running.")
            print("Or create a systemd service for Docker.")
            return False
        
        # Unknown installation - try common methods
        else:
            print("\nCould not detect Docker installation method. Trying common approaches...\n")
            
            # Try systemctl
            if check_command_exists('systemctl'):
                print("Trying systemctl...")
                cmd = ['systemctl', 'start', 'docker']
                if needs_sudo:
                    cmd = ['sudo'] + cmd
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    time.sleep(3)
                    if check_docker_running():
                        print("\n✓ Docker started successfully!")
                        return True
                else:
                    print(f"systemctl failed: {result.stderr.strip()}")
            
            # Try service command
            if check_command_exists('service'):
                print("Trying service command...")
                cmd = ['service', 'docker', 'start']
                if needs_sudo:
                    cmd = ['sudo'] + cmd
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    time.sleep(3)
                    if check_docker_running():
                        print("\n✓ Docker started successfully!")
                        return True
                else:
                    print(f"service command failed: {result.stderr.strip()}")
            
            print("\n✗ Could not start Docker with any method")
            print("\nDocker appears to be installed but may need to be reinstalled or configured.")
            print("Try:")
            print("  1. Reinstall Docker: curl -fsSL https://get.docker.com | sh")
            print("  2. Install Docker Desktop: https://docs.docker.com/desktop/install/linux-install/")
            print("  3. Check Docker documentation for your distribution")
            return False
            
    except KeyboardInterrupt:
        print("\n\n⚠ Cancelled by user")
        return False
    except Exception as e:
        print(f"\n✗ Error starting Docker: {e}")
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
                print(f"  - Local:   http://localhost:{port}")
                print(f"  - Network: http://{local_ip}:{port}")
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
    print(f"      Version {__version__}              ")
    print("====================================")
    
    # Check for updates (only if not running in Docker)
    if not is_running_in_docker():
        check_for_updates()
    
    # Skip Docker installation/management when running inside Docker
    if is_running_in_docker():
        print("\n✓ Running inside Docker container")
        print("  Skipping Docker installation steps...")
        docker_available = False
        docker_installed = False
        docker_running = False
    else:
        # Check Docker status
        docker_installed = check_docker_installed()
        docker_running = check_docker_running()
        docker_available = docker_installed and docker_running
    
    # Handle Docker installation/startup prompts (only if NOT in Docker)
    if not is_running_in_docker() and not docker_installed:
        print("\n⚠ Docker is not installed.")
        print("\nDocker provides the easiest deployment method with:")
        print("  - No dependency issues")
        print("  - Works on all Linux distributions")
        print("  - Easy to manage and update")
        print("  - Automatic restart on failure")
        
        # Retry loop for Docker installation
        while True:
            install_choice = input("\nWould you like to install Docker now? [Y/n]: ").strip().lower()
            
            if install_choice in ('', 'y', 'yes'):
                if install_docker():
                    # Check if Docker is now running
                    if check_docker_running():
                        docker_available = True
                        docker_installed = True
                        docker_running = True
                        break
                    else:
                        # Docker installed but not running, try to start it
                        print("\nDocker is installed but not running.")
                        
                        # Retry loop for starting Docker after installation
                        while True:
                            start_choice = input("Would you like to start Docker now? [Y/n]: ").strip().lower()
                            
                            if start_choice in ('', 'y', 'yes'):
                                if start_docker():
                                    docker_available = True
                                    docker_running = True
                                    break
                                else:#
                                    print("\n⚠ Failed to start Docker.")
                                    print("\nPossible solutions:")
                                    print("  1. Reboot your system (some Docker installations require a reboot)")
                                    print("  2. Check if Docker service exists: systemctl status docker")
                                    print("  3. Try starting manually: sudo systemctl start docker")
                                    
                                    retry_start = input("\nWould you like to retry starting Docker? [y/N]: ").strip().lower()
                                    if retry_start in ('y', 'yes'):
                                        continue
                                    else:
                                        print("\nFalling back to direct installation mode.")
                                        docker_available = False
                                        break
                            else:
                                print("\nFalling back to direct installation mode.")
                                docker_available = False
                                break
                        break
                else:
                    print("\n⚠ Docker installation failed.")
                    print("\nPossible solutions:")
                    print("  1. Check your internet connection")
                    print("  2. Ensure you have curl installed: sudo apt install curl")
                    print("  3. Try installing manually: https://docs.docker.com/engine/install/")
                    
                    retry_install = input("\nWould you like to retry installing Docker? [y/N]: ").strip().lower()
                    if retry_install in ('y', 'yes'):
                        continue
                    else:
                        print("\nFalling back to direct installation mode.")
                        docker_available = False
                        break
            else:
                print("\nSkipping Docker installation. Using direct installation mode.")
                docker_available = False
                break
    
    elif docker_installed and not docker_running:
        print("\n⚠ Docker is installed but not running.")
        print("\nFor the best deployment experience, Docker should be running.")
        
        # Retry loop for starting Docker
        while True:
            start_choice = input("\nWould you like to start Docker now? [Y/n]: ").strip().lower()
            
            if start_choice in ('', 'y', 'yes'):
                if start_docker():
                    docker_available = True
                    docker_running = True
                    break
                else:
                    print("\n⚠ Failed to start Docker.")
                    print("\nPossible solutions:")
                    print("  1. Check Docker service status: systemctl status docker")
                    print("  2. Check Docker logs: journalctl -u docker")
                    print("  3. Try reinstalling Docker")
                    print("  4. Reboot your system")
                    
                    retry_start = input("\nWould you like to retry starting Docker? [y/N]: ").strip().lower()
                    if retry_start in ('y', 'yes'):
                        continue
                    else:
                        print("\nFalling back to direct installation mode.")
                        docker_available = False
                        break
            else:
                print("\nFalling back to direct installation mode.")
                docker_available = False
                break
    
    # Now present deployment options
    if docker_available:
        print("\n✓ Docker is ready!")
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
        print("\n--- Direct Installation Mode ---")
        choice = '2'
    
    print("\n====================================")
    print("      Configuration Setup           ")
    print("====================================\n")
    
    # Load any existing configuration to use as defaults
    current_config = load_current_config()
    
    # Extract port default (shared across all servers)
    default_port = current_config.get("PORT", 5000)  # Default port is 5000
    
    # Extract existing servers if any
    existing_servers = current_config.get("SERVERS", [])
    
    # =================================================================
    # Collect Server Configurations
    # =================================================================
    servers = []
    server_number = 1
    
    # If we have existing servers, ask if user wants to keep or reconfigure
    if existing_servers:
        print(f"\nFound {len(existing_servers)} existing server(s):")
        for idx, srv in enumerate(existing_servers, 1):
            print(f"  {idx}. {srv.get('NAME', 'Unnamed')} - {srv.get('WOL_MAC_ADDRESS', 'N/A')}")
        
        keep_choice = input("\nKeep existing servers? [Y/n]: ").strip().lower()
        if keep_choice in ('', 'y', 'yes'):
            servers = existing_servers.copy()
            server_number = len(servers) + 1
            print("Existing servers kept. You can add more servers below.\n")
        else:
            print("Starting fresh configuration...\n")
    
    # Loop to add servers
    while True:
        print(f"\n{'='*50}")
        print(f"      Server #{server_number} Configuration")
        print(f"{'='*50}\n")
        
        # =================================================================
        # 1. Prompt for Server Name
        # =================================================================
        while True:
            server_name = input(f"Enter Server Name (e.g., Main Server, NAS, etc.): ").strip()
            if server_name:
                break
            print("Error: Server name cannot be empty.")
        
        # =================================================================
        # 2. Prompt for Server MAC Address
        # =================================================================
        while True:
            mac = input(f"Enter MAC Address (e.g., 00:11:22:33:44:55): ").strip()
            if validate_mac(mac):
                break
            print("Invalid MAC address format. Please use XX:XX:XX:XX:XX:XX.")
        
        # =================================================================
        # 3. Prompt for Broadcast Address
        # =================================================================
        while True:
            broadcast_input = input("Enter Broadcast Address [255.255.255.255]: ").strip()
            if not broadcast_input:
                broadcast = "255.255.255.255"
                break
            else:
                broadcast = broadcast_input
                break
        
        # =================================================================
        # 4. Prompt for Site URL
        # =================================================================
        while True:
            url = input(f"Enter Site URL (e.g., http://192.168.1.100:8080): ").strip()
            if url:
                break
            print("Error: Site URL cannot be empty.")
        
        # =================================================================
        # 5. Prompt for Wait Time
        # =================================================================
        while True:
            wait_input = input("Enter Wait Time in Seconds [60]: ").strip()
            if not wait_input:
                wait = 60
                break
            try:
                wait = int(wait_input)
                if wait <= 0:
                    print("Please enter a number greater than zero.")
                    continue
                break
            except ValueError:
                print("Invalid input. Please enter a whole number.")
        
        # Add this server to the list
        servers.append({
            "NAME": server_name,
            "WOL_MAC_ADDRESS": mac,
            "BROADCAST_ADDRESS": broadcast,
            "SITE_URL": url,
            "WAIT_TIME_SECONDS": wait
        })
        
        print(f"\n✓ Server '{server_name}' added!")
        
        # Ask if user wants to add another server
        add_another = input("\nAdd another server? [y/N]: ").strip().lower()
        if add_another in ('y', 'yes'):
            server_number += 1
            continue
        else:
            break
    
    # Ensure at least one server was configured
    if not servers:
        print("\nError: At least one server must be configured.")
        return
    
    # =================================================================
    # Prompt for Flask Port Number (Global Setting)
    # =================================================================
    print(f"\n{'='*50}")
    print("      Global Settings")
    print(f"{'='*50}\n")
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
        "PORT": port,
        "SERVERS": servers
    }

    # Write the configuration to file with pretty formatting (indent=4)
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(new_config, f, indent=4)
        
        # Display success message with all configured values
        print(f"\n[SUCCESS] Configuration saved to '{CONFIG_FILE}'.")
        print(f"Port: {port}")
        print(f"\nConfigured Servers ({len(servers)}):")
        for idx, srv in enumerate(servers, 1):
            print(f"  {idx}. {srv['NAME']}")
            print(f"     MAC: {srv['WOL_MAC_ADDRESS']}")
            print(f"     URL: {srv['SITE_URL']}")
            print(f"     Wait: {srv['WAIT_TIME_SECONDS']}s")
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
