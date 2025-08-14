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
    cmd = ['sudo', script_path, *[str(a) for a in script_args]]
    return _run_cmd(cmd)


# WiFi-related functions

def check_wifi_connection():
    """Check if WiFi is connected"""
    try:
        ssid = current_ssid()
        connected = ssid is not None
        _dbg(f"WLAN-Verbindung prüfen: connected={connected} | SSID={ssid}")
        return connected
    except Exception as e:
        _dbg(f"WLAN-Verbindung prüfen: Ausnahme {type(e).__name__}: {e}")
        return False


def current_ssid(force: bool = False):
    """Return current connected SSID if available, else None (Raspberry Pi/Debian via iwgetid).
    Uses 5s cache by default; set force=True to bypass cache.
    """
    now = time.time()
    with _wifi_cache_lock:
        if not force and (now - _cached_ssid_ts) < _WIFI_CACHE_TTL:
            _dbg(f"Aktuelle SSID (Cache-Hit, Alter={int(now - _cached_ssid_ts)}s): {_cached_ssid}")
            return _cached_ssid
    _dbg("Ermittle aktuelle SSID via iwgetid -r ...")
    res = _run_cmd(['iwgetid', '-r'])
    ssid = None
    if res.returncode == 0:
        s = (res.stdout or '').strip()
        if s:
            _dbg(f"Aktuelle SSID erkannt: '{s}' (Interpretation: verbunden)")
            ssid = s
        else:
            _dbg("iwgetid lieferte leeren String (Interpretation: nicht verbunden)")
    else:
        _dbg(f"iwgetid fehlgeschlagen rc={res.returncode} (Interpretation: Werkzeug nicht verfügbar oder kein Link)")
    with _wifi_cache_lock:
        globals()['_cached_ssid'] = ssid
        globals()['_cached_ssid_ts'] = now
    return ssid


def check_adhoc_network(force: bool = False):
    """Check if adhoc network (hostapd) is truly active.
    Uses 5s cache unless force=True.
    Criteria for 'active':
      - wlan0 is in AP mode (iw dev wlan0 info shows 'type AP'), OR
      - hostapd is active AND wlan0 has an IP in 192.168.4.0/24.
    """
    try:
        now = time.time()
        with _wifi_cache_lock:
            if not force and (now - _cached_adhoc_ts) < _WIFI_CACHE_TTL:
                _dbg(f"AP-Status (Cache-Hit, Alter={int(now - _cached_adhoc_ts)}s): {_cached_adhoc}")
                return bool(_cached_adhoc)

        # 1) Systemd service state
        _dbg("Prüfe Ad-hoc (AP) Status: systemctl is-active hostapd ...")
        result = _run_cmd(['systemctl', 'is-active', 'hostapd'])
        status = (result.stdout or '').strip()
        active_systemd = (status == 'active')
        _dbg(f"hostapd Status: '{status}' (Interpretation: {'aktiv' if active_systemd else 'inaktiv'})")

        # 2) Interface mode via iw (preferred)
        ap_mode = False
        res_iw = _run_cmd(['iw', 'dev', 'wlan0', 'info'])
        if res_iw.returncode == 0 and res_iw.stdout:
            iw_out = res_iw.stdout
            if 'type AP' in iw_out or 'type __ap' in iw_out:
                ap_mode = True
        else:
            # Fallback: iwconfig
            res_iwc = _run_cmd(['iwconfig', 'wlan0'])
            if res_iwc.returncode == 0 and res_iwc.stdout and ('Mode:Master' in res_iwc.stdout or 'Mode:AP' in res_iwc.stdout):
                ap_mode = True
        _dbg(f"AP-Mode erkannt (iw/iwconfig): {ap_mode}")

        # 3) IP presence in AP subnet
        ap_ip = None
        res_ip = _run_cmd(['ip', '-4', 'addr', 'show', 'wlan0'])
        if res_ip.returncode == 0 and res_ip.stdout:
            for line in res_ip.stdout.splitlines():
                line = line.strip()
                if line.startswith('inet '):
                    ip_cidr = line.split()[1]
                    ap_ip = ip_cidr.split('/')[0]
                    break
        ap_ip_in_subnet = bool(ap_ip and ap_ip.startswith('192.168.4.'))
        _dbg(f"wlan0 IP: {ap_ip or '-'} | in AP-Subnetz: {ap_ip_in_subnet}")

        active_true = ap_mode or (active_systemd and ap_ip_in_subnet)
        with _wifi_cache_lock:
            globals()['_cached_adhoc'] = bool(active_true)
            globals()['_cached_adhoc_ts'] = now
        return bool(active_true)
    except Exception as e:
        _dbg(f"Fehler beim Prüfen von hostapd/AP-Status: {type(e).__name__}: {e}")
        return False


def _stop_ap_services():
    _dbg("Stoppe AP über Skript stop-ap.sh ...")
    _run_script('stop-ap.sh')


def _start_ap_services():
    _dbg("Starte AP über Skript start-ap.sh ...")
    _run_script('start-ap.sh')


def stop_adhoc_network():
    """Public wrapper to stop the ad-hoc AP via stop-ap.sh and clear AP cache."""
    try:
        _stop_ap_services()
        with _wifi_cache_lock:
            globals()['_cached_adhoc'] = False
            globals()['_cached_adhoc_ts'] = time.time()
        return True
    except Exception:
        return False



def create_adhoc_network():
    """Create an ad-hoc AP if no WiFi connected by invoking start-ap.sh.
    Robust: start, poll for true AP state; if not active, restart once and poll again.
    """
    try:
        _dbg("Starte Erstellung/Start des Ad-hoc-Netzwerks via start-ap.sh ...")
        _start_ap_services()
        # Poll quickly for a short period
        for i in range(6):  # ~6 seconds total
            time.sleep(1)
            is_active = check_adhoc_network(force=True)
            _dbg(f"AP-Poll {i+1}/6 -> {'aktiv' if is_active else 'inaktiv'}")
            if is_active:
                _dbg("Ad-hoc-Netzwerk aktiv.")
                return True
        _dbg("AP nach erster Startsequenz nicht aktiv – versuche Neustart ...")
        _stop_ap_services()
        time.sleep(1)
        _start_ap_services()
        for i in range(10):  # allow a bit longer after restart
            time.sleep(1)
            is_active = check_adhoc_network(force=True)
            _dbg(f"AP-Poll (Restart) {i+1}/10 -> {'aktiv' if is_active else 'inaktiv'}")
            if is_active:
                _dbg("Ad-hoc-Netzwerk aktiv nach Neustart.")
                return True
        _dbg("Ad-hoc-Netzwerk konnte nicht aktiviert werden.")
        return False
    except Exception as e:
        _dbg(f"Fehler beim Erstellen des Ad-hoc-Netzwerks: {type(e).__name__}: {e}")
        return False


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
    res_local = _run_cmd(['iw', 'dev', 'wlan0', 'scan', '|', 'grep', 'SSID:'])
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
    return ssids_local



def connect_best_known_network():
    """Try to connect to the best available known network using connect-wifi.sh; if none visible, caller can start AP."""
    try:
        _dbg("Beginne Versuch: Verbindung zum besten bekannten Netzwerk via Skript ...")
        known = _load_known_networks()
        _dbg(f"Bekannte Netzwerke: {len(known)} -> {[n.get('ssid') for n in known]}")
        if not known:
            _dbg("Keine bekannten Netzwerke vorhanden.")
            return False
        visible = _scan_visible_ssids()
        _dbg(f"Sichtbare SSIDs: {sorted(list(visible))}")
        if not visible:
            _dbg("Kein WLAN sichtbar – Abbruch.")
            return False
        # Keep networks that are visible
        candidates = [n for n in known if n.get('ssid') in visible]
        _dbg(f"Kandidaten (bekannt & sichtbar): {[n.get('ssid') for n in candidates]}")
        if not candidates:
            _dbg("Keine Kandidaten – Abbruch.")
            return False
        # Stop AP and try candidates in order
        _stop_ap_services()
        for net in candidates:
            ssid = net.get('ssid')
            pwd = net.get('password') or ''
            _dbg(f"Versuche Verbindung mit '{ssid}' über connect-wifi.sh ...")
            _run_script('connect-wifi.sh', ssid, pwd)
            # Poll a few times quickly
            for i in range(6):
                cur = current_ssid(force=True)
                if cur == ssid:
                    _dbg(f"Erfolgreich verbunden mit '{ssid}'.")
                    return True
                time.sleep(2)
            _dbg(f"Konnte nicht mit '{ssid}' verbinden – probiere nächsten Kandidaten ...")
        _dbg("Keine Verbindung zu Kandidaten möglich.")
        return False
    except Exception as e:
        _dbg(f"connect_best_known_network Fehler: {type(e).__name__}: {e}")
        return False


def configure_wifi(ssid, password):
    """Configure WiFi via scripts: stop AP, connect to SSID with password, and persist credentials."""
    try:
        _dbg(f"Konfiguriere WLAN via Skript: gewünschte SSID='{ssid}' ...")
        add_known_network(ssid, password)
        _stop_ap_services()
        _run_script('connect-wifi.sh', ssid, password)
        _dbg(f"Starte Polling (max {_WIFI_POLL_TRIES * _WIFI_POLL_INTERVAL:.0f}s, Intervall={_WIFI_POLL_INTERVAL}s) auf Ziel-SSID ...")
        for i in range(_WIFI_POLL_TRIES):
            cur = current_ssid(force=True)
            _dbg(f"Polling {i+1}/{_WIFI_POLL_TRIES}: aktuelle SSID={cur} | Ziel={ssid} | Interpretation: {'OK' if cur == ssid else 'noch nicht verbunden'}")
            if cur == ssid:
                _dbg("Ziel-SSID verbunden – Erfolg.")
                return True
            time.sleep(_WIFI_POLL_INTERVAL)
        _dbg("Verbindungsaufbau innerhalb des Zeitfensters nicht erfolgt – Misserfolg.")
        return False
    except Exception as e:
        _dbg(f"Error configuring WiFi: {type(e).__name__}: {e}")
        return False


def disconnect_and_forget_current():
    """Disconnect from the currently connected WiFi using forget-wifi.sh, update known list, and start AP. Returns (success, ssid)."""
    try:
        _dbg("Starte Disconnect via Skript und Entfernen des aktuellen WLANs ...")
        ssid = current_ssid(force=True)
        _dbg(f"Aktueller Zustand vor Disconnect: SSID={ssid}")
        # Call forget script (may fail if not connected; ignore rc)
        _run_script('forget-wifi.sh')
        # Remove from known networks if present
        if ssid:
            try:
                removed_known = remove_known_network(ssid)
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
    global target_wifi
    """Background thread to ensure connectivity: connect to known networks, else start AP"""
    _dbg("WiFi-Monitor gestartet – prüfe regelmäßig die Verbindung ...")

    _stop_ap_services()
    _start_ap_services()
    ssids = _scan_visible_ssids()
    known_ssids = _load_known_networks()
    time.sleep(1)

    print(ssids)
    print(known_ssids)


    while True:
        try:
            cur = current_ssid()
            if cur:
                _dbg(f"Monitor: Bereits verbunden mit SSID='{cur}'.")
            else:
                _dbg("Monitor: Nicht verbunden – versuche bekannte Netzwerke ...")
                # Try connect to the best known network first
                connected = connect_best_known_network()
                if connected:
                    _dbg(f"Monitor: Verbindung hergestellt. Aktuelle SSID={current_ssid()}")
                else:
                    if not check_adhoc_network(force=True):
                        _dbg("Monitor: Starte Ad-hoc-Netzwerk ...")
                        create_adhoc_network()
        except Exception as e:
            _dbg(f"wifi_monitor loop error: {type(e).__name__}: {e}")
        time.sleep(60)  # Check every minute



def start_wifi_monitor():
    """Start the WiFi monitoring thread"""
    _dbg("Starte WiFi-Monitor-Thread ...")
    threading.Thread(target=wifi_monitor, daemon=True).start()
    _dbg("WiFi-Monitor-Thread gestartet.")