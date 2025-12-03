# Proxmox Auto-Shutdown Script

This script monitors Pterodactyl-hosted game servers and automatically shuts down your Proxmox server after 5 minutes of no user activity.

## Features

- ✅ Monitors all Pterodactyl servers via API
- ✅ 5-minute inactivity timer before shutdown
- ✅ Automatic reset when users connect
- ✅ Logging for troubleshooting
- ✅ Optional network connection monitoring as backup

## Setup Instructions

### 1. Install Required Dependencies on Proxmox

SSH into your Proxmox server and run:

```bash
apt update
apt install python3 python3-pip -y
pip3 install requests
```

Optional (for Minecraft-specific monitoring):
```bash
pip3 install mcstatus
```

### 2. Get Your Pterodactyl API Key

1. Log into your Pterodactyl Panel
2. Go to **Application** → **API** → **Create New**
3. Give it a description like "Auto-Shutdown Monitor"
4. Enable the following permissions:
   - **Servers**: Read
   - **Nodes**: Read (optional)
5. Copy the generated API key

### 3. Configure the Script

Edit the `auto stop.py` file and update these settings:

```python
# Your Pterodactyl Panel URL
PTERODACTYL_URL = "https://panel.thethings.qzz.io"

# Your API key from step 2
API_KEY = "YOUR_API_KEY_HERE"

# Timeout in seconds (default: 300 = 5 minutes)
INACTIVITY_TIMEOUT = 300

# How often to check (default: 60 = 1 minute)
CHECK_INTERVAL = 60
```

### 4. Transfer Script to Proxmox

From your PC, use SCP or WinSCP to copy the script:

```powershell
scp "auto stop.py" root@YOUR_PROXMOX_IP:/root/auto_shutdown.py
```

Or manually copy the contents via nano:
```bash
nano /root/auto_shutdown.py
# Paste the script content, then Ctrl+X, Y, Enter
chmod +x /root/auto_shutdown.py
```

### 5. Test the Script

Run manually first to test:

```bash
python3 /root/auto_shutdown.py
```

Watch the output - it should show:
- Connected servers
- Inactivity timer countdown
- "Activity detected" when someone connects

Press Ctrl+C to stop the test.

### 6. Set Up Automatic Startup (Systemd Service)

Create a systemd service to run the script automatically on boot:

```bash
nano /etc/systemd/system/auto-shutdown.service
```

Paste this content:

```ini
[Unit]
Description=Pterodactyl Auto-Shutdown Monitor
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root
ExecStart=/usr/bin/python3 /root/auto_shutdown.py
Restart=on-failure
RestartSec=10
StandardOutput=append:/var/log/auto_shutdown.log
StandardError=append:/var/log/auto_shutdown.log

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
systemctl daemon-reload
systemctl enable auto-shutdown.service
systemctl start auto-shutdown.service
```

Check status:
```bash
systemctl status auto-shutdown.service
```

View logs:
```bash
tail -f /var/log/auto_shutdown.log
```

## How It Works

1. **Every 60 seconds** (configurable), the script checks all Pterodactyl servers
2. If any server is **running**, the inactivity timer is **reset to 0**
3. If **no servers are active**, the timer increments by 60 seconds
4. When the timer reaches **300 seconds (5 minutes)**, Proxmox **shuts down**
5. Use your WOL gateway script to wake it back up when needed!

## Monitoring Methods

The script uses multiple methods to detect activity:

1. **Pterodactyl API** - Checks if servers are running (primary method)
2. **Network Connections** - Checks for established connections on game ports (backup, commented out by default)
3. **Minecraft Query** - Direct server query for player count (optional, requires `mcstatus`)

## Customization

### Change Timeout Duration

```python
INACTIVITY_TIMEOUT = 600  # 10 minutes
```

### Change Check Frequency

```python
CHECK_INTERVAL = 30  # Check every 30 seconds
```

### Add Network Monitoring

Uncomment these lines in the main loop:

```python
has_network_activity = check_network_connections()
has_connections = has_connections or has_network_activity
```

### Prevent Shutdown (Maintenance Mode)

Stop the service temporarily:
```bash
systemctl stop auto-shutdown.service
```

Resume:
```bash
systemctl start auto-shutdown.service
```

## Troubleshooting

### Script not detecting connections

1. Verify API key has correct permissions
2. Check logs: `tail -f /var/log/auto_shutdown.log`
3. Test API manually:
   ```bash
   curl -H "Authorization: Bearer YOUR_API_KEY" \
        https://panel.thethings.qzz.io/api/application/servers
   ```

### Script not shutting down

1. Check user permissions (must run as root)
2. Test shutdown command manually: `shutdown -h now`
3. Review systemd logs: `journalctl -u auto-shutdown.service -f`

### Want to disable auto-shutdown

```bash
systemctl disable auto-shutdown.service
systemctl stop auto-shutdown.service
```

## Integration with WOL Gateway

This script works perfectly with your existing `wol_gateway.py`:

1. **No users connected** → Proxmox shuts down after 5 minutes
2. **User visits your site** → WOL gateway wakes up Proxmox
3. **Proxmox boots up** → Auto-shutdown script starts monitoring
4. **User plays/browses** → Server stays on
5. **User leaves** → Timer starts, shutdown after 5 minutes

Perfect for saving electricity! ⚡💰

## Support

If you need help, check:
- Script logs: `/var/log/auto_shutdown.log`
- Systemd logs: `journalctl -u auto-shutdown.service`
- Pterodactyl Panel status
