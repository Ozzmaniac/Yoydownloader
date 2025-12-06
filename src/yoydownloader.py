"""
YOYDOWNLOADER 2.1.1 - CUSTOMTKINTER CONVERSION (Optimized + CTkImage preview)
- Uses CTkImage for preview to avoid HighDPI CTkLabel warnings
- Progress bar uses pack() (no grid/pack mixing)
- Buffered console logging to avoid UI thrashing
- Reduced UI queue polling from 33ms -> 100ms
- Throttled progress updates from yt-dlp
- Keeps original backend logic intact
"""

import os
import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import sys
import platform
import json
from updater import check_for_update, run_updater, perform_update, VERSION
from consoleTab import ConsoleTab
from helperFuncs import resource_path
from downloaderTab import DownloaderTab
from thumbnailTab import ThumbnailTab
from epicTab import EpicTab
from PIL import Image, ImageTk

class MainApp:
    def __init__(self):
        self.app = ctk.CTk()
        self.app.title(f"YoyDownloader v{VERSION}")
        self.app.geometry("1100x700")
        self.spreadsheet_cache = {}
        self.epic_tab_loaded = False
        self.selected_spreadsheet_path = None

        # Set icon
        icon_path = resource_path("assets/gura.ico")
        try:
            if platform.system() == "Windows":
                self.app.iconbitmap(default=icon_path)
            else:
                #Yoy: im assuming the windows path works on your machine and that linux just can't open .ico files directly. fix by using PIL to open and convert
                #im not sure if this could work on windows too, you might wanna test that out. would be nice to have a single code path for both OSes
                ico_img = Image.open(icon_path)
                img = ImageTk.PhotoImage(ico_img)
                self.app.iconphoto(False, img)
        except Exception as e:
            print(f"Failed to load icon: {e}")
        
        #Recommendation #whatever: it might be worth to read page layout from a file instead of with code
        #code just isn't the place for that. plus it gives the benefit of being able to tweak layout to user preference
        #this advice applies to all tabs. the thumbnail tab in particular is quite the chonker
        self.main_frame = ctk.CTkFrame(self.app)
        self.main_frame.pack(fill="both", expand=True, padx=12, pady=12)

        self.tabview = ctk.CTkTabview(self.main_frame, width=1000)
        self.tabview.add("Downloader")
        self.tabview.add("Thumbnail Generator")
        self.tabview.add("Console Output")
        self.tabview.pack(expand=True, fill="both", side="top")

        self.consoleTab = ConsoleTab(self.tabview.tab("Console Output"))
        self.downloaderTab = DownloaderTab(self, self.tabview.tab("Downloader"))
        self.thumbnailTab = ThumbnailTab(self, self.tabview.tab("Thumbnail Generator"))

        footer_frame = ctk.CTkFrame(self.app)
        footer_frame.pack(side="bottom", fill="x", pady=6)
        credit_label = ctk.CTkLabel(footer_frame, text=f"Made by Ozzy :)\nVersion {VERSION}", font=ctk.CTkFont(size=10))
        credit_label.pack(side="bottom", pady=6)

        self.load_config()
        self.check_for_updates_at_launch()

    #saves loaded spreadsheets in cache and reuses them
    def load_spreadsheet_cached(self, path):
        if path in self.spreadsheet_cache:
            return self.spreadsheet_cache[path]
        df = pd.read_excel(path)
        self.spreadsheet_cache[path] = df
        return df

    def load_config(self):
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, 'r') as f:
                    cfg = json.load(f)
                # Apply safely and update UI if necessary
                if cfg.get("link_channel_path") and os.path.exists(cfg["link_channel_path"]):
                    self.thumbnailTab.link_channel_path = cfg["link_channel_path"]
                    self.thumbnailTab.folder_label.configure(text=f"Selected: {self.thumbnailTab.link_channel_path}")
                    self.thumbnailTab.update_character_dropdown()
                    self.thumbnailTab.update_link_alt_dropdown()

                if cfg.get("saved_directory") and os.path.exists(cfg["saved_directory"]):
                    self.thumbnailTab.saved_directory = cfg["saved_directory"]
                    self.thumbnailTab.save_dir_label.configure(text=f"Save to: {self.thumbnailTab.saved_directory}")

                if cfg.get("selected_spreadsheet_path") and os.path.exists(cfg["selected_spreadsheet_path"]):
                    self.selected_spreadsheet_path = cfg["selected_spreadsheet_path"]
                    filename = os.path.basename(cfg["selected_spreadsheet_path"])
                    self.downloaderTab.status_label.configure(text=f"Spreadsheet Loaded: {filename}", fg_color="transparent")
                    self.thumbnailTab.status_label.configure(text=f"Spreadsheet Loaded: {filename}", fg_color="transparent")
                    self.thumbnailTab.populate_dropdowns_from_excel(cfg["selected_spreadsheet_path"])

                if cfg.get("download_directory") and os.path.exists(cfg["download_directory"]):
                    self.downloaderTab.download_directory = cfg["download_directory"]
        except Exception as e:
            self.consoleTab.log(f"Error loading configuration: {e}\n")

    def save_config(self):
        cfg = {
            "link_channel_path": self.thumbnailTab.link_channel_path,
            "saved_directory": self.thumbnailTab.saved_directory,
            "selected_spreadsheet_path": self.selected_spreadsheet_path,
            "download_directory": self.downloaderTab.download_directory
        }
        try:
            with open(CONFIG_PATH, 'w') as f:
                json.dump(cfg, f)
        except Exception as e:
            self.consoleTab.log(f"Error saving configuration: {e}\n")

    def check_for_updates_at_launch(self):
        latest_version = check_for_update()
        if latest_version and messagebox.askyesno(
            "Update Available",
            f"A new version ({latest_version}) is available.\nDo you want to update now?"):
            run_updater()

    def log(self, message):
        self.consoleTab.log(message)

    def run(self):
        self.app.mainloop()

    def show_epic_tab(self, event=None):
        if not self.epic_tab_loaded:
            self.tabview.add("🌀 Awesome Fucking Tien Edit")
            self.epic_tab = EpicTab(self.tabview.tab("🌀 Awesome Fucking Tien Edit"))
            self.epic_tab_loaded = True
        self.tabview.set("🌀 Awesome Fucking Tien Edit")

    #in main app because it's shared between downloader and thumbnail tabs
    def select_spreadsheet(self):
        file_path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx")])
        if not file_path:
            return
        self.selected_spreadsheet_path = file_path

        filename = os.path.basename(file_path)
        self.downloaderTab.status_label.configure(text=f"Spreadsheet Loaded: {filename}")
        self.thumbnailTab.status_label.configure(text=f"Spreadsheet Loaded: {filename}")

        self.thumbnailTab.populate_dropdowns_from_excel(file_path)
        self.save_config()

if __name__ == "__main__":
    APP_NAME = "Yoydownloader"
    CONFIG_FILENAME = "yoydownloader_config.json"

    #recommendation 1: Linux config file should go into ~/.config instead
    CONFIG_PATH = os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"), APP_NAME, CONFIG_FILENAME)

    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)

    # Handle update mode (used by updater)
    if "--update" in sys.argv and len(sys.argv) > 2:
        perform_update(sys.argv[2])
        sys.exit(0)

    # === Initialize CustomTkinter appearance ===
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    main_app = MainApp()
    main_app.run()