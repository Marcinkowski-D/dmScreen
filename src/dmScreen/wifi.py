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
        # Check if hostapd process is running
        result = subprocess.run(['pgrep', 'hostapd'], capture_output=True, text=True)
        return result.returncode == 0
    except:
        return False

def create_adhoc_network():
    """Create an ad-hoc network if WiFi is not connected"""
    try:
        # Stop any existing hostapd and dnsmasq processes
        try:
            subprocess.run(['sudo', 'pkill', 'hostapd'], capture_output=True)
            subprocess.run(['sudo', 'pkill', 'dnsmasq'], capture_output=True)
        except Exception as e:
            print(f"Warning when stopping existing processes: {e}")
        
        # Ensure hostapd directory exists
        import os
        hostapd_dir = '/etc/hostapd'
        
        # Try to create the directory using sudo
        try:
            if not os.path.exists(hostapd_dir):
                subprocess.run(['sudo', 'mkdir', '-p', hostapd_dir], check=True)
                print(f"Created directory: {hostapd_dir}")
                
            # Use sudo to write the configuration file
            hostapd_conf = """interface=wlan0
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
"""
            # Write to a temporary file first
            with open('hostapd.conf.tmp', 'w') as f:
                f.write(hostapd_conf)
            
            # Then use sudo to move it to the correct location
            subprocess.run(['sudo', 'mv', 'hostapd.conf.tmp', '/etc/hostapd/hostapd.conf'], check=True)
            print("Hostapd configuration written successfully")
        except subprocess.CalledProcessError as e:
            raise Exception(f"Failed to create hostapd configuration: {e}")
            
        # Configure dnsmasq
        dnsmasq_dir = '/etc'
        
        # Try to create the directory using sudo (though /etc should always exist)
        try:
            if not os.path.exists(dnsmasq_dir):
                subprocess.run(['sudo', 'mkdir', '-p', dnsmasq_dir], check=True)
                print(f"Created directory: {dnsmasq_dir}")
            
            # Use sudo to write the configuration file
            dnsmasq_conf = """interface=wlan0
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
"""
            # Write to a temporary file first
            with open('dnsmasq.conf.tmp', 'w') as f:
                f.write(dnsmasq_conf)
            
            # Then use sudo to move it to the correct location
            subprocess.run(['sudo', 'mv', 'dnsmasq.conf.tmp', '/etc/dnsmasq.conf'], check=True)
            print("Dnsmasq configuration written successfully")
        except subprocess.CalledProcessError as e:
            raise Exception(f"Failed to create dnsmasq configuration: {e}")
        
        # Configure network interface
        subprocess.run(['sudo', 'ifconfig', 'wlan0', '192.168.4.1', 'netmask', '255.255.255.0'])
        
        # Start services directly as processes instead of using systemctl
        try:
            # Start hostapd in the background
            subprocess.Popen(['sudo', 'hostapd', '/etc/hostapd/hostapd.conf'], 
                            stdout=subprocess.DEVNULL, 
                            stderr=subprocess.DEVNULL)
            
            # Start dnsmasq in the background
            subprocess.Popen(['sudo', 'dnsmasq', '-C', '/etc/dnsmasq.conf'],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
            
            # Give the processes a moment to start
            time.sleep(2)
        except FileNotFoundError:
            print("Error: hostapd or dnsmasq not found. Please install them with:")
            print("sudo apt-get install hostapd dnsmasq")
            return False
        
        print("Ad-hoc network created successfully")
        return True
    except FileNotFoundError as e:
        print(f"Error creating ad-hoc network - File or directory not found: {e}")
        print("Make sure hostapd and dnsmasq are installed: sudo apt-get install hostapd dnsmasq")
        return False
    except PermissionError as e:
        print(f"Error creating ad-hoc network - Permission denied: {e}")
        print("Make sure the script is run with sufficient privileges")
        return False
    except Exception as e:
        print(f"Error creating ad-hoc network: {e}")
        return False

def configure_wifi(ssid, password):
    """Configure WiFi with provided credentials"""
    try:
        # Stop ad-hoc network processes if running
        try:
            subprocess.run(['sudo', 'pkill', 'hostapd'], capture_output=True)
            subprocess.run(['sudo', 'pkill', 'dnsmasq'], capture_output=True)
        except Exception as e:
            print(f"Warning when stopping existing processes: {e}")
        
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