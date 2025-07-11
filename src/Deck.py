from typing import List, Dict, Any, TypedDict, Tuple
from Card import Card


class Deck:
    def __init__(self, name: str, author: str, id: str):
        self.name = name
        self.author = author
        self.id = id
        self.deck: Dict[str, Dict[str, Any]] = {
            "mainboard": {},
            "sideboard": {},
            "maybeboard": {},
            "avatar": {},
        }

    @classmethod
    def from_json(cls, name: str, author: str, id: str, json_data: Dict[str, Any]) -> "Deck":
        deck = cls(name, author, id)
        for board in ["mainboard", "sideboard", "maybeboard", "avatar"]:
            deck._load_board_data(board, json_data)
        return deck

    def _load_board_data(self, board: str, json_data: Dict[str, Any]):
        if board not in json_data:
            print(f"Board {board} not found in json data")
            return

        board_data = json_data[board]
        if not isinstance(board_data, list):
            print(f"Board {board} data is not a list")
            board_data = [board_data]

        for card_entry in board_data:
            if not isinstance(card_entry, dict):
                print(f"Invalid card entry in {board}: {card_entry}")
                continue
                
            try:
                card_name = card_entry.get("card", {}).get("name", "Unknown")
                quantity = card_entry.get("quantity", 1)
                variant = card_entry.get("variant", {})
                set_name = variant.get("setCard", {}).get("set", {}).get("name", "Unknown")
                finish = variant.get("finish", "Unknown")
                product = variant.get("product", "Unknown")
                category = variant.get("setCard", {}).get("meta", {}).get("category", "Unknown")

                for _ in range(quantity):
                    self.add_card(board, card_name, position=(0, 0), set_name=set_name,
                                  finish=finish, product=product, category=category)
            except Exception as e:
                print(f"Error processing card in {board}: {e}")
                continue
        
    def add_card(self, board: str, name: str, position: Tuple[int, int],
                set_name="Unknown", finish="Unknown", product="Unknown", category="Unknown"):
        entry = {
            "position": position,
            "kind": category,
            "set_name": set_name,
            "finish": finish,
            "product": product
        }
        self.deck.setdefault(board, {}).setdefault(name, []).append(entry)
        
    def remove_card(self, board: str, name: str, position: Tuple[int, int]):
        entries = self.deck.get(board, {}).get(name)
        if not entries:
            print(f"Card {name} not found in board {board}")
            return

        for i, entry in enumerate(entries):
            if entry["position"] == position:
                del entries[i]
                break

    def move_card(self, from_board: str, to_board: str, name: str, position: Tuple[int, int]):
        if from_board not in self.deck or to_board not in self.deck:
            print(f"One or both boards '{from_board}' and '{to_board}' not found")
            return
        self.remove_card(from_board, name, position)
        self.add_card(to_board, name, position)

    def update_position(self, board: str, name: str, position: Tuple[int, int], pos_index: int):
        try:
            self.deck[board][name][pos_index]["position"] = position
        except (KeyError, IndexError):
            print(f"Failed to update position: {name} on {board} at index {pos_index}")

    def get_pos_index(self, board: str, name: str, position: Tuple[int, int]) -> int:
        try:
            entries = self.deck[board][name]
            return next((i for i, entry in enumerate(entries) if entry["position"] == position), -1)
        except KeyError:
            print(f"Board '{board}' or card '{name}' not found")
            return -1
    
    def get_closest_index(self, board: str, name: str, position: Tuple[int, int]) -> int:
        try:
            entries = self.deck[board][name]
            px, py = position

            def dist_sq(entry_pos):
                ex, ey = entry_pos
                return (px - ex) ** 2 + (py - ey) ** 2

            return min(
                enumerate(entries),
                key=lambda pair: dist_sq(pair[1]["position"])
            )[0]
        except KeyError:
            print(f"Board '{board}' or card '{name}' not found")
            return -1
        except ValueError:
            print(f"No entries found for {name} on {board}")
            return -1