import os
import json
from typing import Dict, Any, Optional, Generator, List, Tuple, Callable
import tkinter.filedialog
from multiprocessing import Process, Queue

SORCERY_API = "https://api.sorcery.com/cards"
CURIOSA_API = "https://curiosa.io/api/trpc"
DATA_PATH = "data"
TMP_PATH = "tmp"
SORCERY_DATA_PATH = os.path.join(DATA_PATH, "Sorcery_CardData.json")
CURIOSA_DATA_PATH = os.path.join(DATA_PATH, "Curiosa_CardData.json")
BASE_DATA_PATH = os.path.join(DATA_PATH, "Base_CardData.json")
ALL_CARD_DATA_PATH = os.path.join(DATA_PATH, "All_CardData.json")

CARD_ASSETS_PATH = "assets/Cards"
DECK_PATH = "data/decks"
COLLECTION_PATH = "data/Collection"

        
def _save_json(data: Any, filename: str):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"💾 Saved {os.path.basename(filename)} to {os.path.dirname(filename)}")


def _save_text(data: str, filename: str):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w", encoding="utf-8") as f:
        f.write(data)
    print(f"💾 Saved {os.path.basename(filename)} to {os.path.dirname(filename)}")


def select_file(q, title="Select File", filetypes=None):
    if filetypes is None:
        filetypes = [("All files", "*.*")]
    path = tkinter.filedialog.askopenfilename(
        title=title,
        filetypes=filetypes
    )
    q.put(path)


def ask_string(q, title="Input", prompt="Enter text:"):
    import tkinter as tk
    from tkinter.simpledialog import askstring
    root = tk.Tk()
    root.withdraw()
    result = askstring(title, prompt)
    q.put(result)


def ask_choice(q, title="Choose Option", prompt="Select an option:", options=None):
    import tkinter as tk
    from tkinter import simpledialog
    
    if options is None:
        options = ["Option 1", "Option 2"]
    
    root = tk.Tk()
    root.withdraw()
    
    # Create a simple dialog with buttons for each option
    dialog = tk.Toplevel(root)
    dialog.title(title)
    dialog.geometry("300x150")
    dialog.resizable(False, False)
    dialog.transient(root)
    dialog.grab_set()
    
    # Center the dialog
    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() // 2) - (300 // 2)
    y = (dialog.winfo_screenheight() // 2) - (150 // 2)
    dialog.geometry(f"300x150+{x}+{y}")
    
    result = [None]  # Use list to store result from callback
    
    def select_option(option):
        result[0] = option
        dialog.destroy()
        root.destroy()
    
    # Add prompt label
    label = tk.Label(dialog, text=prompt, wraplength=280)
    label.pack(pady=10)
    
    # Add buttons for each option
    for option in options:
        btn = tk.Button(dialog, text=option, command=lambda opt=option: select_option(opt))
        btn.pack(pady=5, padx=20, fill='x')
    
    # Wait for dialog to close
    dialog.wait_window()
    q.put(result[0])


def open_threadsafe_dialog(target_function: Callable, *args, **kwargs):
    q = Queue()
    p = Process(target=target_function, args=(q, *args), kwargs=kwargs)
    p.start()
    p.join()
    return q.get() if not q.empty() else None
