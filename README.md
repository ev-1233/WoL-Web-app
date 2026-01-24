# WOL Gateway

Wake-on-LAN gateway service that provides a simple web interface to wake up your servers remotely from anywhere without a vpn.

## Features



## Installation

### Option 1: Docker Hub (Strongly Recommended)

**Prerequisites:** Docker installed and running

```bash
docker run -it --name wol-gateway --cap-add NET_ADMIN --cap-add NET_RAW --network host --restart unless-stopped ev1233/wol-gateway:latest
```

The setup script will:
- Help you configure your servers (MAC addresses, URLs, etc.)
- Build and start the Docker container automatically
- Set up auto-restart on failure

### Option 2: Standalone Executable (No Prerequisites Required)


1. Download the latest executable for your system:
   - [Linux](https://github.com/ev1233/wol-gateway/releases/latest/download/wol-gateway-linux)
   - [Windows](https://github.com/ev1233/wol-gateway/releases/latest/download/wol-gateway-windows.exe)
   - [macOS](https://github.com/ev1233/wol-gateway/releases/latest/download/wol-gateway-macos)

2. Run the executable:
   ```bash
   # Linux
   chmod +x wol-gateway-linux
   ./wol-gateway-linux
   
   # Windows
   wol-gateway-windows.exe
   
   # macOS
   chmod +x wol-gateway-macos
   ./wol-gateway-macos
   ```

3. Follow the on-screen prompts to configure your servers

## Install with git

If you just love git that much:

**python3 and pip must be installed and we highly recommend you install docker(technically optional):**

- python3 [install guide](https://pythongeeks.org/python-3-installation-and-setup-guide/ "by pythongeeks.org")
- Pip [install guide](https://pip.pypa.io/en/stable/installation/ "from pip themselves")


```bash
# Linux
LATEST_VERSION=$(curl -s https://api.github.com/repos/ev1233/WoL-Gateway/releases/latest | grep "tag_name" | cut -d '"' -f 4)
wget https://github.com/ev1233/WoL-Gateway/archive/refs/tags/$LATEST_VERSION.tar.gz -O wol-gateway-latest.tar.gz
tar --transform='s/^WoL-Gateway-.*/WoL-Gateway/' -xzf wol-gateway-latest.tar.gz
cd WoL-Gateway
python3 setup_wol.py

# macOS
LATEST_VERSION=$(curl -s https://api.github.com/repos/ev1233/WoL-Gateway/releases/latest | grep "tag_name" | cut -d '"' -f 4)
curl -L https://github.com/ev1233/WoL-Gateway/archive/refs/tags/$LATEST_VERSION.tar.gz -o wol-gateway-latest.tar.gz

tar -xzf wol-gateway-latest.tar.gz

mv WoL-Gateway-* WoL-Gateway
cd WoL-Gateway

python3 setup_wol.py

# Windows (PowerShell)
$LATEST_VERSION = (Invoke-RestMethod -Uri "https://api.github.com/repos/ev1233/WoL-Gateway/releases/latest").tag_name
Invoke-WebRequest -Uri "https://github.com/ev1233/WoL-Gateway/archive/refs/tags/$LATEST_VERSION.zip" -OutFile "wol-gateway-latest.zip"

Expand-Archive -Path "wol-gateway-latest.zip" -DestinationPath "."
Rename-Item -Path "WoL-Gateway-*" -NewName "WoL-Gateway"

cd WoL-Gateway

python setup_wol.py
```

## Updating

### Docker
```bash
docker pull ev1233/wol-gateway:latest
docker compose down && docker compose up -d
```

### Standalone Executable
Download the latest version from [Releases](https://github.com/ev1233/wol-gateway/releases/latest)

### Github install
```bash
# Linux/macOS
git pull
python3 setup_wol.py

# Windows (PowerShell)
git pull
python setup_wol.py
```


## Persistent Configuration

If you want to keep your config outside the container:

```bash
# Create config directory
mkdir -p ~/wol-gateway-config

# First run with volume (setup will save here)
docker run -it --name wol-gateway \
  --cap-add NET_ADMIN --cap-add NET_RAW \
  -p 5000:5000 \
  -v ~/wol-gateway-config:/app \
  --restart unless-stopped \
  ev1233/wol-gateway:latest
```

Your config is now saved in `~/wol-gateway-config/WOL_Brige.config`

## Troubleshooting

### Wake-on-LAN not working?

1. Enable WOL in your server's BIOS/UEFI
2. Enable WOL in your network card settings
3. Ensure both devices are on the same network/subnet
4. Check firewall rules allow UDP port 9 (WOL magic packet)

### Docker container won't start?

```bash
# Check logs
docker logs wol-gateway

# Verify Docker has network capabilities
docker inspect wol-gateway | grep CapAdd
```

## Development

```bash
# Linux
git clone https://github.com/ev1233/wol-gateway.git
cd wol-gateway
python3 -m venv venv
source venv/bin/activate
pip install flask wakeonlan
python3 wol_gatway.py

# macOS
git clone https://github.com/ev1233/wol-gateway.git
cd wol-gateway
python3 -m venv venv
source venv/bin/activate
pip install flask wakeonlan
python3 wol_gatway.py

# Windows (PowerShell)
git clone https://github.com/ev1233/wol-gateway.git
cd wol-gateway
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install flask wakeonlan
python wol_gatway.py
```

for more info see 
[the deployment guide][DEPLOYMENT.md]

on VScode you can run the gateway with out the setup script by pressing **ctrl+shift+b**
