# Sorcery Deck Builder

A Python-based deck builder application for the Sorcery TCG that allows you to manage your card collection and build decks with an interactive grid interface.

## Features

- **Collection Management**: Load your card collection from CSV files
- **Card Matching**: Automatically match cards with images and API data using fuzzy matching
- **Interactive Grid**: View your collection in a customizable grid layout
- **Card Manipulation**: Drag and drop cards to rearrange them
- **Camera Controls**: 
  - Right-click and drag to pan the view
  - Mouse wheel to zoom in/out
  - Smooth card animation during dragging
- **Deck Building**: Create decks from your collection with card counts

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Ensure you have the required data files:
   - `assets/collection-2025-07-07T01_38_01.445Z.csv` - Your card collection
   - `data/CardList.json` - Card data from the Sorcery API
   - `assets/Cards/` - Card images organized by set

## Usage

Run the application:
```bash
python src/main.py
```

### Controls

- **Left Click + Drag**: Move cards around the grid
- **Right Click + Drag**: Pan the camera view
- **Mouse Wheel**: Zoom in/out
- **Double Click + Hold**: Move entire rows or columns (planned feature)

### Card Matching

The application uses fuzzy string matching to find card images in your assets directory. If a card name doesn't have a perfect match, it will:

1. Normalize the card name (remove special characters, convert to lowercase)
2. Search through all PNG files in the `assets/Cards/` directory
3. Calculate similarity scores and use the best match above 60% similarity
4. Print matching results to the console

### Grid Layout

Cards are arranged in a grid with:
- 8 cards per row by default
- Configurable card size and spacing
- Automatic positioning with camera and zoom support

## File Structure

```
DeckBuilder01/
├── assets/
│   ├── Cards/           # Card images organized by set
│   └── collection-*.csv # Your card collection
├── data/
│   └── CardList.json    # Card data from Sorcery API
├── src/
│   ├── main.py          # Main application
│   ├── Card.py          # Card data model
│   ├── Util_Loader.py   # Data loading utilities
│   └── Curiosa_Decks.py # Deck management
├── requirements.txt     # Python dependencies
└── README.md           # This file
```

## Troubleshooting

### Missing Images
If cards show "No image found", check:
- Card images are in the `assets/Cards/` directory
- Image filenames are similar to card names
- File permissions allow reading the images

### Missing Card Data
If cards show "No API data found", check:
- `data/CardList.json` contains the card data
- Card names match exactly between collection and API data

### Performance Issues
For large collections:
- Reduce the number of cards displayed at once
- Adjust zoom levels for better performance
- Consider filtering cards by set or type

## Development

The application is built with:
- **Pygame**: Graphics and input handling
- **Pygame-GUI**: User interface components
- **Python Standard Library**: File I/O, data processing

### Extending the Application

To add new features:
1. Modify the `DeckBuilder` class in `main.py`
2. Add new methods for additional functionality
3. Update the event handling in `handle_mouse_events()`
4. Extend the drawing methods in `draw_grid()` and `draw_card()` 