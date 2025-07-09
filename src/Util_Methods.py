import os
import json
from typing import Dict, Any, Optional, Generator, List, Tuple


def _save_json(data: Any, filename: str):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"💾 Saved {os.path.basename(filename)} to {os.path.dirname(filename)}")
