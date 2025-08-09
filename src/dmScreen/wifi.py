import os
import json
import subprocess
import time
import threading
from threading import Lock
from flask import jsonify, request

# File-based storage for known WiFi networks (cleartext as required)
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_DATA_DIR = os.path.join(_PROJECT_ROOT, 'data')
KNOWN_WIFI_FILE = os.path.join(_DATA_DIR, 'wifi_networks.json')
_os_lock = Lock()

# Ensure data directory exists
os.makedirs(_DATA_DIR, exist_ok=True)

# -----------------------------
# Helpers for known networks
# -----------------------------

def _load_known_networks():
    try:
        with _os_lock:
            if not os.path.exists(KNOWN_WIFI_FILE):
                return []
            with open(KNOWN_WIFI_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                return data.get('networks', [])
    except Exception:
        return []


def _save_known_networks(networks):
    with _os_lock:
        with open(KNOWN_WIFI_FILE, 'w', encoding='utf-8') as f:
            json.dump({'networks': networks}, f, indent=2, ensure_ascii=False)


def add_known_network(ssid, password):
    networks = _load_known_networks()
    updated = False
    for n in networks:
        if n.get('ssid') == ssid:
            n['password'] = password
            updated = True
            break
    if not updated:
        networks.append({'ssid': ssid, 'password': password})
    _save_known_networks(networks)
    return True


def list_known_networks():
    return _load_known_networks()


def remove_known_network(ssid):
    networks = _load_known_networks()
    new_list = [n for n in networks if n.get('ssid') != ssid]
    removed = len(new_list) != len(networks)
    if removed:
        _save_known_networks(new_list)
    return removed

# -----------------------------
# WiFi/OS utilities
# -----------------------------

def _run_cmd(args, check=False):
    try:
        return subprocess.run(args, capture_output=True, text=True, check=check)
    except Exception as e:
        return subprocess.CompletedProcess(args=args, returncode=1, stdout='', stderr=str(e))


# WiFi-related functions

def check_wifi_connection():
    """Check if WiFi is connected (Raspberry Pi: iwgetid -r)"""
    try:
        result = _run_cmd(['iwgetid', '-r'])
        return result.stdout.strip() != ''
    except Exception:
        return False


def current_ssid():
    try:
        result = _run_cmd(['iwgetid', '-r'])
        return result.stdout.strip() or None
    except Exception:
        return None


def check_adhoc_network():
    """Check if adhoc network (hostapd) is active"""
    try:
        result = _run_cmd(['systemctl', 'is-active', 'hostapd'])
        return result.stdout.strip() == 'active'
    except Exception:
        return False


def _stop_ap_services():
    _run_cmd(['sudo', 'systemctl', 'stop', 'hostapd', 'dnsmasq'])


def _start_ap_services():
    _run_cmd(['sudo', 'systemctl', 'start', 'hostapd', 'dnsmasq'])


def _write_hostapd_and_dnsmasq():
    """Write configs for hostapd and dnsmasq for AP SSID/password 'dmscreen'"""
    hostapd_conf = """interface=wlan0
ssid=dmscreen
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=dmscreen
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
"""
    dnsmasq_conf = """interface=wlan0
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
"""
    try:
        # Ensure dirs
        if not os.path.exists('/etc/hostapd'):
            _run_cmd(['sudo', 'mkdir', '-p', '/etc/hostapd'], check=True)
        # Write temp files then move with sudo mv
        with open('hostapd.conf.tmp', 'w', encoding='utf-8') as f:
            f.write(hostapd_conf)
        _run_cmd(['sudo', 'mv', 'hostapd.conf.tmp', '/etc/hostapd/hostapd.conf'], check=True)

        with open('dnsmasq.conf.tmp', 'w', encoding='utf-8') as f:
            f.write(dnsmasq_conf)
        _run_cmd(['sudo', 'mv', 'dnsmasq.conf.tmp', '/etc/dnsmasq.conf'], check=True)
        return True
    except Exception as e:
        print(f'Failed to write AP configs: {e}')
        return False


def create_adhoc_network():
    """Create an ad-hoc AP if no WiFi connected. SSID/PW = dmscreen/dmscreen"""
    try:
        _stop_ap_services()
        ok = _write_hostapd_and_dnsmasq()
        # Set static IP on wlan0 for AP network
        _run_cmd(['sudo', 'ifconfig', 'wlan0', '192.168.4.1', 'netmask', '255.255.255.0'])
        if ok:
            _start_ap_services()
        # Wait briefly and verify
        time.sleep(2)
        is_active = check_adhoc_network()
        if is_active:
            print('Ad-hoc network (dmscreen) is active')
        else:
            print('Ad-hoc network failed to start')
        return is_active
    except Exception as e:
        print(f"Error creating ad-hoc network: {e}")
        return False


def _write_wpa_supplicant(networks):
    """Write /etc/wpa_supplicant/wpa_supplicant.conf with multiple networks"""
    header = """ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=DE

"""
    blocks = []
    for prio, net in enumerate(networks[::-1], start=1):
        ssid = net.get('ssid', '')
        psk = net.get('password', '')
        blocks.append(
            f"network={{\n    ssid=\"{ssid}\"\n    psk=\"{psk}\"\n    key_mgmt=WPA-PSK\n    priority={prio}\n}}\n"
        )
    content = header + ''.join(blocks)
    with open('wpa_supplicant.conf.tmp', 'w', encoding='utf-8') as f:
        f.write(content)
    _run_cmd(['sudo', 'mv', 'wpa_supplicant.conf.tmp', '/etc/wpa_supplicant/wpa_supplicant.conf'], check=True)


def _reconfigure_wpa():
    _run_cmd(['sudo', 'wpa_cli', '-i', 'wlan0', 'reconfigure'])


def _os_forget_network_wpa(ssid: str):
    """Remove matching SSID networks from wpa_supplicant runtime and save config."""
    try:
        res = _run_cmd(['sudo', 'wpa_cli', '-i', 'wlan0', 'list_networks'])
        if res.returncode != 0 or not res.stdout:
            return False
        removed_any = False
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line or line.lower().startswith('network id'):
                continue
            # wpa_cli list_networks output is tab-separated: id\tssid\tbssid\tflags
            parts = [p for p in line.split('\t') if p != '']
            if len(parts) < 2:
                parts = [p for p in line.split() if p != '']
            if len(parts) >= 2:
                nid = parts[0].strip()
                s = parts[1].strip()
                if s == ssid:
                    _run_cmd(['sudo', 'wpa_cli', '-i', 'wlan0', 'remove_network', nid])
                    removed_any = True
        if removed_any:
            _run_cmd(['sudo', 'wpa_cli', '-i', 'wlan0', 'save_config'])
            _reconfigure_wpa()
        return removed_any
    except Exception as e:
        print(f'_os_forget_network_wpa error: {e}')
        return False


def _os_forget_network_nmcli(ssid: str):
    """If NetworkManager is present, delete connection with this SSID name."""
    try:
        res = _run_cmd(['nmcli', '-t', '-f', 'NAME,TYPE', 'connection', 'show'])
        if res.returncode != 0 or not res.stdout:
            return False
        deleted = False
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(':')
            if len(parts) >= 2:
                name, ctype = parts[0], parts[1]
                # typical types: wifi or 802-11-wireless
                if name == ssid and ('wifi' in ctype or '802-11-wireless' in ctype):
                    _run_cmd(['sudo', 'nmcli', 'connection', 'delete', 'id', ssid])
                    deleted = True
        return deleted
    except Exception as e:
        # nmcli may not exist; ignore
        return False


def _forget_network_everywhere(ssid: str):
    removed = False
    try:
        if ssid:
            removed = _os_forget_network_wpa(ssid) or removed
    except Exception:
        pass
    try:
        if ssid:
            removed = _os_forget_network_nmcli(ssid) or removed
    except Exception:
        pass
    return removed


def _scan_visible_ssids():
    """Return a set of visible SSIDs using iw or nmcli"""
    ssids = set()
    # Try iw dev wlan0 scan
    res = _run_cmd(['iw', 'dev', 'wlan0', 'scan'])
    if res.returncode == 0 and res.stdout:
        for line in res.stdout.splitlines():
            line = line.strip()
            if line.startswith('SSID:'):
                ssids.add(line.split('SSID:', 1)[1].strip())
    else:
        # Fallback to iwlist
        res2 = _run_cmd(['iwlist', 'wlan0', 'scanning'])
        if res2.returncode == 0 and res2.stdout:
            for line in res2.stdout.splitlines():
                line = line.strip()
                if line.startswith('ESSID:'):
                    name = line.split('ESSID:', 1)[1].strip().strip('"')
                    if name:
                        ssids.add(name)
        else:
            # Fallback to nmcli
            res3 = _run_cmd(['nmcli', '-t', '-f', 'SSID', 'dev', 'wifi'])
            if res3.returncode == 0 and res3.stdout:
                for line in res3.stdout.splitlines():
                    name = line.strip()
                    if name:
                        ssids.add(name)
    return ssids


def connect_best_known_network():
    """Try to connect to the best available known network based on scan results"""
    try:
        known = _load_known_networks()
        if not known:
            return False
        visible = _scan_visible_ssids()
        if not visible:
            return False
        # Keep networks that are visible
        candidates = [n for n in known if n.get('ssid') in visible]
        if not candidates:
            return False
        # Prefer order in the stored list (latest wins at higher priority)
        _stop_ap_services()
        _write_wpa_supplicant(candidates)
        _reconfigure_wpa()
        time.sleep(8)
        return check_wifi_connection()
    except Exception as e:
        print(f'connect_best_known_network error: {e}')
        return False


def configure_wifi(ssid, password):
    """Configure WiFi: persist credentials and attempt to connect"""
    try:
        add_known_network(ssid, password)
        # Write full known list to wpa_supplicant
        networks = _load_known_networks()
        _stop_ap_services()
        _write_wpa_supplicant(networks)
        _reconfigure_wpa()
        time.sleep(8)
        return check_wifi_connection()
    except Exception as e:
        print(f"Error configuring WiFi: {e}")
        return False


def disconnect_and_forget_current():
    """Disconnect from the currently connected WiFi and forget it from known networks.
    Returns (success, ssid)."""
    try:
        ssid = current_ssid()
        # Proactively remove the network from OS runtime configs so it won't reconnect
        if ssid:
            try:
                _forget_network_everywhere(ssid)
            except Exception:
                pass
        # Attempt to disconnect regardless of state
        _run_cmd(['sudo', 'wpa_cli', '-i', 'wlan0', 'disconnect'])
        # Remove from known networks if present
        if ssid:
            try:
                remove_known_network(ssid)
            except Exception:
                pass
        # Rewrite wpa_supplicant based on remaining networks and reconfigure
        try:
            nets = _load_known_networks()
            _write_wpa_supplicant(nets)
            _reconfigure_wpa()
        except Exception as e:
            print(f'Error updating wpa_supplicant during disconnect: {e}')
        time.sleep(3)
        return True, ssid
    except Exception as e:
        print(f'disconnect_and_forget_current error: {e}')
        return False, None


def wifi_monitor():
    """Background thread to ensure connectivity: connect to known networks, else start AP"""
    while True:
        try:
            if not check_wifi_connection():
                # Try connect to the best known network first
                connected = connect_best_known_network()
                if not connected and not check_adhoc_network():
                    create_adhoc_network()
        except Exception as e:
            print(f'wifi_monitor loop error: {e}')
        time.sleep(60)  # Check every minute

# Flask route handlers for WiFi functionality
def register_wifi_routes(app, on_change=None):
    @app.route('/api/wifi/status', methods=['GET'])
    def get_wifi_status():
        connected = check_wifi_connection()
        adhoc_active = False
        adhoc_ssid = None
        if not connected:
            adhoc_active = check_adhoc_network()
            if adhoc_active:
                adhoc_ssid = 'dmscreen'
        return jsonify({
            'connected': connected,
            'ssid': current_ssid() if connected else None,
            'adhoc_active': adhoc_active,
            'adhoc_ssid': adhoc_ssid
        })

    @app.route('/api/wifi/configure', methods=['POST'])
    def set_wifi_config():
        data = request.get_json() or {}
        ssid = data.get('ssid')
        password = data.get('password')
        if not ssid or not password:
            return jsonify({'error': 'SSID and password are required'}), 400
        success = configure_wifi(ssid, password)
        if success and on_change:
            try:
                on_change()
            except Exception:
                pass
        return jsonify({
            'success': success,
            'message': 'WiFi configured successfully' if success else 'Failed to configure WiFi'
        })

    @app.route('/api/wifi/known', methods=['GET'])
    def api_list_known():
        return jsonify({'networks': list_known_networks()})

    @app.route('/api/wifi/known', methods=['POST'])
    def api_add_known():
        data = request.get_json() or {}
        ssid = data.get('ssid')
        password = data.get('password')
        if not ssid or not password:
            return jsonify({'error': 'SSID and password are required'}), 400
        add_known_network(ssid, password)
        if on_change:
            try:
                on_change()
            except Exception:
                pass
        return jsonify({'success': True})

    @app.route('/api/wifi/known/<ssid>', methods=['DELETE'])
    def api_remove_known(ssid):
        removed = remove_known_network(ssid)
        # Also ensure OS forgets the network so it won't reconnect
        try:
            _forget_network_everywhere(ssid)
        except Exception:
            pass
        # Update wpa_supplicant to reflect removal
        try:
            nets = _load_known_networks()
            _write_wpa_supplicant(nets)
            _reconfigure_wpa()
        except Exception:
            pass
        if on_change:
            try:
                on_change()
            except Exception:
                pass
        return jsonify({'removed': removed})

    @app.route('/api/wifi/scan', methods=['GET'])
    def api_scan():
        try:
            ssids = sorted(list(_scan_visible_ssids()))
            return jsonify({'ssids': ssids})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/wifi/disconnect', methods=['POST'])
    def api_disconnect():
        success, ssid = disconnect_and_forget_current()
        if success and on_change:
            try:
                on_change()
            except Exception:
                pass
        return jsonify({'success': success, 'ssid': ssid})

    return {
        'get_wifi_status': get_wifi_status,
        'set_wifi_config': set_wifi_config,
        'list_known': api_list_known,
        'add_known': api_add_known,
        'remove_known': api_remove_known,
        'scan': api_scan,
        'disconnect': api_disconnect,
    }


def start_wifi_monitor():
    """Start the WiFi monitoring thread"""
    threading.Thread(target=wifi_monitor, daemon=True).start()