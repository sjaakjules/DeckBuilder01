from typing import List, Dict, Any
from Card import Card
from Util_IO import open_threadsafe_dialog, ask_string
from Curiosa_API import CuriosaAPI
import os
from Util_IO import _save_json, DECK_PATH
from Deck import Deck
from typing import Tuple
from Card_Manager import Card_Manager
import Layout_Manager as LM


class Deck_Manager:
    # Board region dimensions (in pixels) - region boundaries
    MAINBOARD_WIDTH = 2475  # 45 grid units * 55 = 2475
    MAINBOARD_HEIGHT = 1980  # 36 rows * 55 = 1980
    SIDEBOARD_WIDTH = 2475  # 45 grid units * 55 = 2475
    SIDEBOARD_HEIGHT = 990   # 18 rows * 55 = 990
    MAYBEBOARD_WIDTH = 2475  # 45 grid units * 55 = 2475
    MAYBEBOARD_HEIGHT = 990  # 18 rows * 55 = 990
    
    # Grid configuration - using Layout_Manager constants
    GRID_WIDTH = 45  # supports 15 site cards or 22 portrait cards wide (45 grid units)
    
    def __init__(self):
        self.decks: List[Deck] = []
        self.gui_manager = None  # Will be set by GUI_Manager
    
    @classmethod
    def get_board_regions(cls):
        """Get board region dimensions as a dictionary"""
        return {
            "mainboard": {
                "width": cls.MAINBOARD_WIDTH,
                "height": cls.MAINBOARD_HEIGHT
            },
            "sideboard": {
                "width": cls.SIDEBOARD_WIDTH,
                "height": cls.SIDEBOARD_HEIGHT
            },
            "maybeboard": {
                "width": cls.MAYBEBOARD_WIDTH,
                "height": cls.MAYBEBOARD_HEIGHT
            }
        }
        
    def set_gui_manager(self, gui_manager):
        """Set reference to GUI manager for notifications"""
        self.gui_manager = gui_manager
            
    def load_deck(self):
        deck_url = open_threadsafe_dialog(
            ask_string, 
            title="Load Deck", 
            prompt="Enter Curiosa Deck URL or ID:"
        )
        if not deck_url:
            return
        self._load_deck_url(deck_url)
        
    def _load_deck_url(self, deck_url: str):
        try:
            print(f"  📥 Downloading deck {deck_url}...")
            deck_data = CuriosaAPI.fetch_curiosa_deck(deck_url)
            if deck_data:
                deck_name = deck_data.get("name", f"Deck_{deck_url}")
                deck_author = deck_data.get("author", "Unknown")
                # Extract clean deck ID from URL
                deck_id = CuriosaAPI._extract_deck_id(deck_url)
                print(f"  ✅ Downloaded deck: {deck_name}")
                
                # Save deck to file
                safe_filename = "".join(c for c in deck_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
                safe_filename = safe_filename.replace(' ', '_')
                _save_json(deck_data, f"{DECK_PATH}/{safe_filename}.json")
                
                # Load deck into the viewer
                deck = Deck.from_json(name=deck_name, author=deck_author, id=deck_id, json_data=deck_data)
                self.decks.append(deck)
                print(f"  ✅ Added deck: {deck_name} to deck list")
                
                # Notify GUI to add deck button
                if self.gui_manager and hasattr(self.gui_manager, 'sidebar'):
                    self.gui_manager.sidebar.add_deck_button(deck_name, deck_id)
            else:
                print(f"  ❌ Failed to download deck {deck_url}")
                
        except Exception as e:
            print(f"  ❌ Error downloading deck {deck_url}: {e}")

    def download_user_decks(self, curiosa: CuriosaAPI):
        """Download all decks from the user's folders"""
        if not curiosa or not hasattr(curiosa, 'folders') or curiosa.folders is None:
            print("❌ No folder information available")
            return
        
        print(f"📁 Found {len(curiosa.folders)} folders")
        total_decks = 0
        
        for folder in curiosa.folders:
            folder_name = folder.get('name', 'Unknown Folder')
            decks = folder.get('decks', [])
            print(f"📂 Processing folder '{folder_name}' with {len(decks)} decks")
            
            for deck_info in decks:
                deck_id = deck_info.get('id')
                if not deck_id:
                    continue
                
                self._load_deck_url(deck_id)
                total_decks += 1
        
        print(f"✅ Successfully downloaded and loaded {total_decks} decks")
        
    def place_deck(self, deck: Deck, position: Tuple[int, int], card_manager: Card_Manager):
        """
        Place deck in groups of a grid of cards 6 rows tall.
        Group by type: minions, magic, Aura and Artifacts together and Sites 9 rows tall because they are horizontal
        Sort by element where each element is a new column within that group. no extra spacing between cards tho, only between groups. 
        none or multiple elements in one column.
        if more than 6 cards in an element, make a new row.
        Place the avatar in the top left corner of the deck.
        then minions, magic, aura/artifact, sites with 110 padding between each group.
        spacing between cards is 110x165 or 165x110 for sites 
        The sideboard and maybebord are underneath the mainboard. The total width of rows+padding is divided by the 2 boards with 220 padding between them.
        """
        # Use the new simple placement method
        self._place_deck_simple(deck, position, card_manager)
    
    def _place_deck_simple(self, deck: Deck, position: Tuple[int, int], card_manager: Card_Manager):
        """Simple deck placement with fixed regions and grid-based layout"""
        import Layout_Manager as LM
        
        # Ensure position aligns to grid (use 55 for both X and Y)
        start_x = round(position[0] / LM.GRID_SPACING) * LM.GRID_SPACING
        start_y = round(position[1] / LM.GRID_SPACING) * LM.GRID_SPACING
        
        # Use Layout_Manager constants for grid and region dimensions
        grid_unit = LM.GRID_SPACING  # 55
        row_spacing = LM.GRID_SPACING * LM.LONG_EDGE_SNAP_RATIO  # 165 for proper row spacing
        grid_width = self.GRID_WIDTH
        
        # Region dimensions from class constants
        mainboard_width = self.MAINBOARD_WIDTH
        mainboard_height = self.MAINBOARD_HEIGHT
        sideboard_width = self.SIDEBOARD_WIDTH
        sideboard_height = self.SIDEBOARD_HEIGHT
        maybeboard_width = self.MAYBEBOARD_WIDTH
        maybeboard_height = self.MAYBEBOARD_HEIGHT
        
        # Calculate card start positions with offsets (cards are inset from region edges)
        mainboard_card_start_x = start_x + LM.REGION_PADDING * LM.GRID_SPACING  # 110
        mainboard_card_start_y = start_y + LM.REGION_PADDING * LM.GRID_SPACING  # 110
        
        # Place avatar in top left of mainboard region (with offset)
        if "avatar" in deck.deck and deck.deck["avatar"]:
            avatar_cards = list(deck.deck["avatar"].keys())
            if avatar_cards:
                avatar_name = avatar_cards[0]
                avatar_entries = deck.deck["avatar"][avatar_name]
                for i, entry in enumerate(avatar_entries):
                    deck.update_position("avatar", avatar_name, (mainboard_card_start_x, mainboard_card_start_y), i)
        
        # Place mainboard cards in grid (within the region with offsets)
        mainboard_cards = self._get_sorted_cards(deck, "mainboard", card_manager.card_data_lookup)
        self._place_cards_in_grid(mainboard_cards, deck, "mainboard", 
                                 (mainboard_card_start_x + LM.REGION_PADDING * LM.GRID_SPACING, mainboard_card_start_y), 
                                 mainboard_width, mainboard_height, grid_width, grid_unit, row_spacing)
        
        # Place sideboard cards in grid
        sideboard_cards = self._get_sorted_cards(deck, "sideboard", card_manager.card_data_lookup)
        sideboard_y = start_y + mainboard_height
        sideboard_card_start_x = start_x + LM.REGION_PADDING * LM.GRID_SPACING  # 110
        sideboard_card_start_y = sideboard_y + LM.REGION_PADDING * LM.GRID_SPACING  # 110
        self._place_cards_in_grid(sideboard_cards, deck, "sideboard", 
                                 (sideboard_card_start_x, sideboard_card_start_y), 
                                 sideboard_width, sideboard_height, grid_width, grid_unit, row_spacing)
        
        # Place maybeboard cards in grid
        maybeboard_cards = self._get_sorted_cards(deck, "maybeboard", card_manager.card_data_lookup)
        maybeboard_y = sideboard_y + sideboard_height
        maybeboard_card_start_x = start_x + LM.REGION_PADDING * LM.GRID_SPACING  # 110
        maybeboard_card_start_y = maybeboard_y + LM.REGION_PADDING * LM.GRID_SPACING  # 110
        self._place_cards_in_grid(maybeboard_cards, deck, "maybeboard", 
                                 (maybeboard_card_start_x, maybeboard_card_start_y), 
                                 maybeboard_width, maybeboard_height, grid_width, grid_unit, row_spacing)
    
    def _get_sorted_cards(self, deck: Deck, board_name: str, card_lookup: Dict[str, Any]) -> List[Tuple[str, Dict]]:
        """Get cards sorted by type, element, cost, rarity"""
        cards = []
        
        if board_name not in deck.deck:
            return cards
        
        for card_name, entries in deck.deck[board_name].items():
            try:
                card_data = card_lookup.get(card_name, {})
                card_info = card_data.get("card_data", {})
                
                # Get card properties for sorting with safe defaults
                card_type = card_info.get("type", "unknown").lower()
                elements = card_info.get("elements", [])
                cost = card_info.get("cost", 999)
                rarity = card_info.get("rarity", "unknown").lower()
                
                # Normalize card type
                if card_type in ["aura", "artifact"]:
                    card_type = "aura"  # Group together
                
                # Create sort key: (type_priority, element, cost, rarity_priority)
                type_priority = {"minion": 0, "magic": 1, "aura": 2, "site": 3}.get(card_type, 4)
                rarity_priority = {"ordinary": 0, "exceptional": 1, "elite": 2, "unique": 3}.get(rarity, 4)
                
                # Use first element for sorting, or "none" if no elements
                primary_element = elements[0] if elements else "none"
                
                sort_key = (type_priority, primary_element, cost, rarity_priority)
                
                cards.append((card_name, {"entries": entries, "sort_key": sort_key, "card_info": card_info}))
            except Exception as e:
                print(f"Warning: Error processing card '{card_name}' for sorting: {e}")
                # Add card with default sort key to prevent crashes
                default_sort_key = (4, "none", 999, 4)  # Unknown type, no element, high cost, unknown rarity
                cards.append((card_name, {"entries": entries, "sort_key": default_sort_key, "card_info": {}}))
        
        # Sort by the composite key
        try:
            cards.sort(key=lambda x: x[1]["sort_key"])
        except Exception as e:
            print(f"Warning: Error sorting cards: {e}")
            # If sorting fails, return cards in original order
            pass
        
        return cards
    
    def _place_cards_in_grid(self, sorted_cards: List[Tuple[str, Dict]], deck: Deck, board_name: str,
                            position: Tuple[int, int], region_width: int, region_height: int, 
                            grid_width: int, grid_unit: int, row_spacing: int):
        """Place cards in a grid within the specified region"""
        start_x, start_y = position
        current_x, current_y = start_x + LM.REGION_PADDING * LM.GRID_SPACING, start_y + LM.REGION_PADDING * LM.GRID_SPACING
        cards_in_current_row = 0
        current_row_width = 0
        
        # Calculate available space for cards (region dimensions minus offsets)
        # The region dimensions already include the offset padding, so we need to subtract it
        available_width = region_width - (4 * LM.REGION_PADDING * LM.GRID_SPACING)
        available_height = region_height - (2 * LM.REGION_PADDING * LM.GRID_SPACING)
        
        # Adjust grid width to fit within available space
        max_cards_per_row = available_width // grid_unit
        
        for card_name, card_data in sorted_cards:
            try:
                entries = card_data["entries"]
                card_info = card_data["card_info"]
                
                # Determine card dimensions and spacing based on type
                card_type = card_info.get("type", "unknown").lower()
                if card_type == "site":
                    # Site cards are rotated 90 degrees, so they're 140x100 instead of 100x140
                    # Since they're rotated, they need more horizontal space (140 units) but less vertical space (100 units)
                    # In grid units: 140/55 ≈ 2.55, so we need 3 grid units for width
                    # For height: 100/55 ≈ 1.82, so we need 2 grid units for height
                    card_width_units = 3  # Site cards are 3 grid units wide (165 pixels)
                    # Use 2 grid units for row spacing for site cards
                    card_row_spacing = LM.GRID_SPACING * 2  # 110 pixels (2 units)
                else:
                    # Portrait cards are 100x140
                    # In grid units: 100/55 ≈ 1.82, so we need 2 grid units for width
                    # For height: 140/55 ≈ 2.55, so we need 3 grid units for height
                    card_width_units = 2  # Portrait cards are 2 grid units wide (110 pixels)
                    # Use 3 grid units for row spacing for normal cards
                    card_row_spacing = LM.GRID_SPACING * 3  # 165 pixels (3 units)
                
                for entry in entries:
                    # Check if card fits in current row
                    if current_row_width + card_width_units > max_cards_per_row:
                        # Move to next row with proper spacing
                        current_x = start_x + LM.REGION_PADDING * LM.GRID_SPACING
                        current_y += card_row_spacing  # Use appropriate spacing for card type
                        current_row_width = 0
                        cards_in_current_row = 0
                    
                    # Check if we've exceeded the region height
                    if current_y - start_y >= available_height:
                        print(f"Warning: Cards in {board_name} exceed region height")
                        break
                    
                    # Place the card
                    deck.update_position(board_name, card_name, (current_x, current_y), 
                                       deck.get_pos_index(board_name, card_name, entry["position"]))
                    
                    # Debug output for card placement
                    if card_type == "site":
                        print(f"Placed site card '{card_name}' at ({current_x}, {current_y}) "
                              f"with width_units={card_width_units}, row_spacing={card_row_spacing}")
                    else:
                        print(f"Placed normal card '{card_name}' at ({current_x}, {current_y}) "
                              f"with width_units={card_width_units}, row_spacing={card_row_spacing}")
                    
                    # Update position for next card
                    current_x += grid_unit * card_width_units
                    current_row_width += card_width_units
                    cards_in_current_row += 1
            except Exception as e:
                print(f"Warning: Error placing card '{card_name}' in grid: {e}")
                continue
    
    def _get_deck_elements(self, deck: Deck, card_lookup: Dict[str, Any]) -> set:
        """Get unique elements in the deck (excluding avatar)"""
        elements = set()
        for board_name, board_data in deck.deck.items():
            if board_name == "avatar":
                continue
            for card_name, entries in board_data.items():
                card_data = card_lookup.get(card_name, {})
                card_elements = card_data.get("card_data", {}).get("elements", [])
                elements.update(card_elements)
        return elements
    
    def _place_deck_two_elements(self, deck: Deck, position: Tuple[int, int], card_manager: Card_Manager):
        """Place deck with 2 elements using the new layout approach"""
        start_x, start_y = position
        card_spacing_x, card_spacing_y = LM.GRID_SPACING * LM.SHORT_EDGE_SNAP_RATIO, LM.GRID_SPACING * LM.LONG_EDGE_SNAP_RATIO  # 110x165
        site_spacing_x, site_spacing_y = LM.GRID_SPACING * LM.LONG_EDGE_SNAP_RATIO, LM.GRID_SPACING * LM.SHORT_EDGE_SNAP_RATIO  # 165x110 for sites
        group_padding = LM.GRID_SPACING * LM.REGION_PADDING
        board_padding = LM.GRID_SPACING * LM.BOARD_PADDING
        
        # Get deck elements and card data
        deck_elements = self._get_deck_elements(deck, card_manager.card_data_lookup)
        deck_elements = [e for e in deck_elements if e not in ["Multi", "None"]]
        
        # Place avatar in top left
        if "avatar" in deck.deck and deck.deck["avatar"]:
            avatar_cards = list(deck.deck["avatar"].keys())
            if avatar_cards:
                avatar_name = avatar_cards[0]
                avatar_entries = deck.deck["avatar"][avatar_name]
                for i, entry in enumerate(avatar_entries):
                    deck.update_position("avatar", avatar_name, (start_x, start_y), i)
        
        # Calculate element column positions (6 columns each)
        element_columns = {}
        current_x = start_x + card_spacing_x + group_padding
        for element in deck_elements:
            element_columns[element] = current_x
            current_x += card_spacing_x * 6 + group_padding
        
        # Place mainboard cards by element and type
        for element in deck_elements:
            element_x = element_columns[element]
            current_y = start_y
            
            # Place minions first (6 columns)
            self._place_cards_by_type_in_element(deck, "mainboard", [element], ["minion"], 
                                                (element_x, current_y), card_spacing_x, card_spacing_y, 6)
            current_y += card_spacing_y
            
            # Place magic and aura together (6 columns)
            self._place_cards_by_type_in_element(deck, "mainboard", [element], ["magic", "aura"], 
                                                (element_x, current_y), card_spacing_x, card_spacing_y, 6)
            current_y += card_spacing_y
        
        # Place multi-element and none-element cards (5 columns)
        multi_none_x = current_x
        current_y = start_y
        self._place_cards_by_type_in_element(deck, "mainboard", ["Multi", "None"], ["minion", "magic", "aura"], 
                                            (multi_none_x, current_y), card_spacing_x, card_spacing_y, 5)
        current_y += card_spacing_y
        
        # Place sites (4 columns wide due to landscape orientation)
        sites_x = multi_none_x + card_spacing_x * 5 + group_padding
        self._place_cards_by_type_in_element(deck, "mainboard", deck_elements + ["Multi", "None"], ["site"], 
                                            (sites_x, current_y), site_spacing_x, site_spacing_y, 4)
        
        # Find the lowest Y position for sideboard/maybeboard placement
        lowest_y = start_y
        for board_name, board_data in deck.deck.items():
            for card_name, entries in board_data.items():
                for entry in entries:
                    lowest_y = max(lowest_y, entry["position"][1])
        
        # Place sideboard (10 columns wide)
        sideboard_y = lowest_y + card_spacing_y + group_padding
        self._place_secondary_board_wide(deck, "sideboard", (start_x, sideboard_y), card_spacing_x, card_spacing_y, 10)
        
        # Place maybeboard (10 columns wide)
        maybeboard_y = sideboard_y + card_spacing_y + board_padding
        self._place_secondary_board_wide(deck, "maybeboard", (start_x, maybeboard_y), card_spacing_x, card_spacing_y, 10)
    
    def _place_cards_by_type_in_element(self, deck: Deck, board_name: str, elements: list, card_types: list, 
                                       position: Tuple[int, int], spacing_x: int, spacing_y: int, columns: int):
        """Place cards of specific types and elements in a grid"""
        start_x, start_y = position
        current_x, current_y = start_x, start_y
        cards_in_current_row = 0
        
        for card_name, entries in deck.deck.get(board_name, {}).items():
            # Check if card matches the element and type criteria
            if not self._card_matches_criteria(card_name, elements, card_types):
                continue
                
            for entry in entries:
                if cards_in_current_row >= columns:
                    current_x = start_x
                    current_y += spacing_y
                    cards_in_current_row = 0
                
                deck.update_position(board_name, card_name, (current_x, current_y), 
                                   deck.get_pos_index(board_name, card_name, entry["position"]))
                
                current_x += spacing_x
                cards_in_current_row += 1
    
    def _card_matches_criteria(self, card_name: str, elements: list, card_types: list) -> bool:
        """Check if a card matches the element and type criteria"""
        # This would need to be implemented based on your card data structure
        # For now, return True to place all cards
        return True
    
    def _place_secondary_board_wide(self, deck: Deck, board_name: str, position: Tuple[int, int], 
                                   spacing_x: int, spacing_y: int, columns: int):
        """Place sideboard or maybeboard cards in a wide grid"""
        start_x, start_y = position
        current_x, current_y = start_x, start_y
        cards_in_current_row = 0
        
        if board_name not in deck.deck:
            return
            
        for card_name, entries in deck.deck[board_name].items():
            for entry in entries:
                if cards_in_current_row >= columns:
                    current_x = start_x
                    current_y += spacing_y
                    cards_in_current_row = 0
                
                deck.update_position(board_name, card_name, (current_x, current_y), 
                                   deck.get_pos_index(board_name, card_name, entry["position"]))
                
                current_x += spacing_x
                cards_in_current_row += 1
    
    def _place_deck_standard(self, deck: Deck, position: Tuple[int, int], card_manager: Card_Manager):
        """Original standard deck placement logic"""
        start_x, start_y = position
        card_spacing_x, card_spacing_y = LM.GRID_SPACING * LM.SHORT_EDGE_SNAP_RATIO, LM.GRID_SPACING * LM.LONG_EDGE_SNAP_RATIO  # 110x165
        site_spacing_x, site_spacing_y = LM.GRID_SPACING * LM.LONG_EDGE_SNAP_RATIO, LM.GRID_SPACING * LM.SHORT_EDGE_SNAP_RATIO  # 165x110 for sites
        group_padding = LM.GRID_SPACING * LM.REGION_PADDING
        board_padding = LM.GRID_SPACING * LM.BOARD_PADDING
        
        # Get card data lookup
        card_lookup = card_manager.card_data_lookup
        
        # Group cards by type and element
        grouped_cards = self._group_cards_by_type_and_element(deck, card_lookup)
        
        # Place avatar first (top left corner)
        if "avatar" in deck.deck and deck.deck["avatar"]:
            avatar_cards = list(deck.deck["avatar"].keys())
            if avatar_cards:
                avatar_name = avatar_cards[0]
                avatar_entries = deck.deck["avatar"][avatar_name]
                for i, entry in enumerate(avatar_entries):
                    deck.update_position("avatar", avatar_name, (start_x, start_y), i)
        
        # Calculate starting position for main cards (after avatar)
        current_x = start_x + card_spacing_x + group_padding
        current_y = start_y
        
        # Place cards by type groups in order: minions, magic, aura/artifact, sites
        type_order = ["minion", "magic", "aura", "site"]
        
        for card_type in type_order:
            if card_type not in grouped_cards:
                continue
                
            # Check if this is a site (horizontal cards)
            is_site = card_type == "site"
            spacing_x = site_spacing_x if is_site else card_spacing_x
            spacing_y = site_spacing_y if is_site else card_spacing_y
            max_cards_per_row = 9 if is_site else 6  # 9 rows for sites, 6 for others
            
            # Group by element
            for element, cards in grouped_cards[card_type].items():
                cards_in_current_row = 0
                row_start_x = current_x
                
                for card_name, entries in cards.items():
                    for entry in entries:
                        # Check if we need a new row (more than max_cards_per_row in current row)
                        if cards_in_current_row >= max_cards_per_row:
                            current_x = row_start_x
                            current_y += spacing_y
                            cards_in_current_row = 0
                        
                        # Update card position
                        deck.update_position("mainboard", card_name, (current_x, current_y), 
                                           deck.get_pos_index("mainboard", card_name, entry["position"]))
                        
                        current_x += spacing_x
                        cards_in_current_row += 1
                
                # Move to next element column (no extra spacing between cards, only between groups)
                current_x += group_padding
            
            # Move to next type group
            current_x = start_x + card_spacing_x + group_padding
            current_y += spacing_y + group_padding
        
        # Calculate the total width used by mainboard for sideboard/maybeboard positioning
        mainboard_width = current_x - start_x
        
        # Place sideboard and maybeboard underneath the mainboard
        sideboard_y = current_y + group_padding
        self._place_secondary_board(deck, "sideboard", (start_x, sideboard_y), card_spacing_x, card_spacing_y, mainboard_width)
        
        maybeboard_y = sideboard_y + card_spacing_y + board_padding
        self._place_secondary_board(deck, "maybeboard", (start_x, maybeboard_y), card_spacing_x, card_spacing_y, mainboard_width)
    
    def _group_cards_by_type_and_element(self, deck: Deck, card_lookup: Dict[str, Any]) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Group cards by type and element"""
        grouped = {}
        
        for board in ["mainboard", "sideboard", "maybeboard"]:
            if board not in deck.deck:
                continue
                
            for card_name, entries in deck.deck[board].items():
                # Get card data from lookup
                card_data = card_lookup.get(card_name, {})
                card_type = card_data.get("card_data", {}).get("type", "unknown").lower()
                elements = card_data.get("card_data", {}).get("elements", [])
                
                # Normalize card type
                if card_type in ["aura", "artifact"]:
                    card_type = "aura"  # Group together
                
                if card_type not in grouped:
                    grouped[card_type] = {}
                
                # Group by primary element (first element, or "none" if no elements)
                primary_element = elements[0] if elements else "none"
                if primary_element not in grouped[card_type]:
                    grouped[card_type][primary_element] = {}
                
                grouped[card_type][primary_element][card_name] = entries
        
        return grouped
    
    def _place_secondary_board(self, deck: Deck, board_name: str, position: Tuple[int, int], 
                              spacing_x: int, spacing_y: int, mainboard_width: int):
        """Place sideboard or maybeboard cards"""
        start_x, start_y = position
        current_x, current_y = start_x, start_y
        cards_per_row = 6
        
        if board_name not in deck.deck:
            return
            
        # Calculate how many cards can fit in the mainboard width
        cards_per_row = mainboard_width // spacing_x
        
        cards_in_current_row = 0
        for card_name, entries in deck.deck[board_name].items():
            for entry in entries:
                if cards_in_current_row >= cards_per_row:
                    current_x = start_x
                    current_y += spacing_y
                    cards_in_current_row = 0
                
                deck.update_position(board_name, card_name, (current_x, current_y), 
                                   deck.get_pos_index(board_name, card_name, entry["position"]))
                
                current_x += spacing_x
                cards_in_current_row += 1
    
    def move_deck(self, deck: Deck, position: Tuple[int, int]):
        """
        Move all cards in the deck to new positions, maintaining relative offsets.
        Assumes the avatar position is the deck position, any offsets are calculated before calling this function.
        """
        new_x, new_y = position
        
        # Find current avatar position as reference
        avatar_pos = None
        if "avatar" in deck.deck and deck.deck["avatar"]:
            avatar_cards = list(deck.deck["avatar"].keys())
            if avatar_cards:
                avatar_name = avatar_cards[0]
                avatar_entries = deck.deck["avatar"][avatar_name]
                if avatar_entries:
                    avatar_pos = avatar_entries[0]["position"]
        
        if not avatar_pos:
            print("No avatar found to use as reference position")
            return
        
        # Calculate offset from current avatar position to new position
        offset_x = new_x - avatar_pos[0]
        offset_y = new_y - avatar_pos[1]
        
        # Move all cards by the calculated offset
        for board_name, board_data in deck.deck.items():
            for card_name, entries in board_data.items():
                for i, entry in enumerate(entries):
                    current_pos = entry["position"]
                    new_pos = (current_pos[0] + offset_x, current_pos[1] + offset_y)
                    deck.update_position(board_name, card_name, new_pos, i)
    
    def group_type(self, card_type: str, card_name: str, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Group cards by type and element"""
        grouped = {}
        
        for entry in entries:
            if entry["position"] not in grouped:
                grouped[entry["position"]] = []
            grouped[entry["position"]].append(entry)
        
        return grouped