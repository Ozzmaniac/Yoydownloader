import os
import sys
import requests
import zipfile
import tempfile
import shutil
import subprocess
from tkinter import messagebox

# Config
GITHUB_API = "https://api.github.com/repos/Ozzmaniac/Yoydownloader/releases/latest"
LOCAL_VERSION = "2.0.6"  # Update this when building a new version

def get_latest_release_info():
    try:
        response = requests.get(GITHUB_API, timeout=5)
        response.raise_for_status()
        data = response.json()

        latest_version = data["tag_name"].lstrip("v")  # e.g. "v2.0.7" → "2.0.7"
        zip_url = None

        for asset in data.get("assets", []):
            if asset["name"].endswith(".zip"):
                zip_url = asset["browser_download_url"]
                break

        return latest_version, zip_url
    except Exception as e:
        print(f"[Updater] Failed to get release info: {e}")
        return None, None

def run_updater(zip_url):
    try:
        print(f"[Updater] Downloading update from: {zip_url}")
        with requests.get(zip_url, stream=True) as r:
            r.raise_for_status()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
                for chunk in r.iter_content(chunk_size=8192):
                    tmp_file.write(chunk)
                zip_path = tmp_file.name

        extract_path = tempfile.mkdtemp()
        print(f"[Updater] Extracting to: {extract_path}")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)

        exe_name = os.path.basename(sys.executable)
        new_exe_path = os.path.join(extract_path, exe_name)
        current_exe = sys.executable

        print(f"[Updater] Replacing: {current_exe} with {new_exe_path}")
        shutil.copyfile(new_exe_path, current_exe)

        print("[Updater] Update applied. Restarting...")
        subprocess.Popen([current_exe])
        sys.exit(0)

    except Exception as e:
        print(f"[Updater] Update failed: {e}")
        messagebox.showerror("Update Failed", f"Could not complete update:\n{e}")
