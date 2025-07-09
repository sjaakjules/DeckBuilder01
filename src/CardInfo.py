# flake8: noqa: E501
'''
Purpose: Core data model for all cards.
Responsibilities:
	Stores all metadata:
	•	Cost, Thresholds (Air/Earth/Fire/Water), Stats (Attack, Defense, Life)
	•	Type (Site, Minion, Avatar, Artifact, Aura, Magic)
	•	Subtypes (Tower, Beast, etc)
	•	States (Airborne, Submerge, etc.)
	Implements:
	•	move() — respects movement rules and constraints
	•	attack() — handles strike resolution and triggered responses
	•	resolve_ability() — for passive, activated, and triggered effects
	•	Stores internal state: isTapped, hasSummoningSickness, isCarrying, etc.
	•	Card objects are passed into Rule_Engine for parsing Rule Text into actual abilities.
'''
import re
from typing import List, Dict, Any
from Util_Methods import _save_json

class CardInfo:   

    def __init__(self, name, slug, hotscore, img_url, rarity, type_,
                 subTypes, elements, elements_count, cost, thresholds,
                 attack, defence, life, rulesText, sets, flavorText, typeText, artist):
        self.name = name
        self.slug = slug
        self.hotscore = hotscore
        self.image_url = self.check_img_url(name, img_url)

        self.rareity = rarity
        self.type = type_
        self.subtypes = subTypes
        self.elements = elements
        self.elements_count = elements_count

        self.cost = cost
        self.thresholds = thresholds or {}
        self.attack = attack
        self.defence = defence
        self.life = life
        self.rules_text = rulesText
        self.sets = sets
        self.flavorText = flavorText
        self.typeText = typeText
        self.artist = artist

        self.artifacts = []
        self.movement = 1
        self.range = 1

        self.isTapped = False
        self.hasSummoningSickness = False
        self.isCarrying = False
        self.isDisabled = False
        self.isImmobile = False

        self.isAirborne = False
        self.isSubmergeable = False
        self.isBurrowable = False
        self.isStealthy = False
        self.isLeathal = False
        self.isWaterbound = False
        self.isLandbound = False
        self.isVoidwalker = False
        self.isSpellcaster = False
        self.isRanged = False
        
        self.apply_rules_text_effects()
        
    @classmethod
    def from_card_data(cls, card_data: dict):
        return cls(
            name=card_data.get("name"),
            slug=card_data.get("slug"),
            hotscore=card_data.get("hotscore"),
            img_url=card_data.get("img_url"),
            rarity=card_data.get("rarity"),
            type_=card_data.get("type"),
            subTypes=card_data.get("subTypes", []),
            elements=card_data.get("elements", []),
            elements_count=card_data.get("elements_count", 0),
            cost=card_data.get("cost"),
            thresholds=card_data.get("thresholds"),
            attack=card_data.get("attack"),
            defence=card_data.get("defence"),
            life=card_data.get("life"),
            rulesText=card_data.get("rulesText"),
            sets=card_data.get("sets", []),
            flavorText=card_data.get("flavorText", []),
            typeText=card_data.get("typeText", []),
            artist=card_data.get("artist", [])
        )
        
    @classmethod
    def from_sorcery_data(cls, sorcery_data: dict):
        name = sorcery_data.get("name", "")
        slug = name.lower().replace(" ", "_") if name else "unknown"

        guardian = sorcery_data.get("guardian", {})
        thresholds = guardian.get("thresholds", {})

        elements = []
        if isinstance(sorcery_data.get("elements"), str):
            elements = [e.strip() for e in sorcery_data["elements"].split(",") if e.strip()]
        elif isinstance(sorcery_data.get("elements"), list):
            elements = [e.get("name") for e in sorcery_data["elements"] if isinstance(e, dict)]

        subtypes = []
        if isinstance(sorcery_data.get("subTypes"), str):
            subtypes = [s.strip() for s in sorcery_data["subTypes"].split(",") if s.strip()]
        elif isinstance(sorcery_data.get("subTypes"), list):
            subtypes = sorcery_data["subTypes"]

        # Collect sets, flavorText, typeText, artist
        sets = set()
        flavor_texts = set()
        type_texts = set()
        artists = set()

        for s in sorcery_data.get("sets", []):
            sets.add(s.get("name", ""))
            for v in s.get("variants", []):
                if v.get("flavorText"):
                    flavor_texts.add(v["flavorText"])
                if v.get("typeText"):
                    type_texts.add(v["typeText"])
                if v.get("artist"):
                    artists.add(v["artist"])

        return cls(
            name=name,
            slug=slug,
            hotscore=None,
            img_url=f"https://card.cards.army/cards/{slug}.webp",
            rarity=guardian.get("rarity"),
            type_=guardian.get("type"),
            subTypes=subtypes,
            elements=elements,
            elements_count=len(set(elements)),
            cost=guardian.get("cost"),
            thresholds=thresholds,
            attack=guardian.get("attack"),
            defence=guardian.get("defence"),
            life=guardian.get("life"),
            rulesText=guardian.get("rulesText"),
            sets=list(sets),
            flavorText=list(flavor_texts),
            typeText=list(type_texts),
            artist=list(artists)
        )
        
    @classmethod
    def from_curiosa_data(cls, curiosa_data: dict):
        name = curiosa_data.get("name", "")
        slug = curiosa_data.get("slug", "")
        hotscore = curiosa_data.get("hotscore")
        guardian = curiosa_data.get("guardian", {})

        # Elements
        elements = [el.get("name") for el in curiosa_data.get("elements", []) if el.get("name")]
        elements_count = len(set(elements))

        # Thresholds
        thresholds = {
            "air": guardian.get("airThreshold", 0),
            "earth": guardian.get("earthThreshold", 0),
            "fire": guardian.get("fireThreshold", 0),
            "water": guardian.get("waterThreshold", 0)
        }

        # Rules and stats
        rulesText = guardian.get("rulesText")
        cost = guardian.get("cost")
        attack = guardian.get("attack")
        defence = guardian.get("defense")
        life = guardian.get("life")
        rarity = guardian.get("rarity")
        type_ = guardian.get("type")

        # Sets
        sets = set()
        flavor_texts = set()
        type_texts = set()
        artists = set()
        subtypes = set()

        capital_word_pattern = re.compile(r'\b[A-Z][a-z]+\b')

        for variant in curiosa_data.get("variants", []):
            set_info = variant.get("setCard", {}).get("set", {})
            sets.add(set_info.get("name", ""))

            vmeta = variant.get("vMeta", {})
            if vmeta.get("flavorText"):
                flavor_texts.add(vmeta["flavorText"])
            if vmeta.get("typeText"):
                type_texts.add(vmeta["typeText"])
                # Extract capitalized words as subtypes (excluding type/rarity)
                words = capital_word_pattern.findall(vmeta["typeText"])
                for word in words:
                    if word not in [rarity, type_] and word not in subtypes:
                        subtypes.add(word)

            artist_name = variant.get("artist", {}).get("name")
            if artist_name:
                artists.add(artist_name)

        # Add inferred Knight subtype
        if "sir" in name.lower() or "knight" in name.lower():
            subtypes.add("Knight")

        return cls(
            name=name,
            slug=slug,
            hotscore=hotscore,
            img_url=f"https://card.cards.army/cards/{slug}.webp",
            rarity=rarity,
            type_=type_,
            subTypes=list(subtypes),
            elements=elements,
            elements_count=elements_count,
            cost=cost,
            thresholds=thresholds,
            attack=attack,
            defence=defence,
            life=life,
            rulesText=rulesText,
            sets=list(sets),
            flavorText=list(flavor_texts),
            typeText=list(type_texts),
            artist=list(artists)
        )
    
    def check_img_url(self, name, img_url):
        missing_cards = {
			"Relentless Crowd":"relentless_crowd_p_s",
			"Spire":"spire_dk_s",
			"Spellslinger":"spellslinger_dk_s",
			"Stream":"stream_dk_s",
			"Valley":"valley_dk_s",
			"Wasteland":"wasteland_dk_s"
		}
        if name in missing_cards:
            return f"https://card.cards.army/cards/{missing_cards[name]}.webp"
        return img_url
    
    def apply_rules_text_effects(self):
        """
        Parses rulesText and updates flags like isStealthy, isRanged, movement, etc.
        Ignores conditional clauses (e.g., sentences with "if", "may", "has").
        """
        if not self.rules_text:
            return

        # Normalize
        text = self.rules_text.replace('\r', '').replace('\n', ' ')
        clauses = re.split(r'[.,;]', text)

        # Check for conditionals
        conditional_words = {"if", "may", "has", "whenever", "while", "when", "as long as"}

        # Keywords to check
        keywords = {
            "Airborne": "isAirborne",
            "Submerge": "isSubmergeable",
            "Burrowing": "isBurrowable",
            "Stealth": "isStealthy",
            "Lethal": "isLeathal",
            "Waterbound": "isWaterbound",
            "Landbound": "isLandbound",
            "Voidwalk": "isVoidwalker",
            "Spellcaster": "isSpellcaster",
            "Ranged": "isRanged",
        }

        for clause in clauses:
            clause = clause.strip()
            if not clause or any(word in clause.lower() for word in conditional_words):
                continue  # Skip conditional clauses

            # Movement
            move_match = re.search(r"Movement\s*([+-]?\d+)", clause)
            if move_match:
                try:
                    self.movement += int(move_match.group(1))
                except ValueError:
                    pass

            # Range
            range_match = re.search(r"Range\s*([+-]?\d+)", clause)
            if range_match:
                try:
                    self.range += int(range_match.group(1))
                except ValueError:
                    pass

            # Flags
            for key, attr in keywords.items():
                if key in clause:
                    setattr(self, attr, True)

	
'''
{
    "sorcery_data": {
        "name": "Sir Agravaine",
        "guardian": {
            "rarity": "Unique",
            "type": "Minion",
            "rulesText": "Stealth, Movement +1\\nWhenever another ally attacks an enemy adjacent to Sir Agravaine, he strikes that enemy afterwards without losing Stealth.",
            "cost": 3,
            "attack": 3,
            "defence": 2,
            "life": null,
            "thresholds": {
                "air": 0,
                "earth": 0,
                "fire": 2,
                "water": 1
            }
        },
        "elements": "Fire, Water",
        "subTypes": "Knight, Mortal",
        "sets": [
            {
                "name": "Arthurian Legends",
                "releasedAt": "2024-10-04T00:00:00.000Z",
                "metadata": {
                    "rarity": "Unique",
                    "type": "Minion",
                    "rulesText": "Stealth, Movement +1\\nWhenever another ally attacks an enemy adjacent to Sir Agravaine, he strikes that enemy afterwards without losing Stealth.",
                    "cost": 3,
                    "attack": 3,
                    "defence": 2,
                    "life": null,
                    "thresholds": {
                        "air": 0,
                        "earth": 0,
                        "fire": 2,
                        "water": 1
                    }
                },
                "variants": [
                    {
                        "slug": "art_sir_agravaine_b_s",
                        "finish": "Standard",
                        "product": "Booster",
                        "artist": "Drew Tucker",
                        "flavorText": "",
                        "typeText": "A Unique Mortal seeks strength in numbers"
                    },
                    {
                        "slug": "art_sir_agravaine_b_f",
                        "finish": "Foil",
                        "product": "Booster",
                        "artist": "Drew Tucker",
                        "flavorText": "",
                        "typeText": "A Unique Mortal seeks strength in numbers"
                    }
                ]
            }
        ]
    },
    "curiosa_data": {
        "id": "cm1vlavhq014p12ymfcsac2lf",
        "slug": "sir_agravaine",
        "name": "Sir Agravaine",
        "hotscore": 3664,
        "guardian": {
            "id": "cm1vlax49014s12ym1bvvpqv1",
            "type": "Minion",
            "rarity": "Unique",
            "category": "Spell",
            "rulesText": "Stealth, Movement +1\\nWhenever another ally attacks an enemy adjacent to Sir Agravaine, he strikes that enemy afterwards without losing Stealth.",
            "cost": 3,
            "attack": 3,
            "defense": 2,
            "life": null,
            "waterThreshold": 1,
            "earthThreshold": 0,
            "fireThreshold": 2,
            "airThreshold": 0,
            "cardId": "cm1vlavhq014p12ymfcsac2lf"
        },
        "elements": [
            {
                "id": "fire",
                "name": "Fire"
            },
            {
                "id": "water",
                "name": "Water"
            }
        ],
        "variants": [
            {
                "id": "cm1vlaxjh014u12ymbqodbnav",
                "slug": "art_sir_agravaine_b_s",
                "src": "https://d27a44hjr9gen3.cloudfront.net/art/sir_agravaine_b_s.png",
                "finish": "Standard",
                "product": "Booster",
                "cardId": "cm1vlavhq014p12ymfcsac2lf",
                "setCardId": "cm1vlawkp014q12ym46mxr3m9",
                "artistId": "cm1sb7u0c00aqxxa1gc00tlr6",
                "setCard": {
                    "id": "cm1vlawkp014q12ym46mxr3m9",
                    "slug": "art_sir_agravaine",
                    "setId": "cm1vkycol000012ymd3757f2x",
                    "cardId": "cm1vlavhq014p12ymfcsac2lf",
                    "meta": {
                        "id": "cm1vlawts014r12ym8eyf8ei5",
                        "type": "Minion",
                        "rarity": "Unique",
                        "category": "Spell",
                        "rulesText": "Stealth, Movement +1\\nWhenever another ally attacks an enemy adjacent to Sir Agravaine, he strikes that enemy afterwards without losing Stealth.",
                        "cost": 3,
                        "attack": 3,
                        "defense": 2,
                        "life": null,
                        "waterThreshold": 1,
                        "earthThreshold": 0,
                        "fireThreshold": 2,
                        "airThreshold": 0,
                        "setCardId": "cm1vlawkp014q12ym46mxr3m9"
                    },
                    "set": {
                        "id": "cm1vkycol000012ymd3757f2x",
                        "code": "art",
                        "status": "Released",
                        "releasedAt": "2024-10-04T00:00:00.000Z",
                        "name": "Arthurian Legends"
                    }
                },
                "reverse": null,
                "vMeta": {
                    "id": "cm1vlaxtm014v12ymjexlxkte",
                    "flavorText": "",
                    "typeText": "A Unique Mortal seeks strength in numbers",
                    "variantId": "cm1vlaxjh014u12ymbqodbnav"
                },
                "artist": {
                    "id": "cm1sb7u0c00aqxxa1gc00tlr6",
                    "slug": "drew_tucker",
                    "name": "Drew Tucker"
                }
            },
            {
                "id": "cm1vlay8z014x12ym4fmmdw1u",
                "slug": "art_sir_agravaine_b_f",
                "src": "https://d27a44hjr9gen3.cloudfront.net/art/sir_agravaine_b_f.png",
                "finish": "Foil",
                "product": "Booster",
                "cardId": "cm1vlavhq014p12ymfcsac2lf",
                "setCardId": "cm1vlawkp014q12ym46mxr3m9",
                "artistId": "cm1sb7u0c00aqxxa1gc00tlr6",
                "setCard": {
                    "id": "cm1vlawkp014q12ym46mxr3m9",
                    "slug": "art_sir_agravaine",
                    "setId": "cm1vkycol000012ymd3757f2x",
                    "cardId": "cm1vlavhq014p12ymfcsac2lf",
                    "meta": {
                        "id": "cm1vlawts014r12ym8eyf8ei5",
                        "type": "Minion",
                        "rarity": "Unique",
                        "category": "Spell",
                        "rulesText": "Stealth, Movement +1\\nWhenever another ally attacks an enemy adjacent to Sir Agravaine, he strikes that enemy afterwards without losing Stealth.",
                        "cost": 3,
                        "attack": 3,
                        "defense": 2,
                        "life": null,
                        "waterThreshold": 1,
                        "earthThreshold": 0,
                        "fireThreshold": 2,
                        "airThreshold": 0,
                        "setCardId": "cm1vlawkp014q12ym46mxr3m9"
                    },
                    "set": {
                        "id": "cm1vkycol000012ymd3757f2x",
                        "code": "art",
                        "status": "Released",
                        "releasedAt": "2024-10-04T00:00:00.000Z",
                        "name": "Arthurian Legends"
                    }
                },
                "reverse": null,
                "vMeta": {
                    "id": "cm1vlayjp014y12ym30gytwku",
                    "flavorText": "",
                    "typeText": "A Unique Mortal seeks strength in numbers",
                    "variantId": "cm1vlay8z014x12ym4fmmdw1u"
                },
                "artist": {
                    "id": "cm1sb7u0c00aqxxa1gc00tlr6",
                    "slug": "drew_tucker",
                    "name": "Drew Tucker"
                }
            }
        ],
        "reverse": null
    },
    "card_data": {
        "name": "Sir Agravaine",
        "rarity": "Unique",
        "type": "Minion",
        "rulesText": "Stealth, Movement +1\\nWhenever another ally attacks an enemy adjacent to Sir Agravaine, he strikes that enemy afterwards without losing Stealth.",
        "cost": 3,
        "attack": 3,
        "defence": 2,
        "life": null,
        "thresholds": {
            "air": 0,
            "earth": 0,
            "fire": 2,
            "water": 1
        },
        "hotscore": 3664,
        "slug": "sir_agravaine",
        "img_url": "https://card.cards.army/cards/sir_agravaine.webp",
        "elements": ["Fire", "Water"],
        "elements_count": 2,
        "subTypes": ["Knight", "Mortal"],
        "flavorText": [""],
        "typeText": ["A Unique Mortal seeks strength in numbers"],
        "artist": ["Drew Tucker"],
        "sets": ["Arthurian Legends"]
    }
}
'''
