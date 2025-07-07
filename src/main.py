import csv
import json
import math
import os
import re
import sys
import random
from typing import Dict, List, Optional, Tuple, Any
from difflib import SequenceMatcher
import pygame
import pygame_gui
from pathlib import Path
from tqdm import tqdm

# Import local modules
from CardInfo import CardInfo
from Curiosa_Decks import get_curiosa_deck
from Util_Debug import DebugDisplay
import Util_Config as config

CORS_PROXY = "https://corsproxy.innkeeper1.workers.dev/?url="
CURIOSA_API_BASE = "https://curiosa.io/api/decks/"
SORCERY_API = "https://api.sorcerytcg.com/api/cards"
CARD_DATA_PATH = "data/CardList.json"
CARD_ASSETS_PATH = "assets/Cards"


class DeckBuilder:
    def __init__(self):
        pygame.init()
        self.screen_width = config.DEFAULT_SCREEN_WIDTH
        self.screen_height = config.DEFAULT_SCREEN_HEIGHT
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        pygame.display.set_caption("Sorcery Deck Builder")
        
        # Initialize clock for debug display
        self.clock = pygame.time.Clock()
        
        # Initialize debug display
        DebugDisplay.initialize(self.screen, self.clock)
        
        # Initialize GUI manager
        self.gui_manager = pygame_gui.UIManager((self.screen_width, self.screen_height))
        
        # Collection data
        self.collection = {}  # {card_name: {count: int, image_path: str, card_data: dict}}
        # self.card_objects = {}  # {card_name: Card}
        
        # Image cache for loaded card images
        self.image_cache = {}
        
        # Grid layout
        self.grid_cards = []  # List of cards in grid order
        self.card_positions: List[Tuple[float, float]] = []  # Store positions for each card
        self.card_velocities: List[Tuple[float, float]] = []  # Store velocities for collision resolution
        self.card_size = config.DEFAULT_CARD_SIZE
        self.grid_spacing = config.DEFAULT_GRID_SPACING
        self.cards_per_row = config.DEFAULT_CARDS_PER_ROW
        
        # Camera/viewport
        self.camera_x = 0
        self.camera_y = 0
        self.zoom = config.DEFAULT_ZOOM
        self.target_zoom = config.DEFAULT_ZOOM  # Target zoom for smooth interpolation
        self.grid_zoom = config.DEFAULT_ZOOM  # Smooth zoom for grid
        self.dragging = False
        self.drag_start = None
        
        # Card dragging
        self.dragged_card = None
        self.dragged_card_index = None  # Index of the dragged card
        self.dragged_card_pos = None
        self.drag_offset = None
        
        # Selection system
        self.selected_cards = set()  # Set of selected card indices
        self.selection_rect = None  # (start_x, start_y, end_x, end_y) in screen coordinates
        self.is_selecting = False  # Whether currently drawing selection rectangle
        self.selection_start = None  # Starting point of selection rectangle
        self.shift_held = False  # Whether shift key is currently held
        
        # Hover preview
        self.hovered_card = None
        self.hovered_card_index = None
        self.preview_size = (300, 420)  # Larger size for preview
        
        # Save/Load functionality
        self.save_file_path = "saved_layout.json"
        
        # Colors
        self.BACKGROUND_COLOR = config.BACKGROUND_COLOR
        self.GRID_COLOR = config.GRID_COLOR
        self.CARD_BORDER_COLOR = config.CARD_BORDER_COLOR
        
        # Load data
        self.load_card_data()
        self.load_collection("assets/collection-2025-07-07T01_38_01.445Z.csv", force_update=True)
        
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
            
            with open(json_cache_path, 'w', encoding='utf-8') as file:
                json.dump(cache_data, file, indent=2, ensure_ascii=False)
            
            cache_msg = f"Saved collection cache to {json_cache_path}"
            print(cache_msg)
            DebugDisplay.add_message(cache_msg)
            
        except Exception as e:
            error_msg = f"Failed to save cache: {e}"
            print(error_msg)
            DebugDisplay.add_message(error_msg)
        
        success_msg = f"Loaded {len(self.collection)} unique cards from collection"
        print(success_msg)
        DebugDisplay.add_message(success_msg)
    
    def load_card_data(self):
        """Load card data from JSON file"""
        json_path = CARD_DATA_PATH
        if not os.path.exists(json_path):
            error_msg = f"Card data file not found: {json_path}"
            print(error_msg)
            DebugDisplay.add_message(error_msg)
            return
            
        with open(json_path, 'r', encoding='utf-8') as file:
            self.card_data = json.load(file)
        
        # Create lookup dictionary
        self.card_data_lookup = {}
        for card in self.card_data:
            self.card_data_lookup[card['name']] = card
        
        success_msg = f"Loaded {len(self.card_data)} cards from API data"
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
    
    def layout_collection_clusters(self):
        """Layout collection using sphere-based positioning with collision detection"""
        self.grid_cards = []
        self.card_positions = []
        
        # Create CardInfo objects for all cards
        all_cards = []
        for card_name, card_info in self.collection.items():
            card_info_obj = CardInfo(card_info['image_path'], card_info['card_data'])
            all_cards.append(card_info_obj)
        
        # Start the nested layout from the center
        center_x = 800  # Screen center X
        center_y = 600  # Screen center Y
        
        # Begin hierarchical layout
        self.layout_sphere_based_clusters(all_cards, center_x, center_y, 0)
        
        print(f"Laid out {len(self.grid_cards)} cards in sphere-based clusters")
    
    def layout_sphere_based_clusters(self, cards, center_x, center_y, level):
        """Layout cards using sphere-based positioning with collision detection"""
        if not cards:
            return
        
        if level == 0:  # Elements level
            self.layout_elements_spheres(cards, center_x, center_y)
        elif level == 1:  # Types level
            self.layout_types_grid(cards, center_x, center_y)
    
    def layout_elements_spheres(self, cards, center_x, center_y):
        """Layout cards by elements using sphere positioning"""
        # Group cards by elements
        element_groups = {}
        
        for card in cards:
            element = self.get_card_element(card)
            if element not in element_groups:
                element_groups[element] = []
            element_groups[element].append(card)
        
        # Sort groups by size and find smallest (first level: smallest in center)
        sorted_groups = sorted(element_groups.items(), key=lambda x: len(x[1]))
        smallest_group_name, smallest_group_cards = sorted_groups[0]
        vertex_groups = sorted_groups[1:]
        
        # Calculate sphere positions with collision detection
        sphere_positions = self.calculate_sphere_positions(vertex_groups, center_x, center_y)
        
        # Place smallest group in center
        if smallest_group_cards:
            self.layout_sphere_based_clusters(smallest_group_cards, center_x, center_y, 1)
        
        # Place other groups at calculated sphere positions
        for i, ((element_name, element_cards), (sphere_x, sphere_y)) in enumerate(zip(vertex_groups, sphere_positions)):
            self.layout_sphere_based_clusters(element_cards, sphere_x, sphere_y, 1)
    
    def layout_types_grid(self, cards, center_x, center_y):
        """Layout cards by types, then sort by subtype, cost, and attack within each grid"""
        # Group cards by types
        type_groups = {}
        
        for card in cards:
            card_type = self.get_card_type(card)
            if card_type not in type_groups:
                type_groups[card_type] = []
            type_groups[card_type].append(card)
        
        # Sort groups by size and find largest (second level: largest in center)
        sorted_groups = sorted(type_groups.items(), key=lambda x: len(x[1]), reverse=True)
        largest_group_name, largest_group_cards = sorted_groups[0]
        vertex_groups = sorted_groups[1:]
        
        # Calculate sphere positions with collision detection
        sphere_positions = self.calculate_sphere_positions(vertex_groups, center_x, center_y)
        
        # Place largest group in center (sorted by subtype, cost, then attack)
        if largest_group_cards:
            sorted_center_cards = self.sort_cards_by_subtype_cost_attack(largest_group_cards)
            self.arrange_cards_in_grid(sorted_center_cards, center_x, center_y)
        
        # Place other groups at calculated sphere positions (sorted by subtype, cost, then attack)
        for i, ((type_name, type_cards), (sphere_x, sphere_y)) in enumerate(zip(vertex_groups, sphere_positions)):
            sorted_type_cards = self.sort_cards_by_subtype_cost_attack(type_cards)
            self.arrange_cards_in_grid(sorted_type_cards, sphere_x, sphere_y)
    
    def sort_cards_by_subtype_cost_attack(self, cards):
        """Sort cards by subtype first, then cost, then attack"""
        return sorted(cards, key=lambda card: (
            self.get_card_subtype(card) or 'None',  # Subtype first
            self.get_card_cost(card) if self.get_card_cost(card) is not None else float('inf'),  # Cost second
            self.get_card_attack(card) if self.get_card_attack(card) is not None else float('inf')  # Attack third
        ))
    
    def calculate_sphere_positions(self, groups, center_x, center_y):
        """Calculate sphere positions with collision detection and 50px minimum gap"""
        if not groups:
            return []
        
        # Calculate sphere diameters based on number of items in each group
        sphere_diameters = []
        for group_name, group_cards in groups:
            diameter = 300 * math.sqrt(len(group_cards))  # 200px per item
            sphere_diameters.append(diameter)
        
        # Start with initial polygon positions
        num_groups = len(groups)
        initial_positions = []
        
        for i in range(num_groups):
            angle = (i * 360 / num_groups - 90) * (3.14159 / 180)
            # Start with a reasonable radius based on largest sphere
            max_diameter = max(sphere_diameters)
            radius = max_diameter * 0.8
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
            initial_positions.append((x, y))
        
        # Apply collision detection and separation
        final_positions = self.resolve_sphere_collisions(initial_positions, sphere_diameters, center_x, center_y)
        
        return final_positions
    
    def resolve_sphere_collisions(self, positions, diameters, center_x, center_y):
        """Resolve sphere collisions by moving spheres apart"""
        if len(positions) <= 1:
            return positions
        
        # Convert to list for modification
        positions = list(positions)
        diameters = list(diameters)
        
        # Add minimum gap between spheres
        min_gap = 50
        
        # Iteratively resolve collisions
        max_iterations = 1000
        for iteration in range(max_iterations):
            moved = False
            
            for i in range(len(positions)):
                for j in range(i + 1, len(positions)):
                    x1, y1 = positions[i]
                    x2, y2 = positions[j]
                    r1 = diameters[i] / 2
                    r2 = diameters[j] / 2
                    
                    # Calculate distance between centers
                    dx = x2 - x1
                    dy = y2 - y1
                    distance = math.sqrt(dx * dx + dy * dy)
                    
                    # Check if spheres overlap (including minimum gap)
                    min_distance = r1 + r2 + min_gap
                    
                    if distance < min_distance:
                        moved = True
                        
                        # Calculate separation vector
                        if distance > 0:
                            # Normalize and scale separation
                            separation = (min_distance - distance) / distance
                            move_x = dx * separation * 0.5
                            move_y = dy * separation * 0.5
                        else:
                            # Spheres are exactly on top of each other
                            move_x = min_distance * 0.5
                            move_y = 0
                        
                        # Move spheres apart
                        positions[i] = (x1 - move_x, y1 - move_y)
                        positions[j] = (x2 + move_x, y2 + move_y)
            
            # If no collisions, we're done
            if not moved:
                break
        
        return positions
    
    def arrange_cards_in_grid(self, cards, center_x, center_y):
        """Arrange cards in a grid pattern at the specified center"""
        if not cards:
            return
        
        card_spacing = 25
        num_cards = len(cards)
        grid_width = round(math.sqrt(num_cards)) + 1
        grid_height = (num_cards + grid_width - 1) // grid_width
        
        # Calculate total grid size
        grid_total_width = grid_width * (self.card_size[0] + card_spacing) - card_spacing
        grid_total_height = grid_height * (self.card_size[1] + card_spacing) - card_spacing
        
        # Center the grid
        grid_start_x = center_x - grid_total_width / 2
        grid_start_y = center_y - grid_total_height / 2
        
        # Place cards in grid
        for j, card in enumerate(cards):
            row = j // grid_width
            col = j % grid_width
            
            card_x = float(grid_start_x + col * (self.card_size[0] + card_spacing))
            card_y = float(grid_start_y + row * (self.card_size[1] + card_spacing))
            
            # Add small random movement to initial positions
            random_offset_x = random.uniform(-5, 5)
            random_offset_y = random.uniform(-5, 5)
            card_x += random_offset_x
            card_y += random_offset_y
            
            self.grid_cards.append(card)
            self.card_positions.append((card_x, card_y))
    
    def get_card_element(self, card):
        """Get the element of a card"""
        if card.elements:
            if not card.elements or card.elements == 'None':
                return 'None'
            elif ',' in card.elements or ' ' in card.elements:
                return 'Multiple'
            else:
                return card.elements.strip()
        return 'None'
    
    def get_card_type(self, card):
        """Get the type of a card"""
        return card.type or 'Unknown'
    
    def get_card_subtype(self, card):
        """Get the subtype of a card"""
        return card.subtypes or 'None'
    
    def get_card_cost(self, card):
        """Get the cost of a card"""
        if card.cost is not None:
            try:
                return int(card.cost)
            except (ValueError, TypeError):
                return None
        return None
    
    def get_card_attack(self, card):
        """Get the attack of a card"""
        if card.attack is not None:
            try:
                return int(card.attack)
            except (ValueError, TypeError):
                return None
        return None
    
    def get_grid_position(self, index: int) -> Tuple[int, int]:
        """Get grid position for card index"""
        row = index // self.cards_per_row
        col = index % self.cards_per_row
        return (col, row)
    
    def get_screen_position(self, grid_pos: Tuple[int, int]) -> Tuple[int, int]:
        """Convert grid position to screen position with camera and zoom"""
        x = (grid_pos[0] * (self.card_size[0] + self.grid_spacing) + self.camera_x) * self.zoom
        y = (grid_pos[1] * (self.card_size[1] + self.grid_spacing) + self.camera_y) * self.zoom
        return (int(x), int(y))
    
    def get_card_index_from_screen(self, screen_pos: Tuple[int, int]) -> Optional[int]:
        """Find which card is at the given screen position"""
        # Check each card to see if the screen position is within its bounds
        for i in range(len(self.grid_cards)):
            if i < len(self.card_positions):
                cluster_pos = self.card_positions[i]
                card_screen_pos = self.get_screen_position_from_cluster(cluster_pos)
                
                # Get the correct display size for this card (accounting for rotation)
                card = self.grid_cards[i]
                card_size = self.get_card_display_size(card)
                
                # Check if screen position is within this card's bounds
                if (card_screen_pos[0] <= screen_pos[0] <= card_screen_pos[0] + card_size[0] and
                    card_screen_pos[1] <= screen_pos[1] <= card_screen_pos[1] + card_size[1]):
                    return i
        
        return None
    
    def insert_card_at_position(self, card: CardInfo, position: int):
        """Insert card at specific position, shifting others"""
        if position < 0:
            position = 0
        if position > len(self.grid_cards):
            position = len(self.grid_cards)
        
        self.grid_cards.insert(position, card)
    
    def remove_card_at_position(self, position: int):
        """Remove card at specific position"""
        if 0 <= position < len(self.grid_cards):
            self.grid_cards.pop(position)
    
    def handle_mouse_events(self, event):
        """Handle mouse events for card interaction"""
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:  # Left click
                self.handle_left_click(event.pos)
            elif event.button == 3:  # Right click
                self.handle_right_click(event.pos)
            elif event.button == 2:  # Middle click
                self.handle_middle_click(event.pos)
        
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:  # Left click release
                self.handle_left_release(event.pos)
            elif event.button == 2:  # Middle click release
                self.handle_middle_release()
            elif event.button == 3:  # Right click release
                self.handle_right_release()
        
        elif event.type == pygame.MOUSEMOTION:
            self.handle_mouse_motion(event.pos)
        
        elif event.type == pygame.MOUSEWHEEL:
            # Get current mouse position for zoom centering
            mouse_pos = pygame.mouse.get_pos()
            self.handle_mouse_wheel(event.y, mouse_pos)
    
    def handle_left_click(self, pos):
        """Handle left click for card dragging or selection rectangle"""
        card_index = self.get_card_index_from_screen(pos)
        if card_index is not None and card_index < len(self.grid_cards):
            # Clicked on a card - handle card selection and dragging
            if card_index in self.selected_cards:
                # Move all selected cards together
                self.dragged_card = self.grid_cards[card_index]
                self.dragged_card_index = card_index
                self.dragged_card_pos = pos
                # Calculate offset from card's current screen position
                cluster_pos = self.card_positions[card_index]
                card_screen_pos = self.get_screen_position_from_cluster(cluster_pos)
                self.drag_offset = (pos[0] - card_screen_pos[0], pos[1] - card_screen_pos[1])
            else:
                # Handle shift-click for adding to selection
                if self.shift_held:
                    # Add card to selection without clearing existing selection
                    self.selected_cards.add(card_index)
                    # Start dragging the newly added card (which will move all selected cards)
                    self.dragged_card = self.grid_cards[card_index]
                    self.dragged_card_index = card_index
                    self.dragged_card_pos = pos
                    # Calculate offset from card's current screen position
                    cluster_pos = self.card_positions[card_index]
                    card_screen_pos = self.get_screen_position_from_cluster(cluster_pos)
                    self.drag_offset = (pos[0] - card_screen_pos[0], pos[1] - card_screen_pos[1])
                else:
                    # Clear selection and select/drag single card
                    self.selected_cards.clear()
                    self.selected_cards.add(card_index)  # Add the clicked card to selection
                    self.dragged_card = self.grid_cards[card_index]
                    self.dragged_card_index = card_index
                    self.dragged_card_pos = pos
                    # Calculate offset from card's current screen position
                    cluster_pos = self.card_positions[card_index]
                    card_screen_pos = self.get_screen_position_from_cluster(cluster_pos)
                    self.drag_offset = (pos[0] - card_screen_pos[0], pos[1] - card_screen_pos[1])
        else:
            # Clicked on background - deselect all cards and start selection rectangle
            self.selected_cards.clear()
            self.is_selecting = True
            self.selection_start = pos
            self.selection_rect = (pos[0], pos[1], pos[0], pos[1])
    
    def handle_left_release(self, pos):
        """Handle left click release for card placement or selection finalization"""
        if self.dragged_card and self.drag_offset:
            # Handle card dragging
            cluster_x = ((pos[0] - self.drag_offset[0]) / self.zoom) - self.camera_x
            cluster_y = ((pos[1] - self.drag_offset[1]) / self.zoom) - self.camera_y
            
            if self.dragged_card_index is not None and self.dragged_card_index < len(self.card_positions):
                # Get the original position of the dragged card
                original_pos = self.card_positions[self.dragged_card_index]
                # Calculate the movement delta
                delta_x = cluster_x - original_pos[0]
                delta_y = cluster_y - original_pos[1]
                
                # Move all selected cards by the same delta
                for selected_index in self.selected_cards:
                    if selected_index < len(self.card_positions):
                        old_pos = self.card_positions[selected_index]
                        self.card_positions[selected_index] = (old_pos[0] + delta_x, old_pos[1] + delta_y)
            
            self.dragged_card = None
            self.dragged_card_index = None
            self.dragged_card_pos = None
            self.drag_offset = None
        elif self.is_selecting:
            # Handle selection rectangle finalization
            self.is_selecting = False
            self.selection_start = None
            self.selection_rect = None
    
    def handle_right_click(self, pos):
        """Handle right click for camera panning"""
        self.dragging = True
        self.drag_start = pos
    
    def handle_right_release(self):
        """Handle right click release"""
        self.dragging = False
        self.drag_start = None
    
    def handle_middle_click(self, pos):
        """Handle middle click for camera panning"""
        self.dragging = True
        self.drag_start = pos
    
    def handle_middle_release(self):
        """Handle middle click release"""
        self.dragging = False
        self.drag_start = None
    
    def handle_mouse_motion(self, pos):
        """Handle mouse motion for smooth dragging"""
        if self.dragging and self.drag_start:
            # Camera panning
            dx = pos[0] - self.drag_start[0]
            dy = pos[1] - self.drag_start[1]
            self.camera_x += dx / self.zoom
            self.camera_y += dy / self.zoom
            self.drag_start = pos
        
        elif self.dragged_card and self.dragged_card_pos:
            # Update dragged card position with smooth animation
            self.dragged_card_pos = pos
        
        elif self.is_selecting and self.selection_start:
            # Update selection rectangle
            self.selection_rect = (
                min(self.selection_start[0], pos[0]),
                min(self.selection_start[1], pos[1]),
                max(self.selection_start[0], pos[0]),
                max(self.selection_start[1], pos[1])
            )
            # Check for cards in selection rectangle
            self.update_selection()
        
        # Check for card hover
        self.check_card_hover(pos)
    
    def check_card_hover(self, mouse_pos):
        """Check if mouse is hovering over a card and update hover state"""
        # Find which card the mouse is over
        card_index = self.get_card_index_from_screen(mouse_pos)
        
        if card_index is not None and card_index < len(self.grid_cards):
            # Mouse is over a card
            if self.hovered_card_index != card_index:
                # New card being hovered
                self.hovered_card = self.grid_cards[card_index]
                self.hovered_card_index = card_index
        else:
            # Mouse is not over any card
            self.hovered_card = None
            self.hovered_card_index = None
    
    def update_selection(self):
        """Update selected cards based on current selection rectangle"""
        if not self.selection_rect:
            return
        
        # Clear current selection
        self.selected_cards.clear()
        
        # Check each card to see if it intersects with the selection rectangle
        for i in range(len(self.grid_cards)):
            if i < len(self.card_positions):
                cluster_pos = self.card_positions[i]
                screen_pos = self.get_screen_position_from_cluster(cluster_pos)
                
                # Get the correct display size for this card (accounting for rotation)
                card = self.grid_cards[i]
                card_size = self.get_card_display_size(card)
                
                # Calculate card bounds in screen coordinates
                card_left = screen_pos[0]
                card_right = screen_pos[0] + card_size[0]
                card_top = screen_pos[1]
                card_bottom = screen_pos[1] + card_size[1]
                
                # Check if card intersects with selection rectangle
                if (card_left < self.selection_rect[2] and card_right > self.selection_rect[0] and
                    card_top < self.selection_rect[3] and card_bottom > self.selection_rect[1]):
                    self.selected_cards.add(i)
    
    def handle_mouse_wheel(self, y, mouse_pos):
        """Handle mouse wheel for zooming centered on mouse position"""
        # Set target zoom instead of immediately changing zoom
        zoom_factor = 1.1 if y > 0 else 0.9
        self.target_zoom *= zoom_factor
        self.target_zoom = max(0.1, min(3.0, self.target_zoom))  # Clamp target zoom
        
        # Store mouse position for smooth zoom centering
        self.zoom_mouse_pos = mouse_pos
    
    def handle_keyboard_events(self, event):
        """Handle keyboard events"""
        if event.key == pygame.K_s:
            # Save layout
            self.save_layout()
        elif event.key == pygame.K_l:
            # Load layout
            self.load_layout()
        elif event.key == pygame.K_ESCAPE:
            # Clear selection
            self.selected_cards.clear()
            self.selection_rect = None
            self.is_selecting = False
            self.selection_start = None
        elif event.key == pygame.K_LSHIFT or event.key == pygame.K_RSHIFT:
            # Track shift key press
            self.shift_held = True
    
    def handle_keyboard_up_events(self, event):
        """Handle keyboard key release events"""
        if event.key == pygame.K_LSHIFT or event.key == pygame.K_RSHIFT:
            # Track shift key release
            self.shift_held = False
    
    def draw_card(self, card: CardInfo, pos: Tuple[int, int], size: Tuple[int, int]):
        """Draw a card at the specified position"""
        # Check if this is a Site card that should be rotated
        is_site = card.type == "Site"
        
        # For Site cards, swap width and height for rotation
        if is_site:
            rotated_size = (size[1], size[0])  # Swap width and height
        else:
            rotated_size = size
        
        # Draw card border
        pygame.draw.rect(self.screen, self.CARD_BORDER_COLOR, 
                        (pos[0], pos[1], rotated_size[0], rotated_size[1]), 2)
        
        # Try to load and display the card image
        if card.image_url and os.path.exists(card.image_url):
            try:
                # Load the image if not already cached
                if card.image_url not in self.image_cache:
                    self.image_cache[card.image_url] = pygame.image.load(card.image_url)
                
                # Scale the image to fit the card size with antialiasing
                scaled_image = pygame.transform.smoothscale(self.image_cache[card.image_url], size)
                
                # Rotate the image if it's a Site card
                if is_site:
                    rotated_image = pygame.transform.rotate(scaled_image, -90)  # Clockwise rotation
                    # Adjust position for rotated image
                    rotated_pos = (pos[0] + (rotated_size[0] - rotated_image.get_width()) // 2,
                                 pos[1] + (rotated_size[1] - rotated_image.get_height()) // 2)
                    self.screen.blit(rotated_image, rotated_pos)
                else:
                    # Draw the scaled image normally
                    self.screen.blit(scaled_image, pos)
                
            except Exception:
                # Fallback to background if image loading fails
                pygame.draw.rect(self.screen, (80, 80, 80), 
                                (pos[0] + 2, pos[1] + 2, rotated_size[0] - 4, rotated_size[1] - 4))
                self._draw_card_text(card, pos, rotated_size, is_site)
        else:
            # Draw card background if no image
            pygame.draw.rect(self.screen, (80, 80, 80), 
                            (pos[0] + 2, pos[1] + 2, rotated_size[0] - 4, rotated_size[1] - 4))
            self._draw_card_text(card, pos, rotated_size, is_site)
    
    def draw_card_transparent(self, card: CardInfo, pos: Tuple[int, int], size: Tuple[int, int], alpha: float):
        """Draw a card with transparency at the specified position"""
        # Check if this is a Site card that should be rotated
        is_site = card.type == "Site"
        
        # For Site cards, swap width and height for rotation
        if is_site:
            rotated_size = (size[1], size[0])  # Swap width and height
        else:
            rotated_size = size
        
        # Create a temporary surface for the card
        card_surface = pygame.Surface(rotated_size, pygame.SRCALPHA)
        
        # Draw card border with transparency
        border_color = (*self.CARD_BORDER_COLOR, int(255 * alpha))
        pygame.draw.rect(card_surface, border_color, (0, 0, rotated_size[0], rotated_size[1]), 2)
        
        # Try to load and display the card image with transparency
        if card.image_url and os.path.exists(card.image_url):
            try:
                # Load the image if not already cached
                if card.image_url not in self.image_cache:
                    self.image_cache[card.image_url] = pygame.image.load(card.image_url)
                
                # Scale the image to fit the card size with antialiasing
                scaled_image = pygame.transform.smoothscale(self.image_cache[card.image_url], size)
                
                # Rotate the image if it's a Site card
                if is_site:
                    rotated_image = pygame.transform.rotate(scaled_image, -90)  # Clockwise rotation
                    # Create a copy with transparency
                    transparent_image = rotated_image.copy()
                    transparent_image.set_alpha(int(255 * alpha))
                    # Center the rotated image on the surface
                    rotated_pos = ((rotated_size[0] - rotated_image.get_width()) // 2,
                                 (rotated_size[1] - rotated_image.get_height()) // 2)
                    card_surface.blit(transparent_image, rotated_pos)
                else:
                    # Create a copy with transparency
                    transparent_image = scaled_image.copy()
                    transparent_image.set_alpha(int(255 * alpha))
                    # Draw the transparent image
                    card_surface.blit(transparent_image, (0, 0))
                
            except Exception:
                # Fallback to background if image loading fails
                bg_color = (80, 80, 80, int(255 * alpha))
                pygame.draw.rect(card_surface, bg_color, (2, 2, rotated_size[0] - 4, rotated_size[1] - 4))
                self._draw_card_text_transparent(card, card_surface, rotated_size, alpha, is_site)
        else:
            # Draw card background if no image
            bg_color = (80, 80, 80, int(255 * alpha))
            pygame.draw.rect(card_surface, bg_color, (2, 2, rotated_size[0] - 4, rotated_size[1] - 4))
            self._draw_card_text_transparent(card, card_surface, rotated_size, alpha, is_site)
        
        # Draw the transparent card surface to the screen
        self.screen.blit(card_surface, pos)
    
    def _draw_card_text(self, card: CardInfo, pos: Tuple[int, int], size: Tuple[int, int], is_site: bool = False):
        """Draw card text information (fallback when no image)"""
        font = pygame.font.Font(None, 16)
        
        # Adjust text positioning for rotated Site cards
        if is_site:
            # For rotated cards, center text in the rotated dimensions
            center_x = pos[0] + size[0] // 2
            center_y = pos[1] + size[1] // 2
        else:
            center_x = pos[0] + size[0] // 2
            center_y = pos[1] + 20
        
        # Draw card name (truncated)
        name_text = card.name[:15] + "..." if len(card.name) > 15 else card.name
        text_surface = font.render(name_text, True, (255, 255, 255))
        text_rect = text_surface.get_rect(center=(center_x, center_y))
        self.screen.blit(text_surface, text_rect)
        
        # Draw card type
        type_text = card.type if card.type else "Unknown"
        type_surface = font.render(type_text, True, (200, 200, 200))
        type_rect = type_surface.get_rect(center=(center_x, center_y + 20))
        self.screen.blit(type_surface, type_rect)
        
        # Draw cost
        if card.cost is not None:
            cost_text = f"Cost: {card.cost}"
            cost_surface = font.render(cost_text, True, (255, 255, 0))
            cost_rect = cost_surface.get_rect(center=(center_x, center_y + 40))
            self.screen.blit(cost_surface, cost_rect)
    
    def _draw_card_text_transparent(self, card: CardInfo, surface: pygame.Surface, size: Tuple[int, int], alpha: float, is_site: bool = False):
        """Draw card text information with transparency (fallback when no image)"""
        font = pygame.font.Font(None, 16)
        
        # Adjust text positioning for rotated Site cards
        if is_site:
            # For rotated cards, center text in the rotated dimensions
            center_x = size[0] // 2
            center_y = size[1] // 2
        else:
            center_x = size[0] // 2
            center_y = 20
        
        # Draw card name (truncated) with transparency
        name_text = card.name[:15] + "..." if len(card.name) > 15 else card.name
        text_surface = font.render(name_text, True, (255, 255, 255))
        text_surface.set_alpha(int(255 * alpha))
        text_rect = text_surface.get_rect(center=(center_x, center_y))
        surface.blit(text_surface, text_rect)
        
        # Draw card type with transparency
        type_text = card.type if card.type else "Unknown"
        type_surface = font.render(type_text, True, (200, 200, 200))
        type_surface.set_alpha(int(255 * alpha))
        type_rect = type_surface.get_rect(center=(center_x, center_y + 20))
        surface.blit(type_surface, type_rect)
        
        # Draw cost with transparency
        if card.cost is not None:
            cost_text = f"Cost: {card.cost}"
            cost_surface = font.render(cost_text, True, (255, 255, 0))
            cost_surface.set_alpha(int(255 * alpha))
            cost_rect = cost_surface.get_rect(center=(center_x, center_y + 40))
            surface.blit(cost_surface, cost_rect)
    
    def get_card_display_size(self, card: CardInfo) -> Tuple[int, int]:
        """Get the display size of a card (accounting for rotation)"""
        base_size = (int(self.card_size[0] * self.zoom), int(self.card_size[1] * self.zoom))
        if card.type == "Site":
            # For Site cards, swap width and height
            return (base_size[1], base_size[0])
        else:
            return base_size
    
    def draw_clusters(self):
        """Draw the card clusters"""
        # Draw background
        self.screen.fill(self.BACKGROUND_COLOR)
        
        # Draw background grid
        self.draw_background_grid()
        
        # Draw cards in their cluster positions
        for i in range(len(self.grid_cards)):
            if i < len(self.card_positions):
                cluster_pos = self.card_positions[i]
                screen_pos = self.get_screen_position_from_cluster(cluster_pos)
                
                # Get the correct display size for this card (accounting for rotation)
                card = self.grid_cards[i]
                card_size = self.get_card_display_size(card)
                card_right = screen_pos[0] + card_size[0]
                card_bottom = screen_pos[1] + card_size[1]
                
                # Draw if any part of the card is visible on screen
                if (screen_pos[0] < self.screen_width and card_right > 0 and
                    screen_pos[1] < self.screen_height and card_bottom > 0):
                    
                    # Draw card with base size (rotation is handled inside draw_card)
                    base_size = (int(self.card_size[0] * self.zoom), 
                               int(self.card_size[1] * self.zoom))
                    self.draw_card(card, screen_pos, base_size)
        
        # Draw dragged card with offset and transparency
        if self.dragged_card and self.dragged_card_pos and self.drag_offset:
            base_size = (int(self.card_size[0] * self.zoom), 
                        int(self.card_size[1] * self.zoom))
            
            # Calculate movement delta for all selected cards
            if self.dragged_card_index is not None and self.dragged_card_index < len(self.card_positions):
                original_cluster_pos = self.card_positions[self.dragged_card_index]
                original_screen_pos = self.get_screen_position_from_cluster(original_cluster_pos)
                current_screen_pos = (self.dragged_card_pos[0] - self.drag_offset[0], 
                                    self.dragged_card_pos[1] - self.drag_offset[1])
                
                # Calculate the movement delta
                delta_x = current_screen_pos[0] - original_screen_pos[0]
                delta_y = current_screen_pos[1] - original_screen_pos[1]
                
                # Draw transparent versions at original positions for all selected cards
                for selected_index in self.selected_cards:
                    if selected_index < len(self.card_positions):
                        selected_cluster_pos = self.card_positions[selected_index]
                        selected_screen_pos = self.get_screen_position_from_cluster(selected_cluster_pos)
                        selected_card = self.grid_cards[selected_index]
                        self.draw_card_transparent(selected_card, selected_screen_pos, base_size, 0.3)
                
                # Draw all selected cards at their new positions with transparency
                for selected_index in self.selected_cards:
                    if selected_index < len(self.card_positions):
                        selected_cluster_pos = self.card_positions[selected_index]
                        selected_screen_pos = self.get_screen_position_from_cluster(selected_cluster_pos)
                        selected_card = self.grid_cards[selected_index]
                        
                        # Calculate new position with the same delta
                        new_screen_pos = (selected_screen_pos[0] + delta_x, selected_screen_pos[1] + delta_y)
                        self.draw_card_transparent(selected_card, new_screen_pos, base_size, 0.8)
        
        # Draw hover preview
        self.draw_hover_preview()
        
        # Draw selection feedback
        self.draw_selection_feedback()
    
    def get_screen_position_from_cluster(self, cluster_pos: Tuple[float, float]) -> Tuple[int, int]:
        """Convert cluster position to screen position with camera and zoom"""
        x = (cluster_pos[0] + self.camera_x) * self.zoom
        y = (cluster_pos[1] + self.camera_y) * self.zoom
        return (int(x), int(y))
    
    def update_card_positions(self):
        """Update card positions to resolve overlaps"""
        if len(self.card_positions) < 2:
            return
        
        # Initialize velocities if not already done
        if len(self.card_velocities) != len(self.card_positions):
            self.card_velocities = [(0, 0)] * len(self.card_positions)
        
        # Apply damping to velocities and limit max speed
        damping = 0.8
        friction = 0.95  # Friction to bring cards to rest
        max_speed = 5.0  # Maximum velocity per frame
        min_speed = 0.1  # Minimum speed before stopping
        
        for i in range(len(self.card_velocities)):
            # Skip velocity updates for the dragged card
            if i == self.dragged_card_index:
                continue
                
            vx, vy = self.card_velocities[i]
            # Apply damping
            vx *= damping
            vy *= damping
            # Apply friction
            vx *= friction
            vy *= friction
            # Stop very slow movement
            speed = (vx * vx + vy * vy) ** 0.5
            if speed < min_speed:
                vx = 0
                vy = 0
            # Limit max speed
            elif speed > max_speed:
                vx = (vx / speed) * max_speed
                vy = (vy / speed) * max_speed
            self.card_velocities[i] = (vx, vy)
        
        # Check for collisions and apply forces
        min_gap = 20  # Minimum gap between cards
        
        for i in range(len(self.card_positions)):
            # Skip collision detection for the dragged card
            if i == self.dragged_card_index:
                continue
                
            for j in range(i + 1, len(self.card_positions)):
                # Skip collision detection for the dragged card
                if j == self.dragged_card_index:
                    continue
                    
                pos1 = self.card_positions[i]
                pos2 = self.card_positions[j]
                
                # Get the correct dimensions for each card (accounting for rotation)
                card1 = self.grid_cards[i]
                card2 = self.grid_cards[j]
                
                # Use original card dimensions (not zoom-scaled) since positions are in cluster coordinates
                rect1_width = self.card_size[1] if card1.type == "Site" else self.card_size[0]
                rect1_height = self.card_size[0] if card1.type == "Site" else self.card_size[1]
                rect2_width = self.card_size[1] if card2.type == "Site" else self.card_size[0]
                rect2_height = self.card_size[0] if card2.type == "Site" else self.card_size[1]
                
                # Calculate rectangle bounds for both cards
                # pos1 and pos2 are the cluster positions (not screen positions)
                rect1_left = pos1[0]
                rect1_right = pos1[0] + rect1_width
                rect1_top = pos1[1]
                rect1_bottom = pos1[1] + rect1_height
                
                rect2_left = pos2[0]
                rect2_right = pos2[0] + rect2_width
                rect2_top = pos2[1]
                rect2_bottom = pos2[1] + rect2_height
                
                # Check for rectangle overlap
                if (rect1_left < rect2_right and rect1_right > rect2_left and
                    rect1_top < rect2_bottom and rect1_bottom > rect2_top):
                    
                    # Cards are overlapping, calculate separation vector
                    # Find the minimum separation distance and direction
                    overlap_x = min(rect1_right - rect2_left, rect2_right - rect1_left)
                    overlap_y = min(rect1_bottom - rect2_top, rect2_bottom - rect1_top)
                    
                    # Choose the axis with smaller overlap for separation
                    if overlap_x < overlap_y:
                        # Separate horizontally
                        if rect1_left < rect2_left:
                            # Card1 is to the left of Card2 - push Card1 left, Card2 right
                            separation_x = -(overlap_x + min_gap)
                            separation_y = 0
                        else:
                            # Card1 is to the right of Card2 - push Card1 right, Card2 left
                            separation_x = overlap_x + min_gap
                            separation_y = 0
                    else:
                        # Separate vertically (Y increases downward in screen coordinates)
                        if rect1_top < rect2_top:
                            # Card1 is above Card2 (smaller Y) - push Card1 up, Card2 down
                            separation_x = 0
                            separation_y = -(overlap_y + min_gap)
                        else:
                            # Card1 is below Card2 (larger Y) - push Card1 down, Card2 up
                            separation_x = 0
                            separation_y = overlap_y + min_gap
                    
                    # Apply separation force with normalized direction and controlled magnitude
                    separation_magnitude = (separation_x * separation_x + separation_y * separation_y) ** 0.5
                    if separation_magnitude > 0:
                        # Normalize the separation vector
                        normalized_x = separation_x / separation_magnitude
                        normalized_y = separation_y / separation_magnitude
                        # Apply a small, constant force in the separation direction
                        force_x = normalized_x * 0.5
                        force_y = normalized_y * 0.5
                    else:
                        force_x = 0
                        force_y = 0
                    
                    # Apply forces to velocities - both cards move away from each other
                    vx1, vy1 = self.card_velocities[i]
                    vx2, vy2 = self.card_velocities[j]
                    
                    # Card1 moves in separation direction
                    self.card_velocities[i] = (vx1 + force_x, vy1 + force_y)
                    # Card2 moves in opposite direction
                    self.card_velocities[j] = (vx2 - force_x, vy2 - force_y)
        
        # Update positions based on velocities
        for i in range(len(self.card_positions)):
            # Skip position updates for the dragged card
            if i == self.dragged_card_index:
                continue
                
            x, y = self.card_positions[i]
            vx, vy = self.card_velocities[i]
            
            # Update position
            new_x = x + vx
            new_y = y + vy
            
            self.card_positions[i] = (int(new_x), int(new_y))
    
    def draw_background_grid(self):
        """Draw a background grid that moves with camera"""
        # Grid spacing based on smooth zoom level (flipped behavior)
        grid_spacing = max(20, int(50 * self.grid_zoom))  # Minimum 20px spacing
        
        # Calculate grid offset based on camera position
        # Negative to make grid move in same direction as cards
        offset_x = int(-self.camera_x * self.grid_zoom) % grid_spacing
        offset_y = int(-self.camera_y * self.grid_zoom) % grid_spacing
        
        # Grid color based on smooth zoom level (darker when zoomed out, lighter when zoomed in)
        grid_alpha = max(30, min(100, int(60 / self.grid_zoom)))
        grid_color = (self.GRID_COLOR[0], self.GRID_COLOR[1], self.GRID_COLOR[2], grid_alpha)
        
        # Draw vertical lines
        for x in range(-offset_x, self.screen_width + grid_spacing, grid_spacing):
            pygame.draw.line(self.screen, grid_color, (x, 0), (x, self.screen_height), 1)
        
        # Draw horizontal lines
        for y in range(-offset_y, self.screen_height + grid_spacing, grid_spacing):
            pygame.draw.line(self.screen, grid_color, (0, y), (self.screen_width, y), 1)
    
    def draw_hover_preview(self):
        """Draw the hover preview in the top right corner"""
        if self.hovered_card is None:
            return
        
        # Check if this is a Site card that should be rotated
        is_site = self.hovered_card.type == "Site"
        
        # For Site cards, create a surface with the correct rotated dimensions
        if is_site:
            # Site cards are rotated 90 degrees, so swap width and height
            surface_size = (self.preview_size[1], self.preview_size[0])  # 420x300
            rotated_size = (self.preview_size[1], self.preview_size[0])  # 420x300
        else:
            surface_size = self.preview_size  # 300x420
            rotated_size = self.preview_size  # 300x420
        
        # Calculate preview position (top left corner with some padding)
        padding = 20
        preview_x = padding
        preview_y = padding
        
        # Draw background for preview
        preview_bg_color = (40, 40, 40, 200)  # Semi-transparent dark background
        preview_surface = pygame.Surface(surface_size, pygame.SRCALPHA)
        pygame.draw.rect(preview_surface, preview_bg_color, (0, 0, surface_size[0], surface_size[1]))
        
        # Draw border
        pygame.draw.rect(preview_surface, self.CARD_BORDER_COLOR, (0, 0, surface_size[0], surface_size[1]), 2)
        
        # Try to load and display the card image
        if self.hovered_card.image_url and os.path.exists(self.hovered_card.image_url):
            try:
                # Load the image if not already cached
                if self.hovered_card.image_url not in self.image_cache:
                    self.image_cache[self.hovered_card.image_url] = pygame.image.load(self.hovered_card.image_url)
                
                # Scale the image to fit the preview size with antialiasing
                scaled_image = pygame.transform.smoothscale(self.image_cache[self.hovered_card.image_url], self.preview_size)
                
                # Rotate the image if it's a Site card
                if is_site:
                    rotated_image = pygame.transform.rotate(scaled_image, -90)  # Clockwise rotation
                    # Center the rotated image on the surface
                    rotated_pos = ((rotated_size[0] - rotated_image.get_width()) // 2,
                                 (rotated_size[1] - rotated_image.get_height()) // 2)
                    preview_surface.blit(rotated_image, rotated_pos)
                else:
                    # Draw the scaled image normally
                    preview_surface.blit(scaled_image, (0, 0))
                
            except Exception:
                # Fallback to background if image loading fails
                pygame.draw.rect(preview_surface, (80, 80, 80), 
                                (2, 2, rotated_size[0] - 4, rotated_size[1] - 4))
                self._draw_preview_text(preview_surface, rotated_size, is_site)
        else:
            # Draw card background if no image
            pygame.draw.rect(preview_surface, (80, 80, 80), 
                            (2, 2, rotated_size[0] - 4, rotated_size[1] - 4))
            self._draw_preview_text(preview_surface, rotated_size, is_site)
        
        # Draw the preview surface to the screen
        self.screen.blit(preview_surface, (preview_x, preview_y))
    
    def _draw_preview_text(self, surface: pygame.Surface, size: Tuple[int, int], is_site: bool = False):
        """Draw card text information for preview (fallback when no image)"""
        if self.hovered_card is None:
            return
            
        font = pygame.font.Font(None, 20)  # Slightly larger font for preview
        
        # Adjust text positioning for rotated Site cards
        if is_site:
            # For rotated cards, center text in the rotated dimensions
            center_x = size[0] // 2
            center_y = size[1] // 2
        else:
            center_x = size[0] // 2
            center_y = 25
        
        # Draw card name (less truncated for preview)
        name_text = self.hovered_card.name[:25] + "..." if len(self.hovered_card.name) > 25 else self.hovered_card.name
        text_surface = font.render(name_text, True, (255, 255, 255))
        text_rect = text_surface.get_rect(center=(center_x, center_y))
        surface.blit(text_surface, text_rect)
        
        # Draw card type
        type_text = self.hovered_card.type if self.hovered_card.type else "Unknown"
        type_surface = font.render(type_text, True, (200, 200, 200))
        type_rect = type_surface.get_rect(center=(center_x, center_y + 25))
        surface.blit(type_surface, type_rect)
        
        # Draw subtype
        if self.hovered_card.subtypes:
            subtype_text = f"Subtype: {self.hovered_card.subtypes}"
            subtype_surface = font.render(subtype_text, True, (180, 180, 180))
            subtype_rect = subtype_surface.get_rect(center=(center_x, center_y + 50))
            surface.blit(subtype_surface, subtype_rect)
        
        # Draw cost
        if self.hovered_card.cost is not None:
            cost_text = f"Cost: {self.hovered_card.cost}"
            cost_surface = font.render(cost_text, True, (255, 255, 0))
            cost_rect = cost_surface.get_rect(center=(center_x, center_y + 75))
            surface.blit(cost_surface, cost_rect)
        
        # Draw attack and defense
        if self.hovered_card.attack is not None:
            attack_text = f"Attack: {self.hovered_card.attack}"
            attack_surface = font.render(attack_text, True, (255, 100, 100))
            attack_rect = attack_surface.get_rect(center=(center_x, center_y + 100))
            surface.blit(attack_surface, attack_rect)
        
        if self.hovered_card.defence is not None:
            defense_text = f"Defense: {self.hovered_card.defence}"
            defense_surface = font.render(defense_text, True, (100, 100, 255))
            defense_rect = defense_surface.get_rect(center=(center_x, center_y + 125))
            surface.blit(defense_surface, defense_rect)
    
    def save_layout(self):
        """Save current card positions and camera state to file"""
        if not self.grid_cards:
            DebugDisplay.add_message("No cards to save")
            return
        
        try:
            # Prepare data to save
            layout_data = {
                'camera_x': self.camera_x,
                'camera_y': self.camera_y,
                'zoom': self.zoom,
                'target_zoom': self.target_zoom,
                'card_positions': [],
                'timestamp': str(pygame.time.get_ticks())
            }
            
            # Save card positions with card names for identification
            for i, card in enumerate(self.grid_cards):
                if i < len(self.card_positions):
                    card_data = {
                        'name': card.name,
                        'type': card.type,
                        'position': self.card_positions[i]
                    }
                    layout_data['card_positions'].append(card_data)
            
            # Save to file
            with open(self.save_file_path, 'w', encoding='utf-8') as file:
                json.dump(layout_data, file, indent=2, ensure_ascii=False)
            
            success_msg = f"Layout saved with {len(layout_data['card_positions'])} cards"
            print(success_msg)
            DebugDisplay.add_message(success_msg)
            
        except Exception as e:
            error_msg = f"Failed to save layout: {e}"
            print(error_msg)
            DebugDisplay.add_message(error_msg)
    
    def load_layout(self):
        """Load card positions and camera state from file"""
        if not os.path.exists(self.save_file_path):
            error_msg = f"Save file not found: {self.save_file_path}"
            print(error_msg)
            DebugDisplay.add_message(error_msg)
            return
        
        try:
            # Load data from file
            with open(self.save_file_path, 'r', encoding='utf-8') as file:
                layout_data = json.load(file)
            
            # Restore camera state
            self.camera_x = layout_data.get('camera_x', 0)
            self.camera_y = layout_data.get('camera_y', 0)
            self.zoom = layout_data.get('zoom', config.DEFAULT_ZOOM)
            self.target_zoom = layout_data.get('target_zoom', config.DEFAULT_ZOOM)
            
            # Create a mapping of card names to their saved positions
            saved_positions = {}
            for card_data in layout_data.get('card_positions', []):
                card_name = card_data['name']
                position = card_data['position']
                saved_positions[card_name] = position
            
            # Update current card positions with saved positions
            updated_count = 0
            for i, card in enumerate(self.grid_cards):
                if i < len(self.card_positions) and card.name in saved_positions:
                    self.card_positions[i] = saved_positions[card.name]
                    updated_count += 1
            
            success_msg = f"Layout loaded: {updated_count} cards positioned"
            print(success_msg)
            DebugDisplay.add_message(success_msg)
            
        except Exception as e:
            error_msg = f"Failed to load layout: {e}"
            print(error_msg)
            DebugDisplay.add_message(error_msg)
    
    def draw_selection_feedback(self):
        """Draw selection rectangle and selected card highlights"""
        # Draw selection rectangle
        if self.selection_rect:
            rect_color = (100, 150, 255, 100)  # Semi-transparent blue
            selection_surface = pygame.Surface((
                self.selection_rect[2] - self.selection_rect[0],
                self.selection_rect[3] - self.selection_rect[1]
            ), pygame.SRCALPHA)
            pygame.draw.rect(selection_surface, rect_color, (0, 0, 
                self.selection_rect[2] - self.selection_rect[0],
                self.selection_rect[3] - self.selection_rect[1]))
            self.screen.blit(selection_surface, (self.selection_rect[0], self.selection_rect[1]))
            
            # Draw selection rectangle border
            pygame.draw.rect(self.screen, (100, 150, 255), 
                           (self.selection_rect[0], self.selection_rect[1],
                            self.selection_rect[2] - self.selection_rect[0],
                            self.selection_rect[3] - self.selection_rect[1]), 2)
        
        # Draw selected card highlights
        for selected_index in self.selected_cards:
            if selected_index < len(self.card_positions):
                cluster_pos = self.card_positions[selected_index]
                screen_pos = self.get_screen_position_from_cluster(cluster_pos)
                
                # Get the correct display size for this card (accounting for rotation)
                card = self.grid_cards[selected_index]
                card_size = self.get_card_display_size(card)
                
                # Draw selection highlight
                highlight_color = (255, 255, 0, 100)  # Semi-transparent yellow
                highlight_surface = pygame.Surface(card_size, pygame.SRCALPHA)
                pygame.draw.rect(highlight_surface, highlight_color, (0, 0, card_size[0], card_size[1]))
                self.screen.blit(highlight_surface, screen_pos)
                
                # Draw selection border
                pygame.draw.rect(self.screen, (255, 255, 0), 
                               (screen_pos[0], screen_pos[1], card_size[0], card_size[1]), 3)
    
    def run(self):
        """Main application loop"""
        clock = pygame.time.Clock()
        running = True
        
        # Initialize the application
        self.layout_collection_clusters()
        
        DebugDisplay.add_message("Deck Builder initialized successfully")
        DebugDisplay.add_message(f"Displaying {len(self.grid_cards)} cards in grid")
        
        while running:
            time_delta = clock.tick(60) / 1000.0
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    self.handle_keyboard_events(event)
                elif event.type == pygame.KEYUP:
                    self.handle_keyboard_up_events(event)
                
                self.handle_mouse_events(event)
                self.gui_manager.process_events(event)
            
            # Update debug display
            DebugDisplay.update()
            
            # Smooth zoom interpolation
            if hasattr(self, 'zoom_mouse_pos') and abs(self.zoom - self.target_zoom) > 0.001:
                old_zoom = self.zoom
                # Interpolate towards target zoom
                self.zoom += (self.target_zoom - self.zoom) * 0.15  # Smooth interpolation factor
                
                # Also interpolate grid zoom for smooth grid transitions
                self.grid_zoom += (self.target_zoom - self.grid_zoom) * 0.15
                
                # Adjust camera to keep zoom centered on mouse position
                if self.zoom_mouse_pos:
                    mouse_x, mouse_y = self.zoom_mouse_pos
                    cluster_x_before = (mouse_x / old_zoom) - self.camera_x
                    cluster_y_before = (mouse_y / old_zoom) - self.camera_y
                    
                    screen_x_after = cluster_x_before * self.zoom + self.camera_x * self.zoom
                    screen_y_after = cluster_y_before * self.zoom + self.camera_y * self.zoom
                    
                    self.camera_x += (mouse_x - screen_x_after) / self.zoom
                    self.camera_y += (mouse_y - screen_y_after) / self.zoom
            
            # Update card positions to resolve overlaps
            self.update_card_positions()
            
            self.gui_manager.update(time_delta)
            self.draw_clusters()
            
            # Draw debug display
            DebugDisplay.draw()
            
            self.gui_manager.draw_ui(self.screen)
            
            pygame.display.flip()
        
        pygame.quit()


def main():
    """Main entry point"""
    try:
        deck_builder = DeckBuilder()
        deck_builder.run()
    except Exception as e:
        print(f"Error running deck builder: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()