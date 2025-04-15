import os
import sys
import requests
import zipfile
import tempfile
import shutil
import subprocess

VERSION_URL = "https://github.com/Ozzmaniac/Yoydownloader-2.0.6/blob/main/version.txt"
RELEASE_ZIP_URL = "https://github.com/Ozzmaniac/Yoydownloader-2.0.6/releases/download/v2.0.6/yoydownloader.rar"
LOCAL_VERSION = "2.0.6"  # Must match the current version

def check_for_update():
    try:
        response = requests.get(VERSION_URL, timeout=5)
        response.raise_for_status()
        latest_version = response.text.strip()

        if latest_version != LOCAL_VERSION:
            return latest_version
        return None
    except Exception as e:
        print(f"Failed to check for update: {e}")
        return None

def run_updater(latest_version):
    print(f"Downloading version {latest_version}...")

    try:
        with requests.get(RELEASE_ZIP_URL, stream=True) as r:
            r.raise_for_status()

            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
                for chunk in r.iter_content(chunk_size=8192):
                    tmp_file.write(chunk)
                zip_path = tmp_file.name

        # Extract
        extract_path = tempfile.mkdtemp()
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)

        exe_name = "yoydownloader.exe"
        new_exe_path = os.path.join(extract_path, exe_name)
        current_exe = sys.executable

        # Copy to overwrite
        print("Replacing executable...")
        shutil.copyfile(new_exe_path, current_exe)

        print("Update applied. Restarting...")

        subprocess.Popen([current_exe])
        sys.exit(0)

    except Exception as e:
        print(f"Update failed: {e}")
