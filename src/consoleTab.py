from queue import Queue
import customtkinter as ctk
import time
from threading import Thread

#Yoy: buffers logs then updates the textbox 10 times per second
#honestly probably doesn't even need to be throttled, just did it because that's what you had before
#functions completely differently from before and tbh i already forgot how you did it
class ConsoleTab:
    def __init__(self, parent):
        self.frame = ctk.CTkFrame(parent)
        self.frame.pack(fill="both", expand=True)

        self.textbox = ctk.CTkTextbox(self.frame, wrap="word")
        self.textbox.pack(fill="both", expand=True, padx=10, pady=10)

        self.log_buffer = Queue()
        self._log_thread = Thread(target=self._log_loop, daemon=True)
        self._log_thread.start()

    def log(self, message):
        try:
            self.log_buffer.put(str(message))
        except Exception as e:
            print(f"Logging error: {e}")

    def _log_loop(self):
        while True:
            concatLog = ""
            while not self.log_buffer.empty():
                concatLog += self.log_buffer.get()
            if concatLog:
                self.textbox.insert("end", concatLog)
                self.textbox.see("end")
            time.sleep(0.1)