import pygame
import time
import Util_Config as config
from typing import List, Optional


class DebugDisplay:
    """Static debug display class for showing debug messages across the application."""
    
    _instance: Optional['DebugDisplay'] = None
    _messages: List[str] = []
    _max_messages: int = 10
    _message_lifetime: float = 5.0  # seconds
    _message_timestamps: List[float] = []
    
    @classmethod
    def initialize(cls, screen: pygame.Surface, clock: pygame.time.Clock) -> None:
        """Initialize the debug display if it hasn't been initialized yet."""
        if cls._instance is None:
            cls._instance = cls(screen, clock)
    
    @classmethod
    def get_instance(cls) -> 'DebugDisplay':
        """Get the debug display instance."""
        if cls._instance is None:
            raise RuntimeError("DebugDisplay not initialized. Call initialize() first.")
        return cls._instance
    
    def __init__(self, screen: pygame.Surface, clock: pygame.time.Clock) -> None:
        """Initialize the debug display."""
        self.screen = screen
        self.clock = clock
        self.font = pygame.font.Font(None, 24)
        self.padding = 10
        self.line_height = 25
        self.background_color = (0, 0, 0, 128)  # Semi-transparent black
        self.text_color = (255, 255, 255)  # White text
    
    @classmethod
    def add_message(cls, message: str) -> None:
        """Add a debug message to the display."""
        if not config.IN_DEBUG_MODE:
            return
            
        instance = cls.get_instance()
        current_time = time.time()
        
        # Add new message and timestamp
        cls._messages.append(message)
        cls._message_timestamps.append(current_time)
        
        # Remove old messages
        while len(cls._messages) > cls._max_messages:
            cls._messages.pop(0)
            cls._message_timestamps.pop(0)
    
    @classmethod
    def update(cls) -> None:
        """Update the debug display."""
        if not config.IN_DEBUG_MODE:
            return
            
        instance = cls.get_instance()
        current_time = time.time()
        
        # Remove expired messages
        while cls._messages and current_time - cls._message_timestamps[0] > cls._message_lifetime:
            cls._messages.pop(0)
            cls._message_timestamps.pop(0)
    
    @classmethod
    def draw(cls) -> None:
        """Draw the debug display."""
        if not config.IN_DEBUG_MODE:
            return
            
        instance = cls.get_instance()
        
        if not cls._messages:
            return
            
        # Calculate display dimensions
        max_width = 0
        for message in cls._messages:
            text_surface = instance.font.render(message, True, instance.text_color)
            max_width = max(max_width, text_surface.get_width())
        
        total_height = len(cls._messages) * instance.line_height
        display_rect = pygame.Rect(
            instance.padding,
            instance.screen.get_height() - total_height - instance.padding,
            max_width + instance.padding * 2,
            total_height + instance.padding * 2
        )
        
        # Draw background
        background = pygame.Surface(display_rect.size, pygame.SRCALPHA)
        background.fill(instance.background_color)
        instance.screen.blit(background, display_rect)
        
        # Draw messages
        y = display_rect.top + instance.padding
        for message in cls._messages:
            text_surface = instance.font.render(message, True, instance.text_color)
            instance.screen.blit(text_surface, (display_rect.left + instance.padding, y))
            y += instance.line_height 
            