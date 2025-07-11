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
DECK_PATH = "data/Decks"
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


def open_threadsafe_dialog(target_function: Callable, *args, **kwargs):
    q = Queue()
    p = Process(target=target_function, args=(q, *args), kwargs=kwargs)
    p.start()
    p.join()
    return q.get() if not q.empty() else None
