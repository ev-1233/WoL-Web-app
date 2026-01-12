# WOL Gateway

Wake-on-LAN gateway service that provides a simple web interface to wake up your servers remotely.

## Features

- 🚀 Simple web-based Wake-on-LAN trigger
- 🐳 Docker support for easy deployment
- 📦 Standalone executables for non-technical users
- 🔄 Automatic update notifications
- 🔧 Easy configuration setup
- 🌐 Multiple server support

## Installation

### Option 1: Docker (Recommended)

**Prerequisites:** Docker installed and running

```bash
# Download the repository
git clone https://github.com/yourusername/wol-gateway.git
cd wol-gateway

# Run setup (will guide you through configuration)
python3 setup_wol.py
```

The setup script will:
- Help you configure your servers (MAC addresses, URLs, etc.)
- Build and start the Docker container automatically
- Set up auto-restart on failure

### Option 2: Standalone Executable (No Installation Required)

**For non-technical users:**

1. Download the latest executable for your system:
   - [Linux](https://github.com/yourusername/wol-gateway/releases/latest/download/wol-gateway-linux)
   - [Windows](https://github.com/yourusername/wol-gateway/releases/latest/download/wol-gateway-windows.exe)
   - [macOS](https://github.com/yourusername/wol-gateway/releases/latest/download/wol-gateway-macos)

2. Run the executable:
   ```bash
   # Linux/macOS
   chmod +x wol-gateway-linux
   ./wol-gateway-linux
   
   # Windows
   wol-gateway-windows.exe
   ```

3. Follow the on-screen prompts to configure your servers

### Option 3: Direct Installation (Development)

**Prerequisites:** Python 3.8+

```bash
# Clone the repository
git clone https://github.com/yourusername/wol-gateway.git
cd wol-gateway

# Run setup (will install dependencies automatically)
python3 setup_wol.py
```

## Quick Start with Docker

If you already have Docker running:

```bash
# Pull the pre-built image
docker pull yourusername/wol-gateway:latest

# Create config file (or use setup script)
cat > WOL_Brige.config << EOF
{
  "PORT": 5000,
  "SERVERS": [
    {
      "NAME": "My Server",
      "MAC": "00:11:22:33:44:55",
      "URL": "http://192.168.1.100",
      "WAIT": 30
    }
  ]
}
EOF

# Run the container
docker run -d \
  --name wol-gateway \
  --cap-add NET_ADMIN \
  --cap-add NET_RAW \
  -p 5000:5000 \
  -v $(pwd)/WOL_Brige.config:/app/WOL_Brige.config:ro \
  --restart unless-stopped \
  yourusername/wol-gateway:latest
```

Access at: http://localhost:5000

## Configuration

The `WOL_Brige.config` file uses JSON format:

```json
{
  "PORT": 5000,
  "SERVERS": [
    {
      "NAME": "Server Name",
      "MAC": "00:11:22:33:44:55",
      "URL": "http://192.168.1.100",
      "WAIT": 30
    }
  ]
}
```

- **PORT**: Port number for the web interface
- **NAME**: Display name for the server
- **MAC**: MAC address of the server's network card
- **URL**: URL to redirect to after waking
- **WAIT**: Seconds to wait before redirecting

## Updating

### Docker
```bash
docker pull yourusername/wol-gateway:latest
docker compose down && docker compose up -d
```

### Standalone Executable
Download the latest version from [Releases](https://github.com/yourusername/wol-gateway/releases/latest)

### Direct Installation
```bash
git pull
python3 setup_wol.py
```

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
# Clone repository
git clone https://github.com/yourusername/wol-gateway.git
cd wol-gateway

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install flask wakeonlan

# Run directly
python3 wol_gatway.py
```

## License

MIT License - See LICENSE file for details

## Contributing

Pull requests welcome! Please open an issue first to discuss major changes.
