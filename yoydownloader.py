"""
YOYDOWNLOADER 2.1.0 - CUSTOMTKINTER CONVERSION (Optimized + CTkImage preview)
- Uses CTkImage for preview to avoid HighDPI CTkLabel warnings
- Progress bar uses pack() (no grid/pack mixing)
- Buffered console logging to avoid UI thrashing
- Reduced UI queue polling from 33ms -> 100ms
- Throttled progress updates from yt-dlp
- Keeps original backend logic intact
"""

import os
import random
import pandas as pd
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, Toplevel
import customtkinter as ctk
from threading import Thread
import sys
import platform
from PIL import Image, ImageTk, ImageFont, ImageDraw
import json
import re
import queue
from tkvideo import tkvideo as VideoPlayer
from playsound import playsound as play_audio
from updater import check_for_update, run_updater, perform_update, VERSION
from functools import lru_cache
from psd_tools.api.psd_image import PSDImage
from psd_tools.api.layers import PixelLayer
from customtkinter import CTkImage
import time as _time

# === Constants ===
APP_NAME = "Yoydownloader"
CONFIG_FILENAME = "yoydownloader_config.json"
CONFIG_PATH = os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"), APP_NAME, CONFIG_FILENAME)

os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)

# Handle update mode (used by updater)
if "--update" in sys.argv and len(sys.argv) > 2:
    perform_update(sys.argv[2])
    sys.exit(0)

# === Utility functions ===
def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# LRU cache for images and fonts
@lru_cache(maxsize=256)
def load_image(path):
    return Image.open(path).convert("RGBA")

@lru_cache(maxsize=64)
def get_font(size):
    return ImageFont.truetype(resource_path("assets/HyliaSerif.otf"), size)

# === App State (single object to hold global-like state) ===
class AppState:
    def __init__(self):
        self.download_canceled = False
        self.active_process = None
        self.selected_file = None
        self.selected_spreadsheet_path = None
        self.download_directory = ""
        self.saved_directory = ""
        self.link_channel_path = ""
        self.spreadsheet_cache = {}  # path -> DataFrame
        self.ui_queue = queue.Queue()
        self.downloader_thread = None

state = AppState()

# Buffered log storage to avoid spamming the textbox
log_buffer = []

# Convenience UI queue functions (threads should use enqueue_ui)
def enqueue_ui(func, *args, **kwargs):
    """
    Put a callable and its args into the UI queue. If func expects kwargs,
    it's safest to wrap in a lambda when enqueueing.
    """
    state.ui_queue.put((func, args, kwargs))

def _process_ui_queue_once():
    try:
        while True:
            func, args, kwargs = state.ui_queue.get_nowait()
            try:
                func(*args, **kwargs)
            except Exception as e:
                # Use fallback print if console widget isn't ready
                try:
                    console_output.insert("end", f"[UI queue] callback error: {e}\n")
                    console_output.see("end")
                except Exception:
                    print(f"[UI queue] callback error: {e}")
    except queue.Empty:
        pass

def process_ui_queue_loop():
    _process_ui_queue_once()
    app.after(100, process_ui_queue_loop)  # reduced to 100ms to save CPU

# === Config Save / Load ===
def save_config():
    cfg = {
        "link_channel_path": state.link_channel_path,
        "saved_directory": state.saved_directory,
        "selected_spreadsheet_path": state.selected_spreadsheet_path,
        "download_directory": state.download_directory
    }
    try:
        with open(CONFIG_PATH, 'w') as f:
            json.dump(cfg, f)
    except Exception as e:
        enqueue_ui(log_message, f"Error saving configuration: {e}\n")

def load_config():
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                cfg = json.load(f)
            # Apply safely and update UI if necessary
            if cfg.get("link_channel_path") and os.path.exists(cfg["link_channel_path"]):
                state.link_channel_path = cfg["link_channel_path"]
                enqueue_ui(folder_label.configure, text=f"Selected: {state.link_channel_path}")
                enqueue_ui(update_character_dropdown)
                enqueue_ui(update_link_alt_dropdown)
            if cfg.get("saved_directory") and os.path.exists(cfg["saved_directory"]):
                state.saved_directory = cfg["saved_directory"]
                enqueue_ui(save_dir_label.configure, text=f"Save to: {state.saved_directory}")
            if cfg.get("selected_spreadsheet_path") and os.path.exists(cfg["selected_spreadsheet_path"]):
                state.selected_spreadsheet_path = cfg["selected_spreadsheet_path"]
                state.selected_file = cfg["selected_spreadsheet_path"]
                filename = os.path.basename(cfg["selected_spreadsheet_path"])
                enqueue_ui(spreadsheet_status_label_downloader.configure, text=f"Spreadsheet Loaded: {filename}", fg_color="transparent")
                enqueue_ui(spreadsheet_status_label.configure, text=f"Spreadsheet Loaded: {filename}", fg_color="transparent")
                enqueue_ui(populate_dropdowns_from_excel, cfg["selected_spreadsheet_path"])
            if cfg.get("download_directory") and os.path.exists(cfg["download_directory"]):
                state.download_directory = cfg["download_directory"]
    except Exception as e:
        enqueue_ui(log_message, f"Error loading configuration: {e}\n")

# === Updater logic (start after app created) ===
def check_for_updates_at_launch():
    try:
        latest_version = check_for_update()
        if latest_version:
            app.after(100, lambda: prompt_update(latest_version))
    except Exception as e:
        print(f"[Auto-Updater] Failed to check for updates: {e}")

def prompt_update(latest_version):
    result = messagebox.askyesno(
        "Update Available",
        f"A new version ({latest_version}) is available.\nDo you want to update now?"
    )
    if result:
        run_updater()

# === Initialize CustomTkinter appearance ===
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# === Basic UI setup ===
app = ctk.CTk()
app.title(f"YoyDownloader v{VERSION}")
app.geometry("1100x700")

# Set icon
icon_path = resource_path("assets/gura.ico")
try:
    if platform.system() == "Windows":
        app.iconbitmap(default=icon_path)
    else:
        img = tk.PhotoImage(file=icon_path)
        app.tk.call('wm', 'iconphoto', app._w, img)
except Exception as e:
    print(f"Failed to load icon: {e}")

# === Buffered logging utilities ===
def log_message(message):
    """
    Buffer messages instead of writing them immediately to the textbox.
    A scheduled flusher will push them into the console widget at a reduced rate.
    """
    global log_buffer
    if not isinstance(message, str):
        try:
            message = str(message)
        except Exception:
            message = "<unprintable message>\n"
    log_buffer.append(message)
    # Keep buffer reasonably sized
    if len(log_buffer) > 2000:
        log_buffer = log_buffer[-1000:]

def flush_logs():
    """
    Periodically flush log_buffer to the console widget. Runs on the main thread.
    """
    global log_buffer
    try:
        if log_buffer:
            try:
                console_output.insert("end", "".join(log_buffer))
                console_output.see("end")
            except Exception:
                print("".join(log_buffer))
            log_buffer = []
    except Exception as e:
        try:
            print(f"[flush_logs] {e}")
        except:
            pass
    app.after(100, flush_logs)

# === Parsing timestamps ===
def parse_timestamps(timestamp):
    if pd.isna(timestamp) or str(timestamp).lower() == "full vid":
        return None, None
    if '-' in str(timestamp):
        parts = str(timestamp).split('-')
        if len(parts) != 2:
            enqueue_ui(log_message, f"Invalid timestamp format: {timestamp}\n")
            return None, None
        start_time, end_time = parts
    else:
        start_time = str(timestamp)
        end_time = "inf"
    return start_time.strip(), end_time.strip()

def format_eta(seconds):
    if not isinstance(seconds, (int, float)) or seconds < 0 or seconds > 86400:
        return "Unknown"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"

# === Thread-safe downloader pipeline ===
def safe_terminate_process(proc):
    try:
        if proc.poll() is None:
            if platform.system() == "Windows":
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                try:
                    proc.terminate()
                    proc.wait(timeout=0.5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
    except Exception as e:
        enqueue_ui(log_message, f"Failed to kill process: {e}\n")

# download_vod: unchanged logic but throttles UI updates and uses proper progress scale
def download_vod(url, start_time, end_time, output_filename, index, total, on_complete=None):
    if state.download_canceled:
        return

    command = ["yt-dlp", "-f", "bestvideo+bestaudio/best", "--newline"]
    if start_time and end_time:
        command += ["--download-sections", f"*{start_time}-{end_time}"]
    command += ["-o", os.path.join(state.download_directory, output_filename), url]

    startupinfo = None
    if platform.system() == "Windows":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    try:
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            startupinfo=startupinfo
        )
        state.active_process = proc
    except Exception as e:
        enqueue_ui(log_message, f"Failed to start yt-dlp: {e}\n")
        state.active_process = None
        if on_complete:
            enqueue_ui(on_complete)
        return

    current_percent = 0.0
    is_section_download = start_time and end_time

    def time_to_sec(t):
        parts = t.split(':')
        if len(parts) == 3:
            h, m, s = parts
            return int(h)*3600 + int(m)*60 + float(s)
        elif len(parts) == 2:
            m, s = parts
            return int(m)*60 + float(s)
        return 0

    # Throttle updates so the UI does not get spammed
    last_reported_percent = -1.0
    last_report_time = _time.time()

    def reader_thread():
        nonlocal current_percent, last_reported_percent, last_report_time
        try:
            for raw_line in proc.stdout:
                if state.download_canceled:
                    break
                line = raw_line.rstrip("\n")
                # Buffer logs instead of inserting directly
                enqueue_ui(log_message, line + "\n")

                # Parse typical yt-dlp download progress lines
                if "[download]" in line and "%" in line:
                    m = re.search(r'([\d.]+)%', line)
                    if m:
                        try:
                            new_percent = float(m.group(1))
                            current_percent = new_percent
                        except Exception:
                            pass

                        # throttle: update UI only when percent changed by >= 0.5 or every 0.4s
                        now = _time.time()
                        if abs(current_percent - last_reported_percent) >= 0.5 or (now - last_report_time) >= 0.4:
                            last_reported_percent = current_percent
                            last_report_time = now
                            # progress_bar requires 0.0 - 1.0
                            enqueue_ui(progress_bar.set, min(1.0, max(0.0, current_percent / 100.0)))
                            enqueue_ui(progress_label.configure, text=f"Downloading {index+1}/{total}: {output_filename} | {current_percent:.1f}%")
                elif is_section_download and "time=" in line:
                    # For section downloads, try to estimate percent
                    time_match = re.search(r'time=([\d:.]+)', line)
                    speed_match = re.search(r'speed=\s*([\d.]+x|\d+\.?\d*\s*\w+/s)', line)
                    if time_match:
                        try:
                            current_time = time_to_sec(time_match.group(1))
                            start_sec = time_to_sec(start_time or "0:00")
                            end_sec = time_to_sec(end_time) if end_time and end_time.lower() != "inf" else float('inf')
                            if end_sec == float('inf') or current_time < start_sec:
                                # can't compute reliably; advance slowly
                                current_percent = min(100, current_percent + 0.5)
                                eta = "Unknown"
                            else:
                                duration = max(1, end_sec - start_sec)
                                current_percent = max(0, min(100, ((current_time - start_sec) / duration) * 100))
                                remaining = max(0, end_sec - current_time)
                                if speed_match and "x" in speed_match.group(1):
                                    try:
                                        speed_factor = float(speed_match.group(1).replace("x", ""))
                                        eta = format_eta(remaining / speed_factor)
                                    except Exception:
                                        eta = "Unknown"
                                else:
                                    eta = "Unknown"
                            speed = speed_match.group(1).strip() if speed_match else "N/A"

                            now = _time.time()
                            if abs(current_percent - last_reported_percent) >= 0.5 or (now - last_report_time) >= 0.4:
                                last_reported_percent = current_percent
                                last_report_time = now
                                enqueue_ui(progress_bar.set, min(1.0, max(0.0, current_percent / 100.0)))
                                enqueue_ui(progress_label.configure, text=f"Downloading {index+1}/{total}: {current_percent:.1f}% | Speed: {speed} | ETA: {eta}")
                        except Exception:
                            pass
            proc.wait()
        except Exception as e:
            enqueue_ui(log_message, f"[download reader error] {e}\n")
        finally:
            state.active_process = None
            if not state.download_canceled:
                # Ensure progress hits 100%
                enqueue_ui(progress_bar.set, 1.0)
                # Post-processing message (ok to show)
                enqueue_ui(progress_label.configure, text=f"Post-processing {index+1}/{total}: {output_filename}...")
                def finalize_ui():
                    # Only display "Finished" for non-final downloads (Option A)
                    if index + 1 < total:
                        enqueue_ui(progress_label.configure, text=f"Finished {index+1}/{total}: {output_filename}")
                    # For final download, we don't overwrite the final "Downloads Complete!" text set by the batch worker
                    if on_complete:
                        enqueue_ui(on_complete)
                enqueue_ui(lambda: app.after(800, finalize_ui))
            else:
                if on_complete:
                    enqueue_ui(on_complete)

    Thread(target=reader_thread, daemon=True).start()

# === Spreadsheet caching & helpers ===
def load_spreadsheet_cached(path):
    if path in state.spreadsheet_cache:
        return state.spreadsheet_cache[path]
    df = pd.read_excel(path)
    state.spreadsheet_cache[path] = df
    return df

# === Main downloader worker (single worker thread) ===
def process_spreadsheet_worker():
    try:
        state.download_canceled = False
        enqueue_ui(download_button.configure, state="disabled")
        enqueue_ui(cancel_button.configure, state="normal")

        if not state.selected_file or not state.download_directory:
            enqueue_ui(log_message, "Error: No file or download directory selected.\n")
            enqueue_ui(download_button.configure, state="normal")
            enqueue_ui(cancel_button.configure, state="disabled")
            return

        df = load_spreadsheet_cached(state.selected_file)
        df.columns = df.columns.str.strip().str.lower()

        link_column = next((col for col in df.columns if "twitch link" in col or "vod link" in col), None)
        timestamp_column = next((col for col in df.columns if "timestamps" in col), None)
        character_column = next((col for col in df.columns if "opponent" in col), None)

        if not link_column or not timestamp_column or not character_column:
            enqueue_ui(log_message, "Error: Required columns not found in spreadsheet.\n")
            enqueue_ui(download_button.configure, state="normal")
            enqueue_ui(cancel_button.configure, state="disabled")
            return

        total_vods = len(df)
        enqueue_ui(progress_bar.set, 0.0)

        for i in range(len(df)):
            if state.download_canceled:
                break
            row = df.iloc[i]
            vod_url = str(row[link_column]) if not pd.isna(row[link_column]) else ""
            timestamp = row[timestamp_column]
            opponent_character = row[character_column] if not pd.isna(row[character_column]) else "unknown"

            if not vod_url:
                enqueue_ui(log_message, f"Skipping row {i+1}/{total_vods}: No VOD link.\n")
                enqueue_ui(lambda: console_output.see("end"))
                continue

            output_filename = f"VOD_{i+1}_{opponent_character}.mp4"
            start_time, end_time = parse_timestamps(timestamp)

            download_vod(vod_url, start_time, end_time, output_filename, i, total_vods)

            # Wait while this download runs
            while state.active_process is not None:
                if state.download_canceled:
                    break
                _time.sleep(0.1)

        if state.download_canceled:
            enqueue_ui(progress_label.configure, text="Download canceled")
            enqueue_ui(progress_bar.set, 0.0)
            # hide bar as canceled
            enqueue_ui(progress_bar.pack_forget)
        else:
            # Final message after ALL VODs finish
            enqueue_ui(progress_label.configure, text="Downloads Complete!")
            enqueue_ui(log_message, "All downloads completed successfully!\n")
            enqueue_ui(lambda: console_output.see("end"))
            # Hide the progress bar after batch completion
            enqueue_ui(progress_bar.pack_forget)
    except Exception as e:
        enqueue_ui(log_message, f"[process_spreadsheet_worker] {e}\n")
    finally:
        enqueue_ui(download_button.configure, state="normal")
        enqueue_ui(cancel_button.configure, state="disabled")
        # ensure bar hidden (safety)
        enqueue_ui(progress_bar.pack_forget)

# Public start download (spawns single background worker)
def start_download():
    enqueue_ui(progress_bar.set, 0.0)
    enqueue_ui(lambda: progress_bar.pack(pady=4))  # show by packing (no grid usage)
    enqueue_ui(progress_label.configure, text="Starting download...")
    if state.downloader_thread and state.downloader_thread.is_alive():
        enqueue_ui(log_message, "Downloader is already running.\n")
        return
    state.downloader_thread = Thread(target=process_spreadsheet_worker, daemon=True)
    state.downloader_thread.start()
    enqueue_ui(download_button.configure, state="disabled")
    enqueue_ui(cancel_button.configure, state="normal")

# Cancel logic
def cancel_download():
    if messagebox.askyesno("Cancel Download", "Are you sure you want to cancel the download?"):
        state.download_canceled = True
        enqueue_ui(log_message, "Canceling download...\n")
        if state.active_process:
            safe_terminate_process(state.active_process)
        enqueue_ui(progress_label.configure, text="Download canceled")
        enqueue_ui(download_button.configure, state="normal")
        enqueue_ui(cancel_button.configure, state="disabled")
        enqueue_ui(progress_bar.set, 0.0)
        enqueue_ui(progress_bar.pack_forget)

# === UI Layout ===
# Use CTkTabview
main_frame = ctk.CTkFrame(app)
main_frame.pack(fill="both", expand=True, padx=12, pady=12)

tabview = ctk.CTkTabview(main_frame, width=1000)
tabview.add("Downloader")
tabview.add("Thumbnail Generator")
tabview.add("Console Output")

tabview.pack(expand=True, fill="both", side="top")

# Frames for each tab (CTkFrame)
downloader_frame = ctk.CTkFrame(tabview.tab("Downloader"))
downloader_frame.pack(expand=True, fill="both", padx=12, pady=12)

thumbnail_frame = ctk.CTkFrame(tabview.tab("Thumbnail Generator"))
thumbnail_frame.pack(expand=True, fill="both", padx=12, pady=12)

console_frame = ctk.CTkFrame(tabview.tab("Console Output"))
console_frame.pack(expand=True, fill="both", padx=12, pady=12)

# Thumbnail tab: use CTkScrollableFrame for scrollable content
scrollable = ctk.CTkScrollableFrame(thumbnail_frame)
scrollable.pack(expand=True, fill="both", padx=6, pady=6)

# We'll use CTkLabel with CTkImage for the preview (avoids PIL.PhotoImage warnings)
preview_canvas = ctk.CTkLabel(scrollable, text="", width=640, height=360)
preview_canvas.pack(pady=10)
# store CTkImage reference to avoid GC
_preview_ctkimage_ref = None

center_container = ctk.CTkFrame(scrollable)
center_container.pack(expand=True, padx=20, pady=6)

BUTTON_WIDTH = 180
DROPDOWN_WIDTH = 220
ENTRY_WIDTH = 220

# === App globals (UI-state) ===
download_button = None
cancel_button = None
progress_bar = None
progress_label = None
console_output = None
spreadsheet_status_label_downloader = None
spreadsheet_status_label = None
folder_label = None
save_dir_label = None

# === Thumbnail pipeline (unchanged) ===
positions = {
    "link_center_P1": (-350, 40),
    "link_center_P2": (350, 40),
    "opponent_center_P1": (-350, 40),
    "opponent_center_P2": (350, 40),
    "link_name_P1": (186, 610),
    "link_name_P2": (922, 610),
    "opponent_name_P1": (186, 610),
    "opponent_name_P2": (922, 610),
    "tournament_title": (497, 20),
    "round_info": (602, 87),
}

class ThumbnailComposer:
    def __init__(self, settings):
        self.s = settings
        self.bg_id = settings.get("background_id") or random.randint(1, 5)

    def load_background(self):
        path = os.path.join(state.link_channel_path, "Background layouts", f"BG {self.bg_id}.png")
        return load_image(path).resize((1280, 720), Image.Resampling.LANCZOS)

    def load_link(self):
        name = self.s["link_skin"]
        path = os.path.join(state.link_channel_path, "Transparent cast", "Link alts", f"{name}.png")
        img = load_image(path)
        if self.s["link_pos"] == "P2":
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        return img

    def load_opponent(self):
        name = self.s["opponent_character"]
        path = os.path.join(state.link_channel_path, "Transparent cast", "Rest of cast", f"{name}.png")
        img = load_image(path)
        if self.s["link_pos"] == "P1":
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        return img

    def get_positions(self):
        link_pos = (positions["link_center_P1"] if self.s["link_pos"] == "P1" else positions["link_center_P2"])
        opp_pos = (positions["opponent_center_P2"] if self.s["link_pos"] == "P1" else positions["opponent_center_P1"])
        link_text_pos = (positions["link_name_P1"] if self.s["link_pos"] == "P1" else positions["link_name_P2"])
        opp_text_pos = (positions["opponent_name_P2"] if self.s["link_pos"] == "P1" else positions["opponent_name_P1"])
        return {
            "link_img": link_pos,
            "opp_img": opp_pos,
            "link_text": link_text_pos,
            "opp_text": opp_text_pos,
            "tournament_text": positions["tournament_title"],
            "round_text": positions["round_info"],
        }

    def draw_text(self, base, pos, text, size, outline):
        font = get_font(size)
        draw = ImageDraw.Draw(base)
        x, y = pos
        for dx in range(-outline, outline + 1):
            for dy in range(-outline, outline + 1):
                draw.text((x + dx, y + dy), text, font=font, fill="black")
        draw.text(pos, text, font=font, fill="white")

    def render_preview(self):
        bg = self.load_background()
        link = self.load_link()
        opp = self.load_opponent()
        pos = self.get_positions()
        bg.paste(link, pos["link_img"], link)
        bg.paste(opp, pos["opp_img"], opp)
        self.draw_text(bg, pos["tournament_text"], self.s["tournament"], self.s["font_size"], self.s["outline"])
        self.draw_text(bg, pos["round_text"], self.s["round"], self.s["round_font_size"], self.s["outline"])
        self.draw_text(bg, pos["link_text"], self.s["link_player"], self.s["font_size"], self.s["outline"])
        self.draw_text(bg, pos["opp_text"], self.s["opponent_player"], self.s["font_size"], self.s["outline"])
        return bg

    def render_layers(self):
        bg = self.load_background()
        link = self.load_link()
        opp = self.load_opponent()
        pos = self.get_positions()

        link_layer = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
        link_layer.paste(link, pos["link_img"], link)
        opp_layer = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
        opp_layer.paste(opp, pos["opp_img"], opp)

        text_layers = []
        def TL(name, text, posn, size):
            img = Image.new("RGBA", (1280,720), (0,0,0,0))
            self.draw_text(img, posn, text, size, self.s["outline"])
            return (name, img)

        text_layers.append(TL("Tournament", self.s["tournament"], pos["tournament_text"], self.s["font_size"]))
        text_layers.append(TL("Round", self.s["round"], pos["round_text"], self.s["round_font_size"]))
        text_layers.append(TL("Link Player", self.s["link_player"], pos["link_text"], self.s["font_size"]))
        text_layers.append(TL("Opponent Player", self.s["opponent_player"], pos["opp_text"], self.s["font_size"]))
        return {"background": bg, "link": link_layer, "opponent": opp_layer, "text_layers": text_layers}

# === Thumbnail settings collection & generation ===
def collect_thumbnail_settings():
    bg_id = random.randint(1, 5)
    try:
        return {
            "tournament": tournament_entry.get(),
            "round": round_entry.get(),
            "link_player": link_player_var.get(),
            "opponent_player": opponent_var.get(),
            "link_skin": link_skin_var.get(),
            "opponent_character": character_var.get(),
            "link_pos": link_position_var.get(),
            "font_size": int(font_size_var.get()),
            "round_font_size": int(round_font_size_var.get()),
            "outline": int(outline_size_var.get()),
            "background_id": bg_id
        }
    except Exception:
        return {
            "tournament": tournament_entry.get(),
            "round": round_entry.get(),
            "link_player": link_player_var.get(),
            "opponent_player": opponent_var.get(),
            "link_skin": link_skin_var.get(),
            "opponent_character": character_var.get(),
            "link_pos": link_position_var.get() or "P1",
            "font_size": int(font_size_var.get() or 50),
            "round_font_size": int(round_font_size_var.get() or 28),
            "outline": int(outline_size_var.get() or 1),
            "background_id": bg_id
        }


def generate_thumbnail():
    Thread(target=_generate_thumbnail_async, daemon=True).start()


def _generate_thumbnail_async():
    try:
        settings = collect_thumbnail_settings()
        composer = ThumbnailComposer(settings)
        img = composer.render_preview()
        enqueue_ui(update_preview, img)
    except Exception as e:
        enqueue_ui(log_message, f"Thumbnail Error: {e}\n")


def _generate_thumbnail_sync():
    settings = collect_thumbnail_settings()
    composer = ThumbnailComposer(settings)
    return composer.render_preview()

# Updated: use CTkImage for preview to avoid CTkLabel PIL warning (HighDPI)
def update_preview(thumbnail):
    """
    Create a CTkImage from the PIL thumbnail at a fixed preview size and set it on preview_canvas.
    Using CTkImage avoids the 'Given image is not CTkImage' warning and ensures correct scaling on HighDPI displays.
    """
    global _preview_ctkimage_ref
    try:
        preview_w = 640
        preview_h = 360
        thumbnail_resized = thumbnail.resize((preview_w, preview_h), Image.Resampling.LANCZOS)

        # Create CTkImage (pass PIL.Image directly). CTkImage will handle DPI scaling.
        ctk_preview = CTkImage(light_image=thumbnail_resized, dark_image=thumbnail_resized, size=(preview_w, preview_h))

        # Assign to label
        preview_canvas.configure(image=ctk_preview, text="")
        # Keep reference to avoid GC
        _preview_ctkimage_ref = ctk_preview
        preview_canvas._image = ctk_preview
    except Exception as e:
        enqueue_ui(log_message, f"Preview update failed: {e}\n")

def preview_fullscreen():
    # Generate thumbnail synchronously
    thumbnail = _generate_thumbnail_sync()
    if not thumbnail:
        return

    # Create fullscreen window
    fullscreen = Toplevel()
    fullscreen.title("Fullscreen Preview")
    fullscreen.attributes("-fullscreen", True)

    # Ensure window draws before measuring size
    fullscreen.update_idletasks()

    screen_w = fullscreen.winfo_width()
    screen_h = fullscreen.winfo_height()

    # Resize image for fullscreen
    try:
        resized = thumbnail.resize((screen_w, screen_h), Image.Resampling.LANCZOS)
        fullscreen_img = CTkImage(light_image=resized, dark_image=resized, size=(screen_w, screen_h))
        label = ctk.CTkLabel(fullscreen, image=fullscreen_img, text="")
        label.pack(expand=True, fill="both")
        label._image = fullscreen_img  # prevent GC
    except Exception:
        # fallback: use a slightly smaller PIL->PhotoImage if CTkImage fails
        try:
            resized = thumbnail.resize((int(screen_w*0.9), int(screen_h*0.9)), Image.Resampling.LANCZOS)
            tk_img = ImageTk.PhotoImage(resized)
            label = ctk.CTkLabel(fullscreen, image=tk_img, text="")
            label.pack(expand=True, fill="both")
            label._image = tk_img
        except Exception as e:
            enqueue_ui(log_message, f"Fullscreen preview failed: {e}\n")
            fullscreen.destroy()
            return

    fullscreen.bind("<Escape>", lambda e: fullscreen.destroy())

def save_thumbnail():
    thumbnail = _generate_thumbnail_sync()
    if thumbnail and state.saved_directory:
        try:
            out = os.path.join(state.saved_directory, f"{opponent_var.get() or 'thumbnail'}.png")
            thumbnail.save(out)
            enqueue_ui(log_message, f"Thumbnail saved successfully: {out}\n")
        except Exception as e:
            enqueue_ui(log_message, f"Failed saving PNG: {e}\n")
    else:
        enqueue_ui(log_message, "No save directory selected.\n")


def save_thumbnail_as_psd():
    if not state.saved_directory:
        select_save_directory()
        if not state.saved_directory:
            return
    try:
        settings = collect_thumbnail_settings()
        composer = ThumbnailComposer(settings)
        layers = composer.render_layers()
        psd = PSDImage.new(mode="RGBA", size=(1280,720))
        bg_layer = PixelLayer.frompil(layers['background'], psd); bg_layer.name="Background"; psd.append(bg_layer)
        link_layer = PixelLayer.frompil(layers['link'], psd); link_layer.name="Link"; psd.append(link_layer)
        opp_layer = PixelLayer.frompil(layers['opponent'], psd); opp_layer.name="Opponent"; psd.append(opp_layer)
        for name, img in layers['text_layers']:
            L = PixelLayer.frompil(img, psd); L.name = name; psd.append(L)
        opponent_name = opponent_var.get() or 'unnamed'
        out_path = os.path.join(state.saved_directory, f"{opponent_name}.psd")
        psd.save(out_path)
        enqueue_ui(log_message, f"✅ PSD saved: {os.path.basename(out_path)}\n")
    except Exception as e:
        enqueue_ui(log_message, f"❌ PSD save failed: {e}\n")

# === UI Controls for thumbnail tab ===
folder_button = ctk.CTkButton(center_container, text="Select Link Channel Folder", command=lambda: select_link_channel(), width=BUTTON_WIDTH)
folder_button.pack(pady=6)
folder_label = ctk.CTkLabel(center_container, text="No folder selected")
folder_label.pack(pady=2)
save_dir_label = ctk.CTkLabel(center_container, text="No save directory selected")
save_dir_label.pack(pady=2)


def select_link_channel():
    path = filedialog.askdirectory()
    if path:
        state.link_channel_path = path
        folder_label.configure(text=f"Selected: {path}")
        update_character_dropdown()
        update_link_alt_dropdown()
        save_config()


def select_save_directory():
    path = filedialog.askdirectory()
    if path:
        state.saved_directory = path
        save_dir_label.configure(text=f"Save to: {path}")
        save_config()


def update_character_dropdown():
    if not state.link_channel_path:
        return
    char_folder = os.path.join(state.link_channel_path, "Transparent cast", "Rest of cast")
    if not os.path.exists(char_folder):
        return
    characters = [f.replace(".png", "") for f in os.listdir(char_folder) if f.endswith(".png")]
    character_dropdown.configure(values=characters)


def update_link_alt_dropdown():
    if not state.link_channel_path:
        return
    link_alt_folder = os.path.join(state.link_channel_path, "Transparent cast", "Link alts")
    if not os.path.exists(link_alt_folder):
        return
    link_alts = [f.replace(".png", "") for f in os.listdir(link_alt_folder) if f.endswith(".png")]
    link_skin_dropdown.configure(values=link_alts)

# Populate dropdowns from spreadsheet (uses cached load)
def populate_dropdowns_from_excel(file_path):
    try:
        df = load_spreadsheet_cached(file_path)
        df.columns = df.columns.str.strip().str.lower()
        link_players = df.get("link player", pd.Series()).dropna().tolist() if "link player" in df.columns else []
        opponents = df.get("opponent", pd.Series()).dropna().tolist() if "opponent" in df.columns else []
        link_player_dropdown.configure(values=link_players)
        opponent_dropdown.configure(values=opponents)
    except Exception as e:
        enqueue_ui(log_message, f"Error loading spreadsheet data: {e}\n")

# === Spreadsheet selection ===
def select_spreadsheet():
    file_path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx")])
    if not file_path:
        return
    state.selected_file = file_path
    state.selected_spreadsheet_path = file_path
    filename = os.path.basename(file_path)
    spreadsheet_status_label_downloader.configure(text=f"Spreadsheet Loaded: {filename}")
    spreadsheet_status_label.configure(text=f"Spreadsheet Loaded: {filename}")
    populate_dropdowns_from_excel(file_path)
    save_config()

spreadsheet_status_label = ctk.CTkLabel(center_container, text="")
spreadsheet_status_label.pack(pady=4)
spreadsheet_button = ctk.CTkButton(center_container, text="Select Spreadsheet", command=select_spreadsheet, width=BUTTON_WIDTH)
spreadsheet_button.pack(pady=4)

# Dropdown variables & widgets
link_player_var = tk.StringVar()
opponent_var = tk.StringVar()
character_var = tk.StringVar()
link_skin_var = tk.StringVar()
link_position_var = tk.StringVar(value="P1")

link_player_dropdown = ctk.CTkComboBox(center_container, variable=link_player_var, values=[])
opponent_dropdown = ctk.CTkComboBox(center_container, variable=opponent_var, values=[])
character_dropdown = ctk.CTkComboBox(center_container, variable=character_var, values=[])
link_skin_dropdown = ctk.CTkComboBox(center_container, variable=link_skin_var, values=[])
position_dropdown = ctk.CTkComboBox(center_container, variable=link_position_var, values=["P1", "P2"])

dropdown_fields = [
    ("Link Player:", link_player_dropdown),
    ("Opponent Name:", opponent_dropdown),
    ("Opponent Character:", character_dropdown),
    ("Select Link's Skin:", link_skin_dropdown),
    ("Link Position (P1 or P2):", position_dropdown)
]

for label_text, dropdown in dropdown_fields:
    label = ctk.CTkLabel(center_container, text=label_text)
    label.pack(pady=2)
    dropdown.pack(pady=2)
    dropdown.configure(width=DROPDOWN_WIDTH)

# Tournament & round entries
tournament_var = tk.StringVar()
round_var = tk.StringVar()
tournament_entry = None
round_entry = None

text_fields = [
    ("Tournament Name:", tournament_var),
    ("Round Info:", round_var)
]

for label_text, var in text_fields:
    label = ctk.CTkLabel(center_container, text=label_text)
    entry = ctk.CTkEntry(center_container, textvariable=var, width=ENTRY_WIDTH)
    label.pack(pady=2)
    entry.pack(pady=2)
    if "Tournament" in label_text:
        tournament_entry = entry
    else:
        round_entry = entry

# Font fields
font_size_var = tk.StringVar(value="50")
outline_size_var = tk.StringVar(value="1")
round_font_size_var = tk.StringVar(value="28")

font_fields = [
    ("Font Size:", font_size_var),
    ("Outline Size:", outline_size_var),
    ("Round Info Font Size:", round_font_size_var)
]

for label_text, var in font_fields:
    label = ctk.CTkLabel(center_container, text=label_text)
    entry = ctk.CTkEntry(center_container, textvariable=var, width=ENTRY_WIDTH)
    label.pack(pady=2)
    entry.pack(pady=2)

# Buttons
update_button = ctk.CTkButton(center_container, text="Update Preview", command=generate_thumbnail, width=BUTTON_WIDTH)
update_button.pack(pady=4)
fullscreen_button = ctk.CTkButton(center_container, text="Preview Fullscreen", command=preview_fullscreen, width=BUTTON_WIDTH)
fullscreen_button.pack(pady=4)
save_button = ctk.CTkButton(center_container, text="Save PNG", command=save_thumbnail, width=BUTTON_WIDTH)
save_button.pack(pady=4)
psd_button = ctk.CTkButton(center_container, text="Save PSD", command=save_thumbnail_as_psd, width=BUTTON_WIDTH)
psd_button.pack(pady=4)


def update_character_selection(event=None):
    selected_character = character_dropdown.get()
    character_var.set(selected_character)

character_dropdown.bind("<<ComboboxSelected>>", update_character_selection)
opponent_dropdown.bind("<<ComboboxSelected>>", update_character_selection)

# === Console output tab ===
console_output = ctk.CTkTextbox(console_frame, width=980, height=480)
console_output.pack(expand=True, fill="both", padx=10, pady=10)

# === Downloader tab controls ===
image_label = None
try:
    image_path = resource_path("assets/gawr_gura.png")
    image = Image.open(image_path)

    # Use CTkImage (fixes the DPI scaling warning)
    ctk_photo = CTkImage(light_image=image, dark_image=image, size=(100, 100))

    # Create CTkButton with the CTkImage
    image_label = ctk.CTkButton(
        downloader_frame,
        image=ctk_photo,
        text="",
        width=120,
        height=120,
        fg_color="transparent",
        hover=False
    )
    image_label.pack(pady=10)

    # Handle click (CTkButton still supports bind on underlying widget)
    def on_gura_click(event=None):
        show_epic_tab()

    image_label.bind("<Button-1>", on_gura_click)

except Exception as e:
    print("Error loading image:", e)


DOWNLOADER_BUTTON_WIDTH = 240
spreadsheet_status_label_downloader = ctk.CTkLabel(downloader_frame, text="No spreadsheet loaded")
spreadsheet_status_label_downloader.pack(pady=4)
select_button = ctk.CTkButton(downloader_frame, text="Select Spreadsheet", command=select_spreadsheet, width=DOWNLOADER_BUTTON_WIDTH)
select_button.pack(pady=4)

def select_directory():
    path = filedialog.askdirectory()
    if path:
        state.download_directory = path
        save_config()

select_dir_button = ctk.CTkButton(downloader_frame, text="Set Download Directory", command=select_directory, width=DOWNLOADER_BUTTON_WIDTH)
select_dir_button.pack(pady=4)

# Download controls frame
download_buttons_frame = ctk.CTkFrame(downloader_frame)
download_buttons_frame.pack(pady=6)

download_button = ctk.CTkButton(download_buttons_frame, text="Start Download", command=start_download, width=DOWNLOADER_BUTTON_WIDTH//2)
download_button.pack(side="left", padx=4)

cancel_button = ctk.CTkButton(download_buttons_frame, text="Cancel Download", command=cancel_download, width=DOWNLOADER_BUTTON_WIDTH//2, state="disabled")
cancel_button.pack(side="left", padx=4)

# Progress bar now uses pack() to match the parent's pack layout
progress_bar = ctk.CTkProgressBar(downloader_frame, width=600)
progress_bar.set(0.0)
# initially hidden via pack_forget()
progress_bar.pack_forget()

progress_label = ctk.CTkLabel(downloader_frame, text="Waiting...")
progress_label.pack(pady=6)

# Footer & credits
footer_frame = ctk.CTkFrame(app)
footer_frame.pack(side="bottom", fill="x", pady=6)
credit_label = ctk.CTkLabel(footer_frame, text=f"Made by Ozzy :)\nVersion {VERSION}", font=ctk.CTkFont(size=10))
credit_label.pack(side="bottom", pady=6)

# Secret epic tab (will be added dynamically)
epic_tab_loaded = False

def show_epic_tab():
    global epic_tab_loaded
    if not epic_tab_loaded:
        tabview.add("🌀 Awesome Fucking Tien Edit")
        epic_tab = ctk.CTkFrame(tabview.tab("🌀 Awesome Fucking Tien Edit"))
        epic_tab.pack(expand=True, fill="both", padx=12, pady=12)
        video_label = ctk.CTkLabel(epic_tab, text="")
        video_label.pack(expand=True, fill="both", padx=10, pady=10)
        def play_epic_video():
            video_path = resource_path("assets/edit.mp4")
            audio_path = resource_path("assets/edit_audio.mp3")
            player = VideoPlayer(video_path, video_label._label, loop=0, size=(640, 360))
            player.play()
            Thread(target=play_audio, args=(audio_path,), daemon=True).start()
        play_button = ctk.CTkButton(epic_tab, text="▶ Play Awesome Edit", command=play_epic_video)
        play_button.pack(pady=10)
        epic_tab_loaded = True
    tabview.set("🌀 Awesome Fucking Tien Edit")

# Load saved config & start UI queue
load_config()
process_ui_queue_loop()
flush_logs()
check_for_updates_at_launch()

# Start main loop
app.mainloop()
