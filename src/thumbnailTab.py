import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, Toplevel
import os
from threading import Thread
from PIL import Image, ImageDraw, ImageTk
from helperFuncs import load_image, get_font
from customtkinter import CTkImage
from psd_tools.api.psd_image import PSDImage
from psd_tools.api.layers import PixelLayer
import pandas as pd
import random

class ThumbnailTab:
    def __init__(self, parent, parent_tab):
        #Yoy: this entire init is just setting up a shit ton of UI elements
        self.parent = parent
        self.frame = ctk.CTkFrame(parent_tab)
        self.frame.pack(fill="both", expand=True, padx=12, pady=12)

        scrollable = ctk.CTkScrollableFrame(self.frame)
        scrollable.pack(expand=True, fill="both", padx=6, pady=6)

        self.preview_canvas = ctk.CTkLabel(scrollable, text="", width=640, height=360)
        self.preview_canvas.pack(pady=10)

        center_container = ctk.CTkFrame(scrollable)
        center_container.pack(expand=True, padx=20, pady=6)

        BUTTON_WIDTH = 180
        DROPDOWN_WIDTH = 220
        ENTRY_WIDTH = 220

        self.positions = {
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

        # === UI Controls for thumbnail tab ===
        folder_button = ctk.CTkButton(center_container, text="Select Link Channel Folder", command=lambda: self.select_link_channel(), width=BUTTON_WIDTH)
        folder_button.pack(pady=6)
        self.folder_label = ctk.CTkLabel(center_container, text="No folder selected")
        self.folder_label.pack(pady=2)
        self.save_dir_label = ctk.CTkLabel(center_container, text="No save directory selected")
        self.save_dir_label.pack(pady=2)

        self.status_label = ctk.CTkLabel(center_container, text="")
        self.status_label.pack(pady=4)
        spreadsheet_button = ctk.CTkButton(center_container, text="Select Spreadsheet", command=self.parent.select_spreadsheet, width=BUTTON_WIDTH)
        spreadsheet_button.pack(pady=4)

        # Dropdown variables & widgets
        self.link_player_var = tk.StringVar()
        self.opponent_var = tk.StringVar()
        self.character_var = tk.StringVar()
        self.link_skin_var = tk.StringVar()
        self.link_position_var = tk.StringVar(value="P1")
        self.link_player_dropdown = ctk.CTkComboBox(center_container, variable=self.link_player_var, values=[])
        self.opponent_dropdown = ctk.CTkComboBox(center_container, variable=self.opponent_var, values=[])
        self.character_dropdown = ctk.CTkComboBox(center_container, variable=self.character_var, values=[])
        self.link_skin_dropdown = ctk.CTkComboBox(center_container, variable=self.link_skin_var, values=[])
        self.position_dropdown = ctk.CTkComboBox(center_container, variable=self.link_position_var, values=["P1", "P2"])

        dropdown_fields = [
            ("Link Player:", self.link_player_dropdown),
            ("Opponent Name:", self.opponent_dropdown),
            ("Opponent Character:", self.character_dropdown),
            ("Select Link's Skin:", self.link_skin_dropdown),
            ("Link Position (P1 or P2):", self.position_dropdown)
        ]

        for label_text, dropdown in dropdown_fields:
            label = ctk.CTkLabel(center_container, text=label_text)
            label.pack(pady=2)
            dropdown.pack(pady=2)
            dropdown.configure(width=DROPDOWN_WIDTH)

        # Tournament & round entries
        tournament_var = tk.StringVar()
        round_var = tk.StringVar()
        self.tournament_entry = None
        self.round_entry = None

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
                self.tournament_entry = entry
            else:
                self.round_entry = entry

        # Font fields
        self.font_size_var = tk.StringVar(value="50")
        self.outline_size_var = tk.StringVar(value="1")
        self.round_font_size_var = tk.StringVar(value="28")

        font_fields = [
            ("Font Size:", self.font_size_var),
            ("Outline Size:", self.outline_size_var),
            ("Round Info Font Size:", self.round_font_size_var)
        ]

        for label_text, var in font_fields:
            label = ctk.CTkLabel(center_container, text=label_text)
            entry = ctk.CTkEntry(center_container, textvariable=var, width=ENTRY_WIDTH)
            label.pack(pady=2)
            entry.pack(pady=2)

        # Buttons
        update_button = ctk.CTkButton(center_container, text="Update Preview", command=self.generate_thumbnail, width=BUTTON_WIDTH)
        update_button.pack(pady=4)
        fullscreen_button = ctk.CTkButton(center_container, text="Preview Fullscreen", command=self.preview_fullscreen, width=BUTTON_WIDTH)
        fullscreen_button.pack(pady=4)
        save_button = ctk.CTkButton(center_container, text="Save PNG", command=self.save_thumbnail, width=BUTTON_WIDTH)
        save_button.pack(pady=4)
        psd_button = ctk.CTkButton(center_container, text="Save PSD", command=self.save_thumbnail_as_psd, width=BUTTON_WIDTH)
        psd_button.pack(pady=4)

        #Yoy: why does opponent_dropdown have the same bind? update_character_selection only reads from character_dropdown and updates character_var
        self.character_dropdown.bind("<<ComboboxSelected>>", self.update_character_selection)
        self.opponent_dropdown.bind("<<ComboboxSelected>>", self.update_character_selection)

        self.saved_directory = None
        self.link_channel_path = None
        self.update_settings()

    #Recommendation #4: this calling of update_settings was just to mimic your previous structure. just read the vars directly where needed. applys to all instances of this function
    def update_settings(self):
        self.s = {
            "tournament": self.tournament_entry.get(),
            "round": self.round_entry.get(),
            "link_player": self.link_player_var.get(),
            "opponent_player": self.opponent_var.get(),
            "link_skin": self.link_skin_var.get(),
            "opponent_character": self.character_var.get(),
            "link_pos": self.link_position_var.get(),
            "font_size": int(self.font_size_var.get()),
            "round_font_size": int(self.round_font_size_var.get()),
            "outline": int(self.outline_size_var.get()),
            "background_id": random.randint(1, 5) #recommendation #6: let the user select background
        }

    def select_link_channel(self):
        path = filedialog.askdirectory()
        if path:
            self.link_channel_path = path
            self.folder_label.configure(text=f"Selected: {path}")
            self.update_character_dropdown()
            self.update_link_alt_dropdown()
            self.parent.save_config()

    def update_character_dropdown(self):
        if not self.link_channel_path:
            return
        #recommendation #5: paths are case sensitive on linux
        #i got an error when trying to open Rest of cast because you gave me rest of cast
        char_folder = os.path.join(self.link_channel_path, "Transparent cast", "Rest of cast")
        if not os.path.exists(char_folder):
            self.parent.log(f"Character folder not found: {char_folder}\n")
            return
        #Yoy: this is not sorted. dropdown menu was all jumbled. left as an exercise for the reader. very simple fix
        characters = [f.replace(".png", "") for f in os.listdir(char_folder) if f.endswith(".png")]
        self.character_dropdown.configure(values=characters)


    def update_link_alt_dropdown(self):
        if not self.link_channel_path:
            return
        link_alt_folder = os.path.join(self.link_channel_path, "Transparent cast", "Link alts")
        if not os.path.exists(link_alt_folder):
            return
        #Yoy: this is not sorted. dropdown menu was all jumbled. left as an exercise for the reader. very simple fix
        link_alts = [f.replace(".png", "") for f in os.listdir(link_alt_folder) if f.endswith(".png")]
        self.link_skin_dropdown.configure(values=link_alts)

    def generate_thumbnail(self):
        #recommendation #3: add a guard here to prevent multiple threads from being spawned
        #it gets generated so fast that it's probably not an issue but still
        Thread(target=self._generate_thumbnail_async, daemon=True).start()

    def _generate_thumbnail_async(self):
        try:
            self.update_settings() 
            img = self.render_preview()
            self.update_preview(img)
        except Exception as e:
            self.parent.log(f"Thumbnail Error: {e}\n")

    def render_preview(self):
        self.update_settings()
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
    
    def update_preview(self, thumbnail):
        preview_w = 640
        preview_h = 360
        thumbnail_resized = thumbnail.resize((preview_w, preview_h), Image.Resampling.LANCZOS)

        # Create CTkImage (pass PIL.Image directly). CTkImage will handle DPI scaling.
        ctk_preview = CTkImage(light_image=thumbnail_resized, dark_image=thumbnail_resized, size=(preview_w, preview_h))

        # Assign to label
        self.preview_canvas.configure(image=ctk_preview, text="")
        self.preview_canvas._image = ctk_preview
    
    def load_background(self):
        path = os.path.join(self.link_channel_path, "Background layouts", f"BG {self.s['background_id']}.png")
        return load_image(path).resize((1280, 720), Image.Resampling.LANCZOS)
    
    #Yoy: since you said you wanted to extend this to any character later, you should make a folder for every character with all their alts and load from there
    #then get rid of the dedicated link alt folder and link hardcoded stuff. this would also let you make the code for both opponents identical
    def load_link(self):
        name = self.s["link_skin"]
        path = os.path.join(self.link_channel_path, "Transparent cast", "Link alts", f"{name}.png")
        img = load_image(path)
        if self.s["link_pos"] == "P2":
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        return img
    
    def load_opponent(self):
        name = self.s["opponent_character"]
        path = os.path.join(self.link_channel_path, "Transparent cast", "Rest of cast", f"{name}.png")
        img = load_image(path)
        if self.s["link_pos"] == "P1":
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        return img
    
    def get_positions(self):
        link_pos = (self.positions["link_center_P1"] if self.s["link_pos"] == "P1" else self.positions["link_center_P2"])
        opp_pos = (self.positions["opponent_center_P2"] if self.s["link_pos"] == "P1" else self.positions["opponent_center_P1"])
        link_text_pos = (self.positions["link_name_P1"] if self.s["link_pos"] == "P1" else self.positions["link_name_P2"])
        opp_text_pos = (self.positions["opponent_name_P2"] if self.s["link_pos"] == "P1" else self.positions["opponent_name_P1"])
        return {
            "link_img": link_pos,
            "opp_img": opp_pos,
            "link_text": link_text_pos,
            "opp_text": opp_text_pos,
            "tournament_text": self.positions["tournament_title"],
            "round_text": self.positions["round_info"],
        }
    
    def draw_text(self, base, pos, text, size, outline):
        font = get_font(size)
        draw = ImageDraw.Draw(base)
        x, y = pos
        for dx in range(-outline, outline + 1):
            for dy in range(-outline, outline + 1):
                draw.text((x + dx, y + dy), text, font=font, fill="black")
        draw.text(pos, text, font=font, fill="white")

    def preview_fullscreen(self):
        # Generate thumbnail synchronously
        thumbnail = self.render_preview()
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
                self.parent.log(f"Fullscreen preview failed: {e}\n")
                fullscreen.destroy()
                return

        fullscreen.bind("<Escape>", lambda e: fullscreen.destroy())
    
    def save_thumbnail(self):
        if not self.saved_directory:
            self.select_save_directory()
            if not self.saved_directory:
                return

        thumbnail = self.render_preview()
        if thumbnail and self.saved_directory:
            try:
                out = os.path.join(self.saved_directory, f"{self.opponent_var.get() or 'thumbnail'}.png") #recommendation #7: have file name be more unique or let user specify
                thumbnail.save(out)
                self.parent.log(f"Thumbnail saved successfully: {out}\n")
            except Exception as e:
                self.parent.log(f"Failed saving PNG: {e}\n")
        else:
            self.parent.log("No save directory selected.\n")

    def save_thumbnail_as_psd(self):
        if not self.saved_directory:
            self.select_save_directory()
            if not self.saved_directory:
                return
        try:
            self.update_settings()
            layers = self.render_layers()
            psd = PSDImage.new(mode="RGBA", size=(1280,720))
            bg_layer = PixelLayer.frompil(layers['background'], psd); bg_layer.name="Background"; psd.append(bg_layer)
            link_layer = PixelLayer.frompil(layers['link'], psd); link_layer.name="Link"; psd.append(link_layer)
            opp_layer = PixelLayer.frompil(layers['opponent'], psd); opp_layer.name="Opponent"; psd.append(opp_layer)
            for name, img in layers['text_layers']:
                L = PixelLayer.frompil(img, psd); L.name = name; psd.append(L)
            opponent_name = self.opponent_var.get() or 'unnamed'
            out_path = os.path.join(self.saved_directory, f"{opponent_name}.psd") #recommendation #7: have file name be more unique or let user specify
            psd.save(out_path)
            self.parent.log(f"✅ PSD saved: {os.path.basename(out_path)}\n")
        except Exception as e:
            self.parent.log(f"❌ PSD save failed: {e}\n")

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
    
    def select_save_directory(self):
        path = filedialog.askdirectory()
        if path:
            self.saved_directory = path
            self.save_dir_label.configure(text=f"Save to: {path}")
            self.parent.save_config()

    def update_character_selection(self, event=None):
        selected_character = self.character_dropdown.get()
        self.character_var.set(selected_character)

    # Populate dropdowns from spreadsheet (uses cached load)
    def populate_dropdowns_from_excel(self, file_path):
        try:
            df = self.parent.load_spreadsheet_cached(file_path)
            df.columns = df.columns.str.strip().str.lower()
            link_players = df.get("link player", pd.Series()).dropna().tolist() if "link player" in df.columns else []
            opponents = df.get("opponent", pd.Series()).dropna().tolist() if "opponent" in df.columns else []
            self.link_player_dropdown.configure(values=link_players)
            self.opponent_dropdown.configure(values=opponents)
        except Exception as e:
            self.parent.log(f"Error loading spreadsheet data: {e}\n")