import json
import os
from Curiosa_API import CuriosaAPI
from typing import Dict, Any, Optional, Generator, List, Tuple
from Util_IO import _save_json, CARD_ASSETS_PATH
import time
from Card import Card
from Sorcery_API import SorceryAPI
from Util_IO import BASE_DATA_PATH, ALL_CARD_DATA_PATH
import queue
import threading
import requests
from PIL import Image
from io import BytesIO
import pygame
import Layout_Manager as LM
from collections import defaultdict
import math


class Card_Manager:
    def __init__(self):
        self.loading = True
        self.cards: Dict[str, Card] = {}
        self.card_data_lookup: Dict[str, Dict[str, Any]] = {}
        self.cards_loaded = 0

        # Wait until API data is loaded
        while not SorceryAPI.have_loaded_cards:
            time.sleep(1)
        while not CuriosaAPI.have_loaded_cards:
            time.sleep(1)

        sorcery_cards = SorceryAPI.all_cards
        curiosa_cards = CuriosaAPI.all_cards
        
        # --- Load or build card data file ---
        if os.path.exists(BASE_DATA_PATH):
            with open(BASE_DATA_PATH, "r", encoding="utf-8") as f:
                Base_CardData = json.load(f)
        else:
            Base_CardData = []

        if os.path.exists(ALL_CARD_DATA_PATH):
            with open(ALL_CARD_DATA_PATH, "r", encoding="utf-8") as f:
                self.card_data_lookup = json.load(f)
        else:
            self.card_data_lookup = {}

        print(f"SorceryAPI cards: {len(sorcery_cards)}")
        print(f"CuriosaAPI cards: {len(curiosa_cards)}")
        print(f"CardData cards:   {len(Base_CardData)}")
        print(f"All cards:        {len(self.card_data_lookup)}")

        # --- If all datasets align in length, use file ---
        if (len(sorcery_cards) == len(curiosa_cards) == len(Base_CardData) == len(self.card_data_lookup)):
            print("✅ Card data files are up to date, reticulating cards...")
            self.cards = {cd["name"]: Card.from_card_data(cd) for cd in Base_CardData}
        else:
            print("🛠️ Data mismatch or missing files, rebuilding card data with latest API data...")
            Base_CardData = self.build_card_data(sorcery_cards, curiosa_cards)
            _save_json(self.card_data_lookup, ALL_CARD_DATA_PATH)
            _save_json(Base_CardData, BASE_DATA_PATH)
            print("✅ Card data files are up to date")
            
        # --- With cards loaded, start downloading images ---
        self.download_queue = queue.Queue()
        for card in self.cards.values():
            self.download_queue.put((card))
        self.download_thread = threading.Thread(target=self.image_download_worker, daemon=True)
        self.download_thread.start()

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

            card = Card.from_card_data(card_data)
            self.cards[card.name] = card
            
        return card_data_list

    def image_download_worker(self):
        while not self.download_queue.empty():
            card: Card = self.download_queue.get()
            try:
                filename = os.path.join(CARD_ASSETS_PATH, os.path.basename(card.image_url))
                if os.path.exists(filename):
                    with open(filename, "rb") as f:
                        img_data = f.read()
                else:
                    response = requests.get(card.image_url, timeout=5)
                    img_data = response.content
                    with open(filename, "wb") as f:
                        f.write(img_data)
                
                img = Image.open(BytesIO(img_data)).convert("RGBA")
                card.set_scaled_surfaces(img)
                card.position = ((self.cards_loaded % 25) * LM.GRID_SPACING * LM.LONG_EDGE_SNAP_RATIO,
                                 (self.cards_loaded // 25) * LM.GRID_SPACING * LM.LONG_EDGE_SNAP_RATIO)
                self.cards_loaded += 1
            except Exception as e:
                print(f"Error loading card {getattr(card, 'name', 'unknown')}: {e}")
            self.download_queue.task_done()

        self.loading = False
        self.initialize_card_positions()

    def initialize_card_positions(self):
        # --- Automatically group and layout all base cards when loaded ---
        Cards_list = list(self.cards.values())
        self.group_element_type_rarity(Cards_list, (0, 0))
        print("[DEBUG] Base cards grouped and laid out.")
        # Compute and store base bounding box (300 units larger)
        self.base_bounding_box = self.compute_bounding_box(
            cards=Cards_list,
            padding=LM.REGION_PADDING * LM.GRID_SPACING
        )
        # Compute and store element bounding boxes for base cards
        self.base_element_bounding_boxes = {}
        element_map = {"Air": [], "Fire": [], "Earth": [], "Water": [], "None": [], "Multiple": []}
        for card in self.cards.values():
            if not card.elements:
                element_map["None"].append(card)
            elif len(card.elements) > 1:
                element_map["Multiple"].append(card)
            else:
                element_map[card.elements[0]].append(card)
        for element, cards in element_map.items():
            self.base_element_bounding_boxes[element] = self.compute_bounding_box(Cards_list, padding=int(LM.GRID_SPACING))
            
    def group_element_type_rarity(self, cards: List[Card], top_left: Tuple[int, int]):
        # Filter cards that have the group_name in their positions
        # filtered_cards = [card for card in cards.values() if group_name in card.positions and card.positions[group_name]]
        # Group by element, type, rarity
        grouped = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        for card in cards:
            element_key = "None" if not card.elements else ("Multiple" if len(card.elements) > 1 else card.elements[0])
            type_key = "Spell" if (card.type or "Unknown") in ["Aura", "Magic"] else (card.type or "Unknown")
            rarity_key = card.rareity or "Ordinary"
            grouped[element_key][type_key][rarity_key].append(card)
        
        # Layout with tighter spacing
        # Define spacing for different card types
        portrait_card_width = LM.GRID_SPACING * LM.SHORT_EDGE_SNAP_RATIO  # 110 pixels
        portrait_card_height = LM.GRID_SPACING * LM.LONG_EDGE_SNAP_RATIO  # 165 pixels
        site_card_width = LM.GRID_SPACING * LM.LONG_EDGE_SNAP_RATIO  # 165 pixels (rotated)
        site_card_height = LM.GRID_SPACING * LM.SHORT_EDGE_SNAP_RATIO  # 110 pixels (rotated)
        
        spacing_element = LM.BOARD_PADDING * LM.GRID_SPACING  # Spacing between element groups
        spacing_type = LM.SMALL_PADDING * LM.GRID_SPACING  # Spacing between type groups
        spacing_rarity = 0  # Spacing between rarity rows
        x_offset = 0
        rarity_order_list = ["Ordinary", "Exceptional", "Elite", "Unique"]
        
        for element_key, types in grouped.items():
            # Precompute max rows per rarity across all types in this element
            max_rows_per_rarity = {}
            for rarity_key in rarity_order_list:
                max_rows = 0
                for type_rarities in types.values():
                    items = type_rarities.get(rarity_key, [])
                    type_total = sum(len(cards) for cards in type_rarities.values())
                    cols = max(1, int(math.sqrt(type_total)))
                    rows = math.ceil(len(items) / cols) if len(items) > 0 else 0
                    max_rows = max(max_rows, rows)
                max_rows_per_rarity[rarity_key] = max_rows
            
            local_x = 0
            element_max_width = 0
            
            for type_key, rarities in types.items():
                # Check if this type contains any site cards
                has_sites = any(getattr(card, "type", "").lower() == "site" 
                              for items in rarities.values() for card in items)
                
                # Calculate width for this type based on sqrt of total items
                type_total = sum(len(items) for items in rarities.values())
                cols = max(1, int(math.sqrt(type_total)))
                
                # Use appropriate card width for column calculation
                if has_sites:
                    col_width = cols * site_card_width  # Use site card width if any sites present
                else:
                    col_width = cols * portrait_card_width  # Use portrait card width
                
                type_start_x = x_offset + local_x
                rarity_y_offset = 0
                
                for rarity_key in rarity_order_list:
                    items = rarities.get(rarity_key, [])
                    num_cards = len(items)
                    rows = math.ceil(num_cards / cols) if num_cards > 0 else 0
                    
                    for i, card in enumerate(items):
                        row = i // cols
                        col = i % cols
                        
                        # Determine card spacing based on whether it's a site
                        is_site = getattr(card, "type", "").lower() == "site"
                        if is_site:
                            # Use site card dimensions
                            card_width = site_card_width
                            card_height = site_card_height
                        else:
                            # Use portrait card dimensions
                            card_width = portrait_card_width
                            card_height = portrait_card_height
                        
                        x = type_start_x + col * card_width + top_left[0]
                        y = rarity_y_offset + row * card_height + top_left[1]
                        
                        card.position = (x, y)
                    
                    # Move down by the max height of this rarity band
                    max_rows = max_rows_per_rarity[rarity_key]
                    if max_rows > 0:
                        # Use appropriate row height based on card types in this rarity
                        if has_sites:
                            row_height = site_card_height
                        else:
                            row_height = portrait_card_height
                        rarity_y_offset += max_rows * row_height + spacing_rarity
                
                local_x += col_width + spacing_type
                element_max_width = max(element_max_width, local_x)
            
            x_offset += element_max_width + spacing_element

    def group_type_rarity(self, cards: List[Card], top_left: Tuple[int, int]):
        # Filter cards that have the group_name in their positions
        # filtered_cards = [card for card in cards.values() if group_name in card.positions and card.positions[group_name]]
        # Group by type, rarity
        grouped = defaultdict(lambda: defaultdict(list))
        for card in cards:
            type_key = "Spell" if (card.type or "Unknown") in ["Aura", "Magic"] else (card.type or "Unknown")
            rarity_key = card.rareity or "Ordinary"
            grouped[type_key][rarity_key].append(card)
        
        # Layout with tighter spacing
        # Define spacing for different card types
        portrait_card_width = LM.GRID_SPACING * LM.SHORT_EDGE_SNAP_RATIO  # 110 pixels
        portrait_card_height = LM.GRID_SPACING * LM.LONG_EDGE_SNAP_RATIO  # 165 pixels
        site_card_width = LM.GRID_SPACING * LM.LONG_EDGE_SNAP_RATIO  # 165 pixels (rotated)
        site_card_height = LM.GRID_SPACING * LM.SHORT_EDGE_SNAP_RATIO  # 110 pixels (rotated)
        
        spacing_type = LM.GRID_SPACING * LM.SMALL_PADDING  # Spacing between type groups
        spacing_rarity = 0  # Spacing between rarity rows
        x_offset = 0
        rarity_order_list = ["Ordinary", "Exceptional", "Elite", "Unique"]
        
        for type_key, rarities in grouped.items():
            # Check if this type contains any site cards
            has_sites = any(getattr(card, "type", "").lower() == "site" 
                          for items in rarities.values() for card in items)
            
            # Precompute max rows per rarity across all rarities in this type
            max_rows_per_rarity = {}
            for rarity_key in rarity_order_list:
                items = rarities.get(rarity_key, [])
                type_total = sum(len(cards) for cards in rarities.values())
                cols = max(1, int(math.sqrt(type_total)))
                rows = math.ceil(len(items) / cols) if len(items) > 0 else 0
                max_rows_per_rarity[rarity_key] = rows
            
            # Calculate width for this type based on sqrt of total items
            type_total = sum(len(items) for items in rarities.values())
            cols = max(1, int(math.sqrt(type_total)))
            
            # Use appropriate card width for column calculation
            if has_sites:
                col_width = cols * site_card_width  # Use site card width if any sites present
            else:
                col_width = cols * portrait_card_width  # Use portrait card width
            
            type_start_x = x_offset
            rarity_y_offset = 0
            
            for rarity_key in rarity_order_list:
                items = rarities.get(rarity_key, [])
                num_cards = len(items)
                rows = math.ceil(num_cards / cols) if num_cards > 0 else 0
                
                for i, card in enumerate(items):
                    row = i // cols
                    col = i % cols
                    
                    # Determine card spacing based on whether it's a site
                    is_site = getattr(card, "type", "").lower() == "site"
                    if is_site:
                        # Use site card dimensions
                        card_width = site_card_width
                        card_height = site_card_height
                    else:
                        # Use portrait card dimensions
                        card_width = portrait_card_width
                        card_height = portrait_card_height
                    
                    x = type_start_x + col * card_width + top_left[0]
                    y = rarity_y_offset + row * card_height + top_left[1]
                    
                    card.position = (x, y)
                
                # Move down by the max height of this rarity band
                max_rows = max_rows_per_rarity[rarity_key]
                if max_rows > 0:
                    # Use appropriate row height based on card types in this rarity
                    if has_sites:
                        row_height = site_card_height
                    else:
                        row_height = portrait_card_height
                    rarity_y_offset += max_rows * row_height + spacing_rarity
            
            x_offset += col_width + spacing_type

    def compute_bounding_box(self, cards: List[Card], padding: int = 0):
        # Returns (min_x, min_y, max_x, max_y) with padding
        padding = padding
        xs, ys = [], []
        for card in cards:
            (xPos, yPos) = card.position
            xs.append(xPos)
            ys.append(yPos)
        if xs == -1 or not ys == -1:
            return None
        min_x, max_x = min(xs) - padding, max(xs) + LM.CARD_DIMENSIONS[0] + padding
        min_y, max_y = min(ys) - padding, max(ys) + LM.CARD_DIMENSIONS[1] + padding
        return (min_x, min_y, max_x, max_y)
    