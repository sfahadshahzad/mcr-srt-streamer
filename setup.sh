#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
APP_DIR="/opt/mcr-srt-streamer"
VENV_DIR="/opt/venv"
LOG_DIR="/var/log/srt-streamer"
NGINX_CONF="/etc/nginx/sites-available/mcr-srt-streamer.conf"
SYSTEMD_CONF="/etc/systemd/system/mcr-srt-streamer.service"
APP_USER="root" # Or another user like 'www-data' or 'nginx'
APP_GROUP="root"

# --- Helper Functions ---
info() {
    echo "[INFO] $1"
}

warn() {
    echo "[WARN] $1"
}

error() {
    echo "[ERROR] $1" >&2
    exit 1
}

# --- Pre-flight Checks ---
check_root() {
    if [ "$EUID" -ne 0 ]; then
        error "This script must be run as root. Please use sudo."
    fi
}

detect_os() {
    if [ -f /etc/os-release ]; then
        # freedesktop.org and systemd
        . /etc/os-release
        OS=$ID
        VER=$VERSION_ID
    else
        error "Cannot detect operating system."
    fi
    info "Detected OS: $OS version $VER"
}

# --- Installation Functions ---

install_packages_debian() {
    info "Updating package lists..."
    apt-get update

    info "Installing dependencies for Debian/Ubuntu..."
    # This list is based on the README for Ubuntu/Debian and includes GStreamer 'bad' plugins for DeckLink support.
    apt-get install -y \
        python3 python3-pip python3-venv python3-gi gir1.2-gobject-2.0 gir1.2-glib-2.0 \
        libgirepository1.0-dev gcc libcairo2-dev pkg-config python3-dev \
        gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 \
        gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
        gstreamer1.0-plugins-ugly gstreamer1.0-tools gstreamer1.0-libav gstreamer1.0-x264 \
        nginx curl iperf3 iputils-ping dnsutils ffmpeg mediainfo apache2-utils
}

install_packages_rhel() {
    info "Installing dependencies for RHEL/Rocky..."
    # This is a complex installation on RHEL, assuming RPM Fusion is available.
    # The user should enable EPEL and RPM Fusion first as per README.
    warn "This script assumes EPEL and RPM Fusion repositories are enabled on RHEL-based systems."
    dnf install -y \
        python3 python3-pip python3-gobject gobject-introspection-devel cairo-gobject-devel \
        python3-devel pkgconf-pkg-config gcc gcc-c++ \
        gstreamer1 gstreamer1-plugins-base gstreamer1-plugins-good \
        gstreamer1-plugins-bad-free gstreamer1-plugins-ugly-free gstreamer1-libav \
        gstreamer1-plugin-x264 \
        nginx curl iperf3 iputils bind-utils ffmpeg mediainfo httpd-tools \
        python3-gunicorn python3-gevent
}

setup_python_venv() {
    info "Setting up Python virtual environment in $VENV_DIR..."
    if [ -d "$VENV_DIR" ]; then
        warn "Virtual environment directory already exists. Skipping creation."
    else
        python3 -m venv "$VENV_DIR"
    fi

    info "Installing Python requirements..."
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt"
}

create_directories_and_files() {
    info "Creating application directories and data files..."
    mkdir -p "$APP_DIR/media"
    mkdir -p "$LOG_DIR"
    mkdir -p "$APP_DIR/app/data"

    # Create empty data files if they don't exist
    touch "$APP_DIR/app/data/external_ip_cache.json"
    touch "$APP_DIR/app/data/iperf3_export_servers.json"
    touch "$APP_DIR/app/data/iptv_channels.json"

    info "Setting ownership of application directories..."
    chown -R "$APP_USER":"$APP_GROUP" "$APP_DIR"
    chown -R "$APP_USER":"$APP_GROUP" "$LOG_DIR"
    # Venv should also be owned by the app user
    chown -R "$APP_USER":"$APP_GROUP" "$VENV_DIR"
}

configure_nginx() {
    info "Configuring NGINX reverse proxy..."
    cat > "$NGINX_CONF" <<EOF
server {
    listen 80;
    server_name _;

    access_log /var/log/nginx/srt-streamer-access.log;
    error_log /var/log/nginx/srt-streamer-error.log;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # API endpoints without authentication (if using API keys)
    location ~ ^/(api|smpte2022_7/api|sdi/api)/ {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

    # Enable the site by creating a symlink
    if [ ! -L "/etc/nginx/sites-enabled/mcr-srt-streamer.conf" ]; then
        ln -s "$NGINX_CONF" /etc/nginx/sites-enabled/mcr-srt-streamer.conf
    fi

    # Remove default site if it exists
    if [ -L "/etc/nginx/sites-enabled/default" ]; then
        rm /etc/nginx/sites-enabled/default
    fi

    info "Testing NGINX configuration..."
    nginx -t
}

configure_systemd() {
    info "Generating new SECRET_KEY and API_KEY..."
    SECRET_KEY=$(openssl rand -hex 32)
    API_KEY=$(openssl rand -hex 32)

    info "Configuring systemd service..."
    cat > "$SYSTEMD_CONF" <<EOF
[Unit]
Description=MCR SRT Streamer
After=network.target nginx.service
Wants=nginx.service

[Service]
Type=simple
WorkingDirectory=$APP_DIR
User=$APP_USER
Group=$APP_GROUP

# --- Generated Keys ---
Environment="SECRET_KEY=$SECRET_KEY"
Environment="API_KEY=$API_KEY"

# --- Other Environment Variables ---
Environment="THREADS=8"
Environment="MEDIA_FOLDER=$APP_DIR/media"
Environment="FLASK_ENV=production"
Environment="NETWORK_TEST_MECHANISM=ping_only"

# Use --workers 1 to prevent issues with GLib loops in a multi-process environment.
# Use --worker-class gevent for WebSocket/async support.
ExecStart=$VENV_DIR/bin/gunicorn --workers 1 --worker-class gevent --bind 127.0.0.1:5000 --timeout 90 --log-level=info wsgi:app
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    info "Reloading systemd daemon..."
    systemctl daemon-reload
}

# --- Main Execution ---
main() {
    check_root
    detect_os

    if [ "$OS" == "ubuntu" ] || [ "$OS" == "debian" ]; then
        install_packages_debian
        setup_python_venv
    elif [ "$OS" == "rhel" ] || [ "$OS" == "rocky" ] || [ "$OS" == "centos" ]; then
        install_packages_rhel
        # RHEL setup in README installs python packages system-wide, so no venv step.
        warn "Skipping Python venv setup for RHEL-based system as per README instructions."
        pip3 install -r "$APP_DIR/requirements.txt"
    else
        error "Unsupported operating system: $OS"
    fi

    create_directories_and_files
    configure_nginx
    configure_systemd

    info "--------------------------------------------------"
    info "Setup complete!"
    info "A new SECRET_KEY and API_KEY have been generated and saved in $SYSTEMD_CONF."
    info "Please review the NGINX configuration at $NGINX_CONF."
    info ""
    info "To start the application, run:"
    info "sudo systemctl start mcr-srt-streamer.service"
    info ""
    info "To enable the application to start on boot, run:"
    info "sudo systemctl enable mcr-srt-streamer.service"
    info ""
    info "To check the status, run:"
    info "sudo systemctl status mcr-srt-streamer.service"
    info "To view logs, run:"
    info "journalctl -u mcr-srt-streamer.service -f"
    info "--------------------------------------------------"
}

main
