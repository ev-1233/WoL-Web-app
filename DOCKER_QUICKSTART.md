# Quick Start: Docker Pull & Run

The easiest way to use WOL Gateway without installing anything except Docker.

## Prerequisites

- Docker installed and running
- Know your server's MAC address
- On the same network as the server you want to wake

## Steps

### 1. Create Configuration File

Create a file named `WOL_Brige.config`:

```json
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
```

**Replace:**
- `00:11:22:33:44:55` with your server's MAC address
- `http://192.168.1.100` with your server's URL/IP
- `30` with seconds to wait before redirecting

### 2. Run the Container

```bash
docker run -d \
  --name wol-gateway \
  --cap-add NET_ADMIN \
  --cap-add NET_RAW \
  -p 5000:5000 \
  -v $(pwd)/WOL_Brige.config:/app/WOL_Brige.config:ro \
  --restart unless-stopped \
  yourusername/wol-gateway:latest
```

### 3. Access the Gateway

Open your browser: http://localhost:5000

Or from another device: http://YOUR_IP:5000

## Useful Commands

```bash
# View logs
docker logs wol-gateway

# Follow logs (Ctrl+C to exit)
docker logs -f wol-gateway

# Stop the gateway
docker stop wol-gateway

# Start the gateway
docker start wol-gateway

# Restart after config change
docker restart wol-gateway

# Remove the container
docker rm -f wol-gateway

# Update to latest version
docker pull yourusername/wol-gateway:latest
docker rm -f wol-gateway
# Then run the docker run command again
```

## Multiple Servers

Edit your config file to add more servers:

```json
{
  "PORT": 5000,
  "SERVERS": [
    {
      "NAME": "Gaming PC",
      "MAC": "00:11:22:33:44:55",
      "URL": "http://192.168.1.100",
      "WAIT": 30
    },
    {
      "NAME": "Media Server",
      "MAC": "AA:BB:CC:DD:EE:FF",
      "URL": "http://192.168.1.101:8096",
      "WAIT": 45
    }
  ]
}
```

After editing, restart the container:
```bash
docker restart wol-gateway
```

## Troubleshooting

### Can't access from other devices?

Check your firewall:
```bash
# Allow port 5000
sudo ufw allow 5000/tcp
```

### Wake-on-LAN not working?

1. Check server's BIOS - enable Wake-on-LAN
2. Check server's OS network settings - enable WOL
3. Ensure both devices are on the same network
4. Verify MAC address is correct

### Container won't start?

Check logs:
```bash
docker logs wol-gateway
```

Verify config file syntax:
```bash
cat WOL_Brige.config | python3 -m json.tool
```

## Using Docker Compose (Alternative)

Create `docker-compose.yml`:

```yaml
services:
  wol-gateway:
    image: yourusername/wol-gateway:latest
    container_name: wol-gateway
    cap_add:
      - NET_ADMIN
      - NET_RAW
    ports:
      - "5000:5000"
    volumes:
      - ./WOL_Brige.config:/app/WOL_Brige.config:ro
    restart: unless-stopped
```

Then:
```bash
# Start
docker compose up -d

# Stop
docker compose down

# Update
docker compose pull && docker compose up -d
```

## Health Check

The container includes a health check. View status:
```bash
docker inspect wol-gateway | grep -A 10 Health
```

Healthy container will show `"Status": "healthy"`
