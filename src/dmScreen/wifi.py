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
    """Run a system command and return CompletedProcess. Adds detailed debug logging.
    - Redacts secrets from args (password/psk/passphrase)
    - Logs duration, rc, and trimmed outputs.
    """
    start = time.time()
    # Prepare safe command string
    try:
        safe_args = list(args)
        for i, val in enumerate(list(safe_args)):
            if isinstance(val, str) and val.lower() in ('password', 'psk', 'passphrase'):
                if i + 1 < len(safe_args):
                    safe_args[i + 1] = '****'
        cmd_str = ' '.join(str(a) for a in safe_args)
    except Exception:
        cmd_str = str(args)
    _dbg(f"CMD ausführen: {cmd_str}")
    try:
        res = subprocess.run(args, capture_output=True, text=True, check=check)
        duration = int((time.time() - start) * 1000)
        out = (res.stdout or '').strip()
        err = (res.stderr or '').strip()
        interpretation = 'OK' if res.returncode == 0 else 'FEHLER'
        _dbg(f"CMD Ergebnis ({duration} ms): rc={res.returncode} | stdout='{out[:1000]}' | stderr='{err[:1000]}' | Interpretation: {interpretation}")
        return res
    except Exception as e:
        duration = int((time.time() - start) * 1000)
        _dbg(f"CMD Ausnahme nach {duration} ms: {type(e).__name__}: {e}")
        return subprocess.CompletedProcess(args=args, returncode=1, stdout='', stderr=str(e))


def _run_script(script_name: str, *script_args):
    """Helper to run one of the provided WiFi/AP scripts located at project root with sudo."""
    script_path = os.path.join(_PROJECT_ROOT, script_name)
    cmd = ['sudo', '/bin/bash', script_path, *[str(a) for a in script_args]]
    return _run_cmd(cmd)



def current_ssid(force: bool = False):
    return current_wifi


def _start_ap_services():
    _dbg("Starte AP über Skript start-ap.sh ...")
    _run_script('start-ap.sh')


def _write_wpa_supplicant(networks):
    """Write wpa_supplicant configs. On Debian/RPi, wpa_supplicant@wlan0 reads
    /etc/wpa_supplicant/wpa_supplicant-wlan0.conf, so we write both that file
    and the generic /etc/wpa_supplicant/wpa_supplicant.conf to keep them in sync.
    """
    try:
        pr_list = []
        for prio, net in enumerate(networks, start=1):
            ssid = net.get('ssid', '')
            pr_list.append(f"prio={prio} ssid='{ssid}'")
        _dbg(f"Schreibe wpa_supplicant.conf mit {len(networks)} Netzwerken: {', '.join(pr_list)} (Passwörter werden nicht geloggt)")
    except Exception:
        _dbg(f"Schreibe wpa_supplicant.conf (Anzahl Netzwerke: {len(networks) if isinstance(networks, list) else 'unbekannt'})")
    header = """ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=DE

"""
    blocks = []
    # Assign higher priority to later entries so the most recently added network wins
    for prio, net in enumerate(networks, start=1):
        ssid = net.get('ssid', '')
        psk = net.get('password', '')
        blocks.append(
            f"network={{\n    ssid=\"{ssid}\"\n    psk=\"{psk}\"\n    key_mgmt=WPA-PSK\n    priority={prio}\n}}\n"
        )
    content = header + ''.join(blocks)
    # Ensure target directory exists
    try:
        if not os.path.exists('/etc/wpa_supplicant'):
            _dbg("/etc/wpa_supplicant existiert nicht – lege an ...")
            _run_cmd(['sudo', 'mkdir', '-p', '/etc/wpa_supplicant'], check=True)
    except Exception as e:
        _dbg(f"Warnung: konnte /etc/wpa_supplicant nicht prüfen/anlegen: {type(e).__name__}: {e}")
    # Write temp file then move to generic path
    with open('wpa_supplicant.conf.tmp', 'w', encoding='utf-8') as f:
        f.write(content)
    _run_cmd(['sudo', 'mv', 'wpa_supplicant.conf.tmp', '/etc/wpa_supplicant/wpa_supplicant.conf'], check=True)
    # Also copy to the interface-specific config used by wpa_supplicant@wlan0
    _dbg("Kopiere Konfiguration nach /etc/wpa_supplicant/wpa_supplicant-wlan0.conf ...")
    _run_cmd(['sudo', 'cp', '/etc/wpa_supplicant/wpa_supplicant.conf', '/etc/wpa_supplicant/wpa_supplicant-wlan0.conf'], check=True)
    # Ensure secure ownership and permissions (required by wpa_supplicant)
    _dbg("Setze Besitzer und Berechtigungen (root:root, 600) für wpa_supplicant Konfigurationsdateien ...")
    _run_cmd(['sudo', 'chown', 'root:root', '/etc/wpa_supplicant/wpa_supplicant.conf'])
    _run_cmd(['sudo', 'chmod', '600', '/etc/wpa_supplicant/wpa_supplicant.conf'])
    _run_cmd(['sudo', 'chown', 'root:root', '/etc/wpa_supplicant/wpa_supplicant-wlan0.conf'])
    _run_cmd(['sudo', 'chmod', '600', '/etc/wpa_supplicant/wpa_supplicant-wlan0.conf'])


def _wpa_ping() -> bool:
    """Return True if wpa_cli can reach wpa_supplicant (expects 'PONG')."""
    _dbg("Prüfe Erreichbarkeit von wpa_supplicant (wpa_cli ping) ...")
    res = _run_cmd(['sudo', 'wpa_cli', '-i', 'wlan0', 'ping'])
    ok = (res.returncode == 0) and ('PONG' in (res.stdout or ''))
    _dbg(f"wpa_cli ping -> {'OK' if ok else 'NICHT ERREICHBAR'}")
    return ok


def _ensure_wpa_running() -> bool:
    """Make sure wpa_supplicant for wlan0 is running and its control socket is reachable."""
    _dbg("Stelle sicher, dass wpa_supplicant für wlan0 läuft ...")
    if _wpa_ping():
        _dbg("wpa_supplicant bereits erreichbar.")
        return True
    _dbg("Versuche rfkill unblock und Interface hochzufahren ...")
    _run_cmd(['sudo', 'rfkill', 'unblock', 'all'])
    _run_cmd(['sudo', 'ifconfig', 'wlan0', 'up'])

    _dbg("Starte Dienst neu: wpa_supplicant@wlan0 ...")
    _run_cmd(['sudo', 'systemctl', 'restart', 'wpa_supplicant@wlan0'])
    time.sleep(1)
    if _wpa_ping():
        return True

    _dbg("Starte generischen Dienst neu: wpa_supplicant ...")
    _run_cmd(['sudo', 'systemctl', 'restart', 'wpa_supplicant'])
    time.sleep(1)
    if _wpa_ping():
        return True

    _dbg("Starte wpa_supplicant manuell im Hintergrund ...")
    # Use the interface-specific config common on Debian/RPi
    _run_cmd(['sudo', 'wpa_supplicant', '-B', '-i', 'wlan0', '-c', '/etc/wpa_supplicant/wpa_supplicant-wlan0.conf'])
    time.sleep(1)
    ok = _wpa_ping()
    _dbg(f"wpa_supplicant manuell gestartet -> {'OK' if ok else 'FEHLER'}")
    return ok


def _reconfigure_wpa():
    _dbg("wpa_cli reconfigure ...")
    # Ensure wpa_supplicant control socket is available
    try:
        _ensure_wpa_running()
    except Exception as e:
        _dbg(f"Fehler bei _ensure_wpa_running vor reconfigure: {type(e).__name__}: {e}")
    res = _run_cmd(['sudo', 'wpa_cli', '-i', 'wlan0', 'reconfigure'])
    ok = (res.returncode == 0) and ('FAIL' not in (((res.stdout or '') + ' ' + (res.stderr or '')).upper()))
    if not ok:
        _dbg("wpa_cli reconfigure war nicht erfolgreich – starte wpa_supplicant@wlan0 neu und versuche erneut ...")
        _run_cmd(['sudo', 'systemctl', 'restart', 'wpa_supplicant@wlan0'])
        time.sleep(1)
        res2 = _run_cmd(['sudo', 'wpa_cli', '-i', 'wlan0', 'reconfigure'])
        ok2 = (res2.returncode == 0) and ('FAIL' not in (((res2.stdout or '') + ' ' + (res2.stderr or '')).upper()))
        _dbg(f"wpa_cli reconfigure (Retry) -> {'ERFOLG' if ok2 else 'FEHLER'}")






def _os_forget_network_wpa(ssid: str):
    """Remove matching SSID networks from wpa_supplicant runtime and save config."""
    try:
        _dbg(f"Entferne SSID aus wpa_supplicant Runtime (wenn vorhanden): '{ssid}' ...")
        res = _run_cmd(['sudo', 'wpa_cli', '-i', 'wlan0', 'list_networks'])
        if res.returncode != 0 or not res.stdout:
            _dbg("Keine Netzwerke von wpa_cli list_networks erhalten – Abbruch Forget.")
            return False
        removed_ids = []
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
                    _dbg(f"Entferne network_id={nid} für SSID '{s}' ...")
                    _run_cmd(['sudo', 'wpa_cli', '-i', 'wlan0', 'remove_network', nid])
                    removed_ids.append(nid)
        if removed_ids:
            _dbg(f"Speichere wpa_supplicant Konfiguration nach Entfernen: ids={removed_ids} ...")
            _run_cmd(['sudo', 'wpa_cli', '-i', 'wlan0', 'save_config'])
            _reconfigure_wpa()
        _dbg(f"Forget Ergebnis: removed_any={bool(removed_ids)} ids={removed_ids}")
        return bool(removed_ids)
    except Exception as e:
        _dbg(f"_os_forget_network_wpa Fehler: {type(e).__name__}: {e}")
        return False




def _forget_network_everywhere(ssid: str):
    _dbg(f"Vergesse Netzwerk überall: ssid='{ssid}' ...")
    removed = False
    try:
        if ssid:
            removed = _os_forget_network_wpa(ssid) or removed
    except Exception as e:
        _dbg(f"_forget_network_everywhere Ausnahme: {type(e).__name__}: {e}")
    _dbg(f"Vergessen abgeschlossen: removed={removed}")
    return removed


def _scan_visible_ssids():
    """Return a set of visible SSIDs using iw or iwlist (Debian/Raspberry Pi)."""
    _dbg("Scanne sichtbare WLANs (iw scan) ...")

    ssids_local = set()
    res_local = _run_cmd(['iw', 'dev', 'wlan0', 'scan'])
    if res_local.returncode == 0 and res_local.stdout:
        _dbg("Nutze Ergebnisse von 'iw dev wlan0 scan' ...")
        for line in res_local.stdout.splitlines():
            line = line.strip()
            if line.startswith('SSID:'):
                name = line.split('SSID:', 1)[1].strip()
                if name:
                    ssids_local.add(name)
        _dbg(f"Gefundene SSIDs via iw: {sorted(list(ssids_local))}")
    else:
        _dbg("'iw dev wlan0 scan' lieferte keine verwertbaren Daten")
        return None
    return sorted(list(ssids_local))




def configure_wifi(ssid, password):
    """Add credentials to list and set target ssid"""
    try:
        _dbg(f"Konfiguriere WLAN via Skript: gewünschte SSID='{ssid}' ...")
        add_known_network(ssid, password)
        target_wifi = ssid
        return True
    except Exception as e:
        _dbg(f"Error configuring WiFi: {type(e).__name__}: {e}")
        return False

def connect_network():
    global target_wifi, current_wifi, config_lock
    with config_lock:
        known_ssids = _load_known_networks()
        conf = next((s for s in known_ssids if s['ssid'] == target_wifi), None)
        _run_script('stop-ap.sh')
        _run_script('connect-wifi.sh', conf['ssid'], conf['password'])
        current_wifi = target_wifi

def check_adhoc_network():
    global target_wifi, current_wifi
    return target_wifi is None and current_wifi is None

def check_wifi_connection():
    global target_wifi, current_wifi
    return target_wifi is not None and target_wifi == current_wifi

def disconnect_and_forget_current():

    global target_wifi, current_wifi, config_lock
    """Disconnect from the currently connected WiFi using forget-wifi.sh, update known list, and start AP. Returns (success, ssid)."""
    try:
        with config_lock:
            _run_script('forget-wifi.sh')
            current_wifi = None
            # Remove from known networks if present
            if ssid:
                try:
                    removed_known = remove_known_network(current_wifi)
                    _dbg(f"Entferne aus Known-Liste: ssid='{ssid}' -> removed={removed_known}")
                except Exception as e:
                    _dbg(f"Fehler beim Entfernen aus Known-Liste: {type(e).__name__}: {e}")
            # Start AP so user can reconnect/configure
            _start_ap_services()
            time.sleep(2)
            _dbg("Disconnect abgeschlossen.")
        return True, ssid
    except Exception as e:
        _dbg(f"disconnect_and_forget_current error: {type(e).__name__}: {e}")
        return False, None


def wifi_monitor():
    global target_wifi, current_wifi, change_callback, known_ssids, scanned_ssids
    """Background thread to ensure connectivity: connect to known networks, else start AP"""
    _dbg("WiFi-Monitor gestartet – prüfe regelmäßig die Verbindung ...")
    scanned_ssids = _scan_visible_ssids()
    while scanned_ssids is None:
        scanned_ssids = _scan_visible_ssids()
    known_ssids = _load_known_networks()
    time.sleep(1)

    for k_ssid in known_ssids:
        if k_ssid['ssid'] in scanned_ssids:
            target_wifi = k_ssid['ssid']
            break


    while True:
        if target_wifi is None and current_wifi is not None:
            print(f'target-wifi: {target_wifi}')
            print(f'current-wifi: {current_wifi}')
            disconnect_and_forget_current()
            if change_callback:
                try:
                    change_callback()
                except Exception:
                    pass

        if target_wifi is not None and current_wifi != target_wifi:
            print(f'target-wifi: {target_wifi}')
            print(f'current-wifi: {current_wifi}')
            connect_network()
            if change_callback:
                try:
                    change_callback()
                except Exception:
                    pass
        time.sleep(1)



def start_wifi_monitor():
    """Start the WiFi monitoring thread"""
    _dbg("Starte WiFi-Monitor-Thread ...")
    threading.Thread(target=wifi_monitor, daemon=True).start()
    _dbg("WiFi-Monitor-Thread gestartet.")