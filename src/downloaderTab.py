import customtkinter as ctk
from customtkinter import CTkImage
from PIL import Image
from helperFuncs import resource_path
from tkinter import filedialog, messagebox
import os
from threading import Thread
import pandas as pd
import subprocess
import re
import traceback

class DownloaderTab:
    def __init__(self, parent, parent_tab):
        self.parent = parent
        self.frame = ctk.CTkFrame(parent_tab)
        self.frame.pack(fill="both", expand=True, padx=12, pady=12)

        try:
            image_path = resource_path("assets/gawr_gura.png")
            image = Image.open(image_path)

            # Use CTkImage (fixes the DPI scaling warning)
            ctk_photo = CTkImage(light_image=image, dark_image=image, size=(100, 100))

            # Create CTkButton with the CTkImage
            image_label = ctk.CTkButton(
                self.frame,
                image=ctk_photo,
                text="",
                width=120,
                height=120,
                fg_color="transparent",
                hover=False
            )
            image_label.pack(pady=10)

            image_label.bind("<Button-1>", self.parent.show_epic_tab)

        except Exception as e:
            print("Error loading image:", e)

        self.status_label = ctk.CTkLabel(self.frame, text="No spreadsheet loaded")
        self.status_label.pack(pady=4)

        DOWNLOADER_BUTTON_WIDTH = 240
        select_button = ctk.CTkButton(self.frame, text="Select Spreadsheet", command=self.parent.select_spreadsheet, width=DOWNLOADER_BUTTON_WIDTH)
        select_button.pack(pady=4)

        select_dir_button = ctk.CTkButton(self.frame, text="Set Download Directory", command=self.select_download_directory, width=DOWNLOADER_BUTTON_WIDTH)
        select_dir_button.pack(pady=4)

        # Download controls frame
        download_buttons_frame = ctk.CTkFrame(self.frame)
        download_buttons_frame.pack(pady=6)

        self.download_button = ctk.CTkButton(download_buttons_frame, text="Start Download", command=self.start_download, width=DOWNLOADER_BUTTON_WIDTH//2)
        self.download_button.pack(side="left", padx=4)

        self.cancel_button = ctk.CTkButton(download_buttons_frame, text="Cancel Download", command=self.cancel_download, width=DOWNLOADER_BUTTON_WIDTH//2, state="disabled")
        self.cancel_button.pack(side="left", padx=4)

        self.progress_bar = ctk.CTkProgressBar(self.frame, width=600)
        self.progress_bar.set(0.0)
        self.progress_bar.pack_forget() #Yoy: I don't think this does anything, you just made it so it hasn't been packed yet

        self.progress_label = ctk.CTkLabel(self.frame, text="Waiting...")
        self.progress_label.pack(pady=6)

        self.spreadsheet_cache = {}
        self.downloader_thread=None
        self.download_directory = None

    def select_download_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            self.download_directory = directory
            self.parent.save_config()

    #Yoy: made this cause it showed up a lot in the code
    def set_button_states(self, downloading):
        if downloading:
            self.download_button.configure(state="disabled")
            self.cancel_button.configure(state="normal")
        else:
            self.download_button.configure(state="normal")
            self.cancel_button.configure(state="disabled")

    def start_download(self):
        self.progress_bar.set(0.0)
        self.progress_bar.pack(pady=4)  # show by packing (no grid usage)
        if self.downloader_thread and self.downloader_thread.is_alive():
            self.parent.log("Downloader is already running.\n")
            return
        self.progress_label.configure(text="Starting download...")
        self.set_button_states(downloading=True)
        self.cancel_flag = False
        self.downloader_thread = Thread(target=self.process_spreadsheet_worker, daemon=True)
        self.downloader_thread.start()

    def cancel_download(self):
        if messagebox.askyesno("Cancel Download", "Are you sure you want to cancel the download?"):
            self.parent.log("Canceling download...\n")
            if self.downloader_thread and self.downloader_thread.is_alive():
                self.cancel_flag = True
            self.progress_label.configure(text="Download canceled")
            self.set_button_states(downloading=False)
            self.progress_bar.set(0.0)
            self.progress_bar.pack_forget()

    def process_spreadsheet_worker(self):
        try:
            if not self.parent.selected_spreadsheet_path or not self.download_directory:
                raise ValueError("Error: No file or download directory selected.")

            df = self.parent.load_spreadsheet_cached(self.parent.selected_spreadsheet_path)
            df.columns = df.columns.str.strip().str.lower()

            link_column = next((col for col in df.columns if "twitch link" in col or "vod link" in col), None)
            timestamp_column = next((col for col in df.columns if "timestamps" in col), None)
            character_column = next((col for col in df.columns if "opponent" in col), None)

            if not link_column or not timestamp_column or not character_column:
                raise ValueError("Error: Required columns not found in spreadsheet.")

            total_vods = len(df)
            self.progress_bar.set(0.0)

            for i in range(total_vods):
                row = df.iloc[i]
                vod_url = str(row[link_column]) if not pd.isna(row[link_column]) else ""
                timestamp = row[timestamp_column]
                opponent_character = row[character_column] if not pd.isna(row[character_column]) else "unknown"

                if not vod_url:
                    self.parent.log(f"Skipping row {i+1}/{total_vods}: No VOD link.\n")
                    continue

                output_filename = f"VOD_{i+1}_{opponent_character}.mp4"
                start_time, end_time = self.parse_timestamps(timestamp)
                
                self.download_vod(vod_url, start_time, end_time, output_filename, i, total_vods)

                if(self.cancel_flag):
                    self.parent.log("Download canceled by user.\n")
                    break

            #Yoy: instead of assuming all downloads succeeded, you can check the cancel flag and/or yt-dlp exit codes
            # Final message after ALL VODs finish
            self.progress_label.configure(text="Downloads Complete!")
            self.parent.log("All downloads completed successfully!\n")
        except Exception as e:
            #Yoy: added traceback for easier debugging. i think that's a default python module but you might have to pip install it or whatever
            self.parent.log(f"[process_spreadsheet_worker] {traceback.format_exc()}: {e}\n")
        finally:
            self.set_button_states(downloading=False)
            self.progress_bar.pack_forget()
    
    def parse_timestamps(self,timestamp):
        if pd.isna(timestamp) or str(timestamp).lower() == "full vid":
            return None, None
        if '-' in str(timestamp):
            parts = str(timestamp).split('-')
            if len(parts) != 2:
                self.parent.log(f"Invalid timestamp format: {timestamp}\n")
                return None, None
            start_time, end_time = parts
        else:
            start_time = str(timestamp)
            end_time = "inf"
        return start_time.strip(), end_time.strip()

    def download_vod(self, url, start_time, end_time, output_filename, index, total):
        
        command = ["yt-dlp", "-f", "bestvideo+bestaudio/best", "--newline"]
        if start_time and end_time:
            command += ["--download-sections", f"*{start_time}-{end_time}"]
        command += ["-o", os.path.join(self.download_directory, output_filename), url]
        self.parent.log(f"Running command: {' '.join(command)}\n")
        try:
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
        except Exception as e:
            self.parent.log(f"Failed to start yt-dlp: {e}\n")
            return

        is_section_download = start_time and end_time

        start_sec = self.__time_to_sec(start_time or "0:00")
        
        #Recommendation #2: you should properly handle 'inf' as the end of the video, get the time stamp from yt-dlp
        #your previous solution just pretended to increment progress by 0.5%, so i removed that
        end_sec = self.__time_to_sec(end_time) if end_time and end_time.lower() != "inf" else float('inf')
        if is_section_download and end_sec == float('inf'):
            self.progress_label.configure(text=f"Downloading {index+1}/{total}: Progress reports unsupported for open-ended sections")

        duration = max(1, end_sec - start_sec)

        for stdout_line in iter(proc.stdout.readline, ""):
            stripped_line = stdout_line.rstrip("\n")
            self.parent.log(stripped_line + "\n")
            if is_section_download:
               self.__handle_line_sectioned(stripped_line, start_sec, end_sec, duration, index, total)
            else:
                self.__handle_line_standard(stripped_line, index, total, output_filename)
                
            if self.cancel_flag:
                proc.terminate()
                proc.wait(timeout = 2)
                if(proc.poll() is None):
                    proc.kill()
                return

        proc.wait()

    def __handle_line_sectioned(self, line, start_sec, end_sec, duration, index, total):
        if end_sec == float('inf'): #Yoy: see recommendation #2
            return
        
        time_match = re.search(r'time=([\d:.]+)', line)
        if not time_match:
            return
        
        current_time = self.__time_to_sec(time_match.group(1))
        current_percent = max(0, min(100, (current_time / duration) * 100))
        remaining = max(0, duration - current_time)

        speed_match = re.search(r'speed=\s*([\d.]+x|\d+\.?\d*\s*\w+/s)', line)
        if speed_match and "x" in speed_match.group(1):
            speed_factor = float(speed_match.group(1).replace("x", ""))
            eta = self.__format_eta(remaining / speed_factor)
        else:
            eta = "Unknown"
        speed = speed_match.group(1).strip() if speed_match else "N/A"

        self.progress_bar.set(min(1.0, max(0.0, current_percent / 100.0)))
        self.progress_label.configure(text=f"Downloading {index+1}/{total}: {current_percent:.1f}% | Speed: {speed} | ETA: {eta}")
        #Yoy: since only the part after the first colon changes, pre calculate that part to reduce how many vars you have to pass around 
        #and/or use 2 labels, one for the unchanging part and one for the changing part

    def __handle_line_standard(self, line, index, total, output_filename):
        percent_match = re.search(r'.*\[download\]\s*([\d.]+)%', line)
        if not percent_match:
            return
        
        self.progress_bar.set(min(1.0, max(0.0, float(percent_match.group(1)) / 100.0)))
        self.progress_label.configure(text=f"Downloading {index+1}/{total}: {output_filename} | {percent_match.group(1)}%")

    def __time_to_sec(self,t):
        parts = t.split(':')
        if len(parts) == 3:
            h, m, s = parts
            return int(h)*3600 + int(m)*60 + float(s)
        elif len(parts) == 2:
            m, s = parts
            return int(m)*60 + float(s)
        #Yoy: should probably log an error here
        return 0
    
    def __format_eta(self,seconds):
        if not isinstance(seconds, (int, float)) or seconds < 0 or seconds > 86400:
            return "Unknown"
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"