import json
import os
from Curiosa_API import CuriosaAPI
from Util_Debug import DebugDisplay
import requests
from typing import Dict, Any, Optional, Generator, List, Tuple
from Util_IO import _save_json
import time
from Card import Card
from Util_IO import SORCERY_DATA_PATH, DATA_PATH


class SorceryAPI:
    all_cards: List[Dict[str, Any]] = []
    have_loaded_cards = False
    online_card_count = -1 
    
    @staticmethod
    def fetch_all_cards() -> List[Dict[str, Any]]:
        url = "https://api.sorcerytcg.com/api/cards"
        headers = {
            "accept": "*/*"
        }

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # Raise error for bad status codes
            if response.ok:
                try:
                    data = response.json()
                    
                    if not isinstance(data, list):
                        print("❌ Unexpected collection format from sorceryAPI")
                        return []
                    
                    return data
                except Exception as e:
                    print(f"❌ Failed to fetch cards from sorceryAPI: {e}")
            else:
                print(f"❌ Folder fetch failed: {response.status_code}")
                print(response.text)
            return []
        except requests.RequestException as e:
            print(f"Error fetching cards from sorceryAPI: {e}")
        return []
        
    @staticmethod
    def rebuild_card_list(online_cards: List[Dict[str, Any]]):
        if not online_cards:
            online_cards = SorceryAPI.fetch_all_cards()
            print(f"🌐 Downloaded {len(online_cards)} cards.")
        print("🔄 Rebuilding card list...")
        SorceryAPI.all_cards.clear()
        SorceryAPI.all_cards.extend(online_cards)
        _save_json(SorceryAPI.all_cards, SORCERY_DATA_PATH)
        
        print("✅ Local Sorcery card list is up to date.")
        SorceryAPI.have_loaded_cards = True
        
    @staticmethod  
    def check_card_list():
        os.makedirs(DATA_PATH, exist_ok=True)
        
        if os.path.exists(SORCERY_DATA_PATH):
            with open(SORCERY_DATA_PATH, "r", encoding="utf-8") as f:
                SorceryAPI.all_cards = json.load(f)
            print(f"📁 Loaded {len(SorceryAPI.all_cards)} cards from file.")
        else:
            print("🆕 No card file found.")

        try:
            online_cards = SorceryAPI.fetch_all_cards()
            SorceryAPI.online_card_count = len(online_cards)
            print(f"🌐 Online card count: {len(online_cards)}")
        except Exception as e:
            print(f"❌ Failed to fetch online cards: {e}")
            return

        if len(SorceryAPI.all_cards) != len(online_cards):
            print(f"🔄 Card count mismatch. Got {len(SorceryAPI.all_cards)} cards, expected {len(online_cards)}.")
            SorceryAPI.rebuild_card_list(online_cards)
        else:
            print("✅ Local Sorcery card list is up to date.")
            SorceryAPI.have_loaded_cards = True
    
    def __init__(self):
        return
      
      
SorceryAPI.check_card_list()