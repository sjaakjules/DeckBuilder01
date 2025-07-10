import json
import os
from Curiosa_API import CuriosaAPI
from Util_Debug import DebugDisplay
import requests
from typing import Dict, Any, Optional, Generator, List, Tuple
from Util_Methods import _save_json
import time
from CardInfo import CardInfo

SORCERY_API = "https://api.sorcery.com/cards"  # Replace if needed
DATA_PATH = "data"
SORCERY_DATA_PATH = os.path.join(DATA_PATH, "Sorcery_CardData.json")
CARD_DATA_PATH = os.path.join(DATA_PATH, "CardData.json")
ALL_CARD_DATA_PATH = os.path.join(DATA_PATH, "All_CardData.json")


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
      
        
class CardData:
    def __init__(self):
        self.cards: Dict[str, CardInfo] = {}
        self.card_data_lookup: Dict[str, Dict[str, Any]] = {}
        self.CardData: List[Dict[str, Any]] = []

        # Wait until API data is loaded
        while not SorceryAPI.have_loaded_cards:
            time.sleep(1)
        while not CuriosaAPI.have_loaded_cards:
            time.sleep(1)

        sorcery_cards = SorceryAPI.all_cards
        curiosa_cards = CuriosaAPI.all_cards

        # --- Load or build card data file ---
        if os.path.exists(CARD_DATA_PATH):
            with open(CARD_DATA_PATH, "r", encoding="utf-8") as f:
                self.CardData = json.load(f)
        else:
            self.CardData = []

        if os.path.exists(ALL_CARD_DATA_PATH):
            with open(ALL_CARD_DATA_PATH, "r", encoding="utf-8") as f:
                self.card_data_lookup = json.load(f)
        else:
            self.card_data_lookup = {}

        print(f"📁 SorceryAPI cards: {len(sorcery_cards)}, CuriosaAPI cards: {len(curiosa_cards)}")
        print(f"📁 CardData cards: {len(self.CardData)}, All cards: {len(self.card_data_lookup)}")

        # --- If all datasets align in length, use file ---
        if (len(sorcery_cards) == len(curiosa_cards) == len(self.CardData) == len(self.card_data_lookup)):
            print("✅ Card data files are up to date, loading CardInfo objects...")
            self.cards = {cd["name"]: CardInfo.from_card_data(cd) for cd in self.CardData}
        else:
            print("🛠️ Data mismatch or missing files, rebuilding card data with latest API data...")
            self.CardData = self.build_card_data(sorcery_cards, curiosa_cards)
            _save_json(self.card_data_lookup, ALL_CARD_DATA_PATH)
            _save_json(self.CardData, CARD_DATA_PATH)

    def build_card_data(self, sorcery_data: List[Dict[str, Any]], curiosa_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Build lookup from curiosa_data by name
        curiosa_lookup = {card["name"]: card for card in curiosa_data}
        card_data_list = []

        for s_card in sorcery_data:
            name = s_card.get("name")
            if not name:
                continue
            c_card = curiosa_lookup.get(name)
            if not c_card:
                print(f"❌ Missing curiosa data for {name}")
                continue

            guardian = s_card.get("guardian", {})
            thresholds = guardian.get("thresholds", {})

            elements_list = [e.strip() for e in s_card.get("elements", "").split(",") if e.strip()]
            subtypes_list = [st.strip() for st in s_card.get("subTypes", "").split(",") if st.strip()]

            flavor_texts = set()
            type_texts = set()
            artists = set()
            sets = set()

            for s in s_card.get("sets", []):
                sets.add(s.get("name", ""))
                for v in s.get("variants", []):
                    if v.get("flavorText"):
                        flavor_texts.add(v["flavorText"])
                    if v.get("typeText"):
                        type_texts.add(v["typeText"])
                    if v.get("artist"):
                        artists.add(v["artist"])

            card_data = {
                "name": name,
                "slug": c_card.get("slug"),
                "hotscore": c_card.get("hotscore"),
                "img_url": f"https://card.cards.army/cards/{c_card.get('slug')}.webp",
                "rarity": guardian.get("rarity"),
                "type": guardian.get("type"),
                "subTypes": subtypes_list,
                "elements": elements_list,
                "elements_count": len(set(elements_list)),
                "cost": guardian.get("cost"),
                "thresholds": thresholds,
                "attack": guardian.get("attack"),
                "defence": guardian.get("defence"),
                "life": guardian.get("life"),
                "rulesText": guardian.get("rulesText"),
                "sets": list(sets),
                "flavorText": list(flavor_texts),
                "typeText": list(type_texts),
                "artist": list(artists)
            }

            card_data_list.append(card_data)
            self.card_data_lookup[name] = {
                "sorcery_data": s_card,
                "curiosa_data": c_card,
                "card_data": card_data
            }

            card = CardInfo.from_card_data(card_data)
            self.cards[card.name] = card
            
        return card_data_list


SorceryAPI.check_card_list()