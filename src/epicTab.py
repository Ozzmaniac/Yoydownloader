import customtkinter as ctk
from helperFuncs import resource_path
from tkvideo import tkvideo as VideoPlayer
from threading import Thread
from playsound import playsound as play_audio

#couldn't get this to work on my machine, but i didn't change anything so i assume it still works
class EpicTab:
    def __init__(self, parent):
        self.frame = ctk.CTkFrame(parent)
        self.frame.pack(fill="both", expand=True, padx=12, pady=12)

        self.video_label = ctk.CTkLabel(self.frame, text="")
        self.video_label.pack(expand=True, fill="both", padx=10, pady=10)

        play_button = ctk.CTkButton(self.frame, text="▶ Play Awesome Edit", command=self.play_epic_video)
        play_button.pack(pady=10)

    def play_epic_video(self):
        video_path = resource_path("assets/edit.mp4")
        audio_path = resource_path("assets/edit_audio.mp3")
        player = VideoPlayer(video_path, self.video_label._label, loop=0, size=(640, 360))
        player.play()
        Thread(target=play_audio, args=(audio_path,), daemon=True).start()
