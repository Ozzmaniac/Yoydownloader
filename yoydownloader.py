import os
import random
import pandas as pd
import subprocess
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from threading import Thread
import sys
import platform
from PIL import ImageTk, Image
import json
import re
import time
import queue
from tkinter import Tk, Label
from tkvideo import tkvideo as VideoPlayer
from playsound import playsound as play_audio
import threading


#Resource Path 
def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# Global variables
CONFIG_FILE = "yoydownloader_config.json"
download_speed = "0 KiB/s"
download_eta = "Unknown"
active_process = None
download_canceled = False

# Function to save configuration
def save_config():
    config = {
        "link_channel_path": link_channel_path,
        "saved_directory": saved_directory,
        "selected_spreadsheet_path": selected_spreadsheet_path,
        "download_directory": download_directory
    }
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f)
    except Exception as e:
        console_output.insert(tk.END, f"Error saving configuration: {e}\n")
        console_output.see(tk.END)

# Function to load configuration
def load_config():
    global link_channel_path, saved_directory, selected_spreadsheet_path, download_directory, selected_file
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                
                # Load Link Channel path
                if "link_channel_path" in config and config["link_channel_path"] is not None and os.path.exists(config["link_channel_path"]):
                    link_channel_path = config["link_channel_path"]
                    folder_label.config(text=f"Selected: {link_channel_path}")
                    update_character_dropdown()
                    update_link_alt_dropdown()
                
                # Load saved directory
                if "saved_directory" in config and config["saved_directory"] is not None and os.path.exists(config["saved_directory"]):
                    saved_directory = config["saved_directory"]
                    save_dir_label.config(text=f"Save to: {saved_directory}")
                
                # Load spreadsheet path
                if "selected_spreadsheet_path" in config and config["selected_spreadsheet_path"] is not None and os.path.exists(config["selected_spreadsheet_path"]):
                    selected_spreadsheet_path = config["selected_spreadsheet_path"]
                    selected_file = selected_spreadsheet_path
                    filename = os.path.basename(selected_spreadsheet_path)
                    spreadsheet_status_label_downloader.config(text=f"Spreadsheet Loaded: {filename}", fg="green")
                    spreadsheet_status_label.config(text=f"Spreadsheet Loaded: {filename}", fg="green")
                    
                    # Load data for thumbnail generator
                    populate_dropdowns_from_excel(selected_spreadsheet_path)

                
                # Load download directory
                if "download_directory" in config and config["download_directory"] is not None and os.path.exists(config["download_directory"]):
                    download_directory = config["download_directory"]
    except Exception as e:
        console_output.insert(tk.END, f"Error loading configuration: {e}\n")
        console_output.see(tk.END)
        
        
#Base window creation
root = tk.Tk()
VERSION = "2.0.6"
root.title(f"YoyDownloader v{VERSION}")
root.configure(bg="#2e2e2e")  

# Set program icon
icon_path = resource_path("assets/gura.ico")
try:
    if platform.system() == "Windows":
        root.iconbitmap(default=icon_path)
    else:
        img = tk.PhotoImage(file=icon_path)
        root.tk.call('wm', 'iconphoto', root._w, img)
except Exception as e:
    print(f"Failed to load icon: {e}")


#Parse Timestamps
def parse_timestamps(timestamp):
    if pd.isna(timestamp) or timestamp.lower() == "full vid":
        return None, None  
    if '-' in timestamp:
        parts = timestamp.split('-')
        if len(parts) != 2:
            log_message(f"Invalid timestamp format: {timestamp}\n")
            return None, None
        start_time, end_time = parts
    else:
        start_time = timestamp
        end_time = "inf"  
    return start_time.strip(), end_time.strip()


# Global flag to track if downloads should be canceled
def cancel_download():
    #Reassigning global flags
    global download_canceled, active_process
    
    # Ask for confirmation
    if messagebox.askyesno("Cancel Download", "Are you sure you want to cancel the download?"):
        download_canceled = True
        console_output.insert(tk.END, "Canceling download...\n")
        console_output.see(tk.END)
        
        # Terminate the active process if exists
        if active_process and active_process.poll() is None:
            if platform.system() == "Windows":
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(active_process.pid)], 
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                active_process.terminate()
                progress_bar.pack_forget()

                
        progress_label.config(text="Download canceled")
        # Re-enable the download button
        download_button.config(state=tk.NORMAL)
        cancel_button.config(state=tk.DISABLED)


#Helper
def format_eta(seconds):
    if not isinstance(seconds, (int, float)) or seconds < 0 or seconds > 86400:
        return "Unknown"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"




#Download VOD function
progress_queue = queue.Queue()

def download_vod(url, start_time, end_time, output_filename, index, total, callback=None):
    global download_canceled, active_process, download_speed

    if download_canceled:
        return

    command = ["yt-dlp", "-f", "bestvideo+bestaudio/best", "--newline"]
    if start_time and end_time:
        command += ["--download-sections", f"*{start_time}-{end_time}"]
    command += ["-o", os.path.join(download_directory, output_filename), url]

    startupinfo = None
    if platform.system() == "Windows":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    active_process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
        startupinfo=startupinfo
    )

    current_percent = 0
    is_section_download = start_time and end_time
    q = queue.Queue()

    def time_to_sec(t):
        parts = t.split(':')
        if len(parts) == 3:
            h, m, s = parts
            return int(h)*3600 + int(m)*60 + float(s)
        elif len(parts) == 2:
            m, s = parts
            return int(m)*60 + float(s)
        return 0

    def reader_thread():
        nonlocal current_percent
        for line in active_process.stdout:
            if download_canceled:
                break
            q.put(line)
        active_process.wait()
        

    def ui_updater():
        nonlocal current_percent
        try:
            while True:
                line = q.get_nowait()
                if line is None:
                    break
                log_message(line)
                if "[download]" in line and "%" in line:
                    m = re.search(r'([\d.]+)%.*?of.*?at\s+([\d.]+\w+/s)\s+ETA\s+([\d:]+)', line)
                    if m:
                        current_percent = float(m.group(1))
                        speed = m.group(2)
                        eta = m.group(3)
                        progress_bar["value"] = current_percent
                        progress_label.config(
                            text=f"Downloading {index+1}/{total}: {output_filename} | {current_percent:.1f}% | Speed: {speed} | ETA: {eta}"
                        )
                elif is_section_download and "time=" in line:
                    time_match = re.search(r'time=([\d:.]+)', line)
                    speed_match = re.search(r'speed=\s*([\d.]+x|\d+\.?\d*\s*\w+/s)', line)
                    if time_match:
                        current_time = time_to_sec(time_match.group(1))
                        start_sec = time_to_sec(start_time or "0:00")
                        end_sec = time_to_sec(end_time) if end_time and end_time.lower() != "inf" else float('inf')
                        if end_sec == float('inf') or current_time < start_sec:
                            current_percent = min(100, current_percent + 0.5)
                            eta = "Unknown"
                        else:
                            duration = max(1, end_sec - start_sec)
                            current_percent = max(0, min(100, ((current_time - start_sec) / duration) * 100))
                            remaining = max(0, end_sec - current_time)
                            if speed_match and "x" in speed_match.group(1):
                                speed_factor = float(speed_match.group(1).replace("x", ""))
                                eta = format_eta(remaining / speed_factor)
                            else:
                                eta = "Unknown"
                        speed = speed_match.group(1).strip() if speed_match else "N/A"
                        progress_bar["value"] = current_percent
                        progress_label.config(
                            text=f"Downloading {index+1}/{total}: {current_percent:.1f}% | Speed: {speed} | ETA: {eta}"
                        )
        except queue.Empty:
            pass

        if active_process.poll() is None:
            root.after(100, ui_updater)
        else:
            if not download_canceled:
                progress_bar["value"] = 100
                progress_label.config(text=f"Post-processing {index+1}/{total}: {output_filename}...")

                def finalize():
                    progress_label.config(text=f"Finished {index+1}/{total}: {output_filename}")
                    if callback:
                        callback()

                root.after(1000, finalize)  # Show "Post-processing..." briefly
            else:
                if callback:
                    callback()

    # Start reading yt-dlp output
    Thread(target=reader_thread, daemon=True).start()
    # Start periodic GUI update loop
    root.after(100, ui_updater)


last_gui_update_time = 0

    
#Process Spreadsheet
def process_spreadsheet():
    global download_canceled, download_speed, download_eta
    
    # Reset progress tracking
    download_speed = "0 KiB/s"
    download_eta = "Unknown"
    download_canceled = False
    
    # Disable download button, enable cancel button
    download_button.config(state=tk.DISABLED)
    cancel_button.config(state=tk.NORMAL)
    
    if not selected_file or not download_directory:
        console_output.insert(tk.END, "Error: No file or directory selected.\n")
        # Re-enable download button, disable cancel button
        download_button.config(state=tk.NORMAL)
        cancel_button.config(state=tk.DISABLED)
        return
    
    df = pd.read_excel(selected_file)
    df.columns = df.columns.str.strip().str.lower()
    
    link_column = next((col for col in df.columns if "twitch link" in col or "vod link" in col), None)
    timestamp_column = next((col for col in df.columns if "timestamps" in col), None)
    character_column = next((col for col in df.columns if "opponent" in col), None)
    
    if not link_column or not timestamp_column or not character_column:
        console_output.insert(tk.END, "Error: Required columns not found in spreadsheet.\n")
        # Re-enable download button, disable cancel button
        download_button.config(state=tk.NORMAL)
        cancel_button.config(state=tk.DISABLED)
        return
    
    total_vods = len(df)
    progress_bar["maximum"] = 100  # Set maximum to 100% for each file
    progress_bar["value"] = 0
    
    
    completed = 0
    def run_next(index):
        if index >= len(df) or download_canceled:
            finish_download()
            progress_bar.pack_forget()
            return

        row = df.iloc[index]
        vod_url = str(row[link_column]) if not pd.isna(row[link_column]) else ""
        timestamp = row[timestamp_column]
        opponent_character = row[character_column]

        if not vod_url:
            console_output.insert(tk.END, f"Skipping row {index + 1}/{total_vods}: No VOD link.\n")
            console_output.see(tk.END)
            run_next(index + 1)
            return

        output_filename = f"VOD_{index+1}_{opponent_character}.mp4"
        start_time, end_time = parse_timestamps(timestamp)

        progress_bar["value"] = 0

        def on_done():
            root.after(0, lambda: run_next(index + 1))

        Thread(target=lambda: download_vod(
            vod_url, start_time, end_time, output_filename, index, total_vods, on_done),
            daemon=True
        ).start()

    def finish_download():
        if download_canceled:
            progress_label.config(text="Download canceled")
        else:
            progress_label.config(text="Downloads Complete!")
            console_output.insert(tk.END, "All downloads completed successfully!\n")
            console_output.see(tk.END)
        download_button.config(state=tk.NORMAL)
        cancel_button.config(state=tk.DISABLED)

    run_next(0)

        

#Spreadsheet Reader
def select_directory():
    global download_directory
    download_directory = filedialog.askdirectory()
    if download_directory:
        save_config()  # Save configuration after selecting directory

#Start Download
def start_download():
    progress_bar["value"] = 0
    progress_label.config(text="Starting download...")
    progress_bar.pack(pady=0)
    Thread(target=process_spreadsheet).start()
    download_button.config(state=tk.DISABLED)
    cancel_button.config(state=tk.NORMAL)
    

style = ttk.Style()
style.theme_use("clam")
style.configure("TFrame", background="#2e2e2e")
style.configure("TLabel", background="#2e2e2e", foreground="white")
style.configure("TButton", background="#444", foreground="white")
style.configure("Horizontal.TProgressbar", background="#44a")
style.configure("TNotebook", background="#2e2e2e", borderwidth=0)
style.configure("TNotebook.Tab", background="#444", foreground="white", padding=5)
style.configure("Vertical.TScrollbar", background="#444", troughcolor="#222", borderwidth=0, relief="flat")
style.map("Vertical.TScrollbar", background=[("active", "#666"), ("pressed", "#888")])
style.map("TNotebook.Tab", background=[("selected", "#666")])



notebook = ttk.Notebook(root)
downloader_frame = ttk.Frame(notebook, style="TFrame")
console_frame = ttk.Frame(notebook, style="TFrame")
thumbnail_frame = ttk.Frame(notebook, style="TFrame")  
notebook.add(downloader_frame, text="Downloader")
notebook.add(thumbnail_frame, text="Thumbnail Generator")
notebook.add(console_frame, text="Console Output")
notebook.pack(expand=True, fill="both")

# Adjust scaling based on original window size
def on_resize(event):
    scale_factor = min(event.width / 1280, event.height / 720) 
    update_preview(preview_image) if 'preview_image' in globals() else None
    thumbnail_canvas.configure(scrollregion=thumbnail_canvas.bbox("all")) 

    # Resize the preview image dynamically if it exists
    if 'preview_image' in globals():
        new_size = (int(640 * scale_factor), int(360 * scale_factor))
        resized_image = preview_image._PhotoImage__photo.zoom(new_size[0], new_size[1])
        preview_canvas.config(image=resized_image)

    # Resize only widgets that support the "font" option
    for frame in [downloader_frame, console_frame, thumbnail_frame]:
        for widget in frame.winfo_children():
            try:
                if "font" in widget.keys():  # Only adjust font if the widget supports it
                    widget.config(font=("Arial", int(12 * scale_factor)))
            except tk.TclError:
                pass  # Ignore widgets that don't support fonts

        

# Thumbnail Generator Frame

# Create a canvas inside the thumbnail frame to enable scrolling
thumbnail_canvas = tk.Canvas(thumbnail_frame, bg="#2e2e2e", highlightthickness=0)
scrollbar = ttk.Scrollbar(thumbnail_frame, orient="vertical", command=thumbnail_canvas.yview)

# Create an inner frame to hold all content
scrollable_frame = ttk.Frame(thumbnail_canvas, style="TFrame")

# Configure the scrollable frame to expand to the full width of the canvas
def configure_scrollable_frame(event):
    thumbnail_canvas.itemconfig(window_id, width=event.width)
thumbnail_canvas.bind("<Configure>", configure_scrollable_frame)

# Move preview_canvas outside of the scrollable area
preview_canvas = tk.Label(scrollable_frame, bg="#1e1e1e")
preview_canvas.pack(pady=10)

# Create a container frame for all the UI elements to center them
center_container = ttk.Frame(scrollable_frame, style="TFrame")
center_container.pack(expand=True, padx=20)

# Define standard widths for UI elements
BUTTON_WIDTH = 25
DROPDOWN_WIDTH = 30
ENTRY_WIDTH = 30

# Ensure the scrollable frame expands properly
scrollable_frame.bind(
    "<Configure>",
    lambda e: thumbnail_canvas.configure(scrollregion=thumbnail_canvas.bbox("all"))
)

# Embed the scrollable frame inside the canvas
window_id = thumbnail_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
thumbnail_canvas.configure(yscrollcommand=scrollbar.set)


# Pack the canvas and scrollbar inside the thumbnail tab
thumbnail_canvas.pack(side="left", fill="both", expand=True, padx=5, pady=5)
scrollbar.pack(side="right", fill="y", padx=5, pady=5)

# === Global App State ===
download_directory = ""
selected_file = None
selected_spreadsheet_path = None
saved_directory = None
link_channel_path = None


# Modify the select_link_channel function
def select_link_channel():
    global link_channel_path
    link_channel_path = filedialog.askdirectory()
    folder_label.config(text=f"Selected: {link_channel_path}")
    update_character_dropdown()
    update_link_alt_dropdown()
    save_config()  # Save configuration after changing path

# Modify the select_save_directory function
def select_save_directory():
    global saved_directory
    saved_directory = filedialog.askdirectory()
    if saved_directory:
        save_dir_label.config(text=f"Save to: {saved_directory}")
        save_config()  # Save configuration after changing path

# Function to update the character selection dropdown
def update_character_dropdown():
    if not link_channel_path:
        return
    char_folder = os.path.join(link_channel_path, "Transparent cast", "Rest of cast")
    characters = [f.replace(".png", "") for f in os.listdir(char_folder) if f.endswith(".png")]
    
    character_dropdown["values"] = characters  # Ensure dropdown is properly updated

# Function to update the Link alt selection dropdown
def update_link_alt_dropdown():
    if not link_channel_path:
        return
    link_alt_folder = os.path.join(link_channel_path, "Transparent cast", "Link alts")
    link_alts = [f.replace(".png", "") for f in os.listdir(link_alt_folder) if f.endswith(".png")]
    link_skin_dropdown["values"] = link_alts

positions = {
    "link_center_P1": (-350, 40),  # Link on left side (P1)
    "link_center_P2": (350, 40),  # Link on right side (P2)
    "opponent_center_P1": (-350, 40),  # Opponent on left side (P1)
    "opponent_center_P2": (350, 40),  # Opponent on right side (P2)
    "link_name_P1": (186, 610),  # Below Link (Left)
    "link_name_P2": (922, 610),  # Below Link (Right)
    "opponent_name_P1": (186, 610),  # Below Opponent (Left)
    "opponent_name_P2": (922, 610),  # Below Opponent (Right)
    "tournament_title": (497, 20),  # Centered at the top box
    "round_info": (602, 87),  # Below tournament title box
}



# Thumbnail Generation

def log_message(message):
    """Thread-safe console output"""
    console_output.insert(tk.END, message)
    if int(console_output.index('end-1c').split('.')[0]) > 100:  # Keep last 100 lines
        console_output.delete(1.0, 2.0)
    console_output.see(tk.END)

def generate_thumbnail():
    """Main entry point - starts non-blocking generation"""
    Thread(target=_generate_thumbnail_async, daemon=True).start()

def _generate_thumbnail_async():
    """Background thread work for preview updates"""
    try:
        img = _generate_thumbnail_core()
        if img:
            preview_canvas.after(0, lambda: update_preview(img))
    except Exception as e:
        console_output.after(0, lambda: log_message(f"Thumbnail Error: {str(e)}\n"))

def _generate_thumbnail_core():
    """Core generation logic - returns PIL Image or None"""
    from PIL import Image, ImageDraw, ImageFont
    import os
    # Input validation
    if not link_channel_path:
        log_message("Error: No Link Channel folder selected\n")
        return None
        
    opponent_character = character_var.get().strip()
    if not opponent_character:
        log_message("Error: Please select an opponent character\n")
        return None

    # Load background
    bg_path = os.path.join(link_channel_path, "Background layouts", f"BG {random.randint(1, 5)}.png")
    try:
        background = Image.open(bg_path).resize((1280, 720))
    except Exception as e:
        log_message(f"Error loading background: {str(e)}\n")
        return None

    # Load character images
    link_skin = link_skin_var.get()
    link_path = os.path.join(link_channel_path, "Transparent cast", "Link alts", f"{link_skin}.png")
    char_path = os.path.join(link_channel_path, "Transparent cast", "Rest of cast", f"{opponent_character}.png")
    
    try:
        link_image = Image.open(link_path)
        char_image = Image.open(char_path)
    except Exception as e:
        log_message(f"Error loading character images: {str(e)}\n")
        return None

    # Character positioning
    if link_position_var.get() == "P2":
        link_image = link_image.transpose(Image.FLIP_LEFT_RIGHT)
    elif link_position_var.get() == "P1":
        char_image = char_image.transpose(Image.FLIP_LEFT_RIGHT)

    # Paste characters
    draw = ImageDraw.Draw(background)
    if link_position_var.get() == "P1":
        background.paste(link_image, positions["link_center_P1"], link_image)
        background.paste(char_image, positions["opponent_center_P2"], char_image)
        link_name_pos = positions["link_name_P1"]
        opponent_name_pos = positions["opponent_name_P2"]
    else:
        background.paste(char_image, positions["opponent_center_P1"], char_image)
        background.paste(link_image, positions["link_center_P2"], link_image)
        link_name_pos = positions["link_name_P2"]
        opponent_name_pos = positions["opponent_name_P1"]

    # Text rendering
    font_path = resource_path("assets/HyliaSerif.otf")
    if not os.path.exists(font_path):
        log_message("Error: Missing font file HyliaSerif.otf\n")
        return None

    def draw_text_with_outline(draw, text, position, custom_size=None):
        x, y = position
        size = custom_size if custom_size else int(font_size_var.get())
        outline = int(outline_size_var.get())
        font = ImageFont.truetype(font_path, size)
        
        # Draw outline
        for dx in range(-outline, outline+1):
            for dy in range(-outline, outline+1):
                draw.text((x+dx, y+dy), text, font=font, fill="black")
        # Draw main text
        draw.text(position, text, font=font, fill="white")

    # Draw all text elements
    try:
        draw_text_with_outline(draw, tournament_entry.get(), positions["tournament_title"])
        draw_text_with_outline(draw, round_entry.get(), positions["round_info"], 
                             int(round_font_size_var.get()))
        draw_text_with_outline(draw, link_player_var.get(), link_name_pos)
        draw_text_with_outline(draw, opponent_var.get(), opponent_name_pos)
    except Exception as e:
        log_message(f"Text rendering error: {str(e)}\n")
        return None

    return background


def _generate_thumbnail_sync():
    """Blocking version for saving files"""
    return _generate_thumbnail_core()

def update_preview(thumbnail):
    """Update the preview canvas"""
    global preview_image
    width = thumbnail_frame.winfo_width() - 20
    height = int(width * (9/16))
    thumbnail_resized = thumbnail.resize((width, height), Image.Resampling.LANCZOS)
    preview_image = ImageTk.PhotoImage(thumbnail_resized)
    preview_canvas.config(image=preview_image, width=width, height=height)

def preview_fullscreen():
    thumbnail = _generate_thumbnail_sync()
    if thumbnail:
        fullscreen_window = tk.Toplevel()
        fullscreen_window.title("Fullscreen Preview")

        # Maximize window
        fullscreen_window.attributes('-fullscreen', True)

        # Convert image for Tkinter
        fullscreen_img = ImageTk.PhotoImage(thumbnail)

        # Display image in a label
        img_label = tk.Label(fullscreen_window, image=fullscreen_img)
        img_label.pack(expand=True, fill="both")

        # Close on click
        fullscreen_window.bind("<Escape>", lambda e: fullscreen_window.destroy())

        # Keep reference to avoid garbage collection
        img_label.image = fullscreen_img
        
# Function to save the generated thumbnail
def save_thumbnail():
    thumbnail = _generate_thumbnail_sync()
    if thumbnail and saved_directory:
        thumbnail.save(os.path.join(saved_directory, f"{opponent_var.get()}.png"))
        log_message(f"Thumbnail saved successfully\n")

def save_thumbnail_as_psd():
    """Saves the thumbnail as a layered PSD file"""
    global saved_directory
    
    from psd_tools.api.psd_image import PSDImage
    from psd_tools.api.layers import PixelLayer
    from PIL import ImageFont, ImageDraw, Image
    
    if not saved_directory:
        select_save_directory()
        if not saved_directory:  # User cancelled
            return
    
    thumbnail = _generate_thumbnail_sync()
    if not thumbnail:
        log_message("Failed to generate thumbnail for PSD\n")
        return
    
    opponent_name = opponent_var.get()
    psd_path = os.path.join(saved_directory, f"{opponent_name or 'Unnamed'}.psd")
    
    try:
        # Create base PSD
        psd = PSDImage.new(mode="RGBA", size=(1280, 720), color=(0, 0, 0, 0))
        
        # Add background layer
        bg_layer = PixelLayer.frompil(thumbnail.copy(), psd)
        bg_layer.name = "Background"
        psd.append(bg_layer)
        
        # Add text layers
        def create_text_layer(text, position, layer_name, font_size=None):
            """Helper to create text layers with outline"""
            text_img = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
            draw = ImageDraw.Draw(text_img)
            
            font_path = resource_path("assets/HyliaSerif.otf")
            if not os.path.exists(font_path):
                raise FileNotFoundError("Font file missing")
                
            size = font_size if font_size else int(font_size_var.get())
            outline = int(outline_size_var.get())
            font = ImageFont.truetype(font_path, size)
            x, y = position
            
            # Draw outline
            for dx in range(-outline, outline+1):
                for dy in range(-outline, outline+1):
                    draw.text((x+dx, y+dy), text, font=font, fill="black")
            
            # Draw main text
            draw.text(position, text, font=font, fill="white")
            
            layer = PixelLayer.frompil(text_img, psd)
            layer.name = layer_name
            return layer
        
        # Add all text elements
        psd.append(create_text_layer(
            tournament_entry.get(),
            positions["tournament_title"],
            "Tournament Title"
        ))
        
        psd.append(create_text_layer(
            round_entry.get(),
            positions["round_info"],
            "Round Info",
            int(round_font_size_var.get())
        ))
        
        psd.append(create_text_layer(
            link_player_var.get(),
            positions["link_name_P1"] if link_position_var.get() == "P1" else positions["link_name_P2"],
            "Link Player"
        ))
        
        psd.append(create_text_layer(
            opponent_var.get(),
            positions["opponent_name_P2"] if link_position_var.get() == "P1" else positions["opponent_name_P1"],
            "Opponent Name"
        ))
        
        # Save final PSD
        psd.save(psd_path)
        log_message(f"✅ PSD saved: {os.path.basename(psd_path)}\n")
        
    except Exception as e:
        log_message(f"❌ PSD save failed: {str(e)}\n")

#UI elements for the thumbnail tab

# Select Channel Folder
folder_button = tk.Button(center_container, text="Select Link Channel Folder", command=select_link_channel, bg="#444", fg="white")
folder_button.pack(pady=0)
folder_button.config(width=BUTTON_WIDTH)
folder_label = tk.Label(center_container, text="No folder selected", bg="#2e2e2e", fg="white")
folder_label.pack(pady=0)

# Save Directory Label 
save_dir_label = tk.Label(center_container, text="No save directory selected", bg="#2e2e2e", fg="white")
save_dir_label.pack(pady=0)

# === Helper: Populate dropdowns from spreadsheet ===
def populate_dropdowns_from_excel(file_path):
    try:
        df = pd.read_excel(file_path)
        df.columns = df.columns.str.strip().str.lower()

        link_players = df.get("link player", []).dropna().tolist()
        opponents = df.get("opponent", []).dropna().tolist()

        link_player_dropdown["values"] = link_players
        opponent_dropdown["values"] = opponents
    except Exception as e:
        console_output.insert(tk.END, f"Error loading spreadsheet data: {e}\n")
        console_output.see(tk.END)




#Spreadsheet Selector
def select_spreadsheet():
    global selected_file, selected_spreadsheet_path, df
    file_path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx")])
    
    if not file_path:
        return
        
    selected_file = file_path
    selected_spreadsheet_path = file_path
    
    # Update both status labels
    filename = os.path.basename(file_path)
    spreadsheet_status_label_downloader.config(text=f"Spreadsheet Loaded: {filename}", fg="green")
    spreadsheet_status_label.config(text=f"Spreadsheet Loaded: {filename}", fg="green")
    
    populate_dropdowns_from_excel(file_path)

    
    # Save configuration after selecting spreadsheet
    save_config()

spreadsheet_status_label = tk.Label(center_container, text="", bg="#2e2e2e", fg="white")
spreadsheet_status_label.pack(pady=0)    

# Select Spreadsheet button
spreadsheet_button = tk.Button(center_container, text="Select Spreadsheet", command=select_spreadsheet, bg="#444", fg="white")
spreadsheet_button.pack(pady=0)
spreadsheet_button.config(width=BUTTON_WIDTH)

# === Dropdown Variables ===
link_player_var = tk.StringVar()
opponent_var = tk.StringVar()
character_var = tk.StringVar()
link_skin_var = tk.StringVar()
link_position_var = tk.StringVar(value="P1")  # Default to P1


# === Dropdown Widgets ===
link_player_dropdown = ttk.Combobox(center_container, textvariable=link_player_var)
opponent_dropdown = ttk.Combobox(center_container, textvariable=opponent_var)
character_dropdown = ttk.Combobox(center_container, textvariable=character_var)
link_skin_dropdown = ttk.Combobox(center_container, textvariable=link_skin_var)
position_dropdown = ttk.Combobox(center_container, textvariable=link_position_var)
position_dropdown["values"] = ["P1", "P2"]

# === Display Dropdowns and Labels ===
dropdown_fields = [
    ("Link Player:", link_player_dropdown),
    ("Opponent Name:", opponent_dropdown),
    ("Opponent Character:", character_dropdown),
    ("Select Link's Skin:", link_skin_dropdown),
    ("Link Position (P1 or P2):", position_dropdown)
]

for label_text, dropdown in dropdown_fields:
    label = tk.Label(center_container, text=label_text, bg="#2e2e2e", fg="white")
    label.pack(pady=1)
    dropdown.pack(pady=0)
    dropdown.config(width=DROPDOWN_WIDTH)
    
# === Tournament & Round Info Fields ===
tournament_var = tk.StringVar()
round_var = tk.StringVar()

text_fields = [
    ("Tournament Name:", tournament_var),
    ("Round Info:", round_var)
]

for label_text, var in text_fields:
    label = tk.Label(center_container, text=label_text, bg="#2e2e2e", fg="white")
    entry = tk.Entry(center_container, textvariable=var)
    label.pack(pady=1)
    entry.pack(pady=0)
    entry.config(width=ENTRY_WIDTH)

    # Assign to globals for PSD and thumbnail export
    if "Tournament" in label_text:
        tournament_entry = entry
    else:
        round_entry = entry


# Font/Outline Settings 
font_size_var = tk.StringVar(value="50")
outline_size_var = tk.StringVar(value="1")
round_font_size_var = tk.StringVar(value="28")  # For smaller round info text

font_fields = [
    ("Font Size:", font_size_var),
    ("Outline Size:", outline_size_var),
    ("Round Info Font Size:", round_font_size_var)
]

for label_text, var in font_fields:
    label = tk.Label(center_container, text=label_text, bg="#2e2e2e", fg="white")
    entry = tk.Entry(center_container, textvariable=var)
    label.pack(pady=1)
    entry.pack(pady=0)
    entry.config(width=ENTRY_WIDTH)




# Buttons section
button_frame = ttk.Frame(center_container, style="TFrame")
button_frame.pack(pady=0)

# Update Thumbnail (updates within UI)
update_button = tk.Button(center_container, text="Update Preview", command=generate_thumbnail, bg="#444", fg="white")
update_button.pack(pady=1)
update_button.config(width=BUTTON_WIDTH)

# Fullscreen Preview Button
fullscreen_button = tk.Button(center_container, text="Preview Fullscreen", command=preview_fullscreen, bg="#444", fg="white")
fullscreen_button.pack(pady=1)
fullscreen_button.config(width=BUTTON_WIDTH)

# Save Buttons
save_button = tk.Button(center_container, text="Save PNG", command=save_thumbnail, bg="#444", fg="white")
save_button.pack(pady=1)
save_button.config(width=BUTTON_WIDTH)

psd_button = tk.Button(center_container, text="Save PSD", command=save_thumbnail_as_psd, bg="#444", fg="white")
psd_button.pack(pady=1)
psd_button.config(width=BUTTON_WIDTH)

# Make sure to maintain the original binding for character_dropdown
def update_character_selection(event):
    selected_character = character_dropdown.get()  # Get the selected character
    character_var.set(selected_character)  # Ensure character_var updates properly

character_dropdown.bind("<<ComboboxSelected>>", update_character_selection)
opponent_dropdown.bind("<<ComboboxSelected>>", update_character_selection)

#Console Output 
console_scroll = ttk.Scrollbar(console_frame)
console_output = tk.Text(
    console_frame, 
    wrap="word", 
    height=20, 
    width=80, 
    bg="#1e1e1e", 
    fg="white",
    yscrollcommand=console_scroll.set
)
console_output.pack(side=tk.LEFT, expand=True, fill="both", padx=10, pady=10)
console_scroll.pack(side=tk.RIGHT, fill="y")
console_scroll.config(command=console_output.yview)

# Gura PNG Easter Egg Trigger
def on_gura_click(event):
    show_epic_tab()

try:
    image_path = resource_path("assets/gawr_gura.png")
    image = Image.open(image_path)
    image = image.resize((100, 100), Image.Resampling.LANCZOS)
    photo = ImageTk.PhotoImage(image)
    image_label = tk.Label(downloader_frame, image=photo, bg="#2e2e2e", cursor="hand2")
    image_label.image = photo
    image_label.pack(pady=10)
    image_label.bind("<Button-1>", on_gura_click)  # 🔥 Click to open hidden tab
except Exception as e:
    print("Error loading image:", e)


# Button Width
DOWNLOADER_BUTTON_WIDTH = 30  

# SpreadSheet Select Label
spreadsheet_status_label_downloader = tk.Label(downloader_frame, text="No spreadsheet loaded", bg="#2e2e2e", fg="white")
spreadsheet_status_label_downloader.pack(pady=0)
select_button = tk.Button(downloader_frame, text="Select Spreadsheet", command=select_spreadsheet, bg="#444", fg="white")
select_button.config(width=DOWNLOADER_BUTTON_WIDTH)
select_button.pack(pady=0)
select_dir_button = tk.Button(downloader_frame, text="Set Download Directory", command=select_directory, bg="#444", fg="white")
select_dir_button.config(width=DOWNLOADER_BUTTON_WIDTH)
select_dir_button.pack(pady=0)

# Buttons container frame for download/cancel
download_buttons_frame = ttk.Frame(downloader_frame, style="TFrame")
download_buttons_frame.pack(pady=5)

download_button = tk.Button(download_buttons_frame, text="Start Download", command=start_download, bg="#444", fg="white")
download_button.pack(side=tk.LEFT, padx=1)
download_button.config(width=DOWNLOADER_BUTTON_WIDTH // 2)

# New Cancel button
cancel_button = tk.Button(download_buttons_frame, text="Cancel Download", command=cancel_download, bg="#444", fg="white", state=tk.DISABLED)
cancel_button.pack(side=tk.LEFT, padx=1)
cancel_button.config(width=DOWNLOADER_BUTTON_WIDTH // 2)

progress_bar = ttk.Progressbar(downloader_frame, orient="horizontal", length=300, mode="determinate")
progress_bar.pack_forget()

progress_label = tk.Label(downloader_frame, text="Waiting...", bg="#2e2e2e", fg="white")
progress_label.pack(pady=5)


# Create a frame for the footer that spans across all tabs
footer_frame = ttk.Frame(root, style="TFrame")
footer_frame.pack(side="bottom", fill="x", pady=5)

# Secret tab (initially hidden)
epic_tab = ttk.Frame(notebook, style="TFrame")
epic_tab_loaded = False

def show_epic_tab():
    global epic_tab_loaded

    if not epic_tab_loaded:
        notebook.add(epic_tab, text="🌀 Awesome Fucking Tien Edit")

        video_label = Label(epic_tab, bg="#000")
        video_label.pack(expand=True, fill="both", padx=10, pady=10)

        def play_epic_video():
            from tkvideo import tkvideo
            from playsound import playsound

            video_path = resource_path("assets/edit.mp4")
            audio_path = resource_path("assets/edit_audio.mp3")

            player = VideoPlayer(video_path, video_label, loop=0, size=(640, 360))
            player.play()

            threading.Thread(target=play_audio, args=(audio_path,), daemon=True).start()

        play_button = tk.Button(epic_tab, text="▶ Play Awesome Edit", command=play_epic_video, bg="#444", fg="white")
        play_button.pack(pady=10)

        epic_tab_loaded = True

    notebook.select(epic_tab)


# Credit Label
credit_label = tk.Label(
    footer_frame, 
    text=f"Made by Ozzy :)\nVersion {VERSION}", 
    font=("Arial", 8), 
    bg="#2e2e2e", 
    fg="#7a9fb1"  # Subtle blue-grey color
)
credit_label.pack(side="bottom", pady=5)


# Enable smooth scrolling with mouse wheel
def on_mouse_wheel(event):
    thumbnail_canvas.yview_scroll(-1 * (event.delta // 120), "units")

# Bind mouse wheel scrolling to the canvas
thumbnail_canvas.bind_all("<MouseWheel>", on_mouse_wheel)  # Windows & MacOS

# Load saved configuration at startup
load_config()


root.mainloop()
