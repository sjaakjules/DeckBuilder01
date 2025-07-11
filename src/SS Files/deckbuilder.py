import os
import re
import math
import json
import pygame
import requests
import pygame_gui
from typing import Optional
from pathlib import Path
from CardInfo import Card
from Curiosa_User import CuriosaAPI
from Util_Debug import DebugDisplay
import Util_Config as config

CARD_ASSETS_PATH = "assets/Cards"


class DeckBuilder:
    def __init__(self):
        pygame.init()
        self.screen_width = 1600
        self.screen_height = 1200
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        pygame.display.set_caption("Sorcery Card Grid")

        self.clock = pygame.time.Clock()
        DebugDisplay.initialize(self.screen, self.clock)
        self.gui_manager = pygame_gui.UIManager((self.screen_width, self.screen_height))

        self.game_state = "loading"
        self.cards_loaded = False
        self.loading_text = "Initializing..."

        self.cards = []
        self.card_size = (100, 150)
        self.camera_x = 0
        self.camera_y = 0
        self.zoom = 1.0
        self.target_zoom = 1.0
        self.dragging = False
        self.drag_start = None

        self.dragged_card = None
        self.dragged_card_index = None
        self.drag_offset = None

        self.BACKGROUND_COLOR = (20, 20, 30)
        self.GRID_COLOR = (40, 40, 50)
        self.CARD_BORDER_COLOR = (100, 100, 150)
        
        self.cardinfo_list = []
        
        self.init_game()

    def init_game(self):
        DebugDisplay.add_message("Initializing Card Grid Game...")

        if os.path.exists(CuriosaAPI.cards_path):
            self.loading_text = "Loading cached cards..."
            try:
                if CuriosaAPI.have_loaded_cards:
                    print(f"Got {len(CuriosaAPI.all_cards)} cards from cache")
                    DebugDisplay.add_message(f"Got {len(CuriosaAPI.all_cards)} cards from cache")
                    self.cardinfo_list = self.generate_cardinfo_list()
                    print(f"Got {len(self.cardinfo_list)} cards in custom class type")
                    self.layout_cards()
                    return
            except Exception as e:
                print(f"Failed to load cached cards: {e}")
                DebugDisplay.add_message(f"Failed to load cached cards: {e}")
                self.loading_text = "Failed to load cached cards"

    def layout_cards(self):
        def get_threshold_group(card_info):
            thresholds = card_info.thresholds
            active = [k for k, v in thresholds.items() if v > 0]
            if len(active) == 0:
                return 'none'
            elif len(active) > 1:
                return 'multiple'
            return active[0]

        def get_category(card_info):
            return card_info.type or 'Unknown'

        def get_rarity(card_info):
            return card_info.rareity or 'Common'

        def get_type_and_cost(card_info):
            return (card_info.type or '', card_info.cost or 0)

        cards = self.cardinfo_list
        cards.sort(key=lambda c: (get_threshold_group(c), get_category(c), get_rarity(c)) + get_type_and_cost(c))

        x_start, y_start = 100, 100
        x, y = x_start, y_start
        last_threshold = last_category = last_rarity = None

        for card_info in cards:
            threshold = get_threshold_group(card_info)
            category = get_category(card_info)
            rarity = get_rarity(card_info)

            if threshold != last_threshold:
                x = x_start
                y += 200
                last_threshold = threshold
                last_category = None
            elif category != last_category:
                x = x_start
                y += 160
                last_category = category
                last_rarity = None
            elif rarity != last_rarity:
                x = x_start
                y += 130
                last_rarity = rarity

            image_path = self.download_card_image(card_info.image_url, card_info.name)
            image = self.load_card_image(image_path) if image_path else None

            self.cards.append({
                'data': card_info,
                'position': [x, y],
                'original_position': (x, y),
                'image_path': image_path,
                'image': image
            })

            x += self.card_size[0] + 20

        self.game_state = "playing"
        self.cards_loaded = True

    def download_card_image(self, url, name):
        try:
            safe_name = re.sub(r'[^\w\-_\.]', '_', name)
            image_path = os.path.join(CARD_ASSETS_PATH, f"{safe_name}.png")
            if os.path.exists(image_path):
                return image_path
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            os.makedirs(CARD_ASSETS_PATH, exist_ok=True)
            with open(image_path, 'wb') as f:
                f.write(response.content)
            return image_path
        except Exception as e:
            print(f"Failed to download {name}: {e}")
            return None

    def load_card_image(self, path):
        try:
            image = pygame.image.load(path)
            return pygame.transform.scale(image, self.card_size)
        except Exception:
            return None

    def handle_mouse_events(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                self.handle_left_click(event.pos)
            elif event.button == 2:
                self.dragging = True
                self.drag_start = event.pos
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                self.dragged_card = None
                self.drag_offset = None
            elif event.button == 2:
                self.dragging = False
                self.drag_start = None
        elif event.type == pygame.MOUSEMOTION:
            if self.dragging and self.drag_start:
                dx = event.pos[0] - self.drag_start[0]
                dy = event.pos[1] - self.drag_start[1]
                self.camera_x += dx / self.zoom
                self.camera_y += dy / self.zoom
                self.drag_start = event.pos
            elif self.dragged_card and self.drag_offset:
                world_pos = self.screen_to_world((event.pos[0] - self.drag_offset[0], event.pos[1] - self.drag_offset[1]))
                self.dragged_card['position'] = list(world_pos)
        elif event.type == pygame.MOUSEWHEEL:
            zoom_factor = 1.1 if event.y > 0 else 0.9
            self.target_zoom *= zoom_factor
            self.target_zoom = max(0.1, min(5.0, self.target_zoom))

    def handle_left_click(self, pos):
        for i, card in enumerate(self.cards):
            card_pos = self.world_to_screen(card['position'])
            if (card_pos[0] <= pos[0] <= card_pos[0] + self.card_size[0] and
                card_pos[1] <= pos[1] <= card_pos[1] + self.card_size[1]):
                self.dragged_card = card
                self.drag_offset = (pos[0] - card_pos[0], pos[1] - card_pos[1])
                break

    def world_to_screen(self, pos):
        return (
            (pos[0] - self.camera_x) * self.zoom + self.screen_width // 2,
            (pos[1] - self.camera_y) * self.zoom + self.screen_height // 2
        )

    def screen_to_world(self, pos):
        return (
            (pos[0] - self.screen_width // 2) / self.zoom + self.camera_x,
            (pos[1] - self.screen_height // 2) / self.zoom + self.camera_y
        )

    def draw(self):
        self.screen.fill(self.BACKGROUND_COLOR)
        if self.game_state == "loading":
            font = pygame.font.Font(None, 48)
            text = font.render("Loading Cards...", True, (255, 255, 255))
            text_rect = text.get_rect(center=(self.screen_width // 2, self.screen_height // 2))
            self.screen.blit(text, text_rect)
        elif self.game_state == "playing":
            self.draw_grid()
            self.draw_cards()
        DebugDisplay.draw()

    def draw_grid(self):
        grid_size = 50 * self.zoom
        offset_x = (self.camera_x * self.zoom) % grid_size
        offset_y = (self.camera_y * self.zoom) % grid_size
        for x in range(0, self.screen_width + int(grid_size), int(grid_size)):
            pygame.draw.line(self.screen, self.GRID_COLOR, (x - offset_x, 0), (x - offset_x, self.screen_height))
        for y in range(0, self.screen_height + int(grid_size), int(grid_size)):
            pygame.draw.line(self.screen, self.GRID_COLOR, (0, y - offset_y), (self.screen_width, y - offset_y))

    def draw_cards(self):
        for card in self.cards:
            screen_pos = self.world_to_screen(card['position'])
            pygame.draw.rect(self.screen, self.CARD_BORDER_COLOR, (screen_pos[0], screen_pos[1], self.card_size[0], self.card_size[1]))
            if card['image']:
                self.screen.blit(card['image'], screen_pos)
            else:
                pygame.draw.rect(self.screen, (50, 50, 80), (screen_pos[0] + 2, screen_pos[1] + 2, self.card_size[0] - 4, self.card_size[1] - 4))

    def run(self):
        running = True
        while running:
            time_delta = self.clock.tick(60) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                self.handle_mouse_events(event)
                self.gui_manager.process_events(event)

            if abs(self.zoom - self.target_zoom) > 0.001:
                self.zoom += (self.target_zoom - self.zoom) * 0.1

            self.gui_manager.update(time_delta)
            self.draw()
            self.gui_manager.draw_ui(self.screen)
            pygame.display.flip()
        pygame.quit()
        
    def generate_cardinfo_list(self):
        curiosa_cards = []
        sorcery_cards = []
        for card in CuriosaAPI.all_cards:
            variants = card.get("variants", [])
            image_url = variants[0]["src"] if variants and len(variants) > 0 else None
            cardinfo_list.append(Card(image_url, card))
        return cardinfo_list

