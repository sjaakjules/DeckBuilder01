import os
import math
import pygame
import pygame_gui
import requests
import threading
import queue
from io import BytesIO
from PIL import Image
from Sorcery_API import CardData
from collections import defaultdict
from Curiosa_API import CuriosaAPI  # make sure this path is valid
import json
from Curiosa_OfflineData import Curiosa_OfflineData
from Collection import Collection
import time
from multiprocessing import Process, Queue
import tkinter.filedialog
from typing import List, Dict, Tuple, Mapping
from CardInfo import CardInfo
from Util_Methods import _save_json


class GUI:
    def __init__(self, width=1200, height=900):
        pygame.init()
        self.WIDTH, self.HEIGHT = width, height
        self.window = pygame.display.set_mode((self.WIDTH, self.HEIGHT), pygame.RESIZABLE)
        pygame.display.set_caption("Sorcery TCG Viewer")
        self.LIGHT_THEME = "src/light_theme.json"
        self.DARK_THEME = "src/dark_theme.json"
        self.current_theme = self.DARK_THEME
        self.draw_ui()
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Arial", 24)

        self.zoom = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.is_panning = False
        self.last_mouse_pos = None
        self.spinner_angle = 0

        self.CARD_WIDTH, self.CARD_HEIGHT = 100, 140
        self.GRID_SPACING_H = 55  # Horizontal grid spacing
        self.GRID_SPACING_V = 75  # Vertical grid spacing
        self.SITE_GRID_SPACING_H = 75  # Horizontal grid spacing for sites
        self.SITE_GRID_SPACING_V = 55  # Vertical grid spacing for sites
        self.grid_offset = (0, 0)  # offset in world units (not pixels)
        self.Region_Spacing = 160

        self.selected_card_index = None
        self.selected_position_group = None
        self.selected_position_index = None
        self.dragging_card = False
        self.drag_offset = (0, 0)
        self.card_data = CardData()
        
        self.selection_box = None  # (start_x, start_y, end_x, end_y)
        self.selected_cards: List[Tuple[str, str, int]] = []   # List of (card_name, pos_group, pos_idx) tuples
        self.shift_held = False
        self.alt_held = False
        self.ctrl_held = False
        self.fullscreen = False
        self.show_regions = True  # Toggle for showing bounding boxes
        
        self.cards_loaded = 0
        self.loading = True
        
        self.collection = None
        self.decks = []

        # Asset cache folder
        self.cache_folder = os.path.join("assets", "Cards")
        os.makedirs(self.cache_folder, exist_ok=True)

        # Background download setup
        self.download_queue = queue.Queue()
        for card in self.card_data.cards.values():
            self.download_queue.put((card))
        self.download_thread = threading.Thread(target=self.download_worker, daemon=True)
        self.download_thread.start()
        
        self.curiosa = None
        
        self.base_bounding_box = None  # (min_x, min_y, max_x, max_y)
        self.deck_bounding_boxes = {}  # deck_name: (min_x, min_y, max_x, max_y)
        self.base_element_bounding_boxes = {}  # element: bbox
        
    def download_worker(self):
        while not self.download_queue.empty():
            card: CardInfo = self.download_queue.get()
            try:
                filename = os.path.join(self.cache_folder, os.path.basename(card.image_url))
                if os.path.exists(filename):
                    with open(filename, "rb") as f:
                        img_data = f.read()
                else:
                    response = requests.get(card.image_url, timeout=5)
                    img_data = response.content
                    with open(filename, "wb") as f:
                        f.write(img_data)

                img = Image.open(BytesIO(img_data)).convert("RGBA")
                pygame_img = pygame.image.frombuffer(img.tobytes(), img.size, 'RGBA')
                card.image_surface = pygame_img
                card.positions = {"base": [((self.cards_loaded % 25) * self.GRID_SPACING_H * 2, (self.cards_loaded // 25) * self.GRID_SPACING_V * 2)]}
                self.cards_loaded += 1
            except Exception as e:
                print(f"Error loading card {getattr(card, 'name', 'unknown')}: {e}")
            self.download_queue.task_done()

        self.loading = False
        # --- Automatically group and layout all base cards when loaded ---
        print("[DEBUG] All cards loaded. Grouping and laying out base cards.")
        self.group_element_type_rarity(self.card_data.cards, "base", (0, 0))
        print("[DEBUG] Base cards grouped and laid out.")
        # Compute and store base bounding box (300 units larger)
        self.base_bounding_box = self.compute_bounding_box(
            [card for card in self.card_data.cards.values() if "base" in card.positions and card.positions["base"]],
            "base",
            extra_padding=self.Region_Spacing
        )
        # Compute and store element bounding boxes for base cards
        self.base_element_bounding_boxes = {}
        element_map = {"Air": [], "Fire": [], "Earth": [], "Water": [], "None": [], "Multiple": []}
        for card in self.card_data.cards.values():
            if "base" in card.positions and card.positions["base"]:
                if not card.elements:
                    element_map["None"].append(card)
                elif len(card.elements) > 1:
                    element_map["Multiple"].append(card)
                else:
                    element_map[card.elements[0]].append(card)
        for element, cards in element_map.items():
            self.base_element_bounding_boxes[element] = self.compute_bounding_box(cards, "base", extra_padding=80)

    def compute_bounding_box(self, cards, group, extra_padding=0):
        # Returns (min_x, min_y, max_x, max_y) with padding
        padding = 40 + extra_padding
        xs, ys = [], []
        for card in cards:
            for pos in card.positions.get(group, []):
                xs.append(pos[0])
                ys.append(pos[1])
        if not xs or not ys:
            return None
        min_x, max_x = min(xs) - padding, max(xs) + self.CARD_WIDTH + padding
        min_y, max_y = min(ys) - padding, max(ys) + self.CARD_HEIGHT + padding
        return (min_x, min_y, max_x, max_y)

    def draw_grid(self):
        spacing_h = self.GRID_SPACING_H  # world units
        spacing_v = self.GRID_SPACING_V  # world units
        color = self.grid_color

        # Grid offset in world space
        offset_x_units, offset_y_units = self.grid_offset

        # Viewport bounds in world space
        left = -self.offset_x / self.zoom
        right = (self.WIDTH - self.offset_x) / self.zoom
        top = -self.offset_y / self.zoom
        bottom = (self.HEIGHT - self.offset_y) / self.zoom

        # Adjusted range with grid offset
        start_x = int((left - offset_x_units) // spacing_h) * spacing_h + offset_x_units
        end_x = int((right - offset_x_units) // spacing_h + 1) * spacing_h + offset_x_units
        start_y = int((top - offset_y_units) // spacing_v) * spacing_v + offset_y_units
        end_y = int((bottom - offset_y_units) // spacing_v + 1) * spacing_v + offset_y_units

        for x in range(start_x, end_x, spacing_h):
            sx = x * self.zoom + self.offset_x
            pygame.draw.line(self.window, color, (sx, 0), (sx, self.HEIGHT))

        for y in range(start_y, end_y, spacing_v):
            sy = y * self.zoom + self.offset_y
            pygame.draw.line(self.window, color, (0, sy), (self.WIDTH, sy))

    def draw_bounding_boxes(self, surface):
        # Draw base bounding box (300 units larger)
        if self.base_bounding_box:
            min_x, min_y, max_x, max_y = self.base_bounding_box
            rect = pygame.Rect(
                min_x * self.zoom + self.offset_x,
                min_y * self.zoom + self.offset_y,
                (max_x - min_x) * self.zoom,
                (max_y - min_y) * self.zoom,
            )
            s = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            s.fill((100, 100, 100, 40))  # semi-transparent
            surface.blit(s, rect.topleft)
            pygame.draw.rect(surface, (100, 100, 255), rect, 3)
            self.window.blit(self.font.render("Base", True, (100, 100, 255)), (rect.left + 8, rect.top + 4))
        # Draw element boxes for base cards
        element_colors = {
            "Air": (120, 200, 255),
            "Fire": (255, 100, 60),
            "Earth": (180, 140, 80),
            "Water": (80, 180, 255),
            "None": (180, 180, 180),
            "Multiple": (200, 100, 200),
        }
        if hasattr(self, 'base_element_bounding_boxes'):
            for element, bbox in self.base_element_bounding_boxes.items():
                if bbox is None:
                    continue
                min_x, min_y, max_x, max_y = bbox
                color = element_colors.get(element, (200, 200, 200))
                rect = pygame.Rect(
                    min_x * self.zoom + self.offset_x,
                    min_y * self.zoom + self.offset_y,
                    (max_x - min_x) * self.zoom,
                    (max_y - min_y) * self.zoom,
                )
                s = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
                s.fill((*color, 30))
                surface.blit(s, rect.topleft)
                pygame.draw.rect(surface, color, rect, 2)
                # Draw label at bottom right
                label_surface = self.font.render(element, True, color)
                label_rect = label_surface.get_rect()
                label_rect.bottomright = (rect.right - 8, rect.bottom - 4)
                self.window.blit(label_surface, label_rect)
        # Draw deck bounding boxes
        for deck_name, bbox in self.deck_bounding_boxes.items():
            if bbox is None:
                continue
            min_x, min_y, max_x, max_y = bbox
            rect = pygame.Rect(
                min_x * self.zoom + self.offset_x,
                min_y * self.zoom + self.offset_y,
                (max_x - min_x) * self.zoom,
                (max_y - min_y) * self.zoom,
            )
            s = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            s.fill((100, 255, 100, 40))  # semi-transparent
            surface.blit(s, rect.topleft)
            pygame.draw.rect(surface, (100, 255, 100), rect, 3)
            self.window.blit(self.font.render(deck_name, True, (100, 255, 100)), (rect.left + 8, rect.top + 4))

    def draw_cards(self):
        if self.show_regions:
            self.draw_bounding_boxes(self.window)
        for card in self.card_data.cards.values():
            if card.image_surface is None:
                continue
            for pos_group, positions in card.positions.items():
                for position in positions:
                    world_x, world_y = position
                    screen_x = world_x * self.zoom + self.offset_x
                    screen_y = world_y * self.zoom + self.offset_y
                    
                    is_site = getattr(card, "type", "").lower() == "site"

                    # Base dimensions
                    scaled_w = int(self.CARD_WIDTH * self.zoom)
                    scaled_h = int(self.CARD_HEIGHT * self.zoom)

                    # Prepare and transform card image
                    scaled_surface = pygame.transform.smoothscale(card.image_surface, (scaled_w, scaled_h))

                    if is_site:
                        rotated_surface = pygame.transform.rotate(scaled_surface, -90)  # clockwise
                        rect = rotated_surface.get_rect(center=(screen_x, screen_y))
                        self.window.blit(rotated_surface, rect.topleft)
                    else:
                        rect = scaled_surface.get_rect(center=(screen_x, screen_y))
                        self.window.blit(scaled_surface, rect.topleft)

                    # --- Selection Outline (yellow) ---
                    if (card.name, pos_group, positions.index(position)) in self.selected_cards:
                        pygame.draw.rect(self.window, (255, 255, 0), rect, 3)

                    # --- Ownership Outline (white/red) ---
                    if hasattr(card, "name") and self.collection:
                        if card.name in self.collection.cards:
                            pygame.draw.rect(self.window, (255, 255, 255), rect, 2)
                        else:
                            pygame.draw.rect(self.window, (255, 0, 0), rect, 2)
                    
                    # --- Over-committed Outline (orange) ---
                    if hasattr(card, "name") and self.is_card_over_committed(card.name, pos_group):
                        pygame.draw.rect(self.window, (255, 165, 0), rect, 4)  # Orange outline for over-committed cards
                
    def draw_selection_box(self):
        if self.selection_box:
            x0, y0, x1, y1 = self.selection_box
            rect = pygame.Rect(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))
            pygame.draw.rect(self.window, (255, 255, 0), rect, 1)
            
    def draw_loading_ui(self):
        center = (self.WIDTH // 2, self.HEIGHT // 2)
        radius = 40
        thickness = 6
        rect = pygame.Rect(center[0] - radius, center[1] - radius, radius * 2, radius * 2)

        start_angle = math.radians(self.spinner_angle)
        end_angle = start_angle + math.pi * 1.5
        pygame.draw.circle(self.window, (230, 230, 230), center, radius, thickness)
        pygame.draw.arc(self.window, (120, 200, 255), rect, start_angle, end_angle, thickness)
        self.spinner_angle = (self.spinner_angle + 5) % 360

        pct = int((self.cards_loaded / len(self.card_data.cards)) * 100)
        text_surface = self.font.render(f"{pct}%", True, (230, 230, 230))
        text_rect = text_surface.get_rect(center=center)
        self.window.blit(text_surface, text_rect)
    
    def toggle_fullscreen(self):
        """Toggle between fullscreen and windowed mode"""
        if self.fullscreen:
            # Switch to windowed mode
            self.window = pygame.display.set_mode((1200, 900), pygame.RESIZABLE)
            self.WIDTH, self.HEIGHT = 1200, 900
            self.fullscreen = False
        else:
            # Switch to fullscreen mode
            info = pygame.display.Info()
            self.window = pygame.display.set_mode((info.current_w, info.current_h), pygame.FULLSCREEN)
            self.WIDTH, self.HEIGHT = info.current_w, info.current_h
            self.fullscreen = True
        
        # Recreate UI with new size
        self.draw_ui()

    def toggle_theme(self):
        self.current_theme = self.LIGHT_THEME if self.current_theme == self.DARK_THEME else self.DARK_THEME
        self.draw_ui()
        
    def draw_ui(self):
        # Create new UIManager with the new theme
        self.manager = pygame_gui.UIManager((self.WIDTH, self.HEIGHT), self.current_theme)
        
        self.grid_color = self.manager.get_theme().get_colour("window.colours.normal_border")
        self.background_color = self.manager.get_theme().get_colour("window.colours.normal_bg")
        self.text_color = self.manager.get_theme().get_colour("text_box.colours.normal_text")
        self.text_bg_color = self.manager.get_theme().get_colour("text_box.colours.normal_bg")
        self.button_text_color = self.manager.get_theme().get_colour("button.colours.normal_text")
        self.button_bg_color = self.manager.get_theme().get_colour("button.colours.normal_bg")
        self.button_hovered_color = self.manager.get_theme().get_colour("button.colours.hovered_bg")
        self.button_selected_color = self.manager.get_theme().get_colour("button.colours.selected_bg")
        self.button_disabled_color = self.manager.get_theme().get_colour("button.colours.disabled_bg")
        self.button_disabled_text_color = self.manager.get_theme().get_colour("button.colours.disabled_text")
        self.button_hovered_text_color = self.manager.get_theme().get_colour("button.colours.hovered_text")
        self.button_selected_text_color = self.manager.get_theme().get_colour("button.colours.selected_text")

        # Recreate buttons with new theme manager
        button_y = 10
        button_w = 120
        button_h = 30
        button_spacing = 10
        start_x = 10

        # These start hidden
        self.login_button = None
        self.load_csv_button = None
        
        self.group_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((start_x, button_y), (button_w, button_h)),
            text='Group',
            manager=self.manager
        )

        self.save_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((start_x + (button_w + button_spacing) * 1, button_y), (button_w, button_h)),
            text="Save Layout",
            manager=self.manager
        )

        self.load_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((start_x + (button_w + button_spacing) * 2, button_y), (button_w, button_h)),
            text="Load Layout",
            manager=self.manager
        )

        self.toggle_theme_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((start_x + (button_w + button_spacing) * 4, button_y), (button_w, button_h)),
            text="Toggle Theme",
            manager=self.manager
        )
        
        self.load_collection_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((start_x + (button_w + button_spacing) * 3, button_y), (button_w, button_h)),
            text="Load Collection",
            manager=self.manager
        )
        
        self.load_deck_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((start_x + (button_w + button_spacing) * 5, button_y), (button_w, button_h)),
            text="Load Deck from URL",
            manager=self.manager
        )
        
        self.fullscreen_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((start_x + (button_w + button_spacing) * 6, button_y), (button_w, button_h)),
            text="Toggle Fullscreen",
            manager=self.manager
        )
        
        self.toggle_regions_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((start_x + (button_w + button_spacing) * 7, button_y), (button_w, button_h)),
            text="Hide Regions",
            manager=self.manager
        )
                    
    def show_collection_buttons(self):
        button_y = 50  # Lower down
        button_w = 120
        button_h = 30
        button_spacing = 10
        start_x = 10

        self.login_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((start_x, button_y), (button_w, button_h)),
            text="Login",
            manager=self.manager
        )

        self.load_csv_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((start_x + button_w + button_spacing, button_y), (button_w, button_h)),
            text="Load CSV",
            manager=self.manager
        )
    
    def handle_event(self, event):
        if event.type == pygame.QUIT:
            return False

        elif event.type == pygame.KEYDOWN or event.type == pygame.KEYUP:
            mods = pygame.key.get_mods()
            self.shift_held = mods & pygame.KMOD_SHIFT
            self.alt_held = mods & pygame.KMOD_ALT
            self.ctrl_held = mods & pygame.KMOD_CTRL

        elif event.type == pygame.VIDEORESIZE:
            # Handle window resize
            self.WIDTH, self.HEIGHT = event.size
            self.window = pygame.display.set_mode((self.WIDTH, self.HEIGHT), pygame.RESIZABLE)
            self.draw_ui()  # Recreate UI with new size

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 3:  # Right click = pan
                self.is_panning = True
                self.last_mouse_pos = event.pos

            elif event.button == 1:  # Left click
                mx, my = event.pos
                clicked_card = False

                for card in self.card_data.cards.values():
                    if card.image_surface is None:
                        continue
                    # Check all position groups for hit detection
                    for pos_group, positions in card.positions.items():
                        if not positions:
                            continue
                        for pos_idx, (world_x, world_y) in enumerate(positions):
                            screen_x = world_x * self.zoom + self.offset_x
                            screen_y = world_y * self.zoom + self.offset_y
                            scaled_w = int(self.CARD_WIDTH * self.zoom)
                            scaled_h = int(self.CARD_HEIGHT * self.zoom)

                            # Adjust for rotated Site cards
                            is_site = getattr(card, "type", "").lower() == "site"
                            if is_site:
                                scaled_w, scaled_h = scaled_h, scaled_w

                            rect = pygame.Rect(screen_x - scaled_w // 2, screen_y - scaled_h // 2, scaled_w, scaled_h)
                            if rect.collidepoint(mx, my):
                                clicked_card = True
                                card_name = card.name
                                # Don't change selection if clicking an already selected card without modifiers
                                if (card_name, pos_group, pos_idx) in self.selected_cards:
                                    self.selected_card_index = card_name
                                    self.selected_position_group = pos_group
                                    self.selected_position_index = pos_idx
                                    self.dragging_card = True
                                    self.drag_offset = (
                                        (mx - screen_x) / self.zoom,
                                        (my - screen_y) / self.zoom
                                    )
                                    break
                                # Alt removes from selection
                                if self.alt_held:
                                    if (card_name, pos_group, pos_idx) in self.selected_cards:
                                        self.selected_cards.remove((card_name, pos_group, pos_idx))
                                    break
                                # Shift adds to selection
                                if self.shift_held:
                                    self.selected_cards.append((card_name, pos_group, pos_idx))
                                    self.selected_card_index = card_name
                                    self.selected_position_group = pos_group
                                    self.selected_position_index = pos_idx
                                    self.dragging_card = True
                                    self.drag_offset = (
                                        (mx - screen_x) / self.zoom,
                                        (my - screen_y) / self.zoom
                                    )
                                    break
                                # Default behavior: select this card only
                                self.selected_cards = [(card_name, pos_group, pos_idx)]
                                self.selected_card_index = card_name
                                self.selected_position_group = pos_group
                                self.selected_position_index = pos_idx
                                self.dragging_card = True
                                self.drag_offset = (
                                    (mx - screen_x) / self.zoom,
                                    (my - screen_y) / self.zoom
                                )
                                break
                        if clicked_card:
                            break
                    if clicked_card:
                        break

                if not clicked_card:
                    # Start selection box
                    if not self.shift_held and not self.alt_held:
                        self.selected_cards = []
                    self.selected_card_index = None
                    self.selected_position_group = None
                    self.selected_position_index = None
                    self.selection_box = (mx, my, mx, my)

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 3:  # Right click
                self.is_panning = False
            elif event.button == 1:  # Left click
                if self.selection_box:
                    x0, y0, x1, y1 = self.selection_box
                    box = pygame.Rect(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))
                    affected = []

                    for card in self.card_data.cards.values():
                        if card.image_surface is None:
                            continue
                        # Check all position groups for selection box
                        for pos_group, positions in card.positions.items():
                            if not positions:
                                continue
                            for pos_idx, (world_x, world_y) in enumerate(positions):
                                screen_x = world_x * self.zoom + self.offset_x
                                screen_y = world_y * self.zoom + self.offset_y
                                scaled_w = int(self.CARD_WIDTH * self.zoom)
                                scaled_h = int(self.CARD_HEIGHT * self.zoom)
                                # Check for rotated sites
                                is_site = getattr(card, "type", "").lower() == "site"
                                if is_site:
                                    scaled_w, scaled_h = scaled_h, scaled_w
                                rect = pygame.Rect(screen_x - scaled_w // 2, screen_y - scaled_h // 2, scaled_w, scaled_h)
                                if box.colliderect(rect):
                                    affected.append((card.name, pos_group, pos_idx))

                    if self.alt_held:
                        for name, pos_group, pos_idx in affected:
                            if (name, pos_group, pos_idx) in self.selected_cards:
                                self.selected_cards.remove((name, pos_group, pos_idx))
                    elif self.shift_held:
                        for name, pos_group, pos_idx in affected:
                            if (name, pos_group, pos_idx) not in self.selected_cards:
                                self.selected_cards.append((name, pos_group, pos_idx))
                    else:
                        self.selected_cards = [(name, pos_group, pos_idx) for name, pos_group, pos_idx in affected]

                    self.selection_box = None
                self.dragging_card = False
                if not self.selection_box and self.selected_cards:
                    for name, pos_group, pos_idx in self.selected_cards:
                        if name is None:
                            print("[DEBUG] Skipping None key in selected_cards.")
                            continue
                        if name not in self.card_data.cards:
                            print(f"[DEBUG] Skipping unknown card name in selected_cards: {name}")
                            continue
                        card = self.card_data.cards[name]
                        if pos_group in card.positions and pos_idx < len(card.positions[pos_group]):
                            x, y = card.positions[pos_group][pos_idx]
                            snapped_x, snapped_y = self.snap_card_to_grid(x, y, card)
                            card.positions[pos_group][pos_idx] = (snapped_x, snapped_y)
                            # print(f"[DEBUG] Snapped card {name} in {pos_group} to ({snapped_x}, {snapped_y})")

                # Handle card duplication when Control is held
                if self.ctrl_held and self.selected_cards:
                    self.duplicate_cards_in_deck_boxes()

        elif event.type == pygame.MOUSEMOTION:
            if self.is_panning:
                if self.last_mouse_pos is not None:
                    dx = event.pos[0] - self.last_mouse_pos[0]
                    dy = event.pos[1] - self.last_mouse_pos[1]
                    self.offset_x += dx
                    self.offset_y += dy
                self.last_mouse_pos = event.pos

            elif (self.dragging_card and self.selected_card_index is not None and 
                  self.selected_position_group is not None and self.selected_position_index is not None):
                mx, my = event.pos
                new_world_x = (mx - self.offset_x) / self.zoom - self.drag_offset[0]
                new_world_y = (my - self.offset_y) / self.zoom - self.drag_offset[1]
                dx = (new_world_x - 
                      self.card_data.cards[self.selected_card_index].positions[self.selected_position_group][self.selected_position_index][0])
                dy = (new_world_y - 
                      self.card_data.cards[self.selected_card_index].positions[self.selected_position_group][self.selected_position_index][1])

                # Move all selected cards
                for name, pos_group, pos_idx in self.selected_cards:
                    card = self.card_data.cards[name]
                    if pos_group in card.positions and pos_idx < len(card.positions[pos_group]):
                        x, y = card.positions[pos_group][pos_idx]
                        self.card_data.cards[name].positions[pos_group][pos_idx] = (x + dx, y + dy)

            elif self.selection_box:
                x0, y0, _, _ = self.selection_box
                self.selection_box = (x0, y0, event.pos[0], event.pos[1])

        elif event.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            scale = 1.1 if event.y > 0 else 0.9
            old_zoom = self.zoom
            self.zoom *= scale
            self.offset_x = mx - (mx - self.offset_x) * (self.zoom / old_zoom)
            self.offset_y = my - (my - self.offset_y) * (self.zoom / old_zoom)

        elif event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.group_button:
                self.group_element_type_rarity(self.card_data.cards, "base", (0, 0))
            elif event.ui_element == self.save_button:
                self.save_layout("layout.json")
            elif event.ui_element == self.load_button:
                self.load_layout("layout.json")
            elif event.ui_element == self.load_collection_button:
                self.show_collection_buttons()

            elif event.ui_element == self.login_button:
                self.login_to_curiosa()

            elif event.ui_element == self.load_csv_button:
                self.open_file_and_load_csv()
            elif event.ui_element == self.toggle_theme_button:
                self.toggle_theme()
            if event.ui_element == self.load_deck_button:
                self.open_load_deck_dialog()
            elif event.ui_element == self.fullscreen_button:
                self.toggle_fullscreen()
            elif event.ui_element == self.toggle_regions_button:
                self.show_regions = not self.show_regions
                self.toggle_regions_button.set_text("Hide Regions" if self.show_regions else "Show Regions")
                print(f"Regions {'hidden' if not self.show_regions else 'shown'}")
                    
        self.manager.process_events(event)
        return True
        
    @staticmethod
    def select_deck_url(q):
        import tkinter as tk
        from tkinter.simpledialog import askstring
        root = tk.Tk()
        root.withdraw()
        deck_url = askstring("Load Deck", "Enter Curiosa Deck URL or ID:")
        q.put(deck_url)

    @staticmethod
    def open_deck_url_dialog_safe():
        from multiprocessing import Process, Queue
        q = Queue()
        p = Process(target=GUI.select_deck_url, args=(q,))
        p.start()
        p.join()
        return q.get() if not q.empty() else None

    def open_load_deck_dialog(self):
        deck_url = GUI.open_deck_url_dialog_safe()
        if not deck_url:
            return
        
        try:
            print(f"  📥 Downloading deck {deck_url}...")
            deck_data = CuriosaAPI.fetch_curiosa_deck(deck_url)
            
            if deck_data:
                
                deck_name = deck_data.get("name", f"Deck_{deck_url}")
                print(f"  ✅ Downloaded deck: {deck_name}")
                
                # Save deck to file
                deck_path = "data/decks"
                os.makedirs(deck_path, exist_ok=True)
                safe_filename = "".join(c for c in deck_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
                safe_filename = safe_filename.replace(' ', '_')
                _save_json(deck_data, f"{deck_path}/{safe_filename}.json")
                
                # Load deck into the viewer
                self.load_deck_from_data(deck_data)
            else:
                print(f"  ❌ Failed to download deck {deck_url}")
                
        except Exception as e:
            print(f"  ❌ Error downloading deck {deck_url}: {e}")

    def load_deck(self, deck_url: str):
        print(f"[DEBUG] Loading deck from URL: {deck_url}")
        
        deck_data = CuriosaAPI.fetch_curiosa_deck(deck_url)
        
        if deck_data is None:
            print(f"  ❌ Failed to download deck {deck_url}")
            return
        
        deck_name = deck_data.get("name", "Deck")
        avatar = deck_data.get("avatar", [])
        
        deck_path = "data/decks"
        os.makedirs(deck_path, exist_ok=True)
        _save_json(deck_data, f"{deck_path}/{deck_name}.json")
        # Ensure avatar is always a list
        if isinstance(avatar, dict):
            avatar = [avatar]
        elif not isinstance(avatar, list):
            avatar = []
        mainboard = deck_data.get("mainboard", []) + avatar
        sideboard = deck_data.get("sideboard", [])
        maybeboard = deck_data.get("maybeboard", [])

        print(f"[DEBUG] Deck name: {deck_name}")
        print(f"[DEBUG] mainboard count: {len(mainboard)}")
        print(f"[DEBUG] sideboard count: {len(sideboard)}")
        print(f"[DEBUG] maybeboard count: {len(maybeboard)}")
        
        main_name = f"{deck_name}_mainboard"

        for card_info in mainboard:
            card_name = card_info.get("card").get("name")
            quantity = card_info.get("quantity", 0)
            for _ in range(quantity):
                if main_name not in self.card_data.cards[card_name].positions:
                    self.card_data.cards[card_name].positions[main_name] = []
                self.card_data.cards[card_name].positions[main_name].append((0, 0))
        
        if self.base_bounding_box:
            startx = self.base_bounding_box[0]
            starty = self.base_bounding_box[3]
        else:
            startx = 0
            starty = 0
        for deck_name, box in self.deck_bounding_boxes:  # deck_name: (min_x, min_y, max_x, max_y)
            if box[0] < startx:
                startx = box[0]
            if box[3] > starty:
                starty = box[1]
        
        self.group_type_rarity(self.card_data.cards, main_name, (startx + self.Region_Spacing, starty + 480))
        
        self.deck_bounding_boxes[main_name] = self.compute_bounding_box(
            [card for card in self.card_data.cards.values() if main_name in card.positions and card.positions[main_name]],
            main_name,
            extra_padding=self.Region_Spacing
        )
        
        side_name = f"{deck_name}_sideboard"
        side_start_pos = (self.deck_bounding_boxes[main_name][0] + self.Region_Spacing / 2, 
                          self.deck_bounding_boxes[main_name][3] + self.Region_Spacing)
        self.deck_grid_placement(sideboard, side_name, side_start_pos)
        
        self.deck_bounding_boxes[side_name] = self.compute_bounding_box(
            [card for card in self.card_data.cards.values() if side_name in card.positions and card.positions[side_name]],
            side_name,
            extra_padding=int(self.Region_Spacing / 2)
        )
        
        maybe_name = f"{deck_name}_maybeboard"
        maybe_start_pos = (self.deck_bounding_boxes[side_name][0] + self.Region_Spacing / 2, 
                           self.deck_bounding_boxes[side_name][3] + self.Region_Spacing)
        self.deck_grid_placement(maybeboard, maybe_name, maybe_start_pos)
        
        self.deck_bounding_boxes[maybe_name] = self.compute_bounding_box(
            [card for card in self.card_data.cards.values() if maybe_name in card.positions and card.positions[maybe_name]],
            maybe_name,
            extra_padding=int(self.Region_Spacing / 2)
        )
    
    def deck_grid_placement(self, board_info, group_name, start_pos, n_cols=25):
        i = 0
        for card_info in board_info:
            card_name = card_info.get("card").get("name")
            quantity = card_info.get("quantity", 0)
            for _ in range(quantity):
                if group_name not in self.card_data.cards[card_name].positions:
                    self.card_data.cards[card_name].positions[group_name] = []
                self.card_data.cards[card_name].positions[group_name].append((start_pos[0] + (i % n_cols) * self.GRID_SPACING_H * 2, 
                                                                             start_pos[1] + (i // n_cols) * self.GRID_SPACING_V * 2))
                i += 1
    
    @staticmethod
    def select_file(q):
        path = tkinter.filedialog.askopenfilename(
            title="Select Collection CSV File",
            filetypes=[("CSV files", "*.csv")]
        )
        q.put(path)

    @staticmethod
    def open_file_dialog_safe():
        q = Queue()
        p = Process(target=GUI.select_file, args=(q,))
        p.start()
        p.join()
        return q.get() if not q.empty() else None

    def open_file_and_load_csv(self):
        file_path = GUI.open_file_dialog_safe()
        print(f"📂 Selected file: {file_path}")
        time.sleep(1)

        if file_path:
            try:
                self.collection = Collection.from_csv(file_path, self.card_data.card_data_lookup)
                print(f"✅ Loaded collection from CSV: {len(self.collection.cards)} cards")
            except Exception as e:
                print(f"❌ Failed to load collection: {e}")

    def login_to_curiosa(self):
        try:
            self.curiosa = CuriosaAPI()
            self.curiosa.login()
            self.curiosa.fetch_user_cards()

            if not self.curiosa.collection:
                print("❌ No collection data returned from Curiosa")
                return

            # Only pass a list to from_online_json
            if isinstance(self.curiosa.collection, list):
                self.collection = Collection.from_online_json(self.curiosa.collection)
                print(f"✅ Logged in and loaded {len(self.collection.cards)} unique cards from Curiosa")
            else:
                print("❌ Curiosa collection is not a list, cannot load.")

            # Fetch and download all decks from user's folders
            self.download_user_decks()

        except Exception as e:
            print(f"❌ Login to Curiosa failed: {e}")
    
    def download_user_decks(self):
        """Download all decks from the user's folders"""
        if not self.curiosa or not hasattr(self.curiosa, 'folders') or self.curiosa.folders is None:
            print("❌ No folder information available")
            return
        
        print(f"📁 Found {len(self.curiosa.folders)} folders")
        total_decks = 0
        
        for folder in self.curiosa.folders:
            folder_name = folder.get('name', 'Unknown Folder')
            decks = folder.get('decks', [])
            print(f"📂 Processing folder '{folder_name}' with {len(decks)} decks")
            
            for deck_info in decks:
                deck_id = deck_info.get('id')
                if not deck_id:
                    continue
                
                try:
                    print(f"  📥 Downloading deck {deck_id}...")
                    deck_data = CuriosaAPI.fetch_curiosa_deck(deck_id)
                    
                    if deck_data:
                        deck_name = deck_data.get("name", f"Deck_{deck_id}")
                        print(f"  ✅ Downloaded deck: {deck_name}")
                        
                        # Save deck to file
                        deck_path = "data/decks"
                        os.makedirs(deck_path, exist_ok=True)
                        safe_filename = "".join(c for c in deck_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
                        safe_filename = safe_filename.replace(' ', '_')
                        _save_json(deck_data, f"{deck_path}/{safe_filename}.json")
                        
                        # Load deck into the viewer
                        self.load_deck_from_data(deck_data)
                        total_decks += 1
                    else:
                        print(f"  ❌ Failed to download deck {deck_id}")
                        
                except Exception as e:
                    print(f"  ❌ Error downloading deck {deck_id}: {e}")
        
        print(f"✅ Successfully downloaded and loaded {total_decks} decks")
    
    def load_deck_from_data(self, deck_data):
        """Load a deck from deck data (without prompting for URL)"""
        deck_name = deck_data.get("name", "Deck")
        avatar = deck_data.get("avatar", [])
        
        # Ensure avatar is always a list
        if isinstance(avatar, dict):
            avatar = [avatar]
        elif not isinstance(avatar, list):
            avatar = []
        
        mainboard = deck_data.get("mainboard", []) + avatar
        sideboard = deck_data.get("sideboard", [])
        maybeboard = deck_data.get("maybeboard", [])

        print(f"[DEBUG] Deck name: {deck_name}")
        print(f"[DEBUG] mainboard count: {len(mainboard)}")
        print(f"[DEBUG] sideboard count: {len(sideboard)}")
        print(f"[DEBUG] maybeboard count: {len(maybeboard)}")
        
        main_name = f"{deck_name}_mainboard"

        for card_info in mainboard:
            card_name = card_info.get("card").get("name")
            quantity = card_info.get("quantity", 0)
            for _ in range(quantity):
                if main_name not in self.card_data.cards[card_name].positions:
                    self.card_data.cards[card_name].positions[main_name] = []
                self.card_data.cards[card_name].positions[main_name].append((0, 0))
        
        if self.base_bounding_box:
            startx = self.base_bounding_box[0]
            starty = self.base_bounding_box[3]
        else:
            startx = 0
            starty = 0
        
        for deck_name_key, box in self.deck_bounding_boxes.items():  # deck_name: (min_x, min_y, max_x, max_y)
            if box[0] < startx:
                startx = box[0]
            if box[3] > starty:
                starty = box[3]
        
        self.group_type_rarity(self.card_data.cards, main_name, (startx + self.Region_Spacing, starty + 480))
        
        self.deck_bounding_boxes[main_name] = self.compute_bounding_box(
            [card for card in self.card_data.cards.values() if main_name in card.positions and card.positions[main_name]],
            main_name,
            extra_padding=self.Region_Spacing
        )
        
        if sideboard:
            side_name = f"{deck_name}_sideboard"
            side_start_pos = (self.deck_bounding_boxes[main_name][0] + self.Region_Spacing / 2, 
                            self.deck_bounding_boxes[main_name][3] + self.Region_Spacing)
            self.deck_grid_placement(sideboard, side_name, side_start_pos)
            
            self.deck_bounding_boxes[side_name] = self.compute_bounding_box(
                [card for card in self.card_data.cards.values() if side_name in card.positions and card.positions[side_name]],
                side_name,
                extra_padding=int(self.Region_Spacing / 2)
            )
        
        if maybeboard:
            maybe_name = f"{deck_name}_maybeboard"
            maybe_start_pos = (self.deck_bounding_boxes[side_name][0] + self.Region_Spacing / 2, 
                            self.deck_bounding_boxes[side_name][3] + self.Region_Spacing)
            self.deck_grid_placement(maybeboard, maybe_name, maybe_start_pos)
            
            self.deck_bounding_boxes[maybe_name] = self.compute_bounding_box(
                [card for card in self.card_data.cards.values() if maybe_name in card.positions and card.positions[maybe_name]],
                maybe_name,
                extra_padding=int(self.Region_Spacing / 2)
            )
    
    def duplicate_cards_in_deck_boxes(self):
        """Duplicate selected cards if they're within deck bounding boxes"""
        for card_name, pos_group, pos_idx in self.selected_cards:
            card = self.card_data.cards[card_name]
            
            # Get the card's position
            if pos_group in card.positions and pos_idx < len(card.positions[pos_group]):
                card_pos = card.positions[pos_group][pos_idx]
                screen_x = card_pos[0] * self.zoom + self.offset_x
                screen_y = card_pos[1] * self.zoom + self.offset_y
                
                # Check if card is within any deck bounding box
                for deck_name, bbox in self.deck_bounding_boxes.items():
                    if bbox is None:
                        continue
                    
                    min_x, min_y, max_x, max_y = bbox
                    bbox_screen_x = min_x * self.zoom + self.offset_x
                    bbox_screen_y = min_y * self.zoom + self.offset_y
                    bbox_screen_w = (max_x - min_x) * self.zoom
                    bbox_screen_h = (max_y - min_y) * self.zoom
                    
                    bbox_rect = pygame.Rect(bbox_screen_x, bbox_screen_y, bbox_screen_w, bbox_screen_h)
                    card_rect = pygame.Rect(screen_x - 50, screen_y - 70, 100, 140)  # Approximate card bounds
                    
                    if bbox_rect.colliderect(card_rect):
                        # Card is within this deck box, add a copy
                        if deck_name not in card.positions:
                            card.positions[deck_name] = []
                        
                        # Add a copy at a slightly offset position
                        offset_x = card_pos[0] + 20
                        offset_y = card_pos[1] + 20
                        new_pos_idx = len(card.positions[deck_name])
                        card.positions[deck_name].append((offset_x, offset_y))
                        
                        # Update selection to include the new position group
                        if (card_name, deck_name, new_pos_idx) not in self.selected_cards:
                            self.selected_cards.append((card_name, deck_name, new_pos_idx))
                        
                        print(f"[DEBUG] Duplicated card {card_name} to {deck_name} at ({offset_x}, {offset_y})")
                        break

    def save_layout(self, filepath):
        try:
            # Only save card positions, not the full card objects
            layout_data = {name: card.positions for name, card in self.card_data.cards.items()}
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(layout_data, f)
            print(f"✅ Layout saved to {filepath}")
        except Exception as e:
            print(f"❌ Failed to save layout: {e}")

    def load_layout(self, filepath):
        try:
            if not os.path.exists(filepath):
                print(f"⚠️ Layout file not found: {filepath}")
                return
            with open(filepath, "r", encoding="utf-8") as f:
                layout_data = json.load(f)
            # Restore positions to the correct CardInfo objects by name
            for name, positions in layout_data.items():
                if name in self.card_data.cards:
                    self.card_data.cards[name].positions = positions
            print(f"✅ Layout loaded from {filepath}")
        except Exception as e:
            print(f"❌ Failed to load layout: {e}")
            
    def group_element_type_rarity(self, cards: Dict[str, CardInfo], group_name: str, top_left: Tuple[int, int]):
        # Filter cards that have the group_name in their positions
        filtered_cards = [card for card in cards.values() if group_name in card.positions and card.positions[group_name]]
        # Group by element, type, rarity
        grouped = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        for card in filtered_cards:
            element_key = "None" if not card.elements else ("Multiple" if len(card.elements) > 1 else card.elements[0])
            type_key = "Spell" if (card.type or "Unknown") in ["Aura", "Magic"] else (card.type or "Unknown")
            rarity_key = card.rareity or "Ordinary"
            grouped[element_key][type_key][rarity_key].append(card)
        # Layout with tighter spacing
        card_width = 110  # Normal card width + 10 padding
        card_height = 150  # Normal card height + 10 padding
        spacing_element = 300  # Spacing between element groups
        spacing_type = 50  # Spacing between type groups
        spacing_rarity = 20  # Spacing between rarity rows
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
                # Calculate width for this type based on sqrt of total items
                type_total = sum(len(items) for items in rarities.values())
                cols = max(1, int(math.sqrt(type_total)))
                col_width = cols * card_width  # Use normal card width for column calculation
                
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
                            # Use adaptive spacing for sites to prevent overlap
                            site_grid_h, site_grid_v = self.get_adaptive_grid_spacing(card)
                            x = type_start_x + col * site_grid_h * 2 + top_left[0]
                            y = rarity_y_offset + row * site_grid_v * 2 + top_left[1]
                        else:
                            x = type_start_x + col * card_width + top_left[0]
                            y = rarity_y_offset + row * card_height + top_left[1]
                        
                        card.positions[group_name] = [(x, y)]
                    
                    # Move down by the max height of this rarity band
                    max_rows = max_rows_per_rarity[rarity_key]
                    if max_rows > 0:
                        # Use adaptive spacing for row height calculation
                        _, max_grid_v = self.get_adaptive_grid_spacing(card)  # Use any card for reference
                        row_height = max(card_height, max_grid_v)
                        rarity_y_offset += max_rows * row_height + spacing_rarity
                
                local_x += col_width + spacing_type
                element_max_width = max(element_max_width, local_x)
            
            x_offset += element_max_width + spacing_element

    def group_type_rarity(self, cards: Dict[str, CardInfo], group_name: str, top_left: Tuple[int, int]):
        # Filter cards that have the group_name in their positions
        filtered_cards = [card for card in cards.values() if group_name in card.positions and card.positions[group_name]]
        # Group by type, rarity
        grouped = defaultdict(lambda: defaultdict(list))
        for card in filtered_cards:
            type_key = "Spell" if (card.type or "Unknown") in ["Aura", "Magic"] else (card.type or "Unknown")
            rarity_key = card.rareity or "Ordinary"
            grouped[type_key][rarity_key].append(card)
        # Layout with tighter spacing
        card_width = 110  # Normal card width + 10 padding
        card_height = 150  # Normal card height + 10 padding
        spacing_type = 50  # Spacing between type groups
        spacing_rarity = 20  # Spacing between rarity rows
        x_offset = 0
        rarity_order_list = ["Ordinary", "Exceptional", "Elite", "Unique"]
        
        for type_key, rarities in grouped.items():
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
            col_width = cols * card_width  # Use normal card width for column calculation
            
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
                        # Use adaptive spacing for sites to prevent overlap
                        site_grid_h, site_grid_v = self.get_adaptive_grid_spacing(card)
                        x = type_start_x + col * site_grid_h * 2 + top_left[0]
                        y = rarity_y_offset + row * site_grid_v * 2 + top_left[1]
                    else:
                        x = type_start_x + col * card_width + top_left[0]
                        y = rarity_y_offset + row * card_height + top_left[1]
                    
                    card.positions[group_name] = [(x, y)]
                
                # Move down by the max height of this rarity band
                max_rows = max_rows_per_rarity[rarity_key]
                if max_rows > 0:
                    # Use adaptive spacing for row height calculation
                    _, max_grid_v = self.get_adaptive_grid_spacing(card)  # Use any card for reference
                    row_height = max(card_height, max_grid_v)
                    rarity_y_offset += max_rows * row_height + spacing_rarity
            
            x_offset += col_width + spacing_type

    def get_adaptive_grid_spacing(self, card):
        """Get appropriate grid spacing based on card type"""
        is_site = getattr(card, "type", "").lower() == "site"
        if is_site:
            # Sites need more horizontal space due to rotation
            return self.SITE_GRID_SPACING_H, self.SITE_GRID_SPACING_V
        else:
            return self.GRID_SPACING_H, self.GRID_SPACING_V

    def snap_card_to_grid(self, x, y, card):
        """Snap a card to the appropriate grid based on its type"""
        grid_h, grid_v = self.get_adaptive_grid_spacing(card)
        snapped_x = round(x / grid_h) * grid_h
        snapped_y = round(y / grid_v) * grid_v
        return snapped_x, snapped_y

    def is_card_over_committed(self, card_name: str, pos_group: str) -> bool:
        """Check if a card is over-committed in a mainboard deck (more copies than available in collection)"""
        # Only check mainboard decks
        if not pos_group.endswith("_mainboard"):
            return False
        
        # If no collection loaded, can't be over-committed
        if not self.collection:
            return False
        
        # Count how many copies are in this deck
        deck_copies = 0
        if card_name in self.card_data.cards:
            card = self.card_data.cards[card_name]
            if pos_group in card.positions:
                deck_copies = len(card.positions[pos_group])
        
        # Count how many copies are available in collection
        collection_copies = 0
        if card_name in self.collection.cards:
            collection_copies = self.collection.cards[card_name]["total_quantity"]
        
        # Card is over-committed if deck has more copies than collection
        return deck_copies > collection_copies

    def run(self):
        running = True
        while running:
            time_delta = self.clock.tick(60) / 1000.0
            self.window.fill(self.background_color)  # new black background

            self.draw_grid()
            self.draw_cards()
            self.draw_selection_box()
            if self.loading:
                self.draw_loading_ui()

            for event in pygame.event.get():
                running = self.handle_event(event)

            self.manager.update(time_delta)
            self.manager.draw_ui(self.window)
            pygame.display.flip()

        pygame.quit()


if __name__ == "__main__":
    gui = GUI()
    gui.run()