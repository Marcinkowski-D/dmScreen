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


def current_ssid():
    """Return current connected SSID if available, else None (Raspberry Pi/Debian via iwgetid)."""
    _dbg("Ermittle aktuelle SSID via iwgetid -r …")
    res = _run_cmd(['iwgetid', '-r'])
    if res.returncode == 0:
        s = (res.stdout or '').strip()
        if s:
            _dbg(f"Aktuelle SSID erkannt: '{s}' (Interpretation: verbunden)")
            return s
        _dbg("iwgetid lieferte leeren String (Interpretation: nicht verbunden)")
    else:
        _dbg(f"iwgetid fehlgeschlagen rc={res.returncode} (Interpretation: Werkzeug nicht verfügbar oder kein Link)")
    return None


def check_adhoc_network():
    """Check if adhoc network (hostapd) is active"""
    try:
        _dbg("Prüfe Ad-hoc (AP) Status: systemctl is-active hostapd …")
        result = _run_cmd(['systemctl', 'is-active', 'hostapd'])
        status = (result.stdout or '').strip()
        active = status == 'active'
        _dbg(f"hostapd Status: '{status}' (Interpretation: {'aktiv' if active else 'inaktiv'})")
        return active
    except Exception as e:
        _dbg(f"Fehler beim Prüfen von hostapd: {type(e).__name__}: {e}")
        return False


def _stop_ap_services():
    _dbg("Stoppe AP-Dienste: hostapd und dnsmasq …")
    _run_cmd(['sudo', 'systemctl', 'stop', 'hostapd', 'dnsmasq'])


def _start_ap_services():
    _dbg("Starte AP-Dienste: hostapd und dnsmasq …")
    _run_cmd(['sudo', 'systemctl', 'start', 'hostapd', 'dnsmasq'])


def _write_hostapd_and_dnsmasq():
    """Write configs for hostapd and dnsmasq for AP SSID/password 'dmscreen'"""
    _dbg("Erzeuge AP-Konfigurationen (hostapd/dnsmasq) für SSID 'dmscreen' …")
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
            _dbg("/etc/hostapd existiert nicht – lege an …")
            _run_cmd(['sudo', 'mkdir', '-p', '/etc/hostapd'], check=True)
        # Write temp files then move with sudo mv
        _dbg("Schreibe hostapd.conf.tmp und verschiebe nach /etc/hostapd/hostapd.conf …")
        with open('hostapd.conf.tmp', 'w', encoding='utf-8') as f:
            f.write(hostapd_conf)
        _run_cmd(['sudo', 'mv', 'hostapd.conf.tmp', '/etc/hostapd/hostapd.conf'], check=True)

        _dbg("Schreibe dnsmasq.conf.tmp und verschiebe nach /etc/dnsmasq.conf …")
        with open('dnsmasq.conf.tmp', 'w', encoding='utf-8') as f:
            f.write(dnsmasq_conf)
        _run_cmd(['sudo', 'mv', 'dnsmasq.conf.tmp', '/etc/dnsmasq.conf'], check=True)
        _dbg("AP-Konfigurationsdateien erfolgreich geschrieben.")
        return True
    except Exception as e:
        _dbg(f"Fehler beim Schreiben der AP-Konfigurationen: {type(e).__name__}: {e}")
        return False


def create_adhoc_network():
    """Create an ad-hoc AP if no WiFi connected. SSID/PW = dmscreen/dmscreen"""
    try:
        _dbg("Starte Erstellung des Ad-hoc-Netzwerks 'dmscreen' …")
        _stop_ap_services()
        ok = _write_hostapd_and_dnsmasq()
        _dbg("Setze statische IP auf wlan0: 192.168.4.1/24 …")
        # Set static IP on wlan0 for AP network
        _run_cmd(['sudo', 'ifconfig', 'wlan0', '192.168.4.1', 'netmask', '255.255.255.0'])
        if ok:
            _dbg("Konfigurationsdateien ok – starte AP-Dienste …")
            _start_ap_services()
        else:
            _dbg("Konfigurationsdateien NICHT erstellt – Dienste werden nicht gestartet.")
        # Wait briefly and verify
        _dbg("Warte 2s und prüfe dann den AP-Status …")
        time.sleep(2)
        is_active = check_adhoc_network()
        _dbg(f"Ad-hoc-Netzwerk Status: {'aktiv' if is_active else 'inaktiv'}")
        return is_active
    except Exception as e:
        _dbg(f"Fehler beim Erstellen des Ad-hoc-Netzwerks: {type(e).__name__}: {e}")
        return False


def _write_wpa_supplicant(networks):
    """Write /etc/wpa_supplicant/wpa_supplicant.conf with multiple networks"""
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
    with open('wpa_supplicant.conf.tmp', 'w', encoding='utf-8') as f:
        f.write(content)
    _run_cmd(['sudo', 'mv', 'wpa_supplicant.conf.tmp', '/etc/wpa_supplicant/wpa_supplicant.conf'], check=True)


def _reconfigure_wpa():
    _dbg("wpa_cli reconfigure …")
    _run_cmd(['sudo', 'wpa_cli', '-i', 'wlan0', 'reconfigure'])




def _select_network(ssid: str) -> bool:
    """Select a network by SSID via wpa_cli if present in runtime config."""
    try:
        _dbg(f"Suche Netzwerk in wpa_cli list_networks für SSID '{ssid}' …")
        res = _run_cmd(['sudo', 'wpa_cli', '-i', 'wlan0', 'list_networks'])
        if res.returncode != 0 or not res.stdout:
            _dbg("wpa_cli list_networks ohne Ergebnis – Auswahl nicht möglich.")
            return False
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line or line.lower().startswith('network id'):
                continue
            parts = [p for p in line.split('\t') if p != '']
            if len(parts) < 2:
                parts = [p for p in line.split() if p != '']
            if len(parts) >= 2:
                nid = parts[0].strip()
                s = parts[1].strip()
                if s == ssid:
                    _dbg(f"SSID in Runtime-Konfiguration gefunden (network_id={nid}). Wähle Netzwerk und assoziiere neu …")
                    _run_cmd(['sudo', 'wpa_cli', '-i', 'wlan0', 'select_network', nid])
                    _run_cmd(['sudo', 'wpa_cli', '-i', 'wlan0', 'reassociate'])
                    return True
        _dbg("SSID wurde in wpa_cli list_networks nicht gefunden.")
        return False
    except Exception as e:
        _dbg(f"_select_network Ausnahme: {type(e).__name__}: {e}")
        return False


def _os_forget_network_wpa(ssid: str):
    """Remove matching SSID networks from wpa_supplicant runtime and save config."""
    try:
        _dbg(f"Entferne SSID aus wpa_supplicant Runtime (wenn vorhanden): '{ssid}' …")
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
                    _dbg(f"Entferne network_id={nid} für SSID '{s}' …")
                    _run_cmd(['sudo', 'wpa_cli', '-i', 'wlan0', 'remove_network', nid])
                    removed_ids.append(nid)
        if removed_ids:
            _dbg(f"Speichere wpa_supplicant Konfiguration nach Entfernen: ids={removed_ids} …")
            _run_cmd(['sudo', 'wpa_cli', '-i', 'wlan0', 'save_config'])
            _reconfigure_wpa()
        _dbg(f"Forget Ergebnis: removed_any={bool(removed_ids)} ids={removed_ids}")
        return bool(removed_ids)
    except Exception as e:
        _dbg(f"_os_forget_network_wpa Fehler: {type(e).__name__}: {e}")
        return False




def _forget_network_everywhere(ssid: str):
    _dbg(f"Vergesse Netzwerk überall: ssid='{ssid}' …")
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
    _dbg("Scanne sichtbare WLANs (primär: iw scan, Fallback: iwlist) …")
    ssids = set()
    # Try iw dev wlan0 scan
    res = _run_cmd(['iw', 'dev', 'wlan0', 'scan'])
    if res.returncode == 0 and res.stdout:
        _dbg("Nutze Ergebnisse von 'iw dev wlan0 scan' …")
        for line in res.stdout.splitlines():
            line = line.strip()
            if line.startswith('SSID:'):
                name = line.split('SSID:', 1)[1].strip()
                if name:
                    ssids.add(name)
        _dbg(f"Gefundene SSIDs via iw: {sorted(list(ssids))}")
    else:
        _dbg("'iw dev wlan0 scan' lieferte keine verwertbaren Daten – Fallback auf 'iwlist wlan0 scanning' …")
        # Fallback to iwlist
        res2 = _run_cmd(['iwlist', 'wlan0', 'scanning'])
        if res2.returncode == 0 and res2.stdout:
            for line in res2.stdout.splitlines():
                line = line.strip()
                if line.startswith('ESSID:'):
                    name = line.split('ESSID:', 1)[1].strip().strip('"')
                    if name:
                        ssids.add(name)
            _dbg(f"Gefundene SSIDs via iwlist: {sorted(list(ssids))}")
        else:
            _dbg("Auch 'iwlist' lieferte keine SSIDs.")
    _dbg(f"Scan abgeschlossen. SSIDs gesamt: {len(ssids)}")
    return ssids


def connect_best_known_network():
    """Try to connect to the best available known network based on scan results"""
    try:
        _dbg("Beginne Versuch: Verbindung zum besten bekannten Netzwerk …")
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
        # Prefer order in the stored list (latest wins at higher priority)
        _dbg("Stoppe ggf. AP-Dienste und schreibe wpa_supplicant mit Kandidaten …")
        _stop_ap_services()
        _write_wpa_supplicant(candidates)
        _reconfigure_wpa()
        _dbg("Warte 8s auf Verbindungsaufbau …")
        time.sleep(8)
        connected = check_wifi_connection()
        _dbg(f"Ergebnis Verbindungsversuch: {'verbunden' if connected else 'nicht verbunden'} | SSID={current_ssid()}")
        return connected
    except Exception as e:
        _dbg(f"connect_best_known_network Fehler: {type(e).__name__}: {e}")
        return False


def configure_wifi(ssid, password):
    """Configure WiFi: persist credentials and attempt to connect"""
    try:
        _dbg(f"Konfiguriere WLAN: gewünschte SSID='{ssid}' …")
        add_known_network(ssid, password)
        # Write full known list to wpa_supplicant
        networks = _load_known_networks()
        _dbg(f"Schreibe vollständige Known-Liste in wpa_supplicant (Anzahl={len(networks)}) …")
        _stop_ap_services()
        _write_wpa_supplicant(networks)

        # wpa_supplicant control
        _reconfigure_wpa()
        # Try to actively select the desired network
        selected = _select_network(ssid)
        _dbg(f"_select_network('{ssid}') -> {selected}")
        # Ensure reassociation in case driver is idle
        _dbg("Stelle wpa_cli reconnect her …")
        _run_cmd(['sudo', 'wpa_cli', '-i', 'wlan0', 'reconnect'])

        # Poll for connection up to ~20s
        _dbg("Starte Polling (max 20s) auf Ziel-SSID …")
        for i in range(20):
            cur = current_ssid()
            _dbg(f"Polling {i+1}/20: aktuelle SSID={cur} | Ziel={ssid} | Interpretation: {'OK' if cur == ssid else 'noch nicht verbunden'}")
            if cur == ssid:
                _dbg("Ziel-SSID verbunden – Erfolg.")
                return True
            time.sleep(1)
        _dbg("Verbindungsaufbau innerhalb des Zeitfensters nicht erfolgt – Misserfolg.")
        return False
    except Exception as e:
        _dbg(f"Error configuring WiFi: {type(e).__name__}: {e}")
        return False


def disconnect_and_forget_current():
    """Disconnect from the currently connected WiFi and forget it from known networks.
    Returns (success, ssid)."""
    try:
        _dbg("Starte Disconnect und Vergessen des aktuellen WLANs …")
        ssid = current_ssid()
        _dbg(f"Aktueller Zustand vor Disconnect: SSID={ssid}")
        # Proactively remove the network from OS runtime configs so it won't reconnect
        if ssid:
            try:
                removed_runtime = _forget_network_everywhere(ssid)
                _dbg(f"Runtime-Forget Ergebnis für SSID '{ssid}': {removed_runtime}")
            except Exception as e:
                _dbg(f"Fehler beim Runtime-Forget: {type(e).__name__}: {e}")
        # Attempt to disconnect regardless of state
        _dbg("Sende wpa_cli disconnect …")
        _run_cmd(['sudo', 'wpa_cli', '-i', 'wlan0', 'disconnect'])
        # Remove from known networks if present
        if ssid:
            try:
                removed_known = remove_known_network(ssid)
                _dbg(f"Entferne aus Known-Liste: ssid='{ssid}' -> removed={removed_known}")
            except Exception as e:
                _dbg(f"Fehler beim Entfernen aus Known-Liste: {type(e).__name__}: {e}")
        # Rewrite wpa_supplicant based on remaining networks and reconfigure
        try:
            nets = _load_known_networks()
            _dbg(f"Schreibe wpa_supplicant nach Disconnect mit {len(nets)} verbleibenden Netzwerken …")
            _write_wpa_supplicant(nets)
            _reconfigure_wpa()
        except Exception as e:
            _dbg(f"Error updating wpa_supplicant during disconnect: {type(e).__name__}: {e}")
        time.sleep(3)
        _dbg("Disconnect abgeschlossen.")
        return True, ssid
    except Exception as e:
        _dbg(f"disconnect_and_forget_current error: {type(e).__name__}: {e}")
        return False, None


def wifi_monitor():
    """Background thread to ensure connectivity: connect to known networks, else start AP"""
    _dbg("WiFi-Monitor gestartet – prüfe regelmäßig die Verbindung …")
    while True:
        try:
            cur = current_ssid()
            if cur:
                _dbg(f"Monitor: Bereits verbunden mit SSID='{cur}'.")
            else:
                _dbg("Monitor: Nicht verbunden – versuche bekannte Netzwerke …")
                # Try connect to the best known network first
                connected = connect_best_known_network()
                if connected:
                    _dbg(f"Monitor: Verbindung hergestellt. Aktuelle SSID={current_ssid()}")
                else:
                    _dbg("Monitor: Konnte keine Verbindung herstellen. Prüfe AP-Status …")
                    if not check_adhoc_network():
                        _dbg("Monitor: AP inaktiv – starte Ad-hoc-Netzwerk …")
                        create_adhoc_network()
                    else:
                        _dbg("Monitor: AP bereits aktiv – keine Aktion.")
        except Exception as e:
            _dbg(f"wifi_monitor loop error: {type(e).__name__}: {e}")
        time.sleep(60)  # Check every minute

# Flask route handlers for WiFi functionality
def register_wifi_routes(app, on_change=None):
    @app.route('/api/wifi/status', methods=['GET'])
    def get_wifi_status():
        _dbg("API GET /api/wifi/status aufgerufen …")
        connected = check_wifi_connection()
        adhoc_active = False
        adhoc_ssid = None
        if not connected:
            adhoc_active = check_adhoc_network()
            if adhoc_active:
                adhoc_ssid = 'dmscreen'
        ssid_val = current_ssid() if connected else None
        _dbg(f"API /api/wifi/status Antwort: connected={connected} | ssid={ssid_val} | adhoc_active={adhoc_active} | adhoc_ssid={adhoc_ssid}")
        return jsonify({
            'connected': connected,
            'ssid': ssid_val,
            'adhoc_active': adhoc_active,
            'adhoc_ssid': adhoc_ssid
        })

    @app.route('/api/wifi/configure', methods=['POST'])
    def set_wifi_config():
        data = request.get_json() or {}
        ssid = data.get('ssid')
        password = data.get('password')
        _dbg(f"API POST /api/wifi/configure: ssid='{ssid}' password='****'")
        if not ssid or not password:
            _dbg("API /api/wifi/configure: fehlende Felder -> 400")
            return jsonify({'error': 'SSID and password are required'}), 400
        success = configure_wifi(ssid, password)
        if success and on_change:
            try:
                on_change()
            except Exception:
                pass
        _dbg(f"API /api/wifi/configure Ergebnis: success={success}")
        return jsonify({
            'success': success,
            'message': 'WiFi configured successfully' if success else 'Failed to configure WiFi'
        })

    @app.route('/api/wifi/known', methods=['GET'])
    def api_list_known():
        _dbg("API GET /api/wifi/known …")
        nets = list_known_networks()
        _dbg(f"API /api/wifi/known -> {len(nets)} Netzwerke: {[n.get('ssid') for n in nets]}")
        return jsonify({'networks': nets})

    @app.route('/api/wifi/known', methods=['POST'])
    def api_add_known():
        data = request.get_json() or {}
        ssid = data.get('ssid')
        password = data.get('password')
        _dbg(f"API POST /api/wifi/known: ssid='{ssid}' password='****'")
        if not ssid or not password:
            _dbg("API /api/wifi/known: fehlende Felder -> 400")
            return jsonify({'error': 'SSID and password are required'}), 400
        add_known_network(ssid, password)
        if on_change:
            try:
                on_change()
            except Exception:
                pass
        _dbg("API /api/wifi/known: Netzwerk gespeichert -> success=true")
        return jsonify({'success': True})

    @app.route('/api/wifi/known/<ssid>', methods=['DELETE'])
    def api_remove_known(ssid):
        _dbg(f"API DELETE /api/wifi/known/{ssid} …")
        removed = remove_known_network(ssid)
        _dbg(f"Known-Liste entfernt='{ssid}' -> removed={removed}")
        # Also ensure OS forgets the network so it won't reconnect
        try:
            os_removed = _forget_network_everywhere(ssid)
            _dbg(f"Runtime-Konfiguration vergessen für '{ssid}' -> {os_removed}")
        except Exception as e:
            _dbg(f"Fehler beim Forget in OS Runtime: {type(e).__name__}: {e}")
        # Update wpa_supplicant to reflect removal
        try:
            nets = _load_known_networks()
            _dbg(f"Schreibe wpa_supplicant nach Entfernen. Verbleibend: {len(nets)} Netzwerke …")
            _write_wpa_supplicant(nets)
            _reconfigure_wpa()
        except Exception as e:
            _dbg(f"Fehler beim Aktualisieren von wpa_supplicant nach Entfernen: {type(e).__name__}: {e}")
        if on_change:
            try:
                on_change()
            except Exception:
                pass
        return jsonify({'removed': removed})

    @app.route('/api/wifi/scan', methods=['GET'])
    def api_scan():
        _dbg("API GET /api/wifi/scan …")
        try:
            ssids = sorted(list(_scan_visible_ssids()))
            _dbg(f"API /api/wifi/scan -> {len(ssids)} SSIDs: {ssids}")
            return jsonify({'ssids': ssids})
        except Exception as e:
            _dbg(f"API /api/wifi/scan Fehler: {type(e).__name__}: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/wifi/disconnect', methods=['POST'])
    def api_disconnect():
        _dbg("API POST /api/wifi/disconnect …")
        success, ssid = disconnect_and_forget_current()
        _dbg(f"API /api/wifi/disconnect Ergebnis: success={success} | entfernte SSID={ssid}")
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
    _dbg("Starte WiFi-Monitor-Thread …")
    threading.Thread(target=wifi_monitor, daemon=True).start()
    _dbg("WiFi-Monitor-Thread gestartet.")