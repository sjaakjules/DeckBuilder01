import os
import time
from Card_Manager import Card_Manager
from Util_IO import select_file, open_threadsafe_dialog
from Collection import Collection
from Curiosa_API import CuriosaAPI
from Deck_Manager import Deck_Manager


class Collection_Manager:
    def __init__(self, card_manager: Card_Manager, deck_manager: Deck_Manager):
        self.collection = None
        self.deck_manager = deck_manager
        self.card_manager = card_manager
        self.gui_manager = None  # Will be set by GUI_Manager
        
    def set_gui_manager(self, gui_manager):
        """Set reference to GUI manager for notifications"""
        self.gui_manager = gui_manager
        
    def load_from_csv(self):
        file_path = open_threadsafe_dialog(
            select_file, 
            title="Select CSV File", 
            filetypes=[("CSV files", "*.csv")]
        )
        print(f"📂 Selected file: {file_path}")
        time.sleep(1)

        if file_path:
            try:
                self.collection = Collection.from_csv(file_path, self.card_manager.card_data_lookup)
                print(f"✅ Loaded collection from CSV: {len(self.collection.cards)} cards")
            except Exception as e:
                print(f"❌ Failed to load collection: {e}")

    def load_from_curiosa(self):
        self.card_manager.loading = True
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
            self.deck_manager.download_user_decks(self.curiosa)
            
            # Notify GUI about loaded decks
            if self.gui_manager and hasattr(self.gui_manager, 'sidebar'):
                for deck in self.deck_manager.decks:
                    self.gui_manager.sidebar.add_deck_button(deck.name, deck.id)

        except Exception as e:
            print(f"❌ Login to Curiosa failed: {e}")
    
        self.card_manager.loading = False
        