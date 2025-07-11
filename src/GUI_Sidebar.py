import pygame
import pygame_gui
import os
from pygame_gui.elements import UIButton


class Sidebar:
    def __init__(self, gui_manager, width=50, expanded_width=200, height=900):
        self.manager = gui_manager
        self.width = width
        self.expanded_width = expanded_width
        self.height = height
        self.expanded = False

        self.panel = pygame_gui.elements.UIPanel(
            relative_rect=pygame.Rect((0, 0), (self.width, self.height)),
            manager=self.manager,
        )

        self.buttons = {}
        self.deck_buttons = {}  # Dynamic deck buttons
        self.button_images = {}
        self.load_button_images()
        self.create_buttons()
    
    def load_button_images(self):
        """Load button images from assets/buttons/ directory"""
        button_image_path = "assets/buttons"
        if not os.path.exists(button_image_path):
            print(f"Button images directory not found: {button_image_path}")
            return
            
        image_files = {
            "login": "login.png",
            "load_csv": "csv.png", 
            "load_deck": "deck.png",
            "save_layout": "save.png",
            "load_layout": "load.png",
            "add": "add.png"  # For deck buttons
        }
        
        for key, filename in image_files.items():
            filepath = os.path.join(button_image_path, filename)
            if os.path.exists(filepath):
                try:
                    # Load image with antialiasing
                    original_image = pygame.image.load(filepath).convert_alpha()
                    # Scale image with antialiasing to fit button size (assuming 40x40 for icon buttons)
                    self.button_images[key] = pygame.transform.smoothscale(original_image, (40, 40))
                except Exception as e:
                    print(f"Failed to load button image {filepath}: {e}")
                    self.button_images[key] = None
            else:
                print(f"Button image not found: {filepath}")
                self.button_images[key] = None

    def create_buttons(self):
        button_height = 50
        y_pos = 0

        items = [
            ("login", "Curiosa Login", []),
            ("load_csv", "Curiosa CSV", []),
            ("load_deck", "Load Deck", []),
            ("save_layout", "Save Layout", []),
            ("load_layout", "Load Layout", []),
        ]

        for key, text, options in items:
            # Single button that will dynamically change size and text
            btn_rect = pygame.Rect(0, y_pos, self.width, button_height)
            button = pygame_gui.elements.UIButton(
                relative_rect=btn_rect,
                text="",  # Start with no text (icon only)
                manager=self.manager,
                container=self.panel,
                object_id=f"sidebar_button#{key}_btn",
            )
            
            # Store button data
            self.buttons[key] = {
                "button": button,
                "text": text,
                "key": key,
                "base_rect": btn_rect.copy(),
                "expanded_rect": pygame.Rect(0, y_pos, self.expanded_width, button_height),
            }

            y_pos += button_height

    def add_deck_button(self, deck_name: str, deck_id: str):
        """Add a dynamic button for a loaded deck"""
        if deck_id in self.deck_buttons:
            return  # Already exists
        
        button_height = 50
        y_pos = len(self.buttons) * button_height + len(self.deck_buttons) * button_height
        
        # Sanitize deck_id for pygame_gui object ID (remove special characters)
        sanitized_id = "".join(c for c in deck_id if c.isalnum() or c in ('_', '-'))
        
        # Truncate deck name if longer than 15 characters
        display_name = deck_name
        if len(deck_name) > 15:
            display_name = deck_name[:12] + "..."
        
        # Create button for the deck
        btn_rect = pygame.Rect(0, y_pos, self.width, button_height)
        button = pygame_gui.elements.UIButton(
            relative_rect=btn_rect,
            text="",  # Start with no text (icon only)
            manager=self.manager,
            container=self.panel,
            object_id=f"sidebar_deck_button#{sanitized_id}_btn",
        )
        
        # Store deck button data
        self.deck_buttons[deck_id] = {
            "button": button,
            "text": display_name,  # Use truncated name for display
            "key": deck_id,
            "deck_name": deck_name,  # Keep full name for reference
            "base_rect": btn_rect.copy(),
            "expanded_rect": pygame.Rect(0, y_pos, self.expanded_width, button_height),
        }
        
        print(f"✅ Added deck button: {deck_name}")

    def remove_deck_button(self, deck_id: str):
        """Remove a deck button and reposition remaining buttons"""
        if deck_id in self.deck_buttons:
            btn_data = self.deck_buttons[deck_id]
            btn_data["button"].kill()  # Remove from UI
            del self.deck_buttons[deck_id]
            print(f"✅ Removed deck button: {deck_id}")
            
            # Reposition remaining deck buttons to fill the gap
            self.reposition_deck_buttons()

    def reposition_deck_buttons(self):
        """Reposition all deck buttons to fill gaps"""
        button_height = 50
        base_y = len(self.buttons) * button_height  # Start after regular buttons
        
        # Get sorted list of deck buttons to maintain order
        deck_items = list(self.deck_buttons.items())
        deck_items.sort(key=lambda x: x[1]["base_rect"].y)  # Sort by original y position
        
        for i, (deck_id, btn_data) in enumerate(deck_items):
            new_y = base_y + i * button_height
            
            # Update button position
            button = btn_data["button"]
            button.set_dimensions((self.width, button_height))
            button.set_position((0, new_y))
            
            # Update stored rectangles
            btn_data["base_rect"] = pygame.Rect(0, new_y, self.width, button_height)
            btn_data["expanded_rect"] = pygame.Rect(0, new_y, self.expanded_width, button_height)

    def update(self, mouse_pos):
        mouse_over_sidebar = mouse_pos[0] < self.expanded_width

        if mouse_over_sidebar:
            if not self.expanded:
                self.expanded = True
                self.panel.set_dimensions((self.expanded_width, self.height))
                # Expand all buttons
                for btn_data in self.buttons.values():
                    button = btn_data["button"]
                    button.set_dimensions(btn_data["expanded_rect"].size)
                    button.set_text(btn_data["text"])
                # Expand deck buttons
                for btn_data in self.deck_buttons.values():
                    button = btn_data["button"]
                    button.set_dimensions(btn_data["expanded_rect"].size)
                    button.set_text(btn_data["text"])
        else:
            if self.expanded:
                self.expanded = False
                self.panel.set_dimensions((self.width, self.height))
                # Collapse all buttons
                for btn_data in self.buttons.values():
                    button = btn_data["button"]
                    button.set_dimensions(btn_data["base_rect"].size)
                    button.set_text("")
                # Collapse deck buttons
                for btn_data in self.deck_buttons.values():
                    button = btn_data["button"]
                    button.set_dimensions(btn_data["base_rect"].size)
                    button.set_text("")
    
    def draw_button_images(self, surface):
        """Draw button images on the buttons (both collapsed and expanded states)"""
        # Draw regular button images
        for btn_data in self.buttons.values():
            button = btn_data["button"]
            key = btn_data["key"]
            
            if key in self.button_images and self.button_images[key]:
                # Calculate center position for the image
                img = self.button_images[key]
                img_rect = img.get_rect()
                
                if self.expanded:
                    # In expanded state, position image on the left side of the button
                    img_rect.centery = button.rect.centery
                    img_rect.left = button.rect.left + 5  # 5 pixels from left edge
                else:
                    # In collapsed state, center the image
                    img_rect.center = button.rect.center
                
                # Draw the image
                surface.blit(img, img_rect)
        
        # Draw deck button images
        for btn_data in self.deck_buttons.values():
            button = btn_data["button"]
            
            if "add" in self.button_images and self.button_images["add"]:
                # Calculate center position for the image
                img = self.button_images["add"]
                img_rect = img.get_rect()
                
                if self.expanded:
                    # In expanded state, position image on the left side of the button
                    img_rect.centery = button.rect.centery
                    img_rect.left = button.rect.left + 5  # 5 pixels from left edge
                else:
                    # In collapsed state, center the image
                    img_rect.center = button.rect.center
                
                # Draw the image
                surface.blit(img, img_rect)