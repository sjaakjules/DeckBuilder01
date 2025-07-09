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


class GUI:
    def __init__(self, width=1200, height=900):
        pygame.init()
        self.WIDTH, self.HEIGHT = width, height
        self.window = pygame.display.set_mode((self.WIDTH, self.HEIGHT))
        pygame.display.set_caption("Sorcery TCG Viewer")

        self.manager = pygame_gui.UIManager((self.WIDTH, self.HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Arial", 24)

        self.zoom = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.is_panning = False
        self.last_mouse_pos = None
        self.spinner_angle = 0

        self.CARD_WIDTH, self.CARD_HEIGHT = 100, 140
        self.GRID_SPACING = 160
        self.grid_offset = (50, 50)  # offset in world units (not pixels)

        self.selected_card_index = None
        self.dragging_card = False
        self.drag_offset = (0, 0)
        self.card_data = CardData()
        self.card_images = [None] * len(self.card_data.cards)
        self.card_positions = [
            ((i % 10) * self.GRID_SPACING, (i // 10) * self.GRID_SPACING)
            for i in range(len(self.card_data.cards))
        ]
        self.selection_box = None  # (start_x, start_y, end_x, end_y)
        self.selected_cards = []   # List of selected card indices
        self.shift_held = False
        self.alt_held = False
        
        self.cards_loaded = 0
        self.loading = True

        # Asset cache folder
        self.cache_folder = os.path.join("assets", "Cards")
        os.makedirs(self.cache_folder, exist_ok=True)

        # Background download setup
        self.download_queue = queue.Queue()
        for i, card in enumerate(self.card_data.cards):
            self.download_queue.put((i, card.image_url))
        self.download_thread = threading.Thread(target=self.download_worker, daemon=True)
        self.download_thread.start()
        
        button_y = 10
        button_w = 120
        button_h = 30
        button_spacing = 10
        start_x = 10

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

        self.login_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((start_x + (button_w + button_spacing) * 3, button_y), (button_w, button_h)),
            text="Login",
            manager=self.manager
        )

        self.curiosa = None
        self.owned_slugs = set()

    def download_worker(self):
        while not self.download_queue.empty():
            i, url = self.download_queue.get()
            try:
                filename = os.path.join(self.cache_folder, os.path.basename(url))
                if os.path.exists(filename):
                    with open(filename, "rb") as f:
                        img_data = f.read()
                else:
                    response = requests.get(url, timeout=5)
                    img_data = response.content
                    with open(filename, "wb") as f:
                        f.write(img_data)

                img = Image.open(BytesIO(img_data)).convert("RGBA")
                pygame_img = pygame.image.frombuffer(img.tobytes(), img.size, img.mode)
                self.card_images[i] = pygame_img
                self.cards_loaded += 1
            except Exception as e:
                print(f"Error loading card {i}: {e}")
            self.download_queue.task_done()

        self.loading = False

    def draw_grid(self):
        spacing = self.GRID_SPACING  # world units
        zoomed_spacing = spacing * self.zoom
        color = (80, 80, 80)

        # Grid offset in world space
        offset_x_units, offset_y_units = self.grid_offset

        # Viewport bounds in world space
        left = -self.offset_x / self.zoom
        right = (self.WIDTH - self.offset_x) / self.zoom
        top = -self.offset_y / self.zoom
        bottom = (self.HEIGHT - self.offset_y) / self.zoom

        # Adjusted range with grid offset
        start_x = int((left - offset_x_units) // spacing) * spacing + offset_x_units
        end_x = int((right - offset_x_units) // spacing + 1) * spacing + offset_x_units
        start_y = int((top - offset_y_units) // spacing) * spacing + offset_y_units
        end_y = int((bottom - offset_y_units) // spacing + 1) * spacing + offset_y_units

        for x in range(start_x, end_x, spacing):
            sx = x * self.zoom + self.offset_x
            pygame.draw.line(self.window, color, (sx, 0), (sx, self.HEIGHT))

        for y in range(start_y, end_y, spacing):
            sy = y * self.zoom + self.offset_y
            pygame.draw.line(self.window, color, (0, sy), (self.WIDTH, sy))

    def draw_cards(self):
        for idx, card_surface in enumerate(self.card_images):
            if card_surface is None:
                continue

            world_x, world_y = self.card_positions[idx]
            screen_x = world_x * self.zoom + self.offset_x
            screen_y = world_y * self.zoom + self.offset_y

            card_info = self.card_data.cards[idx]
            is_site = getattr(card_info, "type", "").lower() == "site"

            # Base dimensions
            scaled_w = int(self.CARD_WIDTH * self.zoom)
            scaled_h = int(self.CARD_HEIGHT * self.zoom)

            # Prepare and transform card image
            scaled_surface = pygame.transform.smoothscale(card_surface, (scaled_w, scaled_h))

            if is_site:
                rotated_surface = pygame.transform.rotate(scaled_surface, -90)  # clockwise
                rect = rotated_surface.get_rect(center=(screen_x, screen_y))
                self.window.blit(rotated_surface, rect.topleft)
            else:
                rect = scaled_surface.get_rect(center=(screen_x, screen_y))
                self.window.blit(scaled_surface, rect.topleft)

            # --- Selection Outline (yellow) ---
            if idx in self.selected_cards:
                pygame.draw.rect(self.window, (255, 255, 0), rect, 3)

            # --- Ownership Outline (white/red) ---
            if hasattr(card_info, "name") and self.owned_slugs:
                if card_info.name in self.owned_slugs:
                    pygame.draw.rect(self.window, (255, 255, 255), rect, 2)
                else:
                    pygame.draw.rect(self.window, (255, 0, 0), rect, 2)
                
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

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            return False

        elif event.type == pygame.KEYDOWN or event.type == pygame.KEYUP:
            mods = pygame.key.get_mods()
            self.shift_held = mods & pygame.KMOD_SHIFT
            self.alt_held = mods & pygame.KMOD_ALT

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 3:  # Right click = pan
                self.is_panning = True
                self.last_mouse_pos = event.pos

            elif event.button == 1:  # Left click
                mx, my = event.pos
                clicked_card = False

                for i, card in enumerate(self.card_images):
                    if card is None:
                        continue
                    world_x, world_y = self.card_positions[i]
                    screen_x = world_x * self.zoom + self.offset_x
                    screen_y = world_y * self.zoom + self.offset_y
                    scaled_w = int(self.CARD_WIDTH * self.zoom)
                    scaled_h = int(self.CARD_HEIGHT * self.zoom)

                    # Adjust for rotated Site cards
                    card_info = self.card_data.cards[i]
                    is_site = getattr(card_info, "type", "").lower() == "site"
                    if is_site:
                        scaled_w, scaled_h = scaled_h, scaled_w

                    rect = pygame.Rect(screen_x - scaled_w // 2, screen_y - scaled_h // 2, scaled_w, scaled_h)
                    if rect.collidepoint(mx, my):
                        clicked_card = True

                        # Don't change selection if clicking an already selected card without modifiers
                        if i in self.selected_cards and not self.shift_held and not self.alt_held:
                            self.selected_card_index = i
                            self.dragging_card = True
                            self.drag_offset = (
                                (mx - screen_x) / self.zoom,
                                (my - screen_y) / self.zoom
                            )
                            break

                        # Alt removes from selection
                        if self.alt_held:
                            if i in self.selected_cards:
                                self.selected_cards.remove(i)
                            break

                        # Shift adds to selection
                        if self.shift_held:
                            if i not in self.selected_cards:
                                self.selected_cards.append(i)
                            self.selected_card_index = i
                            self.dragging_card = True
                            self.drag_offset = (
                                (mx - screen_x) / self.zoom,
                                (my - screen_y) / self.zoom
                            )
                            break

                        # Default behavior: select this card only
                        self.selected_cards = [i]
                        self.selected_card_index = i
                        self.dragging_card = True
                        self.drag_offset = (
                            (mx - screen_x) / self.zoom,
                            (my - screen_y) / self.zoom
                        )
                        break

                if not clicked_card:
                    # Start selection box
                    if not self.shift_held and not self.alt_held:
                        self.selected_cards = []
                    self.selected_card_index = None
                    self.selection_box = (mx, my, mx, my)

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 3:
                self.is_panning = False
            elif event.button == 1:
                if self.selection_box:
                    x0, y0, x1, y1 = self.selection_box
                    box = pygame.Rect(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))
                    affected = []

                    for i, card in enumerate(self.card_images):
                        if card is None:
                            continue
                        world_x, world_y = self.card_positions[i]
                        screen_x = world_x * self.zoom + self.offset_x
                        screen_y = world_y * self.zoom + self.offset_y
                        scaled_w = int(self.CARD_WIDTH * self.zoom)
                        scaled_h = int(self.CARD_HEIGHT * self.zoom)

                        # Check for rotated sites
                        card_info = self.card_data.cards[i]
                        is_site = getattr(card_info, "type", "").lower() == "site"
                        if is_site:
                            scaled_w, scaled_h = scaled_h, scaled_w

                        rect = pygame.Rect(screen_x - scaled_w // 2, screen_y - scaled_h // 2, scaled_w, scaled_h)

                        if box.colliderect(rect):
                            affected.append(i)

                    if self.alt_held:
                        self.selected_cards = [i for i in self.selected_cards if i not in affected]
                    elif self.shift_held:
                        for i in affected:
                            if i not in self.selected_cards:
                                self.selected_cards.append(i)
                    else:
                        self.selected_cards = affected

                    self.selection_box = None
                self.dragging_card = False

        elif event.type == pygame.MOUSEMOTION:
            if self.is_panning:
                dx = event.pos[0] - self.last_mouse_pos[0]
                dy = event.pos[1] - self.last_mouse_pos[1]
                self.offset_x += dx
                self.offset_y += dy
                self.last_mouse_pos = event.pos

            elif self.dragging_card and self.selected_card_index is not None:
                mx, my = event.pos
                new_world_x = (mx - self.offset_x) / self.zoom - self.drag_offset[0]
                new_world_y = (my - self.offset_y) / self.zoom - self.drag_offset[1]
                dx = new_world_x - self.card_positions[self.selected_card_index][0]
                dy = new_world_y - self.card_positions[self.selected_card_index][1]

                # Move all selected cards
                for i in self.selected_cards:
                    x, y = self.card_positions[i]
                    self.card_positions[i] = (x + dx, y + dy)

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
                grouped = self.group_and_sort_cards(self.card_data.cards)
                layout = self.layout_grouped_cards_treemap_style(grouped, zoom=self.zoom)
                for idx, (x, y) in layout.items():
                    self.card_positions[idx] = (x, y)
            elif event.ui_element == self.save_button:
                self.save_layout("layout.json")
            elif event.ui_element == self.load_button:
                self.load_layout("layout.json")
            elif event.ui_element == self.login_button:
                self.login_to_curiosa()
                    
        self.manager.process_events(event)
        return True

    def login_to_curiosa(self):
        try:
            self.curiosa = CuriosaAPI()
            self.curiosa.login()
            self.curiosa.fetch_user_cards()
            if self.curiosa.collection:
                for card in self.curiosa.collection:
                    self.owned_slugs.add(card["card"]["name"])
            else:
                print("❌ No collection found")
            print(f"✅ Logged in. Found {len(self.owned_slugs)} owned cards.")
        except Exception as e:
            print(f"❌ Login failed: {e}")
            
    def save_layout(self, filepath):
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self.card_positions, f)
            print(f"✅ Layout saved to {filepath}")
        except Exception as e:
            print(f"❌ Failed to save layout: {e}")

    def load_layout(self, filepath):
        try:
            if not os.path.exists(filepath):
                print(f"⚠️ Layout file not found: {filepath}")
                return
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Convert keys back to int
            self.card_positions = {int(k): tuple(v) for k, v in data.items()}
            print(f"✅ Layout loaded from {filepath}")
        except Exception as e:
            print(f"❌ Failed to load layout: {e}")
            
    def group_and_sort_cards(self, cards):
        grouped = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

        for idx, card in enumerate(cards):
            # Determine element key
            if not card.elements:
                element_key = "None"
            elif len(card.elements) > 1:
                element_key = "Multiple"
            else:
                element_key = card.elements[0]

            # Group Auras and Magic together
            original_type = card.type or "Unknown"
            if original_type in ["Aura", "Magic"]:
                type_key = "Spell"
            else:
                type_key = original_type

            # Handle missing rarity
            rarity_key = card.rareity or "Ordinary"

            grouped[element_key][type_key][rarity_key].append((idx, card))

        # Sort each rarity group by subtype then cost
        for element_groups in grouped.values():
            for type_groups in element_groups.values():
                for rarity_key, items in type_groups.items():
                    type_groups[rarity_key] = sorted(
                        items,
                        key=lambda item: (
                            ", ".join(item[1].subtypes) if item[1].subtypes else "",
                            item[1].cost if item[1].cost is not None else 999
                        )
                    )

        return grouped

    def layout_grouped_cards_grid_3x4(self, grouped, zoom=1.0):
        layout = {}
        card_base_w = self.CARD_WIDTH
        card_base_h = self.CARD_HEIGHT
        pad = 20  # spacing between cards

        spacing_element = 300
        spacing_type = 200
        spacing_rarity = 100

        # Arrange element groups in 3x4 grid
        element_keys = list(grouped.keys())
        grid_cols = 3
        grid_rows = 4

        assert len(element_keys) <= grid_cols * grid_rows, "Too many element groups for 3x4 layout"

        # Calculate position of each element group in 3x4 grid
        element_positions = {}
        for idx, element_key in enumerate(element_keys):
            col = idx % grid_cols
            row = idx // grid_cols
            element_x = col * (2000 + spacing_element)  # Estimate width per block
            element_y = row * (1200 + spacing_element)
            element_positions[element_key] = (element_x, element_y)

        for element_key, types in grouped.items():
            element_x, element_y = element_positions[element_key]

            type_keys = list(types.keys())
            for t_idx, type_key in enumerate(type_keys):
                type_x = element_x + t_idx * (600 + spacing_type)
                rarity_y = element_y

                for r_idx, rarity_key in enumerate(["Common", "Ordinary", "Elite", "Unique"]):
                    cards = types[type_key].get(rarity_key, [])
                    num_cards = len(cards)
                    if num_cards == 0:
                        continue

                    # Square layout per rarity group
                    cols = max(1, int(math.ceil(math.sqrt(num_cards))))
                    rows = math.ceil(num_cards / cols)

                    for i, (card_index, card) in enumerate(cards):
                        row = i // cols
                        col = i % cols

                        is_site = getattr(card, "type", "").lower() == "site"
                        c_w = int(card_base_h * zoom) if is_site else int(card_base_w * zoom)
                        c_h = int(card_base_w * zoom) if is_site else int(card_base_h * zoom)

                        x = type_x + col * (c_w + pad)
                        y = rarity_y + row * (c_h + pad)
                        layout[card_index] = (x, y)

                    rarity_y += rows * (card_base_h + pad) + spacing_rarity

        return layout
    
    def layout_grouped_cards_treemap_style(self, grouped, zoom=1.0):
        layout = {}
        card_w = int(self.CARD_WIDTH * zoom)
        card_h = int(self.CARD_HEIGHT * zoom)
        pad = 20  # spacing between cards

        spacing_element = 300
        spacing_type = 200
        spacing_rarity = 100

        x_offset = 0

        for element_key, types in grouped.items():
            # Flatten all cards under this element to size bounding grid
            total_cards = sum(len(items) for r in types.values() for items in r.values())
            est_cols = max(1, int(math.sqrt(total_cards)))
            col_width = est_cols * (card_w + pad)
            row_height = ((total_cards // est_cols) + 1) * (card_h + pad)

            # Reset local offset for this element group
            local_x = 0
            local_y = 0
            for type_key, rarities in types.items():
                for rarity_key, items in rarities.items():
                    num_cards = len(items)
                    cols = max(1, int(math.ceil(math.sqrt(num_cards))))
                    rows = math.ceil(num_cards / cols)

                    for i, (card_index, _) in enumerate(items):
                        row = i // cols
                        col = i % cols
                        x = x_offset + local_x + col * (card_w + pad)
                        y = local_y + row * (card_h + pad)
                        layout[card_index] = (x, y)

                    # advance local_y for next rarity
                    local_y += rows * (card_h + pad) + spacing_rarity
                local_y += spacing_type

            # advance to next top-level element group
            x_offset += col_width + spacing_element

        return layout

    def run(self):
        running = True
        while running:
            time_delta = self.clock.tick(60) / 1000.0
            self.window.fill((0, 0, 0))  # new black background

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