from typing import List
from CardInfo import CardInfo

class Deck:
    def __init__(self, name: str, cards: List[CardInfo]):
        self.name = name
        self.cards = cards

    def add_card(self, card: CardInfo):
        self.cards.append(card)

    def remove_card(self, card: CardInfo):
        self.cards.remove(card)