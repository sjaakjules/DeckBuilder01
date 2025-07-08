import os
import sys
import time
import json
import requests
from typing import Dict, Any, Optional
from urllib.parse import urlencode, quote
from playwright.sync_api import sync_playwright

# --- CONFIG ---
SORCERY_API = "https://api.sorcery.com/cards"  # Replace if needed
DATA_PATH = "data"


class CuriosaUser:
    def __init__(self):
        self.token = self.get_app_session_cookie()
        self.user_info = self.fetch_user_info()
        if self.user_info:
            self.username = self.resolve_username(self.user_info)
        else:
            print("❌ Failed to log in. Please check your credentials.")
            sys.exit(1)
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
            
    def get_app_session_cookie(self, timeout=60) -> str:
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

            browser.close()

            if not app_session:
                print("❌ Session cookie not found after timeout.")
                sys.exit(1)

            return app_session

    def _headers(self, referer_path: str) -> Dict[str, str]:
        return {
            'authority': 'curiosa.io',
            'accept': '*/*',
            'accept-language': 'en-AU,en;q=0.9',
            'content-type': 'application/json',
            'x-build-id': 'a5081202dd6bb8f53d26358febc079b618a142e8',
            'x-trpc-source': 'nextjs-react',
            'user-agent': 'Mozilla/5.0',
            'cookie': f'appSession={self.token}',
            'origin': 'https://curiosa.io',
            'referer': f'https://curiosa.io{referer_path}'
        }

    def fetch_user_info(self) -> Optional[Dict[str, Any]]:
        query = {
            "0": {"json": None}
        }

        url = (
            "https://curiosa.io/api/trpc/"
            "collection.getBySession"
            f"?batch=1&input={quote(json.dumps(query))}"
        )

        response = requests.get(url, headers=self._headers("/collection"))
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

        response = requests.get(url, headers=self._headers("/collection"))
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

        response = requests.get(url, headers=self._headers("/users"))
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

    def fetch_curiosa_deck(self, deck_id: str) -> Optional[Dict[str, Any]]:
        query = {
            str(i): {"json": {"id": deck_id}} for i in range(4)
        }

        url = (
            "https://curiosa.io/api/trpc/"
            "deck.getDecklistById,deck.getAvatarById,"
            "deck.getSideboardById,deck.getMaybeboardById"
            f"?batch=1&input={quote(json.dumps(query))}"
        )

        response = requests.get(url, headers=self._headers(f"/decks/{deck_id}"))
        if response.ok:
            try:
                results = response.json()
                if not isinstance(results, list) or len(results) != 4:
                    print("❌ Unexpected deck result format")
                    return None

                return {
                    "main": results[0]["result"]["data"]["json"],
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

    def save_user_cards(self):
        os.makedirs(f"{DATA_PATH}/{self.username}", exist_ok=True)
        
        with open(f"{DATA_PATH}/{self.username}/curiosa_collection.json", "w", encoding="utf-8") as f:
            json.dump(self.collection, f, indent=4, ensure_ascii=False)

        with open(f"{DATA_PATH}/{self.username}/curiosa_folders.json", "w", encoding="utf-8") as f:
            json.dump(self.folders, f, indent=4, ensure_ascii=False)
        
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
                            with open(f"{folder_path}/{deck_id}.json", "w", encoding="utf-8") as f:
                                json.dump(deck_data, f, indent=4, ensure_ascii=False)
                            print(f"✅ Saved deck: {folder_path}/{deck_id}.json")
                    except Exception as e:
                        print(f"❌ Failed to fetch deck {deck_id}: {e}")

    @staticmethod
    def extract_deck_id(url_or_id: str) -> str:
        return url_or_id.rstrip('/').split('/')[-1] if '/' in url_or_id else url_or_id


if __name__ == "__main__":
    user = CuriosaUser()
    user.save_user_cards()
    