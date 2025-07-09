import os
import sys
import re
import time
import json
import requests
from typing import Dict, Any, Optional, Generator, List, Tuple
from urllib.parse import urlencode, quote
from playwright.sync_api import sync_playwright
import random
from queue import Queue, Empty
import threading
from Util_Methods import _save_json

# --- CONFIG ---
BASE_URL = "https://curiosa.io/api/trpc"
DATA_PATH = "data"
TMP_PATH = "tmp"
CARD_DATA_PATH = os.path.join(DATA_PATH, "Curiosa_CardData.json")


class CuriosaAPI:
    buildID: Optional[str] = None  # Static class variable
    card_queue = Queue()
    all_cards: List[Dict[str, Any]] = []
    thread = None
    online_card_count = -1 
    have_loaded_cards = False
        
    @staticmethod
    def fetch_build_id() -> str | None:
        try:
            response = requests.get("https://curiosa.io", headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()

            # Look for a line like: /_next/static/<build_id>/_buildManifest.js
            match = re.search(r"/_next/static/([^/]+)/_buildManifest\.js", response.text)
            if match:
                build_id = match.group(1)
                print(f"✅ Found buildId: {build_id}")
                return build_id
            else:
                print("❌ buildId not found in homepage HTML.")
                return None
        except Exception as e:
            print(f"❌ Error fetching buildId: {e}")
            return None
        
    @staticmethod
    def _headerInfo(referer_path: str) -> Dict[str, str]:
        headers = {
            'authority': 'curiosa.io',
            'accept': '*/*',
            'accept-language': 'en-AU,en;q=0.9',
            'content-type': 'application/json',
            'x-trpc-source': 'nextjs-react',
            'user-agent': 'Mozilla/5.0',
            'origin': 'https://curiosa.io',
            'referer': f'https://curiosa.io{referer_path}'
        }
        if CuriosaAPI.buildID:
            headers['x-build-id'] = CuriosaAPI.buildID
        else:
            CuriosaAPI.buildID = CuriosaAPI.fetch_build_id()
            if CuriosaAPI.buildID:
                headers['x-build-id'] = CuriosaAPI.buildID
            else:
                headers['x-build-id'] = 'a5081202dd6bb8f53d26358febc079b618a142e8'
        return headers
    
    @staticmethod
    def fetch_curiosa_deck(deck_id: str) -> Optional[Dict[str, Any]]:
        deck_id = CuriosaAPI._extract_deck_id(deck_id)
        query = {
            str(i): {"json": {"id": deck_id}} for i in range(4)
        }

        url = (
            "https://curiosa.io/api/trpc/"
            "deck.getDecklistById,deck.getAvatarById,"
            "deck.getSideboardById,deck.getMaybeboardById"
            f"?batch=1&input={quote(json.dumps(query))}"
        )

        response = requests.get(url, headers=CuriosaAPI._headerInfo(f"/decks/{deck_id}"))
        if response.ok:
            try:
                results = response.json()
                if not isinstance(results, list) or len(results) != 4:
                    print("❌ Unexpected deck result format")
                    return None

                return {
                    "mainboard": results[0]["result"]["data"]["json"],
                    "avatar": results[1]["result"]["data"]["json"],
                    "sideboard": results[2]["result"]["data"]["json"],
                    "maybeboard": results[3]["result"]["data"]["json"]
                }

            except Exception as e:
                print(f"❌ Failed to parse deck {deck_id}: {e}")
        else:
            print(f"❌ Deck ({deck_id}) fetch failed: {response.status_code}")
            print(response.text)

        return None
    
    @staticmethod
    def _extract_deck_id(url_or_id: str) -> str:
        return url_or_id.rstrip('/').split('/')[-1] if '/' in url_or_id else url_or_id

    @staticmethod
    def fetch_total_card_count() -> int:
        query = {
            "0": {"json": {"query": "", "set": "*", "filters": []}}
        }
        
        url = (
            "https://curiosa.io/api/trpc/"
            "card.count"
            f"?batch=1&input={quote(json.dumps(query))}"
        )
        
        response = requests.get(url, headers=CuriosaAPI._headerInfo("/cards"))
        if response.ok:
            try:
                data = response.json()
                
                if not isinstance(data, list):
                    print("❌ Unexpected card count format")
                    return -1
                print(data)
                return int(data[0]["result"]["data"]["json"])
            except Exception as e:
                print(f"❌ Failed to parse card count JSON: {e}")
        else:
            print(f"❌ card count fetch failed: {response.status_code}")
            print(response.text)
        return -1

    @staticmethod
    def fetch_nth_of_i_cards(n: int, i: int) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str], Optional[str]]:
        query = {
            "0": {"json": {"query": "", "sort": "relevance", "set": "*",
                           "filters": [], "limit": i, "variantLimit": False,
                           "cursor": n * i, "direction": "forward"}
                  }
        }
        url = (
            "https://curiosa.io/api/trpc/"
            "card.search"
            f"?batch=1&input={quote(json.dumps(query))}"
        )
        
        response = requests.get(url, headers=CuriosaAPI._headerInfo("/cards"))
        if response.ok:
            try:
                data = response.json()
                print()
                if not isinstance(data, list):
                    print("❌ Unexpected card search format")
                    return None, None, None
                
                cards = data[0]["result"]["data"]["json"]["cards"]
                rate_limit = response.headers.get("x-ratelimit-limit")
                rate_remaining = response.headers.get("x-ratelimit-remaining")
                return cards, rate_limit, rate_remaining

            except Exception as e:
                print(f"❌ Failed to parse card search JSON: {e}")
        else:
            print(f"❌ card search fetch failed: {response.status_code}")
            print(response.text)
            
        return None, None, None
    
    @staticmethod
    def fetch_all_cards() -> Generator[Dict[str, Any], None, None]:
        card_fetch_limit = 30
        total = CuriosaAPI.fetch_total_card_count()
        print(f"🔢 Total cards: {total}")

        for batch_num in range((total + card_fetch_limit - 1) // card_fetch_limit):
            try:
                cards, rate_limit, rate_remaining = CuriosaAPI.fetch_nth_of_i_cards(n=batch_num, i=card_fetch_limit)
                if cards is None:
                    print(f"❌ No cards fetched for batch {batch_num}")
                    continue
                
                print(f"📦 Batch {batch_num} → Fetched {len(cards)} cards")

                for card in cards:
                    yield card  # live yield to caller

                # optional: also yield intermediate stats
                print(f"  ⏳ Rate remaining: {rate_limit}/{rate_remaining}")
            except Exception as e:
                print(f"❌ Failed batch {batch_num}: {e}")
                break

            time.sleep(1 + random.random())

    @classmethod
    def background_card_fetch(cls):
        try:
            for card in cls.fetch_all_cards():
                cls.card_queue.put(card)

            while True:
                try:
                    card = cls.card_queue.get(timeout=2)
                    cls.all_cards.append(card)
                    if len(cls.all_cards) == cls.online_card_count:
                        print("✅ Card list complete. Saving to file.")
                        _save_json(cls.all_cards, CARD_DATA_PATH)
                        break
                    
                except Empty:
                    if not cls.thread or not cls.thread.is_alive():
                        print("🛑 Done: thread finished and queue empty.")
                        break
                    else:
                        print(f"⏳ Waiting for more cards... got {len(cls.all_cards)}/{cls.online_card_count} cards.")

        except Exception as e:
            print(f"❌ Unexpected top-level error in background fetch: {type(e).__name__}: {e}")
        
        print("✅ Local Curiosa card list is up to date.")
        CuriosaAPI.have_loaded_cards = True
        
    @staticmethod
    def rebuild_card_list():
        CuriosaAPI.all_cards.clear()
        CuriosaAPI.thread = threading.Thread(target=CuriosaAPI.background_card_fetch)
        CuriosaAPI.thread.daemon = True
        CuriosaAPI.thread.start()
    
    @staticmethod
    def check_card_list():
        os.makedirs(DATA_PATH, exist_ok=True)
        
        if os.path.exists(CARD_DATA_PATH):
            with open(CARD_DATA_PATH, "r", encoding="utf-8") as f:
                CuriosaAPI.all_cards = json.load(f)
            print(f"📁 Loaded {len(CuriosaAPI.all_cards)} cards from cache.")
        else:
            print("🆕 No card cache `found.")

        try:
            CuriosaAPI.online_card_count = CuriosaAPI.fetch_total_card_count()
            print(f"🌐 Online card count: {CuriosaAPI.online_card_count}")
        except Exception as e:
            print(f"❌ Failed to fetch online card count: {e}")
            return

        if len(CuriosaAPI.all_cards) != CuriosaAPI.online_card_count:
            print("🔄 Card count mismatch. Rebuilding card list...")
            CuriosaAPI.rebuild_card_list()
        else:
            print("✅ Local Curiosa card list is up to date.")
            CuriosaAPI.have_loaded_cards = True
    
    def __init__(self):
        self.buildID = self.fetch_build_id()
        self.token = None
        self.username = None
        self.user_info = None
        self.collection = None
        self.folders = None
        
    def login(self):
        self.token, browser_buildID = self.get_app_session_cookie()
        if self.buildID is None:
            self.buildID = browser_buildID
        self.user_info = self.fetch_user_info()
        if self.user_info:
            self.username = self.resolve_username(self.user_info)
        else:
            print("❌ Failed to log in. Please check your credentials.")
            
    def fetch_user_cards(self):
        self.collection = self.fetch_collection()
        self.folders: Optional[list[Dict[str, Any]]] = self.fetch_only_folders()
    
    def find_all_usernames(self, data):
        usernames = []

        if isinstance(data, dict):
            for key, value in data.items():
                if key == "username":
                    usernames.append(value)
                else:
                    usernames.extend(self.find_all_usernames(value))
        elif isinstance(data, list):
            for item in data:
                usernames.extend(self.find_all_usernames(item))

        return usernames

    def resolve_username(self, data):
        usernames = self.find_all_usernames(data)
        unique_usernames = list(set(usernames))

        if not unique_usernames:
            raise ValueError("❌ No 'username' fields found in the provided data.")

        if len(unique_usernames) == 1:
            print(f"✅ Single username found: {unique_usernames[0]}")
            return unique_usernames[0]

        # Multiple usernames found
        print("⚠️ Multiple usernames found:")
        for idx, uname in enumerate(unique_usernames):
            print(f"  [{idx + 1}] {uname}")

        while True:
            choice = input("Please select the number of the correct username: ").strip()
            if choice.isdigit():
                choice_index = int(choice) - 1
                if 0 <= choice_index < len(unique_usernames):
                    selected = unique_usernames[choice_index]
                    print(f"✅ Selected username: {selected}")
                    return selected
            print("Invalid input. Try again.")
            
    def get_app_session_cookie(self, timeout=60) -> tuple[str, str | None]:
        with sync_playwright() as p:
            browser = p.webkit.launch(headless=False) if sys.platform == "darwin" else p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()

            print("🔓 A browser window has opened. Please log in to https://curiosa.io.")
            page.goto("https://curiosa.io/api/auth/login?redirect=/")

            print(f"⏳ Waiting for session cookie (timeout: {timeout} sec)...")
            start_time = time.time()
            app_session = None

            while time.time() - start_time < timeout:
                cookies = context.cookies("https://curiosa.io")
                app_session = next((c.get('value') for c in cookies if c.get('name') == 'appSession'), None)
                if app_session:
                    print("✅ appSession cookie detected.")
                    break
                time.sleep(1)

            # Attempt to extract buildId from page
            build_id = None
            if self.buildID is None:
                try:
                    print("🔍 Extracting buildId from page...")
                    page.goto("https://curiosa.io/")
                    page.wait_for_selector("script[src*='_buildManifest.js']", timeout=10000)
                    build_script_tags = page.query_selector_all("script[src*='_buildManifest.js']")
                    for tag in build_script_tags:
                        src = tag.get_attribute("src")
                        if src:
                            parts = src.split("/")
                            if len(parts) > 3:
                                build_id = parts[3]
                                break
                    if build_id:
                        print(f"✅ Found buildId: {build_id}")
                    else:
                        print("❌ Could not extract buildId.")
                except Exception as e:
                    print(f"❌ Error extracting buildId: {e}")

            browser.close()

            if not app_session:
                print("❌ Session cookie not found after timeout.")
                sys.exit(1)

            return app_session, build_id

    def _loggedIn_headers(self, referer_path: str) -> Dict[str, str]:
        headers = {
            'authority': 'curiosa.io',
            'accept': '*/*',
            'accept-language': 'en-AU,en;q=0.9',
            'content-type': 'application/json',
            'x-trpc-source': 'nextjs-react',
            'user-agent': 'Mozilla/5.0',
            'origin': 'https://curiosa.io',
            'referer': f'https://curiosa.io{referer_path}'
        }
        if self.token:
            headers['cookie'] = f'appSession={self.token}'
        if self.buildID:
            headers['x-build-id'] = self.buildID
        else:
            headers['x-build-id'] = 'a5081202dd6bb8f53d26358febc079b618a142e8'
        return headers

    def fetch_user_info(self) -> Optional[Dict[str, Any]]:
        query = {
            "0": {"json": None}
        }

        url = (
            "https://curiosa.io/api/trpc/"
            "collection.getBySession"
            f"?batch=1&input={quote(json.dumps(query))}"
        )

        response = requests.get(url, headers=self._loggedIn_headers("/collection"))
        if response.ok:
            try:
                return response.json()
            except Exception as e:
                print(f"❌ Failed to parse collection JSON: {e}")
        else:
            print(f"❌ Collection fetch failed: {response.status_code}")
            print(response.text)
        return None

    def fetch_collection(self) -> Optional[Dict[str, Any]]:
        query = {
            "0": {"json": None}
        }

        url = (
            "https://curiosa.io/api/trpc/"
            "collection.getCollectionlistBySession"
            f"?batch=1&input={quote(json.dumps(query))}"
        )

        response = requests.get(url, headers=self._loggedIn_headers("/collection"))
        if response.ok:
            try:
                data = response.json()
                
                if not isinstance(data, list):
                    print("❌ Unexpected collection format")
                    return None
                
                return data[0]["result"]["data"]["json"]
            except Exception as e:
                print(f"❌ Failed to parse collection JSON: {e}")
        else:
            print(f"❌ Collection fetch failed: {response.status_code}")
            print(response.text)
        return None

    def fetch_only_folders(self) -> Optional[list[Dict[str, Any]]]:
        query = {
            "0": {"json": {"folderId": None}, "meta": {"values": {"folderId": ["undefined"]}}}
        }

        url = (
            "https://curiosa.io/api/trpc/deck.getMyFolders"
            f"?batch=1&input={quote(json.dumps(query))}"
        )

        response = requests.get(url, headers=self._loggedIn_headers("/users"))
        if response.ok:
            try:
                data = response.json()
                
                if not isinstance(data, list):
                    print("❌ Unexpected collection format")
                    return None
                
                return data[0]["result"]["data"]["json"]
            except Exception as e:
                print(f"❌ Failed to parse folders JSON: {e}")
        else:
            print(f"❌ Folder fetch failed: {response.status_code}")
            print(response.text)
        return None

    def save_user_cards(self):
        if not self.username:
            print("❌ Username not set. Please login first.")
            return
            
        user_path = os.path.join(DATA_PATH, self.username)
        os.makedirs(f"{DATA_PATH}/{self.username}", exist_ok=True)
        _save_json(data=self.collection, filename=os.path.join(user_path, "curiosa_collection.json"))

        _save_json(data=self.folders, filename=os.path.join(user_path, "curiosa_folders.json"))
        
        if self.folders is not None:  
            for folder in self.folders:
                folder_name = folder["name"].replace("/", "-")
                folder_path = f"{DATA_PATH}/{self.username}/{folder_name}"
                os.makedirs(folder_path, exist_ok=True)

                for deck in folder["decks"]:
                    deck_id = deck["id"]
                    try:
                        deck_data = self.fetch_curiosa_deck(deck_id)
                        if deck_data:
                            _save_json(data=deck_data, filename=os.path.join(folder_path, f"{deck_id}.json"))
                    except Exception as e:
                        print(f"❌ Failed to fetch deck {deck_id}: {e}")


if __name__ == "__main__":
    user = CuriosaAPI()


# Automatically check and fetch cards in background at import time
CuriosaAPI.check_card_list()