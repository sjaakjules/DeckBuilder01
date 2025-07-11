"""
Purpose: Interface with the Curiosa API for online deck retrieval.
Responsibilities:
	•	Downloads user-supplied deck by ID.
	•	Parses it into Atlas and Spellbook format.
	•	Handles conversion into the internal Deck structure.
"""

import os
import json
import requests
from typing import Dict, List, Any
import Util_Config as config

# API Configuration
CURIOSA_API_BASE = "https://api.curiosa.io/decks/"
CORS_PROXY = "https://cors-anywhere.herokuapp.com/"  # For development only
SORCERY_API = "https://api.sorcery.com/cards"  # Replace with actual API endpoint
CARD_DATA_PATH = "data/card_metadata.json"

# Preconstructed Decks
PRECON_ALPHA = {
    'avatar_air': "https://curiosa.io/precons/clso3l1mg001q2w08qv1nexky",
    'avatar_water': "https://curiosa.io/precons/clso3lffd006jhb60hiwpltyc",
    'avatar_fire': "https://curiosa.io/precons/clso3l8ph005ihb60cxkus6mh",
    'avatar_earth': "https://curiosa.io/precons/clso3lngx007lhb600v843gd7"
}

PRECON_BETA = {
    'sparkmage': "https://curiosa.io/precons/clczbmbxb008av5ugml35rdwt",
    'waveshaper': "https://curiosa.io/precons/clczbmbxb008ev5ugiovmxcw1",
    'flamecaller': "https://curiosa.io/precons/clczbmbxb0085v5ug7eyxn2dk",
    'geomancer': "https://curiosa.io/precons/clczbmbxb008hv5uggpws66fe"
}

# Single Element Decks
SINGLE_ELEMENT = {
    'avatar_air': ["https://curiosa.io/decks/clur4vvfi007393mb1jeks49q",
                   "https://curiosa.io/decks/cm7h1bo280003jy03d6h9vjdk"],
    'avatar_earth': ["https://curiosa.io/decks/clf3gywls001xjs0fq0oymxrw"],
    'avatar_fire': ["https://curiosa.io/decks/clllgewcb000al70f1trl23nj"],
    'avatar_water': ["https://curiosa.io/decks/clkta1lm80016ml0fx7j5g85z"],
    'flamecaller': ["https://curiosa.io/decks/clp4lhy3k000ml40f7tz4kzt9"],
    'geomancer': ["https://curiosa.io/decks/clq0g9545005v18uw6wys5j7s"],
    'sparkmage': ["https://curiosa.io/decks/cloneejb7003al80fj99t5zse"],
    'spellslinger': ["https://curiosa.io/decks/clzyaqvk200f69z9318843mvj"],
    'waveshaper': ["https://curiosa.io/decks/cm778jggb0004la031y4lihll"]
}

# Double Element Decks
DOUBLE_ELEMENT = {
    'archimago': ["https://curiosa.io/decks/cm5gwcht600cajv03o66g813t"],
    'battlemage': ["https://curiosa.io/decks/clczbmbxk00l5v5ug8fszmefg",
                   "https://curiosa.io/decks/clvotbl1x000hdr85httnltx9"],
    'deathspeaker': ["https://curiosa.io/decks/clczbmbxm00osv5ug2r4pyidz"],
    'druid': ["https://curiosa.io/decks/cm6idlshk003jl803y6gvrshg"],
    'enchantress': ["https://curiosa.io/decks/clsmmlhou001z11pizfcx1ika"],
    'pathfinder': ["https://curiosa.io/decks/clfu91ick0000mo0f2o0ydeo2"],
    'seer': ["https://curiosa.io/decks/cltwmj6vp0040ydfaz3qodjgd"],
    'sorcerer': ["https://curiosa.io/decks/clrno48s50029nptuqqoxyioa"],
    'spellslinger': ["https://curiosa.io/decks/cm1zd8c0h006ezuaazqvybyiu"],
    'witch': ["https://curiosa.io/decks/cm2biop6z00006htx57qzp8fm"]
}

# Triple Element Decks
TRIPLE_ELEMENT = {
    'archimago': ["https://curiosa.io/decks/cm36h7lls005ltupl99xqsoj0"],
    'deathspeaker': ["https://curiosa.io/decks/cm6ksu9us00m0lb03jr9ft22q"],
    'enchantress': ["https://curiosa.io/decks/clf7hjfxc002lmk0gy6nyzgl9",
                    "https://curiosa.io/decks/cm7e9p2x80002jr03v9v2d7pg"],
    'seer': ["https://curiosa.io/decks/cm8m6vbdu002tie03di2cqd8g"]
}

# Quadruple Element Decks
QUADRUPLE_ELEMENT = {
    'elementalist': ["https://curiosa.io/decks/clp2hendb007ol70ffaln2e5x",
                     "https://curiosa.io/decks/cmamc8l5r008jih047su6gbtf"],
    'templar': ["https://curiosa.io/decks/cm29j1szy0030j0oagg8ujs0t"]
}

def get_all_precon_alpha() -> List[str]:
    """Returns a list of all Preconstructed Alpha deck URLs."""
    return list(PRECON_ALPHA.values())

def get_all_precon_beta() -> List[str]:
    """Returns a list of all Preconstructed Beta deck URLs."""
    return list(PRECON_BETA.values())

def get_all_single_element() -> List[str]:
    """Returns a list of all Single Element deck URLs."""
    urls = []
    for value in SINGLE_ELEMENT.values():
            urls.extend(value)
    return urls

def get_all_double_element() -> List[str]:
    """Returns a list of all Double Element deck URLs."""
    urls = []
    for value in DOUBLE_ELEMENT.values():
            urls.extend(value)
    return urls

def get_all_triple_element() -> List[str]:
    """Returns a list of all Triple Element deck URLs."""
    urls = []
    for value in TRIPLE_ELEMENT.values():
            urls.extend(value)
    return urls

def get_all_quadruple_element() -> List[str]:
    """Returns a list of all Quadruple Element deck URLs."""
    urls = []
    for value in QUADRUPLE_ELEMENT.values():
            urls.extend(value)
    return urls

def get_all_decks() -> List[str]:
    """Returns a list of all deck URLs."""
    return (
        get_all_precon_alpha() +
        get_all_precon_beta() +
        get_all_single_element() +
        get_all_double_element() +
        get_all_triple_element() +
        get_all_quadruple_element()
    )

def get_avatar_decks(avatar_name: str) -> List[str]:
    """
    Returns all decks for a specific avatar/archetype.
    
    Args:
        avatar_name (str): The name of the avatar/archetype (e.g., 'avatar', 'archimago', 'enchantress')
        
    Returns:
        list: A list of deck URLs for the specified avatar/archetype
    """
    decks = []
    
    # Check in single element decks
    if avatar_name in SINGLE_ELEMENT:
        decks.extend(SINGLE_ELEMENT[avatar_name])
    
    # Check in double element decks
    if avatar_name in DOUBLE_ELEMENT:
        decks.extend(DOUBLE_ELEMENT[avatar_name])
    
    # Check in triple element decks
    if avatar_name in TRIPLE_ELEMENT:
        decks.extend(TRIPLE_ELEMENT[avatar_name])
    
    # Check in quadruple element decks
    if avatar_name in QUADRUPLE_ELEMENT:
        decks.extend(QUADRUPLE_ELEMENT[avatar_name])
    
    return decks

def get_available_avatars() -> List[str]:
    """
    Returns a list of all available avatar/archetype names.
    
    Returns:
        list: A list of all avatar/archetype names that have decks
    """
    avatars = set()
    avatars.update(SINGLE_ELEMENT.keys())
    avatars.update(DOUBLE_ELEMENT.keys())
    avatars.update(TRIPLE_ELEMENT.keys())
    avatars.update(QUADRUPLE_ELEMENT.keys())
    return sorted(list(avatars))

def extract_deck_id(url_or_id: str) -> str:
    """
    Extract the deck ID from a Curiosa URL or ID.
    
    Args:
        url_or_id (str): Full URL or deck ID
        
    Returns:
        str: The deck ID
    """
    if '/' in url_or_id:
        return url_or_id.rstrip('/').split('/')[-1]
    return url_or_id

def get_curiosa_deck(deck_url_or_id: str) -> Dict[str, Any]:
    """
    Fetch deck data from Curiosa API.
    
    Args:
        deck_url_or_id (str): Full URL or deck ID
        
    Returns:
        Dict[str, Any]: Deck data from Curiosa API
    """
    deck_id = extract_deck_id(deck_url_or_id)
    url = f"{CORS_PROXY}{CURIOSA_API_BASE}{deck_id}"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

def fetch_all_cards_metadata() -> List[Dict[str, Any]]:
    """
    Fetch or load from cache all card metadata from Sorcery API.
    
    Returns:
        List[Dict[str, Any]]: List of card metadata
    """
    if os.path.exists(CARD_DATA_PATH):
        with open(CARD_DATA_PATH, 'r') as f:
            all_data = json.load(f)
    else:
        # Ensure data directory exists
        os.makedirs(os.path.dirname(CARD_DATA_PATH), exist_ok=True)
        
        # Fetch and save data
        response = requests.get(SORCERY_API)
        all_data = response.json()
        
        with open(CARD_DATA_PATH, 'w') as f:
            json.dump(all_data, f, indent=4, sort_keys=True)

    return all_data

def match_curiosa_to_sorcery(curiosa_cards: List[Dict[str, Any]], 
                           all_sorcery_cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Match Curiosa cards with Sorcery API card data.
    
    Args:
        curiosa_cards (List[Dict[str, Any]]): Cards from Curiosa
        all_sorcery_cards (List[Dict[str, Any]]): All cards from Sorcery API
        
    Returns:
        List[Dict[str, Any]]: Matched cards with full details
    """
    matched = []
    for card in curiosa_cards:
        name = card["name"].strip().lower()
        match = next((c for c in all_sorcery_cards if c["name"].strip().lower() == name), None)
        if match:
            matched.append({
                "name": card["name"],
                "quantity": card["quantity"],
                "img_url": card["src"],
                "details": match
            })
        else:
            print(f"❌ Not found in API: {card['name']}")
    return matched

def get_deck_json_from_curiosa(deck_url: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get full deck data from Curiosa and match with Sorcery API.
    
    Args:
        deck_url (str): URL of the deck on Curiosa
        
    Returns:
        Dict[str, List[Dict[str, Any]]]: Full deck data with matched card details
    """
    curiosa_data = get_curiosa_deck(deck_url)
    
    with open("tmp/curiosa_deck.json", 'w') as f:
        json.dump(curiosa_data, f, indent=4, ensure_ascii=False)
        
    sorcery_cards = fetch_all_cards_metadata()

    full_deck = {}
    for section in ["avatar", "atlas", "spellbook", "sideboard"]:
        matched_cards = match_curiosa_to_sorcery(curiosa_data.get(section, []), sorcery_cards)
        full_deck[section] = matched_cards

    with open("tmp/full_deck.json", 'w') as f:
        json.dump(full_deck, f, indent=4, ensure_ascii=False)
        
    return full_deck