import csv
import json
import os
import re
import pygame
from tqdm import tqdm
from Util_Debug import DebugDisplay
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional, List, Dict, Any
from Util_Methods import _save_json
import Levenshtein
from CardInfo import CardInfo
from Collection import Collection
import easygui

CARD_ASSETS_PATH = "assets/Cards"


class Curiosa_OfflineData:
    def __init__(self, path: str, card_data_lookup: Dict[str, Dict[str, Any]]):
        self.card_data_lookup = card_data_lookup
        self.collection: Collection
        self.load_collection(path, force_update=False)
        
    def load_collection(self, path: str, force_update: bool = False):
        """Load collection from CSV file with JSON caching"""
        csv_path = path
        if not os.path.exists(csv_path):
            error_msg = f"Collection file not found: {csv_path}"
            print(error_msg)
            DebugDisplay.add_message(error_msg)
            return
        
        # Generate JSON cache filename based on CSV filename
        csv_filename = os.path.basename(csv_path)
        json_cache_path = f"assets/{csv_filename.replace('.csv', '_cache.json')}"
        
        # Try to load from JSON cache first (unless force_update is True)
        if not force_update and os.path.exists(json_cache_path):
            try:
                with open(json_cache_path, 'r', encoding='utf-8') as file:
                    cached_data = json.load(file)
                    self.collection = cached_data['collection']
                
                success_msg = f"Loaded {len(self.collection)} unique cards from cache"
                print(success_msg)
                DebugDisplay.add_message(success_msg)
                return
            except Exception as e:
                print(f"Failed to load cache, falling back to CSV: {e}")
        
        # Load from CSV and process
        self._load_collection_from_csv(csv_path, json_cache_path)

    def _load_collection_from_csv(self, csv_path: str, json_cache_path: str):
        with open(csv_path, 'r', encoding='utf-8') as file:
            total_rows = sum(1 for _ in csv.DictReader(file))

        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)

            with tqdm(total=total_rows, desc="Loading Collection", unit="cards") as pbar:
                for row in reader:
                    collection_card_name = row['card name'].strip()
                    # normalized_name = self.normalize_card_name(collection_card_name)

                    matched_name = None

                    # Try exact match
                    if collection_card_name in self.card_data_lookup:
                        matched_name = collection_card_name
                    else:
                        # Use Levenshtein to find closest name
                        min_distance = float('inf')
                        for json_name in self.card_data_lookup:
                            dist = Levenshtein.distance(collection_card_name.lower(), json_name.lower())
                            if dist < min_distance:
                                min_distance = dist
                                matched_name = json_name

                        if min_distance > 5:  # You can tune this threshold
                            print(f"❌ Card not matched: '{collection_card_name}' (closest: '{matched_name}', distance: {min_distance})")
                            continue

                    if not matched_name:
                        print(f"❌ Card not found in lookup: '{collection_card_name}'")
                        continue  # Skip this card if not matched

                    if matched_name not in self.collection:
                        self.collection[matched_name] = {
                            'count': 0,
                            'card_data': self.card_data_lookup[matched_name],
                            'sets': [],
                            'finishes': [],
                            'products': []
                        }

                    self.collection[matched_name]['count'] += 1
                    self.collection[matched_name]['sets'].append(row['set'])
                    self.collection[matched_name]['finishes'].append(row['finish'])
                    self.collection[matched_name]['products'].append(row['product'])

                    pbar.update(1)
                    pbar.set_postfix({'Unique Cards': len(self.collection)})

        try:
            cache_data = {
                'collection': self.collection,
                'timestamp': str(pygame.time.get_ticks()),
                'csv_filename': os.path.basename(csv_path)
            }
            os.makedirs(os.path.dirname(json_cache_path), exist_ok=True)
            _save_json(cache_data, json_cache_path)

        except Exception as e:
            error_msg = f"Failed to save cache: {e}"
            print(error_msg)
            DebugDisplay.add_message(error_msg)

        success_msg = f"✅ Loaded {len(self.collection)} unique cards from collection"
        print(success_msg)
        DebugDisplay.add_message(success_msg)
        
    def normalize_card_name(self, name: str) -> str:
        """Normalize card name for matching"""
        # Remove special characters and convert to lowercase
        normalized = re.sub(r'[^\w\s]', '', name.lower())
        # Replace multiple spaces with single space
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized
