import os
import math
import pygame
import pygame_gui
from Card_Manager import Card_Manager
import json
from typing import List, Dict, Tuple, Mapping
from Deck_Manager import Deck_Manager
from Collection_Manager import Collection_Manager
import Layout_Manager as LM
from GUI_Sidebar import Sidebar
from GUI_Themes import Modern_theme
from Util_IO import _save_json
from Deck import Deck


class GUI_Manager:
    def __init__(self, card_manager: Card_Manager, deck_manager: Deck_Manager, collection_manager: Collection_Manager, width=1200, height=900):
        self.card_manager = card_manager
        self.deck_manager = deck_manager
        self.collection_manager = collection_manager
        
        # Set GUI references in managers
        self.deck_manager.set_gui_manager(self)
        self.collection_manager.set_gui_manager(self)
        
        pygame.init()
        self.WIDTH, self.HEIGHT = width, height
        self.window = pygame.display.set_mode((self.WIDTH, self.HEIGHT), pygame.RESIZABLE)
        pygame.display.set_caption("Sorcery TCG Viewer")
        self.active_theme = "src/UI/Themes.json"
        _save_json(Modern_theme, self.active_theme)
        
        self.draw_ui()
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Arial", 24)

        self.zoom = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.is_panning = False
        self.last_mouse_pos = None
        self.spinner_angle = 0

        self.grid_offset = (0, 0)  # offset in world units (not pixels)

        self.selected_card_index = None
        self.selected_position_group = None
        self.selected_position_index = None
        self.dragging_card = False
        self.drag_offset = (0, 0)
        
        self.selection_box = None  # (start_x, start_y, end_x, end_y)
        self.selected_cards: List[Tuple[str, str, int]] = []   # List of (card_name, pos_group, pos_idx) tuples
        self.shift_held = False
        self.alt_held = False
        self.ctrl_held = False
        self.fullscreen = False
        self.show_regions = True  # Toggle for showing bounding boxes
        
        self.base_bounding_box: Tuple[int, int, int, int] | None = None  # (min_x, min_y, max_x, max_y)
        self.deck_bounding_boxes = {}  # deck_name: (min_x, min_y, max_x, max_y)
        self.base_element_bounding_boxes = {}  # element: bbox
        
        # Track placed decks
        self.placed_decks = set()  # Set of deck IDs that have been placed on the grid
        
        # Double-click tracking for card duplication
        self.last_click_time = 0
        self.last_click_pos = None
        self.double_click_threshold = 300  # milliseconds
        self.double_click_distance = 10  # pixels
      
    def draw_grid(self):
        spacing_h = LM.GRID_SPACING[0]  # world units
        spacing_v = LM.GRID_SPACING[0]  # world units
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
    
    def draw_deck_regions(self, surface):
        """Draw the specific deck regions (mainboard, sideboard, maybeboard) for placed decks"""
        import Layout_Manager as LM
        
        # Get board region dimensions from Deck_Manager
        board_regions = self.deck_manager.get_board_regions()
        
        for deck in self.deck_manager.decks:
            if deck.id not in self.placed_decks:
                continue
            
            # Get deck position from the avatar (which should be at the top-left of the deck)
            deck_position = None
            if "avatar" in deck.deck and deck.deck["avatar"]:
                avatar_cards = list(deck.deck["avatar"].keys())
                if avatar_cards:
                    avatar_name = avatar_cards[0]
                    avatar_entries = deck.deck["avatar"][avatar_name]
                    if avatar_entries:
                        deck_position = avatar_entries[0]["position"]
            
            # Fallback: if no avatar, use the first card position
            if not deck_position:
                for board_name, board_data in deck.deck.items():
                    for card_name, entries in board_data.items():
                        if entries:
                            deck_position = entries[0]["position"]
                            break
                    if deck_position:
                        break
            
            if not deck_position:
                continue
            
            # The avatar position is the deck position, so the region starts at the avatar position
            # minus the region padding (since cards are placed with offset from region edge)
            start_x = deck_position[0] - LM.REGION_PADDING
            start_y = deck_position[1] - LM.REGION_PADDING
            
            # Region dimensions from Deck_Manager
            mainboard_width = board_regions["mainboard"]["width"]
            mainboard_height = board_regions["mainboard"]["height"]
            sideboard_width = board_regions["sideboard"]["width"]
            sideboard_height = board_regions["sideboard"]["height"]
            maybeboard_width = board_regions["maybeboard"]["width"]
            maybeboard_height = board_regions["maybeboard"]["height"]
            
            # Draw mainboard region
            mainboard_rect = pygame.Rect(
                start_x * self.zoom + self.offset_x,
                start_y * self.zoom + self.offset_y,
                mainboard_width * self.zoom,
                mainboard_height * self.zoom
            )
            s = pygame.Surface((mainboard_rect.width, mainboard_rect.height), pygame.SRCALPHA)
            s.fill((255, 255, 100, 20))  # Light yellow, very transparent
            surface.blit(s, mainboard_rect.topleft)
            pygame.draw.rect(surface, (255, 255, 100), mainboard_rect, 2)
            
            # Draw sideboard region
            sideboard_y = start_y + mainboard_height
            sideboard_rect = pygame.Rect(
                start_x * self.zoom + self.offset_x,
                sideboard_y * self.zoom + self.offset_y,
                sideboard_width * self.zoom,
                sideboard_height * self.zoom
            )
            s = pygame.Surface((sideboard_rect.width, sideboard_rect.height), pygame.SRCALPHA)
            s.fill((100, 255, 255, 20))  # Light cyan, very transparent
            surface.blit(s, sideboard_rect.topleft)
            pygame.draw.rect(surface, (100, 255, 255), sideboard_rect, 2)
            
            # Draw maybeboard region
            maybeboard_y = sideboard_y + sideboard_height
            maybeboard_rect = pygame.Rect(
                start_x * self.zoom + self.offset_x,
                maybeboard_y * self.zoom + self.offset_y,
                maybeboard_width * self.zoom,
                maybeboard_height * self.zoom
            )
            s = pygame.Surface((maybeboard_rect.width, maybeboard_rect.height), pygame.SRCALPHA)
            s.fill((255, 100, 255, 20))  # Light magenta, very transparent
            surface.blit(s, maybeboard_rect.topleft)
            pygame.draw.rect(surface, (255, 100, 255), maybeboard_rect, 2)
            
            # Draw region labels with center justification and fixed size
            label_y_offset = 4
            
            # Create a fixed-size font for region labels (100 units tall)
            fixed_font_size = int(100 * self.zoom)  # Scale font size with zoom to maintain 100 unit height
            fixed_font = pygame.font.SysFont("Arial", fixed_font_size)
            
            # Mainboard label
            mainboard_text = f"{deck.name} - Mainboard"
            mainboard_text_surface = fixed_font.render(mainboard_text, True, (255, 255, 100))
            mainboard_text_rect = mainboard_text_surface.get_rect()
            mainboard_text_rect.centerx = mainboard_rect.centerx
            mainboard_text_rect.top = mainboard_rect.top + label_y_offset
            self.window.blit(mainboard_text_surface, mainboard_text_rect)
            
            # Sideboard label
            sideboard_text = f"{deck.name} - Sideboard"
            sideboard_text_surface = fixed_font.render(sideboard_text, True, (100, 255, 255))
            sideboard_text_rect = sideboard_text_surface.get_rect()
            sideboard_text_rect.centerx = sideboard_rect.centerx
            sideboard_text_rect.top = sideboard_rect.top + label_y_offset
            self.window.blit(sideboard_text_surface, sideboard_text_rect)
            
            # Maybeboard label
            maybeboard_text = f"{deck.name} - Maybeboard"
            maybeboard_text_surface = fixed_font.render(maybeboard_text, True, (255, 100, 255))
            maybeboard_text_rect = maybeboard_text_surface.get_rect()
            maybeboard_text_rect.centerx = maybeboard_rect.centerx
            maybeboard_text_rect.top = maybeboard_rect.top + label_y_offset
            self.window.blit(maybeboard_text_surface, maybeboard_text_rect)

    def draw_cards(self):
        if self.show_regions:
            self.draw_bounding_boxes(self.window)
        # Always draw deck regions when decks are placed
        self.draw_deck_regions(self.window)
        for card in self.card_manager.cards.values():
            if card.image_surface is None:
                continue
            for pos_group, positions in card.positions.items():
                for position in positions:
                    world_x, world_y = position
                    screen_x = world_x * self.zoom + self.offset_x
                    screen_y = world_y * self.zoom + self.offset_y
                    
                    is_site = getattr(card, "type", "").lower() == "site"

                    # Base dimensions
                    scaled_w = int(LM.CARD_DIMENSIONS[0] * self.zoom)
                    scaled_h = int(LM.CARD_DIMENSIONS[1] * self.zoom)

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
                    if hasattr(card, "name") and self.collection_manager.collection:
                        if card.name in self.collection_manager.collection.cards:
                            pygame.draw.rect(self.window, (255, 255, 255), rect, 2)
                        else:
                            pygame.draw.rect(self.window, (255, 0, 0), rect, 2)
                        
                    if pos_group != "base":
                        # --- Over-committed Outline (orange) ---
                        if hasattr(card, "name") and self.is_card_over_committed(card.name, pos_group) == 0:
                            pygame.draw.rect(self.window, (255, 165, 0), rect, 4)  # Orange outline for over-committed cards
                            
                        elif hasattr(card, "name") and self.is_card_over_committed(card.name, pos_group) < 0:
                            pygame.draw.rect(self.window, (255, 0, 0), rect, 4)  # Red outline for over-committed cards
                            
                        elif hasattr(card, "name") and self.is_card_over_committed(card.name, pos_group) > 0:
                            pygame.draw.rect(self.window, (255, 255, 255), rect, 4)  # White outline for under-committed cards
                
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

        pct = int((self.card_manager.cards_loaded / len(self.card_manager.cards)) * 100)
        text_surface = self.font.render(f"{pct}%", True, (230, 230, 230))
        text_rect = text_surface.get_rect(center=center)
        self.window.blit(text_surface, text_rect)
    
    def draw_debug_info(self):
        """Draw debug information including mouse grid position"""
        mouse_pos = pygame.mouse.get_pos()
        
        # Convert screen coordinates to world coordinates
        world_x = (mouse_pos[0] - self.offset_x) / self.zoom
        world_y = (mouse_pos[1] - self.offset_y) / self.zoom
        
        # Snap to grid
        grid_x = round(world_x / LM.GRID_SPACING[0]) * LM.GRID_SPACING[0]
        grid_y = round(world_y / LM.GRID_SPACING[1]) * LM.GRID_SPACING[1]
        
        # Create debug text
        debug_lines = [
            f"Mouse Screen: ({mouse_pos[0]}, {mouse_pos[1]})",
            f"Mouse World: ({world_x:.1f}, {world_y:.1f})",
            f"Mouse Grid: ({grid_x}, {grid_y})",
            f"Zoom: {self.zoom:.2f}",
            f"Offset: ({self.offset_x:.0f}, {self.offset_y:.0f})",
            f"Base BBox: {self.base_bounding_box}",
            f"Placed Decks: {len(self.placed_decks)}",
            f"Selected Cards: {len(self.selected_cards)}",
            "Controls: Double-click=Duplicate, Delete=Remove deck cards",
            "Save/Load: Layout+Updated Decks"
        ]
        
        # Draw debug info in bottom-right corner with right justification
        line_height = 25
        total_height = len(debug_lines) * line_height
        start_y = self.HEIGHT - total_height - 10  # 10 pixels from bottom
        
        for i, line in enumerate(debug_lines):
            text_surface = self.font.render(line, True, (255, 255, 255))
            # Right justify by positioning text at screen width minus text width
            x_pos = self.WIDTH - text_surface.get_width() - 10  # 10 pixels from right edge
            y_pos = start_y + i * line_height
            self.window.blit(text_surface, (x_pos, y_pos))
    
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
        
    def draw_ui(self):
        # Create new UIManager with the new theme
        self.manager = pygame_gui.UIManager((self.WIDTH, self.HEIGHT), self.active_theme)
        
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
        
        self.sidebar = Sidebar(self.manager, height=self.HEIGHT)
                    
    def handle_event(self, event):
        if event.type == pygame.QUIT:
            return False

        elif event.type == pygame.KEYDOWN or event.type == pygame.KEYUP:
            mods = pygame.key.get_mods()
            self.shift_held = mods & pygame.KMOD_SHIFT
            self.alt_held = mods & pygame.KMOD_ALT
            self.ctrl_held = mods & pygame.KMOD_CTRL
            
            # Handle delete key for card deletion
            if event.type == pygame.KEYDOWN and event.key == pygame.K_DELETE:
                self.delete_selected_cards()

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
                current_time = pygame.time.get_ticks()
                
                # Check for double-click
                is_double_click = False
                if (self.last_click_pos and 
                    current_time - self.last_click_time < self.double_click_threshold and
                    abs(mx - self.last_click_pos[0]) < self.double_click_distance and
                    abs(my - self.last_click_pos[1]) < self.double_click_distance):
                    is_double_click = True
                
                # Update click tracking
                self.last_click_time = current_time
                self.last_click_pos = (mx, my)

                for card in self.card_manager.cards.values():
                    if card.image_surface is None:
                        continue
                    # Check all position groups for hit detection
                    for pos_group, positions in card.positions.items():
                        if not positions:
                            continue
                        for pos_idx, (world_x, world_y) in enumerate(positions):
                            screen_x = world_x * self.zoom + self.offset_x
                            screen_y = world_y * self.zoom + self.offset_y
                            scaled_w = int(LM.CARD_DIMENSIONS[0] * self.zoom)
                            scaled_h = int(LM.CARD_DIMENSIONS[1] * self.zoom)

                            # Adjust for rotated Site cards
                            is_site = getattr(card, "type", "").lower() == "site"
                            if is_site:
                                scaled_w, scaled_h = scaled_h, scaled_w

                            rect = pygame.Rect(screen_x - scaled_w // 2, screen_y - scaled_h // 2, scaled_w, scaled_h)
                            if rect.collidepoint(mx, my):
                                clicked_card = True
                                card_name = card.name
                                
                                # Handle double-click for card duplication/deletion
                                if is_double_click:
                                    self.handle_card_double_click(card_name, pos_group, pos_idx, world_x, world_y)
                                    return True
                                
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

                    for card in self.card_manager.cards.values():
                        if card.image_surface is None:
                            continue
                        # Check all position groups for selection box
                        for pos_group, positions in card.positions.items():
                            if not positions:
                                continue
                            for pos_idx, (world_x, world_y) in enumerate(positions):
                                screen_x = world_x * self.zoom + self.offset_x
                                screen_y = world_y * self.zoom + self.offset_y
                                scaled_w = int(LM.CARD_DIMENSIONS[0] * self.zoom)
                                scaled_h = int(LM.CARD_DIMENSIONS[1] * self.zoom)
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
                
                # DISABLED: Check if cards were dropped on deck regions or dragged out of regions
                # if self.selected_cards:
                #     self.handle_card_drop_on_deck_regions()
                
                if not self.selection_box and self.selected_cards:
                    for name, pos_group, pos_idx in self.selected_cards:
                        if name is None:
                            print("[DEBUG] Skipping None key in selected_cards.")
                            continue
                        if name not in self.card_manager.cards:
                            print(f"[DEBUG] Skipping unknown card name in selected_cards: {name}")
                            continue
                        card = self.card_manager.cards[name]
                        if pos_group in card.positions and pos_idx < len(card.positions[pos_group]):
                            x, y = card.positions[pos_group][pos_idx]
                            snapped_x, snapped_y = self.snap_card_to_grid(x, y, card)
                            card.positions[pos_group][pos_idx] = (snapped_x, snapped_y)
                            # print(f"[DEBUG] Snapped card {name} in {pos_group} to ({snapped_x}, {snapped_y})")

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
                      self.card_manager.cards[self.selected_card_index].positions[self.selected_position_group][self.selected_position_index][0])
                dy = (new_world_y - 
                      self.card_manager.cards[self.selected_card_index].positions[self.selected_position_group][self.selected_position_index][1])

                # Move all selected cards
                for name, pos_group, pos_idx in self.selected_cards:
                    card = self.card_manager.cards[name]
                    if pos_group in card.positions and pos_idx < len(card.positions[pos_group]):
                        x, y = card.positions[pos_group][pos_idx]
                        self.card_manager.cards[name].positions[pos_group][pos_idx] = (x + dx, y + dy)

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
            # Handle sidebar button events
            if hasattr(self, 'sidebar'):
                # Check regular buttons first
                for key, btn_data in self.sidebar.buttons.items():
                    if event.ui_element == btn_data["button"]:
                        self.handle_sidebar_button_click(key)
                        return True
                
                # Check deck buttons
                for deck_id, btn_data in self.sidebar.deck_buttons.items():
                    if event.ui_element == btn_data["button"]:
                        self.handle_deck_button_click(deck_id)
                        return True
                    
        self.manager.process_events(event)
        return True

    def handle_sidebar_button_click(self, button_key):
        """Handle clicks on sidebar buttons"""
        if button_key == "save_layout":
            self.save_layout("layout.json")
        elif button_key == "load_layout":
            self.load_layout("layout.json")
        elif button_key == "load_deck":
            self.deck_manager.load_deck()
        elif button_key == "login":
            self.collection_manager.load_from_curiosa()
        elif button_key == "load_csv":
            self.collection_manager.load_from_csv()

    def handle_deck_button_click(self, deck_id):
        """Handle clicks on deck buttons - place deck on grid (single deck only)"""
        # Find the deck by ID
        deck = None
        for d in self.deck_manager.decks:
            if d.id == deck_id:
                deck = d
                break
        
        if not deck:
            print(f"❌ Deck {deck_id} not found")
            return
        
        # Clear any existing deck before placing the new one
        if self.placed_decks:
            print(f"🗑️ Clearing existing deck before placing '{deck.name}'")
            self.clear_all_placed_decks()
        
        # Place the deck on the grid
        self.place_deck_on_grid(deck)
        
        # Mark deck as placed
        self.placed_decks.add(deck_id)
        
        # Remove the button since deck is now placed
        self.sidebar.remove_deck_button(deck_id)

    def clear_all_placed_decks(self):
        """Clear all placed decks and their card positions from the grid"""
        # Store the deck IDs that were placed so we can restore their buttons
        placed_deck_ids = list(self.placed_decks)
        
        # Remove all deck cards from card manager positions
        for deck in self.deck_manager.decks:
            if deck.id in self.placed_decks:
                for board_name, board_data in deck.deck.items():
                    for card_name, entries in board_data.items():
                        if card_name not in self.card_manager.cards:
                            continue
                        
                        card = self.card_manager.cards[card_name]
                        position_group = f"{deck.name}_{board_name}"
                        
                        # Remove all positions for this deck
                        if position_group in card.positions:
                            del card.positions[position_group]
        
        # Clear placed decks set
        self.placed_decks.clear()
        
        # Clear deck bounding boxes
        self.deck_bounding_boxes.clear()
        
        # Restore deck buttons so users can select a different deck
        for deck_id in placed_deck_ids:
            deck = None
            for d in self.deck_manager.decks:
                if d.id == deck_id:
                    deck = d
                    break
            if deck:
                self.sidebar.add_deck_button(deck.name, deck.id)
        
        print("✅ Cleared all placed decks from the grid")

    def handle_card_double_click(self, card_name: str, pos_group: str, pos_idx: int, world_x: float, world_y: float):
        """Handle double-click on a card - duplicate if in deck, add to deck if base card, ignore if no deck"""
        # Check if this card is in a deck
        deck_name = None
        board_name = None
        
        # Extract deck name from position group (format: "DeckName_boardname")
        if "_" in pos_group:
            parts = pos_group.split("_", 1)
            if len(parts) == 2:
                deck_name = parts[0]
                board_name = parts[1]
        
        if deck_name and board_name:
            # Card is in a deck - duplicate it
            self.duplicate_card_in_deck(card_name, deck_name, board_name, world_x, world_y)
        elif pos_group == "base":
            # Base card - add to deck if one is loaded, otherwise do nothing
            if self.placed_decks:
                self.add_base_card_to_deck(card_name, world_x, world_y)
            else:
                print("ℹ️ No deck loaded - base card double-click ignored")
        else:
            # Card is not in a deck and not a base card - do nothing
            print("ℹ️ Double-click ignored for non-deck, non-base card")

    def duplicate_card_in_deck(self, card_name: str, deck_name: str, board_name: str, world_x: float, world_y: float):
        """Duplicate a card within a deck by adding a new position offset by grid spacing"""
        # Find the deck
        target_deck = None
        for deck in self.deck_manager.decks:
            if deck.name == deck_name and deck.id in self.placed_decks:
                target_deck = deck
                break
        
        if not target_deck:
            print(f"❌ Deck '{deck_name}' not found or not placed")
            return
        
        # Calculate new position offset by grid spacing
        import Layout_Manager as LM
        grid_spacing_x, grid_spacing_y = LM.GRID_SPACING
        new_x = int(world_x + grid_spacing_x)
        new_y = int(world_y + grid_spacing_y)
        
        # Add the card to the deck at the new position
        print(f"➕ Duplicating {card_name} in {deck_name} - {board_name} at ({new_x}, {new_y})")
        target_deck.add_card(board_name, card_name, (new_x, new_y))
        
        # Add to card manager positions
        card = self.card_manager.cards[card_name]
        position_group = f"{deck_name}_{board_name}"
        if position_group not in card.positions:
            card.positions[position_group] = []
        card.positions[position_group].append((new_x, new_y))
        
        print(f"✅ Duplicated {card_name} in {deck_name} - {board_name}")

    def add_base_card_to_deck(self, card_name: str, world_x: float, world_y: float):
        """Add a base card to the currently loaded deck with position offset by grid spacing"""
        # Get the currently loaded deck (should be only one)
        if not self.placed_decks:
            print("❌ No deck loaded")
            return
        
        # Get the first (and only) placed deck
        deck_id = list(self.placed_decks)[0]
        target_deck = None
        for deck in self.deck_manager.decks:
            if deck.id == deck_id:
                target_deck = deck
                break
        
        if not target_deck:
            print("❌ Placed deck not found")
            return
        
        # Calculate new position offset by grid spacing
        import Layout_Manager as LM
        grid_spacing_x, grid_spacing_y = LM.GRID_SPACING
        new_x = int(world_x + grid_spacing_x)
        new_y = int(world_y + grid_spacing_y)
        
        # Add the card to the deck's mainboard at the new position
        print(f"➕ Adding base card {card_name} to {target_deck.name} - mainboard at ({new_x}, {new_y})")
        target_deck.add_card("mainboard", card_name, (new_x, new_y))
        
        # Add to card manager positions
        card = self.card_manager.cards[card_name]
        position_group = f"{target_deck.name}_mainboard"
        if position_group not in card.positions:
            card.positions[position_group] = []
        card.positions[position_group].append((new_x, new_y))
        
        print(f"✅ Added base card {card_name} to {target_deck.name} - mainboard")

    def delete_selected_cards(self):
        """Delete all selected cards from their respective deck locations only"""
        if not self.selected_cards:
            print("ℹ️ No cards selected for deletion")
            return
        
        print(f"🗑️ Deleting {len(self.selected_cards)} selected cards from decks")
        
        # Process each selected card for deletion
        for card_name, pos_group, pos_idx in self.selected_cards:
            if card_name not in self.card_manager.cards:
                continue
            
            # Check if this card is in a deck
            deck_name = None
            board_name = None
            
            # Extract deck name from position group (format: "DeckName_boardname")
            if "_" in pos_group:
                parts = pos_group.split("_", 1)
                if len(parts) == 2:
                    deck_name = parts[0]
                    board_name = parts[1]
            
            if deck_name and board_name:
                # Card is in a deck - remove it from the deck
                self.delete_card_from_deck(card_name, deck_name, board_name, pos_idx)
            else:
                # Card is not in a deck (base card or other) - cannot be deleted
                print(f"ℹ️ Cannot delete {card_name} - not in a deck")
        
        # Clear selection after deletion
        self.selected_cards = []
        print("✅ Card deletion completed")

    def delete_card_from_deck(self, card_name: str, deck_name: str, board_name: str, pos_idx: int):
        """Delete a card from a deck by removing its position"""
        # Find the deck
        target_deck = None
        for deck in self.deck_manager.decks:
            if deck.name == deck_name and deck.id in self.placed_decks:
                target_deck = deck
                break
        
        if not target_deck:
            print(f"❌ Deck '{deck_name}' not found or not placed")
            return
        
        # Get the card's position
        card = self.card_manager.cards[card_name]
        position_group = f"{deck_name}_{board_name}"
        if position_group not in card.positions or pos_idx >= len(card.positions[position_group]):
            print("❌ Card position not found")
            return
        
        position = card.positions[position_group][pos_idx]
        
        # Remove from deck
        print(f"🗑️ Deleting {card_name} from {deck_name} - {board_name} at {position}")
        target_deck.remove_card(board_name, card_name, position)
        
        # Remove from card manager positions
        del card.positions[position_group][pos_idx]
        
        print(f"✅ Deleted {card_name} from {deck_name} - {board_name}")

    def place_deck_on_grid(self, deck):
        """Place a deck on the game grid with proper positioning"""
        # Calculate position based on existing decks
        position = self.calculate_deck_position(deck)
        print(f"Placing deck '{deck.name}' at position {position}")
        
        # Place the deck using the deck manager
        self.deck_manager.place_deck(deck, position, self.card_manager)
        
        # Add deck cards to card manager positions
        self.add_deck_to_card_manager(deck)
        
        print(f"✅ Placed deck '{deck.name}' at position {position}")

    def calculate_deck_position(self, deck):
        """Calculate where to place a deck - always at the same position since only one deck is shown at a time"""
        import Layout_Manager as LM
        
        # Always place at the same position since we only show one deck at a time
        start_x = 0
        start_y = 2035
        
        return (start_x, start_y)

    def add_deck_to_card_manager(self, deck):
        """Add deck cards to the card manager's position tracking"""
        for board_name, board_data in deck.deck.items():
            for card_name, entries in board_data.items():
                if card_name not in self.card_manager.cards:
                    continue
                
                card = self.card_manager.cards[card_name]
                position_group = f"{deck.name}_{board_name}"
                
                # Add positions for this deck
                if position_group not in card.positions:
                    card.positions[position_group] = []
                
                for entry in entries:
                    card.positions[position_group].append(entry["position"])
        
        # Update bounding boxes
        self.update_deck_bounding_boxes()

    def update_deck_bounding_boxes(self):
        """Update bounding boxes for all placed decks"""
        self.deck_bounding_boxes = {}
        
        for deck in self.deck_manager.decks:
            if deck.id in self.placed_decks:
                min_x, min_y, max_x, max_y = float('inf'), float('inf'), float('-inf'), float('-inf')
                
                for board_name, board_data in deck.deck.items():
                    for card_name, entries in board_data.items():
                        for entry in entries:
                            x, y = entry["position"]
                            min_x = min(min_x, x)
                            min_y = min(min_y, y)
                            max_x = max(max_x, x)
                            max_y = max(max_y, y)
                
                if min_x != float('inf'):
                    self.deck_bounding_boxes[deck.name] = (min_x, min_y, max_x, max_y)
                    print(f"Deck bounding box for {deck.name}: {self.deck_bounding_boxes[deck.name]}")

    def save_layout(self, filepath):
        try:
            # Create layout data structure
            layout_data = {
                "card_positions": {name: card.positions for name, card in self.card_manager.cards.items()},
                "metadata": {
                    "version": "1.0",
                    "timestamp": str(pygame.time.get_ticks()),
                    "has_updated_decks": len(self.placed_decks) > 0
                }
            }
            
            # Save layout file
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(layout_data, f, indent=2)
            print(f"✅ Layout saved to {filepath}")
            
            # Save updated decks to separate files
            self.save_updated_decks()
            
        except Exception as e:
            print(f"❌ Failed to save layout: {e}")

    def save_updated_decks(self):
        """Save all placed decks to separate JSON files with '_updated' suffix"""
        if not self.placed_decks:
            print("ℹ️ No decks to save")
            return
        
        saved_count = 0
        for deck in self.deck_manager.decks:
            if deck.id in self.placed_decks:
                try:
                    # Create filename with _updated suffix
                    safe_filename = "".join(c for c in deck.name if c.isalnum() or c in (' ', '-', '_')).rstrip()
                    safe_filename = safe_filename.replace(' ', '_')
                    updated_filename = f"{safe_filename}_updated.json"
                    
                    # Convert deck to JSON format
                    deck_data = {
                        "name": deck.name,
                        "author": deck.author,
                        "id": deck.id,
                        "mainboard": [],
                        "sideboard": [],
                        "maybeboard": [],
                        "avatar": []
                    }
                    
                    # Convert deck structure to JSON format
                    for board_name in ["mainboard", "sideboard", "maybeboard", "avatar"]:
                        if board_name in deck.deck:
                            for card_name, entries in deck.deck[board_name].items():
                                for entry in entries:
                                    card_entry = {
                                        "card": {"name": card_name},
                                        "quantity": 1,
                                        "variant": {
                                            "setCard": {
                                                "set": {"name": entry.get("set_name", "Unknown")},
                                                "meta": {"category": entry.get("kind", "Unknown")}
                                            },
                                            "finish": entry.get("finish", "Unknown"),
                                            "product": entry.get("product", "Unknown")
                                        },
                                        "position": entry["position"]
                                    }
                                    deck_data[board_name].append(card_entry)
                    
                    # Save to file
                    from Util_IO import DECK_PATH
                    deck_filepath = os.path.join(DECK_PATH, updated_filename)
                    with open(deck_filepath, "w", encoding="utf-8") as f:
                        json.dump(deck_data, f, indent=2)
                    
                    print(f"✅ Saved updated deck: {updated_filename}")
                    saved_count += 1
                    
                except Exception as e:
                    print(f"❌ Failed to save updated deck {deck.name}: {e}")
        
        print(f"✅ Saved {saved_count} updated deck(s)")

    def load_layout(self, filepath):
        try:
            if not os.path.exists(filepath):
                print(f"⚠️ Layout file not found: {filepath}")
                return
            
            with open(filepath, "r", encoding="utf-8") as f:
                layout_data = json.load(f)
            
            # Handle both old and new format
            if "card_positions" in layout_data:
                # New format with metadata
                card_positions = layout_data["card_positions"]
                metadata = layout_data.get("metadata", {})
                has_updated_decks = metadata.get("has_updated_decks", False)
                
                # Load updated decks if flag is set
                if has_updated_decks:
                    print("🔄 Loading updated decks...")
                    self.load_updated_decks()
            else:
                # Old format - just card positions
                card_positions = layout_data
                has_updated_decks = False
            
            # Restore positions to the correct CardInfo objects by name
            for name, positions in card_positions.items():
                if name in self.card_manager.cards:
                    self.card_manager.cards[name].positions = positions
            
            print(f"✅ Layout loaded from {filepath}")
            if has_updated_decks:
                print("✅ Updated decks loaded")
            
        except Exception as e:
            print(f"❌ Failed to load layout: {e}")

    def load_updated_decks(self):
        """Load updated deck files and replace existing decks"""
        from Util_IO import DECK_PATH
        
        if not os.path.exists(DECK_PATH):
            print("⚠️ Deck directory not found")
            return
        
        # Find all _updated.json files
        updated_files = []
        for filename in os.listdir(DECK_PATH):
            if filename.endswith("_updated.json"):
                updated_files.append(filename)
        
        if not updated_files:
            print("ℹ️ No updated deck files found")
            return
        
        print(f"📁 Found {len(updated_files)} updated deck file(s)")
        
        # Clear existing placed decks
        self.clear_all_placed_decks()
        
        # Load each updated deck
        for filename in updated_files:
            try:
                filepath = os.path.join(DECK_PATH, filename)
                with open(filepath, "r", encoding="utf-8") as f:
                    deck_data = json.load(f)
                
                # Extract deck info
                deck_name = deck_data.get("name", "Unknown")
                deck_author = deck_data.get("author", "Unknown")
                deck_id = deck_data.get("id", "unknown")
                
                # Create deck object
                deck = Deck.from_json(name=deck_name, author=deck_author, id=deck_id, json_data=deck_data)
                
                # Add to deck manager if not already present
                deck_exists = False
                for existing_deck in self.deck_manager.decks:
                    if existing_deck.id == deck_id:
                        # Replace existing deck
                        existing_deck.deck = deck.deck
                        deck = existing_deck
                        deck_exists = True
                        break
                
                if not deck_exists:
                    self.deck_manager.decks.append(deck)
                
                # Place the deck on the grid
                self.place_deck_on_grid(deck)
                self.placed_decks.add(deck_id)
                
                print(f"✅ Loaded updated deck: {deck_name}")
                
            except Exception as e:
                print(f"❌ Failed to load updated deck {filename}: {e}")
        
        print(f"✅ Loaded {len(updated_files)} updated deck(s)")

    def snap_card_to_grid(self, x, y, card):
        """Snap a card to the appropriate grid based on its type"""
        grid_h, grid_v = Card_Manager.get_adaptive_grid_spacing(card)
        snapped_x = round(x / grid_h) * grid_h
        snapped_y = round(y / grid_v) * grid_v
        return snapped_x, snapped_y

    def is_card_over_committed(self, card_name: str, pos_group: str) -> int:
        """Check if a card is over-committed in a mainboard deck (more copies than available in collection)"""
        # Only check mainboard decks
        if not pos_group.endswith("_mainboard"):
            return False
        
        # If no collection loaded, can't be over-committed
        if not self.collection_manager.collection:
            return False
        
        # Extract deck name from position group (format: "DeckName_mainboard")
        deck_name = pos_group.replace("_mainboard", "")
        
        # Find the deck by name
        target_deck = None
        for deck in self.deck_manager.decks:
            if deck.name == deck_name and deck.id in self.placed_decks:
                target_deck = deck
                break
        
        if not target_deck:
            return False
        
        # Count how many copies are in this deck's mainboard
        deck_copies = 0
        if card_name in target_deck.deck["mainboard"]:
            deck_copies = len(target_deck.deck["mainboard"][card_name])
        
        # Count how many copies are available in collection
        collection_copies = 0
        if card_name in self.collection_manager.collection.cards:
            collection_copies = self.collection_manager.collection.cards[card_name]["total_quantity"]
        
        # Card is over-committed if deck has more copies than collection
        return collection_copies - deck_copies

    def get_deck_region_at_position(self, world_x: float, world_y: float):
        """Get the deck and board region at the given world position"""
        import Layout_Manager as LM
        
        # Get board region dimensions from Deck_Manager
        board_regions = self.deck_manager.get_board_regions()
        
        for deck in self.deck_manager.decks:
            if deck.id not in self.placed_decks:
                continue
            
            # Get deck position from the avatar
            deck_position = None
            if "avatar" in deck.deck and deck.deck["avatar"]:
                avatar_cards = list(deck.deck["avatar"].keys())
                if avatar_cards:
                    avatar_name = avatar_cards[0]
                    avatar_entries = deck.deck["avatar"][avatar_name]
                    if avatar_entries:
                        deck_position = avatar_entries[0]["position"]
            
            if not deck_position:
                continue
            
            # Calculate region boundaries
            start_x = deck_position[0] - LM.REGION_PADDING
            start_y = deck_position[1] - LM.REGION_PADDING
            
            # Check mainboard region
            mainboard_width = board_regions["mainboard"]["width"]
            mainboard_height = board_regions["mainboard"]["height"]
            if (start_x <= world_x <= start_x + mainboard_width and 
                start_y <= world_y <= start_y + mainboard_height):
                return deck, "mainboard"
            
            # Check sideboard region
            sideboard_y = start_y + mainboard_height
            sideboard_height = board_regions["sideboard"]["height"]
            if (start_x <= world_x <= start_x + mainboard_width and 
                sideboard_y <= world_y <= sideboard_y + sideboard_height):
                return deck, "sideboard"
            
            # Check maybeboard region
            maybeboard_y = sideboard_y + sideboard_height
            maybeboard_height = board_regions["maybeboard"]["height"]
            if (start_x <= world_x <= start_x + mainboard_width and 
                maybeboard_y <= world_y <= maybeboard_y + maybeboard_height):
                return deck, "maybeboard"
        
        return None, None

    def handle_card_drop_on_deck_regions(self):
        """Handle dropping cards on deck regions to add/remove them from decks - DISABLED"""
        # DISABLED: Drag-to-add/remove functionality has been disabled
        # This method is kept for reference but is no longer called
        pass
        
        # if not self.selected_cards:
        #     return
        
        # # Get the current mouse position in world coordinates
        # mouse_pos = pygame.mouse.get_pos()
        # world_x = (mouse_pos[0] - self.offset_x) / self.zoom
        # world_y = (mouse_pos[1] - self.offset_y) / self.zoom
        
        # # Check if we're dropping on a deck region
        # target_deck, target_board = self.get_deck_region_at_position(world_x, world_y)
        
        # # If not dropping on a deck region, check if we need to remove cards from decks
        # if not target_deck or not target_board:
        #     self.handle_cards_dropped_outside_deck_regions()
        #     return
        
        # print(f"🎯 Dropping cards on {target_deck.name} - {target_board}")
        # print(f"📊 Cards in {target_board} before: {len(target_deck.deck[target_board])} unique cards")
        
        # # Store original positions to restore them after adding cards
        # original_positions = {}
        # for card_name, pos_group, pos_idx in self.selected_cards:
        #     if card_name not in self.card_manager.cards:
        #         continue
        #     card = self.card_manager.cards[card_name]
        #     if pos_group in card.positions and pos_idx < len(card.positions[pos_group]):
        #         original_positions[(card_name, pos_group, pos_idx)] = card.positions[pos_group][pos_idx]
        
        # # Process each selected card
        # for card_name, pos_group, pos_idx in self.selected_cards:
        #     if card_name not in self.card_manager.cards:
        #         continue
            
        #     card = self.card_manager.cards[card_name]
        #     if pos_group not in card.positions or pos_idx >= len(card.positions[pos_group]):
        #         continue
            
        #     # Check if card is already in this deck and determine source board
        #     card_already_in_deck = False
        #     source_board = None
        #     if card_name in target_deck.deck[target_board]:
        #         for entry in target_deck.deck[target_board][card_name]:
        #             if entry["position"] == card.positions[pos_group][pos_idx]:
        #                 card_already_in_deck = True
        #                 break
            
        #     # Check if card is in a different board of the same deck
        #     if not card_already_in_deck:
        #         for board_name in ["mainboard", "sideboard", "maybeboard"]:
        #             if board_name != target_board and card_name in target_deck.deck[board_name]:
        #                 for entry in deck.deck[board_name][card_name]:
        #                     if entry["position"] == card.positions[pos_group][pos_idx]:
        #                         source_board = board_name
        #                         break
        #                 if source_board:
        #                     break
            
        #     if card_already_in_deck:
        #         # Remove card from deck
        #         print(f"🗑️ Removing {card_name} from {target_deck.name} - {target_board}")
        #         target_deck.remove_card(target_board, card_name, card.positions[pos_group][pos_idx])
                
        #         # Remove from card manager positions
        #         deck_pos_group = f"{target_deck.name}_{target_board}"
        #         if deck_pos_group in card.positions:
        #             # Find and remove the matching position
        #             for i, pos in enumerate(card.positions[deck_pos_group]):
        #                 if pos == card.positions[pos_group][pos_idx]:
        #                     del card.positions[deck_pos_group][i]
        #                     break
        #     elif source_board:
        #         # Move card between boards of the same deck
        #         print(f"🔄 Moving {card_name} from {target_deck.name} - {source_board} to {target_board}")
        #         target_deck.move_card(source_board, target_board, card_name, card.positions[pos_group][pos_idx])
                
        #         # Update card manager positions
        #         old_deck_pos_group = f"{target_deck.name}_{source_board}"
        #         new_deck_pos_group = f"{target_deck.name}_{target_board}"
                
        #         # Remove from old board positions
        #         if old_deck_pos_group in card.positions:
        #             for i, pos in enumerate(card.positions[old_deck_pos_group]):
        #                 if pos == card.positions[pos_group][pos_idx]:
        #                     del card.positions[old_deck_pos_group][i]
        #                     break
                
        #         # Add to new board positions
        #         if new_deck_pos_group not in card.positions:
        #             card.positions[new_deck_pos_group] = []
        #         card.positions[new_deck_pos_group].append(card.positions[pos_group][pos_idx])
                
        #         # For moves within the deck, keep the card at the drop location
        #         # (don't return to original position since we're moving it)
        #         print(f"✅ {card_name} moved to {target_board} at drop location")
        #     else:
        #         # Add card to deck (only if card exists in card manager)
        #         if card_name in self.card_manager.cards:
        #             print(f"➕ Adding {card_name} to {target_deck.name} - {target_board}")
        #             target_deck.add_card(target_board, card_name, card.positions[pos_group][pos_idx])
                    
        #             # Add to card manager positions
        #             deck_pos_group = f"{target_deck.name}_{target_board}"
        #             if deck_pos_group not in card.positions:
        #                 card.positions[deck_pos_group] = []
        #             card.positions[deck_pos_group].append(card.positions[pos_group][pos_idx])
                    
        #             # Return the dragged card to its original position
        #             original_pos = original_positions.get((card_name, pos_group, pos_idx))
        #             if original_pos:
        #                 card.positions[pos_group][pos_idx] = original_pos
        #                 print(f"🔄 Returning {card_name} to original position {original_pos}")
        #         else:
        #             print(f"⚠️ Cannot add {card_name} to deck - card not found in card manager")
        
        # print(f"📊 Cards in {target_board} after: {len(target_deck.deck[target_board])} unique cards")

    def handle_cards_dropped_outside_deck_regions(self):
        """Handle cards that were dropped outside of deck regions - remove them from decks - DISABLED"""
        # DISABLED: Drag-to-remove functionality has been disabled
        # This method is kept for reference but is no longer called
        pass
        
        # if not self.selected_cards:
        #     return
        
        # print("🚪 Cards dropped outside deck regions - checking for removal")
        
        # # Check each selected card to see if it was originally from a deck
        # for card_name, pos_group, pos_idx in self.selected_cards:
        #     if card_name not in self.card_manager.cards:
        #         continue
            
        #     card = self.card_manager.cards[card_name]
        #     if pos_group not in card.positions or pos_idx >= len(card.positions[pos_group]):
        #         continue
            
        #     # Check if this card is in any deck
        #     for deck in self.deck_manager.decks:
        #         if deck.id not in self.placed_decks:
        #             continue
                
        #         for board_name in ["mainboard", "sideboard", "maybeboard"]:
        #             if card_name in deck.deck[board_name]:
        #                 for entry in deck.deck[board_name][card_name]:
        #                     if entry["position"] == card.positions[pos_group][pos_idx]:
        #                         # Found the card in a deck - remove it
        #                         print(f"🗑️ Removing {card_name} from {deck.name} - {board_name} (dragged outside)")
        #                         deck.remove_card(board_name, card_name, card.positions[pos_group][pos_idx])
                                
        #                         # Remove from card manager positions
        #                         deck_pos_group = f"{deck.name}_{board_name}"
        #                         if deck_pos_group in card.positions:
        #                             for i, pos in enumerate(card.positions[deck_pos_group]):
        #                                 if pos == card.positions[pos_group][pos_idx]:
        #                                     del card.positions[deck_pos_group][i]
        #                                     break
        #                         break
        #                 else:
        #                     continue
        #                 break

    def draw_card_preview(self):
        """Draw a large preview of the card being hovered over in the top right corner"""
        mouse_pos = pygame.mouse.get_pos()
        hovered_card = None
        
        # Find which card the mouse is hovering over
        for card in self.card_manager.cards.values():
            if card.image_surface is None:
                continue
            for pos_group, positions in card.positions.items():
                if not positions:
                    continue
                for pos_idx, (world_x, world_y) in enumerate(positions):
                    screen_x = world_x * self.zoom + self.offset_x
                    screen_y = world_y * self.zoom + self.offset_y
                    scaled_w = int(LM.CARD_DIMENSIONS[0] * self.zoom)
                    scaled_h = int(LM.CARD_DIMENSIONS[1] * self.zoom)

                    # Adjust for rotated Site cards
                    is_site = getattr(card, "type", "").lower() == "site"
                    if is_site:
                        scaled_w, scaled_h = scaled_h, scaled_w

                    rect = pygame.Rect(screen_x - scaled_w // 2, screen_y - scaled_h // 2, scaled_w, scaled_h)
                    if rect.collidepoint(mouse_pos):
                        hovered_card = card
                        break
                if hovered_card:
                    break
            if hovered_card:
                break
        
        if hovered_card and hovered_card.image_surface:
            # Check if this is a site card (horizontal cards)
            is_site = getattr(hovered_card, "type", "").lower() == "site"
            
            if is_site:
                # For site cards, use width as the base dimension and rotate
                preview_width = 420
                preview_height = int(preview_width * (LM.CARD_DIMENSIONS[1] / LM.CARD_DIMENSIONS[0]))
                
                # Scale the card image for preview
                preview_surface = pygame.transform.smoothscale(hovered_card.image_surface, (preview_width, preview_height))
                # Rotate the preview -90 degrees (clockwise)
                preview_surface = pygame.transform.rotate(preview_surface, -90)
            else:
                # For regular cards, use width as the base dimension
                preview_width = 300
                preview_height = int(preview_width * (LM.CARD_DIMENSIONS[1] / LM.CARD_DIMENSIONS[0]))
                
                # Scale the card image for preview
                preview_surface = pygame.transform.smoothscale(hovered_card.image_surface, (preview_width, preview_height))
            
            # Position in top right corner with some padding
            padding = 20
            preview_x = self.WIDTH - preview_surface.get_width() - padding
            preview_y = padding
            
            # Draw background rectangle for the preview
            bg_rect = pygame.Rect(preview_x - 10, preview_y - 10, preview_surface.get_width() + 20, preview_surface.get_height() + 20)
            pygame.draw.rect(self.window, (50, 50, 50), bg_rect)
            pygame.draw.rect(self.window, (200, 200, 200), bg_rect, 2)
            
            # Draw the card preview
            self.window.blit(preview_surface, (preview_x, preview_y))

    def run(self):
        running = True
        while running:
            time_delta = self.clock.tick(60) / 1000.0
            mouse_pos = pygame.mouse.get_pos()
            
            self.sidebar.update(mouse_pos)
            
            for event in pygame.event.get():
                running = self.handle_event(event)
            
            self.manager.update(time_delta)
            self.window.fill(self.background_color)  # new black background

            self.draw_grid()
            self.draw_cards()
            self.draw_selection_box()
            
            if self.card_manager.loading:
                self.draw_loading_ui()
            
            self.draw_debug_info()
            self.draw_card_preview()  # Draw the new preview

            self.manager.draw_ui(self.window)
            
            # Draw button images on top of the UI
            self.sidebar.draw_button_images(self.window)
            
            pygame.display.flip()

        pygame.quit()
