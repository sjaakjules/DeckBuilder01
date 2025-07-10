import csv
import os
from tqdm import tqdm
from typing import Dict, Any, List
from Levenshtein import distance as levenshtein_distance


class Collection:
    def __init__(self):
        self.cards: Dict[str, Dict[str, Any]] = {}

    def add_card(self, name: str, count: int = 1, set_name="Unknown", finish="Unknown", product="Unknown"):
        if name not in self.cards:
            self.cards[name] = {
                "total_quantity": 0,
                "entries": []
            }

        self.cards[name]["total_quantity"] += count

        for entry in self.cards[name]["entries"]:
            if (entry["set_name"] == set_name and
                entry["finish"] == finish and
                entry["product"] == product):
                entry["count"] += count
                return

        self.cards[name]["entries"].append({
            "set_name": set_name,
            "finish": finish,
            "product": product,
            "count": count
        })

    @classmethod
    def from_online_json(cls, json_data: List[Dict[str, Any]]):
        collection = cls()

        for entry in json_data:
            card = entry["card"]
            name = card["name"]
            variants_by_id = {v["id"]: v for v in card.get("variants", [])}

            for grouping in entry.get("groupings", []):
                variant_id = grouping.get("variantId")
                variant = variants_by_id.get(variant_id)

                if not variant:
                    print(f"⚠️ Variant ID not found for card: {name}")
                    continue

                set_name = variant.get("setCard", {}).get("set", {}).get("name", "Unknown")
                finish = variant.get("finish", "Unknown")
                product = variant.get("product", "Unknown")
                count = len(grouping.get("items", []))

                collection.add_card(name, count, set_name, finish, product)

        return collection

    @classmethod
    def from_csv(cls, path: str, card_data_lookup: Dict[str, Any]):
        collection = cls()

        if not os.path.exists(path):
            print(f"❌ Collection file not found: {path}")
            return collection

        with open(path, 'r', encoding='utf-8') as f:
            total_rows = sum(1 for _ in csv.DictReader(f))

        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            with tqdm(total=total_rows, desc="Loading CSV Collection", unit="cards") as pbar:
                for row in reader:
                    csv_name = row["card name"].strip()
                    matched_name = None

                    if csv_name in card_data_lookup:
                        matched_name = csv_name
                    else:
                        min_dist = float("inf")
                        for name in card_data_lookup:
                            d = levenshtein_distance(csv_name.lower(), name.lower())
                            if d < min_dist:
                                min_dist = d
                                matched_name = name

                        if min_dist > 5:
                            print(f"❌ Could not match '{csv_name}' (closest: '{matched_name}', dist={min_dist})")
                            continue

                    set_name = row.get("set", "Unknown")
                    finish = row.get("finish", "Unknown")
                    product = row.get("product", "Unknown")

                    collection.add_card(matched_name, 1, set_name, finish, product)

                    pbar.update(1)
                    pbar.set_postfix({"Unique": len(collection.cards)})

        print(f"✅ Loaded {len(collection.cards)} unique cards from CSV")
        return collection