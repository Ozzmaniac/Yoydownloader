import os
import sys
import requests
import zipfile
import tempfile
import shutil
import subprocess
from tkinter import messagebox

VERSION = "2.0.9"
VERSION_URL = "https://raw.githubusercontent.com/Ozzmaniac/Yoydownloader/main/version.txt"
ZIP_URL = "https://github.com/Ozzmaniac/Yoydownloader/releases/latest/download/yoydownloader.zip"


def check_for_update():
    try:
        response = requests.get(VERSION_URL, timeout=5)
        response.raise_for_status()
        latest = response.text.strip()
        print(f"[Updater] Current: {VERSION} | Latest from version.txt: {latest}")
        if latest != VERSION:
            print("[Updater] Update is available!")
            return latest
        else:
            print("[Updater] No update needed.")
    except Exception as e:
        print(f"[Updater] Failed to check version: {e}")
    return None


def run_updater():
    # Create a temporary copy of the running EXE and run it with update flag
    current_exe = sys.executable
    temp_updater = os.path.join(tempfile.gettempdir(), "temp_updater.exe")
    shutil.copyfile(current_exe, temp_updater)
    subprocess.Popen([temp_updater, "--update", current_exe])
    sys.exit(0)

from tkinter import messagebox, Tk  # Make sure this is at the top of your file

def perform_update(target_exe):
    try:
        print("[Updater] Downloading update...")
        with requests.get(ZIP_URL, stream=True) as r:
            r.raise_for_status()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
                for chunk in r.iter_content(chunk_size=8192):
                    tmp_file.write(chunk)
                zip_path = tmp_file.name

        extract_path = tempfile.mkdtemp()
        print(f"[Updater] Extracting to: {extract_path}")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)

        new_exe_path = os.path.join(extract_path, os.path.basename(target_exe))
        shutil.copyfile(new_exe_path, target_exe)

        print("[Updater] Relaunching updated app...")
        subprocess.Popen([target_exe])
        sys.exit(0)

    except Exception as e:
        print(f"[Updater] Update failed: {e}")
        try:
            root = Tk()
            root.withdraw()  # 🧼 Hides the ghost window
            messagebox.showerror("Update Failed", str(e))
            root.destroy()
        except:
            pass
        sys.exit(1)




