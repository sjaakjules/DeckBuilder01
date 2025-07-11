from Card_Manager import Card_Manager
from Deck_Manager import Deck_Manager
from Collection_Manager import Collection_Manager
from GUI_Manager import GUI_Manager

if __name__ == "__main__":
    card_manager = Card_Manager()
    deck_manager = Deck_Manager()
    collection_manager = Collection_Manager(card_manager, deck_manager)
    gui = GUI_Manager(card_manager, deck_manager, collection_manager)
    gui.run()