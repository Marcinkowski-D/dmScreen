import subprocess
import time
import threading
from flask import jsonify, request

# WiFi-related functions

def check_wifi_connection():
    """Check if WiFi is connected"""
    try:
        # This command works on Raspberry Pi with Raspbian
        result = subprocess.run(['iwgetid', '-r'], capture_output=True, text=True)
        print(result.stdout.strip())
        return result.stdout.strip() != ""
    except:
        return False
        
def check_adhoc_network():
    """Check if adhoc network is active"""
    try:
        # Check if hostapd service is running
        result = subprocess.run(['systemctl', 'is-active', 'hostapd'], capture_output=True, text=True)
        return result.stdout.strip() == "active"
    except:
        return False

def create_adhoc_network():
    """Create an ad-hoc network if WiFi is not connected"""
    try:
        # Stop any existing hostapd and dnsmasq services
        subprocess.run(['sudo', 'systemctl', 'stop', 'hostapd', 'dnsmasq'])
        
        # Configure hostapd
        with open('/etc/hostapd/hostapd.conf', 'w') as f:
            f.write("""interface=wlan0
driver=nl80211
ssid=DMScreen
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=dmscreen123
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
""")
        
        # Configure dnsmasq
        with open('/etc/dnsmasq.conf', 'w') as f:
            f.write("""interface=wlan0
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
""")
        
        # Configure network interface
        subprocess.run(['sudo', 'ifconfig', 'wlan0', '192.168.4.1', 'netmask', '255.255.255.0'])
        
        # Start services
        subprocess.run(['sudo', 'systemctl', 'start', 'hostapd', 'dnsmasq'])
        
        return True
    except Exception as e:
        print(f"Error creating ad-hoc network: {e}")
        return False

def configure_wifi(ssid, password):
    """Configure WiFi with provided credentials"""
    try:
        # Stop ad-hoc network if running
        subprocess.run(['sudo', 'systemctl', 'stop', 'hostapd', 'dnsmasq'])
        
        # Update wpa_supplicant configuration
        with open('/etc/wpa_supplicant/wpa_supplicant.conf', 'w') as f:
            f.write(f"""ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=US

network={{
    ssid="{ssid}"
    psk="{password}"
    key_mgmt=WPA-PSK
}}
""")
        
        # Reconfigure wpa_supplicant
        subprocess.run(['sudo', 'wpa_cli', '-i', 'wlan0', 'reconfigure'])
        
        # Wait for connection
        time.sleep(10)
        
        return check_wifi_connection()
    except Exception as e:
        print(f"Error configuring WiFi: {e}")
        return False

def wifi_monitor():
    """Background thread to monitor WiFi and create ad-hoc network if needed"""
    while True:
        if not check_wifi_connection():
            create_adhoc_network()
        time.sleep(60)  # Check every minute

# Flask route handlers for WiFi functionality
def register_wifi_routes(app):
    @app.route('/api/wifi/status', methods=['GET'])
    def get_wifi_status():
        connected = check_wifi_connection()
        adhoc_active = False
        adhoc_ssid = None
        
        if not connected:
            adhoc_active = check_adhoc_network()
            if adhoc_active:
                adhoc_ssid = "DMScreen"  # This is the SSID set in create_adhoc_network()
                
        return jsonify({
            'connected': connected,
            'ssid': subprocess.run(['iwgetid', '-r'], capture_output=True, text=True).stdout.strip() if connected else None,
            'adhoc_active': adhoc_active,
            'adhoc_ssid': adhoc_ssid
        })

    @app.route('/api/wifi/configure', methods=['POST'])
    def set_wifi_config():
        data = request.get_json()
        ssid = data.get('ssid')
        password = data.get('password')
        
        if not ssid or not password:
            return jsonify({'error': 'SSID and password are required'}), 400
        
        success = configure_wifi(ssid, password)
        
        return jsonify({
            'success': success,
            'message': 'WiFi configured successfully' if success else 'Failed to configure WiFi'
        })

    return {
        'get_wifi_status': get_wifi_status,
        'set_wifi_config': set_wifi_config
    }

def start_wifi_monitor():
    """Start the WiFi monitoring thread"""
    threading.Thread(target=wifi_monitor, daemon=True).start()