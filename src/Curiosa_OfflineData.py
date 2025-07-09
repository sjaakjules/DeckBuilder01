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

CARD_ASSETS_PATH = "assets/Cards"


class CuriosaOfflineData:
    def __init__(self, card_data: List[Dict[str, Any]]):
        self.card_data = card_data
        self.card_data_lookup = {card["name"]: card for card in card_data}
        self.collection = {}
        self.load_collection("assets/collection-2025-07-07T01_38_01.445Z.csv", force_update=False)
        
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
        """Load collection from CSV file and save to JSON cache"""
        # First, count total rows for progress bar
        with open(csv_path, 'r', encoding='utf-8') as file:
            total_rows = sum(1 for _ in csv.DictReader(file))
        
        name_list = {}
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            
            # Create progress bar with ETA
            with tqdm(total=total_rows, desc="Loading Collection", unit="cards") as pbar:
                for row in reader:
                    found_in_json = False
                    collection_card_name = row['card name'].strip()
                    if collection_card_name not in name_list:
                        
                        card_name = collection_card_name
                        
                        # Split the name by special characters to get arrays of letters
                        # Use the largest sequence of letters to search names in JSON
                        letter_sequences = re.findall(r'[a-zA-Z]+', card_name)
                        longest_sequence = max(letter_sequences, key=len) if letter_sequences else ""
                        
                        # Search for this sequence in JSON card names
                        json_name = 'not found'
                        if longest_sequence:
                            for json_card in self.card_data:
                                if longest_sequence.lower() in json_card['name'].lower():
                                    found_in_json = True
                                    json_name = json_card['name']
                                    name_list[collection_card_name] = json_name
                                    break
                        
                        if not found_in_json:
                            print(f"Card not found in JSON: '{card_name}' (longest sequence: '{longest_sequence}')")
                        else:
                            card_name = json_name
                    else:
                        card_name = name_list[collection_card_name]
                    
                    if card_name not in self.collection:
                        self.collection[card_name] = {
                            'count': 0,
                            'image_path': None,
                            'card_data': None,
                            'sets': [],
                            'finishes': [],
                            'products': []
                        }
                        if found_in_json:
                            self.collection[card_name]['card_data'] = self.card_data_lookup[card_name]
                            self.collection[card_name]['image_path'] = self.find_card_image(json_name)
                    self.collection[card_name]['count'] += 1
                    self.collection[card_name]['sets'].append(row['set'])
                    self.collection[card_name]['finishes'].append(row['finish'])
                    self.collection[card_name]['products'].append(row['product'])
                    
                    # Update progress bar
                    pbar.update(1)
                    pbar.set_postfix({
                        'Unique Cards': len(self.collection)
                    })
        
        # Save processed data to JSON cache
        try:
            cache_data = {
                'collection': self.collection,
                'name_list': name_list,
                'timestamp': str(pygame.time.get_ticks()),
                'csv_filename': os.path.basename(csv_path)
            }
            
            # Ensure assets directory exists
            os.makedirs(os.path.dirname(json_cache_path), exist_ok=True)
            
            _save_json(cache_data, json_cache_path)
            
        except Exception as e:
            error_msg = f"Failed to save cache: {e}"
            print(error_msg)
            DebugDisplay.add_message(error_msg)
        
        success_msg = f"Loaded {len(self.collection)} unique cards from collection"
        print(success_msg)
        DebugDisplay.add_message(success_msg)
        

    def find_card_image(self, card_name: str) -> Optional[str]:
        """Find card image in assets/Cards directory with fuzzy matching"""
        assets_dir = Path(CARD_ASSETS_PATH)
        if not assets_dir.exists():
            print(f"Assets directory not found: {assets_dir}")
            return None
        
        # Try multiple variations of the card name
        name_variations = [
            card_name,
            self.normalize_card_name(card_name),
        ]
        
        best_match = None
        best_ratio = 0.0
        best_name = None
        
        # Search directly in assets/Cards directory
        for image_file in assets_dir.glob("*.png"):
            filename = image_file.stem  # Remove extension
            
            # Try each name variation
            for name_variation in name_variations:
                normalized_name = self.normalize_card_name(name_variation)
                normalized_filename = self.normalize_card_name(filename)
                
                # Calculate similarity
                ratio = SequenceMatcher(None, normalized_name, normalized_filename).ratio()
                if ratio > best_ratio and ratio > 0.6:  # Threshold for matching
                    best_ratio = ratio
                    best_match = str(image_file)
                    best_name = name_variation
        
        if best_match:
            if best_name != card_name:
                DebugDisplay.add_message(f"Image match with encoding fix: '{card_name}' -> '{best_name}'")
        else:
            print(f"No image found for '{card_name}'")
            
        return best_match
    
    def normalize_card_name(self, name: str) -> str:
        """Normalize card name for matching"""
        # Remove special characters and convert to lowercase
        normalized = re.sub(r'[^\w\s]', '', name.lower())
        # Replace multiple spaces with single space
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized
    
    def extract_all_slugs(self, card_list):
        top_level_slugs = [card["slug"] for card in card_list if "slug" in card]
        return top_level_slugs