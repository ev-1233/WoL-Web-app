#!/usr/bin/env python3
"""
Admin Panel Module for WOL Gateway

This module provides a web-based admin panel for managing the WOL Gateway configuration.
Features:
  - Password-protected access
  - Optional 2FA via TOTP authenticator apps
  - Configuration management for all servers
  - Add/edit/delete server entries
  - Does NOT allow changing Flask port (requires restart)
"""

import json
import os
import hashlib
import secrets
from functools import wraps
from flask import Blueprint, render_template_string, request, redirect, url_for, session, flash
import pyotp
import qrcode
from io import BytesIO
import base64

# Create Blueprint for admin routes
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Configuration files
CONFIG_FILE = "WOL_Brige.config"
ADMIN_CONFIG_FILE = "admin_config.json"

# Session secret key - should be generated on first run
SECRET_KEY = secrets.token_hex(32)


def load_admin_config():
    """Load admin configuration from file."""
    if not os.path.exists(ADMIN_CONFIG_FILE):
        # Create default config with users array
        default_config = {
            "admin_enabled": False,
            "users": []
        }
        save_admin_config(default_config)
        return default_config
    
    try:
        with open(ADMIN_CONFIG_FILE, 'r') as f:
            config = json.load(f)
            
            # Migrate old single-user format to new multi-user format
            if 'admin_username' in config and 'users' not in config:
                old_user = {
                    "username": config.get('admin_username', 'admin'),
                    "password_hash": config.get('admin_password_hash', ''),
                    "2fa_enabled": config.get('2fa_enabled', False),
                    "2fa_secret": config.get('2fa_secret', '')
                }
                config = {
                    "admin_enabled": config.get('admin_enabled', False),
                    "users": [old_user] if old_user['password_hash'] else []
                }
                save_admin_config(config)
            
            return config
    except:
        return {
            "admin_enabled": False,
            "users": []
        }


def save_admin_config(config):
    """Save admin configuration to file."""
    with open(ADMIN_CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)


def hash_password(password):
    """Hash a password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password, password_hash):
    """Verify a password against its hash."""
    return hash_password(password) == password_hash


def login_required(f):
    """Decorator to require admin login."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        admin_config = load_admin_config()
        
        # If admin panel is disabled, show error
        if not admin_config.get('admin_enabled', False):
            return "Admin panel is disabled. Enable it using setup_wol.py", 403
        
        # Check if user is logged in
        if 'admin_logged_in' not in session or not session.get('admin_logged_in'):
            return redirect(url_for('admin.login'))
        
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Admin login page."""
    admin_config = load_admin_config()
    
    # If admin panel is disabled, show error
    if not admin_config.get('admin_enabled', False):
        return "Admin panel is disabled. Enable it using setup_wol.py", 403
    
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        totp_code = request.form.get('totp_code', '')
        
        # Find user in users array
        user = None
        for u in admin_config.get('users', []):
            if u['username'] == username and verify_password(password, u['password_hash']):
                user = u
                break
        
        if user:
            # Check 2FA if enabled for this user
            if user.get('2fa_enabled', False):
                totp = pyotp.TOTP(user['2fa_secret'])
                if not totp.verify(totp_code, valid_window=1):
                    error = "Invalid 2FA code"
                    return render_template_string(LOGIN_TEMPLATE, error=error, 
                                                 require_2fa=True)
            
            # Login successful
            session['admin_logged_in'] = True
            session['admin_username'] = username
            session.permanent = True
            return redirect(url_for('admin.dashboard'))
        else:
            error = "Invalid username or password"
            # Check if any user has 2FA to show the field
            any_2fa = any(u.get('2fa_enabled', False) for u in admin_config.get('users', []))
            return render_template_string(LOGIN_TEMPLATE, error=error,
                                         require_2fa=any_2fa)
    
    # Check if any user has 2FA enabled
    any_2fa = any(u.get('2fa_enabled', False) for u in admin_config.get('users', []))
    return render_template_string(LOGIN_TEMPLATE, error=None, require_2fa=any_2fa)


@admin_bp.route('/logout')
def logout():
    """Admin logout."""
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    return redirect(url_for('admin.login'))


@admin_bp.route('/')
@login_required
def dashboard():
    """Main admin dashboard."""
    # Load current configuration
    if not os.path.exists(CONFIG_FILE):
        return "Configuration file not found. Run setup_wol.py first.", 500
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
    except:
        return "Error loading configuration file.", 500
    
    servers = config.get('SERVERS', [])
    port = config.get('PORT', 5000)
    
    return render_template_string(DASHBOARD_TEMPLATE, servers=servers, port=port)


@admin_bp.route('/server/add', methods=['GET', 'POST'])
@login_required
def add_server():
    """Add a new server."""
    if request.method == 'POST':
        # Load current config
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        
        # Create new server entry
        new_server = {
            "NAME": request.form.get('name', '').strip(),
            "WOL_MAC_ADDRESS": request.form.get('mac', '').strip(),
            "BROADCAST_ADDRESS": request.form.get('broadcast', '255.255.255.255').strip(),
            "SITE_URL": request.form.get('url', '').strip(),
            "WAIT_TIME_SECONDS": int(request.form.get('wait_time', 60))
        }
        
        # Add to servers list
        config['SERVERS'].append(new_server)
        
        # Save config
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        
        flash('Server added successfully! Restart the application for changes to take effect.', 'success')
        return redirect(url_for('admin.dashboard'))
    
    return render_template_string(SERVER_FORM_TEMPLATE, server=None, action='Add')


@admin_bp.route('/server/edit/<int:server_id>', methods=['GET', 'POST'])
@login_required
def edit_server(server_id):
    """Edit an existing server."""
    # Load current config
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
    
    servers = config.get('SERVERS', [])
    
    if server_id < 0 or server_id >= len(servers):
        return "Invalid server ID", 404
    
    if request.method == 'POST':
        # Update server entry
        servers[server_id] = {
            "NAME": request.form.get('name', '').strip(),
            "WOL_MAC_ADDRESS": request.form.get('mac', '').strip(),
            "BROADCAST_ADDRESS": request.form.get('broadcast', '255.255.255.255').strip(),
            "SITE_URL": request.form.get('url', '').strip(),
            "WAIT_TIME_SECONDS": int(request.form.get('wait_time', 60))
        }
        
        # Save config
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        
        flash('Server updated successfully! Restart the application for changes to take effect.', 'success')
        return redirect(url_for('admin.dashboard'))
    
    server = servers[server_id]
    return render_template_string(SERVER_FORM_TEMPLATE, server=server, 
                                 action='Edit', server_id=server_id)


@admin_bp.route('/server/delete/<int:server_id>', methods=['POST'])
@login_required
def delete_server(server_id):
    """Delete a server."""
    # Load current config
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
    
    servers = config.get('SERVERS', [])
    
    if server_id < 0 or server_id >= len(servers):
        return "Invalid server ID", 404
    
    # Remove server
    deleted_name = servers[server_id]['NAME']
    servers.pop(server_id)
    
    # Save config
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)
    
    flash(f'Server "{deleted_name}" deleted successfully! Restart the application for changes to take effect.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/restart', methods=['POST'])
@login_required
def restart_application():
    """Restart the Flask application."""
    import sys
    import os
    
    # Check if running in Docker
    is_docker = os.path.exists('/.dockerenv')
    
    flash('Restarting application... Please wait a few seconds and refresh the page.', 'success')
    
    # Use a background thread to exit after sending the response
    def exit_app():
        import time
        time.sleep(0.5)  # Give time for response to be sent
        os._exit(0)  # Force exit (Docker will restart the container)
    
    import threading
    threading.Thread(target=exit_app, daemon=True).start()
    
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/users')
@login_required
def manage_users():
    """Manage admin users."""
    admin_config = load_admin_config()
    users = admin_config.get('users', [])
    current_user = session.get('admin_username', '')
    
    return render_template_string(USER_MANAGEMENT_TEMPLATE, users=users, current_user=current_user)


@admin_bp.route('/users/add', methods=['GET', 'POST'])
@login_required
def add_user():
    """Add a new admin user."""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        enable_2fa = request.form.get('enable_2fa') == 'on'
        
        # Validate
        if not username:
            flash('Username is required', 'error')
            return render_template_string(USER_FORM_TEMPLATE, user=None, action='Add')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters', 'error')
            return render_template_string(USER_FORM_TEMPLATE, user=None, action='Add')
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template_string(USER_FORM_TEMPLATE, user=None, action='Add')
        
        # Check if username already exists
        admin_config = load_admin_config()
        if any(u['username'] == username for u in admin_config.get('users', [])):
            flash('Username already exists', 'error')
            return render_template_string(USER_FORM_TEMPLATE, user=None, action='Add')
        
        # Create new user
        new_user = {
            'username': username,
            'password_hash': hash_password(password),
            '2fa_enabled': enable_2fa,
            '2fa_secret': pyotp.random_base32() if enable_2fa else ''
        }
        
        admin_config['users'].append(new_user)
        save_admin_config(admin_config)
        
        flash(f'User "{username}" added successfully!', 'success')
        return redirect(url_for('admin.manage_users'))
    
    return render_template_string(USER_FORM_TEMPLATE, user=None, action='Add')


@admin_bp.route('/users/edit/<username>', methods=['GET', 'POST'])
@login_required
def edit_user(username):
    """Edit an admin user."""
    admin_config = load_admin_config()
    users = admin_config.get('users', [])
    
    # Find user
    user_index = None
    user = None
    for i, u in enumerate(users):
        if u['username'] == username:
            user_index = i
            user = u
            break
    
    if user is None:
        flash('User not found', 'error')
        return redirect(url_for('admin.manage_users'))
    
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        enable_2fa = request.form.get('enable_2fa') == 'on'
        
        # Update password if provided
        if password:
            if len(password) < 6:
                flash('Password must be at least 6 characters', 'error')
                return render_template_string(USER_FORM_TEMPLATE, user=user, action='Edit')
            
            if password != confirm_password:
                flash('Passwords do not match', 'error')
                return render_template_string(USER_FORM_TEMPLATE, user=user, action='Edit')
            
            users[user_index]['password_hash'] = hash_password(password)
        
        # Update 2FA
        users[user_index]['2fa_enabled'] = enable_2fa
        if enable_2fa and not users[user_index].get('2fa_secret'):
            users[user_index]['2fa_secret'] = pyotp.random_base32()
        
        save_admin_config(admin_config)
        flash(f'User "{username}" updated successfully!', 'success')
        return redirect(url_for('admin.manage_users'))
    
    return render_template_string(USER_FORM_TEMPLATE, user=user, action='Edit')


@admin_bp.route('/users/delete/<username>', methods=['POST'])
@login_required
def delete_user(username):
    """Delete an admin user."""
    current_user = session.get('admin_username', '')
    
    # Prevent deleting yourself
    if username == current_user:
        flash('Cannot delete your own account', 'error')
        return redirect(url_for('admin.manage_users'))
    
    admin_config = load_admin_config()
    users = admin_config.get('users', [])
    
    # Find and remove user
    admin_config['users'] = [u for u in users if u['username'] != username]
    
    save_admin_config(admin_config)
    flash(f'User "{username}" deleted successfully!', 'success')
    return redirect(url_for('admin.manage_users'))


@admin_bp.route('/security', methods=['GET', 'POST'])
@login_required
def security_settings():
    """Security settings page."""
    admin_config = load_admin_config()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'change_password':
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')
            
            # Verify current password
            if not verify_password(current_password, admin_config['admin_password_hash']):
                flash('Current password is incorrect', 'error')
            elif new_password != confirm_password:
                flash('New passwords do not match', 'error')
            elif len(new_password) < 6:
                flash('Password must be at least 6 characters', 'error')
            else:
                admin_config['admin_password_hash'] = hash_password(new_password)
                save_admin_config(admin_config)
                flash('Password changed successfully', 'success')
        
        elif action == 'enable_2fa':
            # Check if TOTP is available
            if not TOTP_AVAILABLE:
                flash('2FA requires pyotp and qrcode packages. Install with: pip3 install pyotp qrcode pillow', 'error')
                return redirect(url_for('admin.security_settings'))
            
            # Generate new 2FA secret
            secret = pyotp.random_base32()
            admin_config['2fa_secret'] = secret
            admin_config['2fa_enabled'] = False  # Not enabled until verified
            save_admin_config(admin_config)
            
            # Generate QR code
            totp = pyotp.TOTP(secret)
            provisioning_uri = totp.provisioning_uri(
                name=admin_config['admin_username'],
                issuer_name="WOL Gateway"
            )
            
            qr_code = generate_qr_code(provisioning_uri)
            return render_template_string(SETUP_2FA_TEMPLATE, 
                                         secret=secret,
                                         qr_code=qr_code)
        
        elif action == 'verify_2fa':
            totp_code = request.form.get('totp_code', '')
            totp = pyotp.TOTP(admin_config['2fa_secret'])
            
            if totp.verify(totp_code, valid_window=1):
                admin_config['2fa_enabled'] = True
                save_admin_config(admin_config)
                flash('2FA enabled successfully', 'success')
                return redirect(url_for('admin.security_settings'))
            else:
                flash('Invalid 2FA code. Please try again.', 'error')
                return redirect(url_for('admin.security_settings'))
        
        elif action == 'disable_2fa':
            password = request.form.get('password', '')
            if verify_password(password, admin_config['admin_password_hash']):
                admin_config['2fa_enabled'] = False
                admin_config['2fa_secret'] = ''
                save_admin_config(admin_config)
                flash('2FA disabled successfully', 'success')
            else:
                flash('Incorrect password', 'error')
        
        return redirect(url_for('admin.security_settings'))
    
    return render_template_string(SECURITY_TEMPLATE, 
                                 two_fa_enabled=admin_config.get('2fa_enabled', False))


# HTML Templates
LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Admin Login - WOL Gateway</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        :root {
            --bg-color: #ffffff;
            --text-color: #333333;
            --card-bg: #ffffff;
            --border-color: #e0e0e0;
            --input-bg: #ffffff;
            --shadow: rgba(0,0,0,0.2);
        }
        [data-theme="dark"] {
            --bg-color: #1a1a1a;
            --text-color: #e0e0e0;
            --card-bg: #2d2d2d;
            --border-color: #404040;
            --input-bg: #3d3d3d;
            --shadow: rgba(0,0,0,0.5);
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: var(--bg-color);
            color: var(--text-color);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            transition: background-color 0.3s, color 0.3s;
        }
        .login-container {
            background: var(--card-bg);
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 10px 40px var(--shadow);
            width: 100%;
            max-width: 400px;
            position: relative;
        }
        .theme-toggle {
            position: fixed;
            top: 15px;
            left: 15px;
            background: none;
            border: none;
            font-size: 24px;
            cursor: pointer;
            opacity: 0.7;
            transition: opacity 0.2s;
            z-index: 1000;
            color: var(--text-color);
        }
        .theme-toggle:hover {
            opacity: 1;
        }
        h1 {
            text-align: center;
            color: var(--text-color);
            margin-bottom: 30px;
            font-size: 24px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            color: var(--text-color);
            font-weight: 500;
        }
        input[type="text"], input[type="password"] {
            width: 100%;
            padding: 12px;
            border: 2px solid var(--border-color);
            border-radius: 5px;
            font-size: 14px;
            transition: border-color 0.3s;
            background: var(--input-bg);
            color: var(--text-color);
        }
        input[type="text"]:focus, input[type="password"]:focus {
            outline: none;
            border-color: #667eea;
        }
        button {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 5px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
        }
        button:hover {
            transform: translateY(-2px);
        }
        button:active {
            transform: translateY(0);
        }
        .error {
            background: #fee;
            color: #c33;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 20px;
            border-left: 4px solid #c33;
        }
        .lock-icon {
            text-align: center;
            font-size: 48px;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <button class="theme-toggle" onclick="toggleTheme()" title="Toggle dark mode"><i class="fas fa-moon"></i></button>
    <div class="login-container">
        <div class="lock-icon"><i class="fas fa-lock"></i></div>
        <h1>WOL Gateway Admin</h1>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        <form method="POST">
            <div class="form-group">
                <label for="username">Username</label>
                <input type="text" id="username" name="username" required autofocus>
            </div>
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required>
            </div>
            {% if require_2fa %}
            <div class="form-group">
                <label for="totp_code">2FA Code</label>
                <input type="text" id="totp_code" name="totp_code" required 
                       placeholder="6-digit code" pattern="[0-9]{6}" maxlength="6">
            </div>
            {% endif %}
            <button type="submit">Login</button>
        </form>
    </div>
    <script>
        function toggleTheme() {
            const html = document.documentElement;
            const currentTheme = html.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            html.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeIcon();
        }
        function updateThemeIcon() {
            const theme = document.documentElement.getAttribute('data-theme');
            const toggle = document.querySelector('.theme-toggle i');
            toggle.className = theme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
        }
        // Load theme on page load
        const savedTheme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-theme', savedTheme);
        updateThemeIcon();
    </script>
</body>
</html>
'''

DASHBOARD_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Admin Dash - WOL Gateway</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        :root {
            --bg-color: #f5f5f5;
            --text-color: #333333;
            --card-bg: #ffffff;
            --border-color: #e0e0e0;
            --hover-bg: #f8f9fa;
            --shadow: rgba(0,0,0,0.1);
        }
        [data-theme="dark"] {
            --bg-color: #1a1a1a;
            --text-color: #e0e0e0;
            --card-bg: #2d2d2d;
            --border-color: #404040;
            --hover-bg: #3d3d3d;
            --shadow: rgba(0,0,0,0.3);
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: var(--bg-color);
            color: var(--text-color);
            padding: 20px;
            transition: background-color 0.3s, color 0.3s;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        .header {
            background: var(--card-bg);
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px var(--shadow);
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        h1 { color: var(--text-color); font-size: 24px; }
        .theme-toggle {
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
        }
        .theme-toggle:hover {
            opacity: 1;
        }
        .nav {
            display: flex;
            gap: 15px;
        }
        .nav a, .nav button {
            padding: 10px 20px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 5px;
            border: none;
            cursor: pointer;
            font-size: 14px;
        }
        .nav a:hover, .nav button:hover {
            background: #5568d3;
        }
        .nav .restart-btn {
            background: #f39c12;
        }
        .nav .restart-btn:hover {
            background: #e67e22;
        }
        .nav .logout {
            background: #e74c3c;
        }
        .nav .logout:hover {
            background: #c0392b;
        }
        .alert {
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .alert-success {
            background: #d4edda;
            color: #155724;
            border-left: 4px solid #28a745;
        }
        .card {
            background: var(--card-bg);
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px var(--shadow);
            margin-bottom: 20px;
        }
        .card h2 {
            color: var(--text-color);
            margin-bottom: 15px;
            font-size: 20px;
        }
        .info-box {
            background: var(--hover-bg);
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .info-box p {
            margin: 5px 0;
            color: var(--text-color);
        }
        .info-box strong {
            color: var(--text-color);
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th {
            background: var(--hover-bg);
            padding: 12px;
            text-align: left;
            font-weight: 600;
            color: var(--text-color);
            border-bottom: 2px solid var(--border-color);
        }
        td {
            padding: 12px;
            border-bottom: 1px solid var(--border-color);
            color: var(--text-color);
        }
        tr:hover {
            background: var(--hover-bg);
        }
        .actions {
            display: flex;
            gap: 10px;
        }
        .btn {
            padding: 6px 12px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
            text-decoration: none;
            display: inline-block;
        }
        .btn-edit {
            background: #3498db;
            color: white;
        }
        .btn-edit:hover {
            background: #2980b9;
        }
        .btn-delete {
            background: #e74c3c;
            color: white;
        }
        .btn-delete:hover {
            background: #c0392b;
        }
        .btn-add {
            background: #27ae60;
            color: white;
            padding: 10px 20px;
            margin-bottom: 15px;
            display: inline-block;
        }
        .btn-add:hover {
            background: #229954;
        }
        .warning {
            background: #fff3cd;
            color: #856404;
            padding: 15px;
            border-radius: 5px;
            border-left: 4px solid #ffc107;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <button class="theme-toggle" onclick="toggleTheme()" title="Toggle dark mode"><i class="fas fa-moon"></i></button>
    <div class="container">
        <div class="header">
            <h1><i class="fas fa-cog"></i> Admin Dash</h1>
            <div class="nav">
                <a href="{{ url_for('admin.manage_users') }}"><i class="fas fa-users"></i> Users</a>
                <a href="{{ url_for('admin.security_settings') }}"><i class="fas fa-shield-alt"></i> Security</a>
                <a href="/" target="_blank"><i class="fas fa-home"></i> Home</a>
                <form method="POST" action="{{ url_for('admin.restart_application') }}" style="display: inline;">
                    <button type="submit" class="restart-btn" onclick="return confirm('Are you sure you want to restart the application? This will take a few seconds.');"><i class="fas fa-sync-alt"></i> Restart</button>
                </form>
                <a href="{{ url_for('admin.logout') }}" class="logout">Logout</a>
            </div>
        </div>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        <div class="warning">
            <i class="fas fa-exclamation-triangle"></i> <strong>Important:</strong> Configuration changes require restarting the WOL Gateway app.
        </div>
        
        <div class="card">
            <h2>Global Settings</h2>
            <div class="info-box">
                <p><strong>Flask Port:</strong> {{ port }}</p>
                <p><em>Note: Port cannot be changed from admin panel. Use setup_wol.py to change the port.</em></p>
            </div>
        </div>
        
        <div class="card">
            <h2>Server Configuration</h2>
            <a href="{{ url_for('admin.add_server') }}" class="btn btn-add"><i class="fas fa-plus"></i> Add New Server</a>
            
            {% if servers %}
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Name</th>
                        <th>MAC Address</th>
                        <th>Broadcast Address</th>
                        <th>Site URL</th>
                        <th>Wait Time</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {% for server in servers %}
                    <tr>
                        <td>{{ loop.index0 }}</td>
                        <td><strong>{{ server.NAME }}</strong></td>
                        <td><code>{{ server.WOL_MAC_ADDRESS }}</code></td>
                        <td>{{ server.BROADCAST_ADDRESS }}</td>
                        <td>{{ server.SITE_URL }}</td>
                        <td>{{ server.WAIT_TIME_SECONDS }}s</td>
                        <td>
                            <div class="actions">
                                <a href="{{ url_for('admin.edit_server', server_id=loop.index0) }}" 
                                   class="btn btn-edit">Edit</a>
                                <form method="POST" 
                                      action="{{ url_for('admin.delete_server', server_id=loop.index0) }}"
                                      style="display: inline;"
                                      onsubmit="return confirm('Are you sure you want to delete {{ server.NAME }}?');">
                                    <button type="submit" class="btn btn-delete">Delete</button>
                                </form>
                            </div>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <p style="color: #999; text-align: center; padding: 40px;">No servers configured yet.</p>
            {% endif %}
        </div>
    </div>
    <script>
        function toggleTheme() {
            const html = document.documentElement;
            const currentTheme = html.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            html.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeIcon();
        }
        function updateThemeIcon() {
            const theme = document.documentElement.getAttribute('data-theme');
            const toggle = document.querySelector('.theme-toggle i');
            toggle.className = theme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
        }
        const savedTheme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-theme', savedTheme);
        updateThemeIcon();
    </script>
</body>
</html>
'''

SERVER_FORM_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>{{ action }} Server - WOL Gateway</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        :root {
            --bg-color: #f5f5f5;
            --text-color: #333333;
            --card-bg: #ffffff;
            --border-color: #e0e0e0;
            --input-bg: #ffffff;
            --shadow: rgba(0,0,0,0.1);
        }
        [data-theme="dark"] {
            --bg-color: #1a1a1a;
            --text-color: #e0e0e0;
            --card-bg: #2d2d2d;
            --border-color: #404040;
            --input-bg: #3d3d3d;
            --shadow: rgba(0,0,0,0.3);
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: var(--bg-color);
            color: var(--text-color);
            padding: 20px;
            transition: background-color 0.3s, color 0.3s;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
        }
        .header {
            background: var(--card-bg);
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px var(--shadow);
            margin-bottom: 20px;
        }
        h1 { color: var(--text-color); font-size: 24px; }
        .card {
            background: var(--card-bg);
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px var(--shadow);
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            color: var(--text-color);
            font-weight: 500;
        }
        input[type="text"], input[type="number"] {
            width: 100%;
            padding: 12px;
            border: 2px solid var(--border-color);
            border-radius: 5px;
            font-size: 14px;
            background: var(--input-bg);
            color: var(--text-color);
        }
        input[type="text"]:focus, input[type="number"]:focus {
            outline: none;
            border-color: #667eea;
        }
        .help-text {
            font-size: 12px;
            color: #999;
            margin-top: 5px;
        }
        .button-group {
            display: flex;
            gap: 10px;
            margin-top: 30px;
        }
        button, .btn-link {
            padding: 12px 24px;
            border: none;
            border-radius: 5px;
            font-size: 14px;
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
        }
        button[type="submit"] {
            background: #27ae60;
            color: white;
        }
        button[type="submit"]:hover {
            background: #229954;
        }
        .btn-link {
            background: #95a5a6;
            color: white;
        }
        .btn-link:hover {
            background: #7f8c8d;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{{ action }} Server</h1>
        </div>
        
        <div class="card">
            <form method="POST">
                <div class="form-group">
                    <label for="name">Server Name *</label>
                    <input type="text" id="name" name="name" required
                           value="{{ server.NAME if server else '' }}">
                    <div class="help-text">A friendly name for this server (e.g., "Main Server", "NAS")</div>
                </div>
                
                <div class="form-group">
                    <label for="mac">MAC Address *</label>
                    <input type="text" id="mac" name="mac" required
                           pattern="([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})"
                           value="{{ server.WOL_MAC_ADDRESS if server else '' }}"
                           placeholder="00:11:22:33:44:55">
                    <div class="help-text">MAC address in format XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX</div>
                </div>
                
                <div class="form-group">
                    <label for="broadcast">Broadcast Address</label>
                    <input type="text" id="broadcast" name="broadcast"
                           value="{{ server.BROADCAST_ADDRESS if server else '255.255.255.255' }}">
                    <div class="help-text">Network broadcast address (default: 255.255.255.255)</div>
                </div>
                
                <div class="form-group">
                    <label for="url">Site URL *</label>
                    <input type="text" id="url" name="url" required
                           value="{{ server.SITE_URL if server else '' }}"
                           placeholder="http://192.168.1.100:8080">
                    <div class="help-text">URL to redirect to after waking the server</div>
                </div>
                
                <div class="form-group">
                    <label for="wait_time">Wait Time (seconds) *</label>
                    <input type="number" id="wait_time" name="wait_time" required min="1"
                           value="{{ server.WAIT_TIME_SECONDS if server else '60' }}">
                    <div class="help-text">How long to wait before redirecting (typically 30-120 seconds)</div>
                </div>
                
                <div class="button-group">
                    <button type="submit"><i class="fas fa-save"></i> Save Server</button>
                    <a href="{{ url_for('admin.dashboard') }}" class="btn-link">Cancel</a>
                </div>
            </form>
        </div>
    </div>
    <script>
        const savedTheme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-theme', savedTheme);
    </script>
</body>
</html>
'''

SECURITY_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Security Settings - WOL Gateway</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        :root {
            --bg-color: #f5f5f5;
            --text-color: #333333;
            --card-bg: #ffffff;
            --border-color: #e0e0e0;
            --input-bg: #ffffff;
            --hover-bg: #f8f9fa;
            --shadow: rgba(0,0,0,0.1);
        }
        [data-theme="dark"] {
            --bg-color: #1a1a1a;
            --text-color: #e0e0e0;
            --card-bg: #2d2d2d;
            --border-color: #404040;
            --input-bg: #3d3d3d;
            --hover-bg: #3d3d3d;
            --shadow: rgba(0,0,0,0.3);
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: var(--bg-color);
            color: var(--text-color);
            padding: 20px;
            transition: background-color 0.3s, color 0.3s;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
        }
        .header {
            background: var(--card-bg);
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px var(--shadow);
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        h1 { color: var(--text-color); font-size: 24px; }
        .nav a {
            padding: 10px 20px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 5px;
        }
        .nav a:hover {
            background: #5568d3;
        }
        .alert {
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .alert-success {
            background: #d4edda;
            color: #155724;
            border-left: 4px solid #28a745;
        }
        .alert-error {
            background: #f8d7da;
            color: #721c24;
            border-left: 4px solid #dc3545;
        }
        .card {
            background: var(--card-bg);
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px var(--shadow);
            margin-bottom: 20px;
        }
        .card h2 {
            color: var(--text-color);
            margin-bottom: 20px;
            font-size: 20px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            color: var(--text-color);
            font-weight: 500;
        }
        input[type="password"] {
            width: 100%;
            padding: 12px;
            border: 2px solid var(--border-color);
            border-radius: 5px;
            font-size: 14px;
            background: var(--input-bg);
            color: var(--text-color);
        }
        input[type="password"]:focus {
            outline: none;
            border-color: #667eea;
        }
        button {
            padding: 12px 24px;
            border: none;
            border-radius: 5px;
            font-size: 14px;
            cursor: pointer;
            color: white;
        }
        .btn-primary {
            background: #667eea;
        }
        .btn-primary:hover {
            background: #5568d3;
        }
        .btn-success {
            background: #27ae60;
        }
        .btn-success:hover {
            background: #229954;
        }
        .btn-danger {
            background: #e74c3c;
        }
        .btn-danger:hover {
            background: #c0392b;
        }
        .status-badge {
            display: inline-block;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
        }
        .status-enabled {
            background: #d4edda;
            color: #155724;
        }
        .status-disabled {
            background: #f8d7da;
            color: #721c24;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1><i class="fas fa-shield-alt"></i> Security Settings</h1>
            <div class="nav">
                <a href="{{ url_for('admin.dashboard') }}">← Back to Dashboard</a>
            </div>
        </div>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        <div class="card">
            <h2>Change Password</h2>
            <form method="POST">
                <input type="hidden" name="action" value="change_password">
                <div class="form-group">
                    <label for="current_password">Current Password</label>
                    <input type="password" id="current_password" name="current_password" required>
                </div>
                <div class="form-group">
                    <label for="new_password">New Password</label>
                    <input type="password" id="new_password" name="new_password" required minlength="6">
                </div>
                <div class="form-group">
                    <label for="confirm_password">Confirm New Password</label>
                    <input type="password" id="confirm_password" name="confirm_password" required minlength="6">
                </div>
                <button type="submit" class="btn-primary">Update Password</button>
            </form>
        </div>
        
        <div class="card">
            <h2>Two-Factor Authentication (2FA)</h2>
            <p style="margin-bottom: 15px;">
                Status: 
                {% if two_fa_enabled %}
                <span class="status-badge status-enabled"><i class="fas fa-check"></i> Enabled</span>
                {% else %}
                <span class="status-badge status-disabled"><i class="fas fa-times"></i> Disabled</span>
                {% endif %}
            </p>
            
            {% if two_fa_enabled %}
            <p style="color: #555; margin-bottom: 20px;">
                Two-factor authentication is currently enabled. Enter your password to disable it.
            </p>
            <form method="POST">
                <input type="hidden" name="action" value="disable_2fa">
                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required>
                </div>
                <button type="submit" class="btn-danger">Disable 2FA</button>
            </form>
            {% else %}
            <p style="color: #555; margin-bottom: 20px;">
                Add an extra layer of security by requiring a 6-digit code from your authenticator app 
                (Google Authenticator, Authy, etc.) when logging in.
            </p>
            <form method="POST">
                <input type="hidden" name="action" value="enable_2fa">
                <button type="submit" class="btn-success">Enable 2FA</button>
            </form>
            {% endif %}
        </div>
    </div>
    <script>
        const savedTheme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-theme', savedTheme);
    </script>
</body>
</html>
'''

SETUP_2FA_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Setup 2FA - WOL Gateway</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        :root {
            --bg-color: #f5f5f5;
            --text-color: #333333;
            --card-bg: #ffffff;
            --border-color: #e0e0e0;
            --input-bg: #ffffff;
            --step-bg: #f8f9fa;
            --shadow: rgba(0,0,0,0.1);
        }
        [data-theme="dark"] {
            --bg-color: #1a1a1a;
            --text-color: #e0e0e0;
            --card-bg: #2d2d2d;
            --border-color: #404040;
            --input-bg: #3d3d3d;
            --step-bg: #3d3d3d;
            --shadow: rgba(0,0,0,0.3);
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: var(--bg-color);
            color: var(--text-color);
            padding: 20px;
            transition: background-color 0.3s, color 0.3s;
        }
        .container {
            max-width: 600px;
            margin: 0 auto;
        }
        .card {
            background: var(--card-bg);
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px var(--shadow);
        }
        h1 {
            color: var(--text-color);
            margin-bottom: 20px;
            font-size: 24px;
            text-align: center;
        }
        .step {
            margin-bottom: 25px;
            padding: 15px;
            background: var(--step-bg);
            border-radius: 5px;
        }
        .step h3 {
            color: #667eea;
            margin-bottom: 10px;
            font-size: 16px;
        }
        .step p {
            color: var(--text-color);
            line-height: 1.6;
        }
        .step ul {
            color: var(--text-color);
        }
        .qr-container {
            text-align: center;
            margin: 20px 0;
        }
        .qr-container img {
            max-width: 250px;
            border: 2px solid var(--border-color);
            border-radius: 5px;
            padding: 10px;
            background: white;
        }
        .secret-code {
            background: #e8f4f8;
            padding: 15px;
            border-radius: 5px;
            text-align: center;
            margin: 20px 0;
            border: 1px solid #b8dce8;
        }
        .secret-code code {
            font-size: 18px;
            font-weight: 600;
            color: #2c3e50;
            letter-spacing: 2px;
        }
        .form-group {
            margin: 20px 0;
        }
        label {
            display: block;
            margin-bottom: 5px;
            color: var(--text-color);
            font-weight: 500;
        }
        input[type="text"] {
            width: 100%;
            padding: 12px;
            border: 2px solid var(--border-color);
            border-radius: 5px;
            font-size: 16px;
            text-align: center;
            letter-spacing: 5px;
            background: var(--input-bg);
            color: var(--text-color);
        }
        input[type="text"]:focus {
            outline: none;
            border-color: #667eea;
        }
        button {
            width: 100%;
            padding: 12px;
            background: #27ae60;
            color: white;
            border: none;
            border-radius: 5px;
            font-size: 16px;
            cursor: pointer;
        }
        button:hover {
            background: #229954;
        }
        .cancel-link {
            display: block;
            text-align: center;
            margin-top: 15px;
            color: #999;
            text-decoration: none;
        }
        .cancel-link:hover {
            color: #667eea;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1><i class="fas fa-shield-alt"></i> Setup Two-Factor Authentication</h1>
            
            <div class="step">
                <h3>Step 1: Install an Authenticator App</h3>
                <p>If you don't have one already, install an authenticator app on your phone:</p>
                <ul style="margin-top: 10px; margin-left: 20px; color: #555;">
                    <li>Google Authenticator (iOS/Android)</li>
                    <li>Microsoft Authenticator (iOS/Android)</li>
                    <li>Authy (iOS/Android/Desktop)</li>
                </ul>
            </div>
            
            <div class="step">
                <h3>Step 2: Scan QR Code</h3>
                <p>Open your authenticator app and scan this QR code:</p>
                <div class="qr-container">
                    <img src="data:image/png;base64,{{ qr_code }}" alt="2FA QR Code">
                </div>
                <p style="text-align: center; color: #999; font-size: 14px;">Or enter this code manually:</p>
                <div class="secret-code">
                    <code>{{ secret }}</code>
                </div>
            </div>
            
            <div class="step">
                <h3>Step 3: Verify Setup</h3>
                <p>Enter the 6-digit code from your authenticator app to complete setup:</p>
            </div>
            
            <form method="POST" action="{{ url_for('admin.security_settings') }}">
                <input type="hidden" name="action" value="verify_2fa">
                <div class="form-group">
                    <label for="totp_code">6-Digit Code</label>
                    <input type="text" id="totp_code" name="totp_code" required 
                           pattern="[0-9]{6}" maxlength="6" placeholder="000000" autofocus>
                </div>
                <button type="submit"><i class="fas fa-check"></i> Verify and Enable 2FA</button>
            </form>
            
            <a href="{{ url_for('admin.security_settings') }}" class="cancel-link">Cancel</a>
        </div>
    </div>
    <script>
        const savedTheme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-theme', savedTheme);
    </script>
</body>
</html>
'''


def generate_qr_code(provisioning_uri):
    """Generate QR code as base64 image."""
    if not TOTP_AVAILABLE:
        return ""
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    
    return base64.b64encode(buffer.getvalue()).decode()


# User Management Templates
USER_MANAGEMENT_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Manage Users - WOL Gateway</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        .header {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        h1 { color: #333; font-size: 24px; }
        .nav {
            display: flex;
            gap: 15px;
        }
        .nav a, .nav button {
            padding: 10px 20px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 5px;
            border: none;
            cursor: pointer;
            font-size: 14px;
        }
        .nav a:hover, .nav button:hover {
            background: #5568d3;
        }
        .card {
            background: var(--card-bg);
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px var(--shadow);
        }
        h2 {
            color: var(--text-color);
            margin-bottom: 20px;
            font-size: 20px;
        }
        .alert {
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .alert-success {
            background: #d4edda;
            color: #155724;
            border-left: 4px solid #28a745;
        }
        .alert-error {
            background: #f8d7da;
            color: #721c24;
            border-left: 4px solid #dc3545;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th {
            text-align: left;
            padding: 12px;
            background: var(--hover-bg);
            font-weight: 600;
            color: var(--text-color);
            border-bottom: 2px solid var(--border-color);
        }
        td {
            padding: 12px;
            border-bottom: 1px solid var(--border-color);
            color: var(--text-color);
        }
        tr:hover {
            background: var(--hover-bg);
        }
        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 3px;
            font-size: 12px;
            font-weight: 600;
        }
        .badge-success {
            background: #d4edda;
            color: #155724;
        }
        .badge-secondary {
            background: #e2e3e5;
            color: #383d41;
        }
        .actions {
            display: flex;
            gap: 10px;
        }
        .btn {
            padding: 6px 12px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
            text-decoration: none;
            display: inline-block;
        }
        .btn-edit {
            background: #3498db;
            color: white;
        }
        .btn-edit:hover {
            background: #2980b9;
        }
        .btn-delete {
            background: #e74c3c;
            color: white;
        }
        .btn-delete:hover {
            background: #c0392b;
        }
        .btn-add {
            background: #27ae60;
            color: white;
            padding: 10px 20px;
            margin-bottom: 15px;
            display: inline-block;
        }
        .btn-add:hover {
            background: #229954;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1><i class="fas fa-users"></i> User Management</h1>
            <div class="nav">
                <a href="{{ url_for('admin.dashboard') }}">← Back to Dashboard</a>
            </div>
        </div>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        <div class="card">
            <h2>Admin Users</h2>
            <a href="{{ url_for('admin.add_user') }}" class="btn btn-add"><i class="fas fa-plus"></i> Add New User</a>
            
            {% if users %}
            <table>
                <thead>
                    <tr>
                        <th>Username</th>
                        <th>2FA Status</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {% for user in users %}
                    <tr>
                        <td>
                            <strong>{{ user.username }}</strong>
                            {% if user.username == current_user %}
                            <span class="badge badge-success">You</span>
                            {% endif %}
                        </td>
                        <td>
                            {% if user['2fa_enabled'] %}
                            <span class="badge badge-success"><i class="fas fa-check"></i> Enabled</span>
                            {% else %}
                            <span class="badge badge-secondary">Disabled</span>
                            {% endif %}
                        </td>
                        <td>
                            <div class="actions">
                                <a href="{{ url_for('admin.edit_user', username=user.username) }}" 
                                   class="btn btn-edit">Edit</a>
                                {% if user.username != current_user %}
                                <form method="POST" 
                                      action="{{ url_for('admin.delete_user', username=user.username) }}"
                                      style="display: inline;"
                                      onsubmit="return confirm('Are you sure you want to delete {{ user.username }}?');">
                                    <button type="submit" class="btn btn-delete">Delete</button>
                                </form>
                                {% endif %}
                            </div>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <p style="color: #999; text-align: center; padding: 40px;">No users configured yet.</p>
            {% endif %}
        </div>
    </div>
    <script>
        const savedTheme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-theme', savedTheme);
    </script>
</body>
</html>
'''

USER_FORM_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>{{ action }} User - WOL Gateway</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        :root {
            --bg-color: #f5f5f5;
            --text-color: #333333;
            --card-bg: #ffffff;
            --border-color: #e0e0e0;
            --input-bg: #ffffff;
            --shadow: rgba(0,0,0,0.1);
        }
        [data-theme="dark"] {
            --bg-color: #1a1a1a;
            --text-color: #e0e0e0;
            --card-bg: #2d2d2d;
            --border-color: #404040;
            --input-bg: #3d3d3d;
            --shadow: rgba(0,0,0,0.3);
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: var(--bg-color);
            color: var(--text-color);
            min-height: 100vh;
            padding: 20px;
            transition: background-color 0.3s, color 0.3s;
        }
        .container {
            max-width: 600px;
            margin: 0 auto;
        }
        .card {
            background: var(--card-bg);
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px var(--shadow);
        }
        h1 {
            color: var(--text-color);
            margin-bottom: 20px;
            font-size: 24px;
        }
        .alert {
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .alert-error {
            background: #f8d7da;
            color: #721c24;
            border-left: 4px solid #dc3545;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: var(--text-color);
            font-weight: 500;
        }
        input[type="text"],
        input[type="password"] {
            width: 100%;
            padding: 12px;
            border: 1px solid var(--border-color);
            border-radius: 5px;
            font-size: 14px;
            background: var(--input-bg);
            color: var(--text-color);
        }
        input[type="checkbox"] {
            width: 20px;
            height: 20px;
            margin-right: 10px;
        }
        .checkbox-group {
            display: flex;
            align-items: center;
        }
        button {
            width: 100%;
            padding: 12px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 5px;
            font-size: 16px;
            cursor: pointer;
            margin-top: 10px;
        }
        button:hover {
            background: #5568d3;
        }
        .cancel-link {
            display: block;
            text-align: center;
            margin-top: 15px;
            color: #667eea;
            text-decoration: none;
        }
        .note {
            color: #666;
            font-size: 13px;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1>{{ action }} Admin User</h1>
            
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                    <div class="alert alert-{{ category }}">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            
            <form method="POST">
                {% if action == 'Add' %}
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" required autofocus>
                </div>
                {% else %}
                <div class="form-group">
                    <label>Username</label>
                    <input type="text" value="{{ user.username }}" disabled>
                    <p class="note">Username cannot be changed</p>
                </div>
                {% endif %}
                
                <div class="form-group">
                    <label for="password">Password{% if action == 'Edit' %} (leave blank to keep current){% endif %}</label>
                    <input type="password" id="password" name="password" {% if action == 'Add' %}required{% endif %} minlength="6">
                    <p class="note">Minimum 6 characters</p>
                </div>
                
                <div class="form-group">
                    <label for="confirm_password">Confirm Password</label>
                    <input type="password" id="confirm_password" name="confirm_password" {% if action == 'Add' %}required{% endif %}>
                </div>
                
                <div class="form-group">
                    <div class="checkbox-group">
                        <input type="checkbox" id="enable_2fa" name="enable_2fa" 
                               {% if user and user['2fa_enabled'] %}checked{% endif %}>
                        <label for="enable_2fa" style="margin: 0;">Enable Two-Factor Authentication (2FA)</label>
                    </div>
                </div>
                
                <button type="submit">{{ action }} User</button>
            </form>
            
            <a href="{{ url_for('admin.manage_users') }}" class="cancel-link">Cancel</a>
        </div>
    </div>
    <script>
        const savedTheme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-theme', savedTheme);
    </script>
</body>
</html>
'''
