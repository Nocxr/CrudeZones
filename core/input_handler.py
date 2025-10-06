# core/input_handler.py
"""Handles all keyboard and mouse input detection - no hardcoded keys"""

import win32api
import win32con
from typing import Optional, Tuple
from .keycodes import parse_key_to_vk


class InputHandler:
    """Centralized input detection - all key codes come from config"""
    
    # Virtual key mappings for modifier keys
    MODIFIER_VK_MAP = {
        'shift': win32con.VK_SHIFT,
        'ctrl': win32con.VK_CONTROL,
        'alt': win32con.VK_MENU,
        'win': win32con.VK_LWIN
    }
    
    def __init__(self, config_manager):
        self.config = config_manager
        self._last_key_states = {}  # Track key states for edge detection
        self.monitor_keys = config_manager.get_monitor_keys()
        
    def is_modifier_pressed(self, modifier_name: str) -> bool:
        """Check if a modifier key is currently pressed"""
        vk = self.MODIFIER_VK_MAP.get(modifier_name.lower())
        if vk is None:
            return False
        return (win32api.GetAsyncKeyState(vk) & 0x8000) != 0
    
    def is_drag_show_key_pressed(self) -> bool:
        """Check if the configured drag-to-show-overlay key is pressed"""
        drag_config = self.config.get_drag_config()
        key_name = drag_config['show_zones_key']
        return self.is_modifier_pressed(key_name)
    
    def get_pressed_monitor_key(self) -> Optional[int]:
        """
        Check which monitor selection key (stage 1) is pressed.
        Now supports ANY key, not just modifiers.
        Returns monitor ID or None.
        """
        for mon_id, key_name in self.monitor_keys.items():
            # Check if it's a standard modifier first
            if key_name.lower() in ['shift', 'ctrl', 'alt', 'win']:
                if self.is_modifier_pressed(key_name):
                    return mon_id
            else:
                # Custom key - use the generic key checking
                from .keycodes import parse_key_to_vk
                vk, _ = parse_key_to_vk(key_name.upper())
                if vk and self._is_key_edge_or_held(vk):
                    return mon_id
        return None
    
    def is_mouse_button_down(self, button: str = 'left') -> bool:
        """Check if a mouse button is currently pressed"""
        vk_map = {
            'left': win32con.VK_LBUTTON,
            'right': win32con.VK_RBUTTON,
            'middle': win32con.VK_MBUTTON
        }
        vk = vk_map.get(button.lower())
        if vk is None:
            return False
        return (win32api.GetAsyncKeyState(vk) & 0x8000) != 0
    
    def get_pressed_number(self) -> Optional[int]:
        """
        Check if any number key (1-9) is pressed.
        Returns the number or None.
        Checks both top row and numpad.
        IMPORTANT: Excludes numbers that are configured as monitor keys.
        """
        # Get list of numbers used as monitor keys
        monitor_key_numbers = set()
        for key_name in self.monitor_keys.values():
            if key_name.isdigit():
                monitor_key_numbers.add(int(key_name))
        
        # Top row '1'-'9' (VK 0x31-0x39)
        for i in range(1, 10):
            if i not in monitor_key_numbers:  # Skip if used as monitor key
                if self._is_key_edge_or_held(0x30 + i):
                    return i
        
        # Numpad '1'-'9' (VK 0x61-0x69)
        for i in range(1, 10):
            if i not in monitor_key_numbers:  # Skip if used as monitor key
                if self._is_key_edge_or_held(0x60 + i):
                    return i
        
        return None
    
    def is_zone_key_pressed(self, zone_key_str: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a zone-specific key from config is pressed.
        Returns (is_pressed, label) tuple.
        """
        if not zone_key_str:
            return (False, None)
            
        vk, label = parse_key_to_vk(zone_key_str)
        if vk is None:
            return (False, None)
            
        is_pressed = self._is_key_edge_or_held(vk)
        return (is_pressed, label)
    
    def _is_key_edge_or_held(self, vk: int) -> bool:
        """
        Check if a key was just pressed (edge) OR is currently held.
        This catches quick taps between polling intervals.
        """
        state = win32api.GetAsyncKeyState(vk)
        # Bit 0 = key was pressed since last check (edge)
        # Bit 15 = key is currently down
        return (state & 0x1) != 0 or (state & 0x8000) != 0
    
    def reset_key_states(self) -> None:
        """Reset tracked key states (call after handling input)"""
        # Clear the edge-detect bit by reading all tracked keys
        for vk in self._last_key_states.keys():
            win32api.GetAsyncKeyState(vk)