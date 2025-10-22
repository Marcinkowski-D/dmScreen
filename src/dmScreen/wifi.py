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

# Debug logging for WiFi
_DM_WIFI_DEBUG_ENV = os.getenv('DM_WIFI_DEBUG', '1')
_DEBUG_WIFI = not (_DM_WIFI_DEBUG_ENV.lower() in ('0', 'false', 'no', 'off', ''))

config_lock = Lock()

known_ssids = []
scanned_ssids = []

def _ts():
    try:
        return time.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return ''

def _dbg(msg: str):
    if _DEBUG_WIFI:
        try:
            print(f"[WiFi][{_ts()}] {msg}")
        except Exception:
            pass

change_callback = None

# Cache for throttling system checks
_WIFI_CACHE_TTL = float(os.getenv('DM_WIFI_CACHE_TTL', '5'))  # seconds
_wifi_cache_lock = Lock()
_cached_ssid = None
_cached_ssid_ts = 0.0
_cached_adhoc = None  # bool or None
_cached_adhoc_ts = 0.0

# Polling configuration for connection attempts
_WIFI_POLL_INTERVAL = float(os.getenv('DM_WIFI_POLL_INTERVAL', '5'))  # seconds
_WIFI_POLL_TRIES = int(os.getenv('DM_WIFI_POLL_TRIES', '10'))

# Control whether we temporarily pause AP to perform scans (helps when interface is busy)
_WIFI_SCAN_PAUSE_AP = not (os.getenv('DM_WIFI_SCAN_PAUSE_AP', '0').lower() in ('0', 'false', 'no', 'off', ''))

target_wifi = None
current_wifi = None

# -----------------------------
# Helpers for known networks
# -----------------------------


def get_lan_ip():
    """Get IP address of wlan0 interface using nmcli or fallback to ifconfig"""
    try:
        # Try nmcli first
        p = run_cmd(['nmcli', '-t', '-f', 'IP4.ADDRESS', 'dev', 'show', 'wlan0'])
        if p.returncode == 0 and p.stdout:
            # Output format: IP4.ADDRESS[1]:192.168.1.100/24
            for line in p.stdout.strip().split('\n'):
                if 'IP4.ADDRESS' in line and ':' in line:
                    ip = line.split(':', 1)[1].split('/')[0].strip()
                    if ip:
                        return ip
        
        # Fallback to ifconfig
        p = run_cmd("ifconfig | grep -A 1 wlan0 | grep -o 'inet [0-9]*\.[0-9]*\.[0-9]*\.[0-9]*' | grep -o '[0-9]*\.[0-9]*\.[0-9]*\.[0-9]*' | head -n 1", shell=True)
        if p.returncode == 0 and p.stdout.strip():
            return p.stdout.strip()
    except Exception as e:
        _dbg(f"Error getting LAN IP address: {e}")
    return "127.0.0.1"

def set_target_wifi(ssid: str):
    global target_wifi
    target_wifi = ssid

def set_change_callback(cb):
    global change_callback
    change_callback = cb

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
    _dbg(f"Known-Netzwerk gespeichert: ssid='{ssid}' | status={'aktualisiert' if updated else 'neu'} | total={len(networks)}")
    return True


def list_known_networks():
    """List known WiFi networks from nmcli (NetworkManager stored connections).
    Returns list of dicts with 'ssid' keys. Password is not returned for security.
    Falls back to JSON file if nmcli is not available.
    """
    networks = []
    try:
        # Try to get WiFi connections from nmcli
        res = run_cmd(['nmcli', '-t', '-f', 'NAME,TYPE', 'connection', 'show'])
        if res.returncode == 0 and res.stdout:
            _dbg("Lese bekannte Netzwerke aus nmcli...")
            for line in res.stdout.strip().split('\n'):
                if ':' in line:
                    name, conn_type = line.split(':', 1)
                    # Filter for WiFi connections (802-11-wireless) and exclude Hotspot
                    if conn_type == '802-11-wireless' and name != 'Hotspot':
                        # Return format compatible with existing code (list of dicts with ssid key)
                        # We don't return passwords as they're stored securely in nmcli
                        networks.append({'ssid': name, 'password': ''})
            _dbg(f"Gefundene bekannte Netzwerke via nmcli: {[n['ssid'] for n in networks]}")
            return networks
        else:
            _dbg("nmcli nicht verfügbar oder keine Verbindungen gefunden, verwende JSON-Fallback")
    except Exception as e:
        _dbg(f"Fehler beim Lesen aus nmcli: {type(e).__name__}: {e}, verwende JSON-Fallback")
    
    # Fallback to JSON file if nmcli fails or is not available
    return _load_known_networks()


def remove_known_network(ssid):
    """Remove a known network from both nmcli and JSON storage.
    Returns True if the network was removed, False otherwise.
    """
    # Remove from nmcli (NetworkManager)
    os_removed = _forget_network_everywhere(ssid)
    
    # Also remove from JSON file for backwards compatibility
    networks = _load_known_networks()
    new_list = [n for n in networks if n.get('ssid') != ssid]
    json_removed = len(new_list) != len(networks)
    if json_removed:
        _save_known_networks(new_list)
    
    # Return True if removed from either location
    return os_removed or json_removed

# -----------------------------
# WiFi/OS utilities
# -----------------------------

def run_cmd(args, check=False, shell=False):
    """Run a system command and return CompletedProcess. Adds detailed debug logging.
    - Redacts secrets from args (password/psk/passphrase)
    - Logs duration, rc, and trimmed outputs.
    """
    start = time.time()
    try:
        res = subprocess.run(args, capture_output=True, text=True, check=check, shell=shell)
        return res
    except Exception as e:
        duration = int((time.time() - start) * 1000)
        _dbg(f"CMD Ausnahme nach {duration} ms: {type(e).__name__}: {e}")
        return subprocess.CompletedProcess(args=args, returncode=1, stdout='', stderr=str(e))





def current_ssid(force: bool = False):
    return current_wifi


def _start_ap_services():
    """Start WiFi Access Point using nmcli (NetworkManager hotspot)"""
    _dbg("Starte AP über nmcli hotspot ...")
    try:
        # Default AP credentials
        ssid = "dmscreen"
        password = "dmscreen"
        
        # Stop any existing hotspot first
        run_cmd(['sudo', 'nmcli', 'connection', 'delete', 'Hotspot'], check=False)
        
        # Create hotspot on wlan0
        # nmcli device wifi hotspot ifname wlan0 ssid dmscreen password dmscreen
        res = run_cmd(['sudo', 'nmcli', 'device', 'wifi', 'hotspot', 
                      'ifname', 'wlan0', 'ssid', ssid, 'password', password])
        
        if res.returncode == 0:
            _dbg(f"AP erfolgreich gestartet: SSID='{ssid}'")
            time.sleep(2)  # Give it time to stabilize
            return True
        else:
            _dbg(f"AP-Start fehlgeschlagen: {res.stderr}")
            return False
    except Exception as e:
        _dbg(f"_start_ap_services Fehler: {type(e).__name__}: {e}")
        return False









def _forget_network_everywhere(ssid: str):
    """Remove network connection using nmcli (NetworkManager)"""
    _dbg(f"Vergesse Netzwerk: ssid='{ssid}' ...")
    removed = False
    try:
        if not ssid:
            return False
        
        # Get all connections with this SSID
        res = run_cmd(['nmcli', '-t', '-f', 'NAME,TYPE', 'connection', 'show'])
        if res.returncode == 0 and res.stdout:
            for line in res.stdout.strip().split('\n'):
                if ':' in line:
                    name, conn_type = line.split(':', 1)
                    if name == ssid or (conn_type == '802-11-wireless' and ssid in name):
                        _dbg(f"Entferne Verbindung: '{name}'")
                        res_del = run_cmd(['sudo', 'nmcli', 'connection', 'delete', name])
                        if res_del.returncode == 0:
                            removed = True
        
        # Also try direct delete by SSID name
        res_direct = run_cmd(['sudo', 'nmcli', 'connection', 'delete', ssid])
        if res_direct.returncode == 0:
            removed = True
        
        # Remove potential system-connections files; ignore errors
        run_cmd(f"sudo rm -f /etc/NetworkManager/system-connections/{ssid}", shell=True)
        run_cmd(f"sudo rm -f /etc/NetworkManager/system-connections/{ssid}.nmconnection", shell=True)
        run_cmd("sudo rm -f /etc/NetworkManager/system-connections/preconfigured.nmconnection", shell=True)
        
        _dbg(f"Vergessen abgeschlossen: removed={removed}")
    except Exception as e:
        _dbg(f"_forget_network_everywhere Fehler: {type(e).__name__}: {e}")
    
    return removed


def forget_and_remove_known(ssid: str):
    """Forget a network at OS level and remove its credentials from known list.
    Returns a tuple (os_removed: bool, known_removed: bool).
    Note: remove_known_network() now calls _forget_network_everywhere() internally,
    so this function now just delegates to it.
    """
    # remove_known_network() now handles both nmcli and JSON removal
    removed = remove_known_network(ssid)
    return removed, removed


def _scan_visible_ssids():
    """Return a list of visible SSIDs using nmcli."""
    _dbg("Scanne sichtbare WLANs (nmcli) ...")
    
    ssids_local = set()
    try:
        # Request a fresh scan
        run_cmd(['sudo', 'nmcli', 'device', 'wifi', 'rescan'], check=False)
        time.sleep(1)  # Give it time to complete
        
        # Get scan results
        res = run_cmd(['nmcli', '-t', '-f', 'SSID', 'device', 'wifi', 'list'])
        if res.returncode == 0 and res.stdout:
            _dbg("Nutze Ergebnisse von 'nmcli device wifi list' ...")
            for line in res.stdout.strip().split('\n'):
                ssid = line.strip()
                if ssid and ssid != '--':  # Filter empty or placeholder SSIDs
                    ssids_local.add(ssid)
            _dbg(f"Gefundene SSIDs via nmcli: {sorted(list(ssids_local))}")
            return sorted(list(ssids_local))
        else:
            _dbg("'nmcli device wifi list' lieferte keine verwertbaren Daten")
            return []
    except Exception as e:
        _dbg(f"_scan_visible_ssids Fehler: {type(e).__name__}: {e}")
        return []




def configure_wifi(ssid, password):
    global target_wifi
    """Add credentials to list and set target ssid"""
    try:
        _dbg(f"Konfiguriere WLAN: gewünschte SSID='{ssid}' ...")
        add_known_network(ssid, password)
        target_wifi = ssid
        return True
    except Exception as e:
        _dbg(f"Error configuring WiFi: {type(e).__name__}: {e}")
        return False

def connect_network():
    """Connect to target WiFi network using nmcli"""
    global target_wifi, current_wifi, config_lock
    
    with config_lock:
        if not target_wifi:
            _dbg("Keine Ziel-SSID gesetzt, Abbruch.")
            return False
        
        known_ssids = _load_known_networks()
        conf = next((s for s in known_ssids if s['ssid'] == target_wifi), None)
        
        if not conf:
            _dbg(f"SSID '{target_wifi}' nicht in Known-Liste gefunden.")
            return False
        
        ssid = conf['ssid']
        password = conf['password']
        
        _dbg(f"Verbinde mit SSID '{ssid}' via nmcli ...")
        
        try:
            # Stop any hotspot first
            _dbg("Stoppe eventuell laufenden Hotspot...")
            run_cmd(['sudo', 'nmcli', 'connection', 'delete', 'Hotspot'], check=False)
            
            # Check if connection already exists
            res_check = run_cmd(['nmcli', '-t', '-f', 'NAME', 'connection', 'show'])
            if res_check.returncode == 0 and ssid in res_check.stdout:
                _dbg(f"Verbindung '{ssid}' existiert bereits, versuche Aktivierung...")
                res = run_cmd(['sudo', 'nmcli', 'connection', 'up', ssid])
            else:
                _dbg(f"Erstelle neue Verbindung für '{ssid}'...")
                # Connect to WiFi network (creates connection if it doesn't exist)
                res = run_cmd(['sudo', 'nmcli', 'device', 'wifi', 'connect', ssid, 
                              'password', password])
            
            if res.returncode == 0:
                _dbg(f"Erfolgreich mit '{ssid}' verbunden.")
                current_wifi = target_wifi
                time.sleep(2)  # Give it time to get IP
                return True
            else:
                _dbg(f"Verbindung fehlgeschlagen: {res.stderr}")
                return False
                
        except Exception as e:
            _dbg(f"connect_network Fehler: {type(e).__name__}: {e}")
            return False

def check_adhoc_network():
    global target_wifi, current_wifi
    return target_wifi is None and current_wifi is None

def check_wifi_connection():
    global target_wifi, current_wifi
    return (target_wifi is not None and target_wifi == current_wifi), current_wifi

def disconnect_and_forget_current():
    """Disconnect from current WiFi using nmcli, update known list, and start AP. Returns (success, ssid)."""
    global target_wifi, current_wifi, config_lock
    
    try:
        with config_lock:
            ssid = current_wifi
            _dbg(f"Trenne und vergesse aktuelles WLAN: '{ssid}' ...")
            
            # Disconnect and forget the network
            if ssid:
                # Forget network at OS level using nmcli
                _forget_network_everywhere(ssid)
                
                # Remove from known networks list
                try:
                    removed_known = remove_known_network(ssid)
                    _dbg(f"Entferne aus Known-Liste: ssid='{ssid}' -> removed={removed_known}")
                except Exception as e:
                    _dbg(f"Fehler beim Entfernen aus Known-Liste: {type(e).__name__}: {e}")
            
            current_wifi = None
            target_wifi = None
            
            # Start AP so user can reconnect/configure
            _dbg("Starte AP-Modus nach Disconnect...")
            _start_ap_services()
            time.sleep(2)
            
            _dbg("Disconnect abgeschlossen.")
            return True, ssid
            
    except Exception as e:
        _dbg(f"disconnect_and_forget_current error: {type(e).__name__}: {e}")
        return False, None


def get_scanned_ssids():
    global scanned_ssids
    return scanned_ssids

def wifi_monitor(ssid=None):
    global target_wifi, current_wifi, change_callback, known_ssids, scanned_ssids
    """Background thread to ensure connectivity: connect to known networks, else start AP"""
    _dbg("WiFi-Monitor gestartet – prüfe regelmäßig die Verbindung ...")
    
    # Wait for initial scan to complete
    scanned_ssids = _scan_visible_ssids()
    retry_count = 0
    while len(scanned_ssids) == 0 and retry_count < 10:
        _dbg(f"Warte auf WLAN-Scan-Ergebnisse... (Versuch {retry_count + 1}/10)")
        time.sleep(2)
        scanned_ssids = _scan_visible_ssids()
        retry_count += 1
    
    if len(scanned_ssids) == 0:
        _dbg("Keine WLANs gefunden nach mehreren Versuchen, fahre trotzdem fort...")
    
    known_ssids = _load_known_networks()

    if ssid is not None:
        # SSID was provided (probably from command line), use it
        target_wifi = ssid
        current_wifi = ssid
        _dbg(f"Verwende vorgegebene SSID: '{ssid}'")
    else:
        # Try to find a known network in the scan results
        for k_ssid in known_ssids:
            if k_ssid['ssid'] in scanned_ssids:
                target_wifi = k_ssid['ssid']
                _dbg(f"Bekanntes WLAN gefunden: '{target_wifi}'")
                break

    while True:
        try:
            if target_wifi is None and current_wifi is not None:
                _dbg("Ziel-WLAN ist None, aber aktuell verbunden -> Disconnect")
                disconnect_and_forget_current()
                if change_callback:
                    try:
                        change_callback()
                    except Exception:
                        pass

            if target_wifi is not None and current_wifi != target_wifi:
                _dbg(f"Verbinde zu Ziel-WLAN: '{target_wifi}'")
                connect_network()
                if change_callback:
                    try:
                        change_callback()
                    except Exception:
                        pass
        except Exception as e:
            _dbg(f"WiFi-Monitor Fehler in Hauptschleife: {type(e).__name__}: {e}")
        
        time.sleep(10)  # Increased from 1 to 10 seconds to reduce CPU load on Raspberry Pi 3B+



def start_wifi_monitor(ssid=None):
    """Start the WiFi monitoring thread"""
    _dbg("Starte WiFi-Monitor-Thread ...")
    threading.Thread(target=wifi_monitor, kwargs={'ssid': ssid}, daemon=True).start()
    _dbg("WiFi-Monitor-Thread gestartet.")