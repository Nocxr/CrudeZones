# core/zone_numbering.py
"""Handles zone numbering and labeling logic"""

from typing import Dict, Tuple, Optional


class ZoneNumbering:
    """Manages zone number assignments and label generation"""
    
    def __init__(self, zone_manager):
        self.zone_manager = zone_manager
        self.zone_numbers: Dict[Tuple[int, str], int] = {}  # (mon_id, zone_name) -> number
        self.zone_labels: Dict[Tuple[int, str], str] = {}   # (mon_id, zone_name) -> label
        
    def assign_numbers_and_labels(self) -> None:
        """
        Assign numbers 1-9 to zones across all monitors.
        Also generate labels (prefer zone.key, fallback to number).
        """
        self.zone_numbers.clear()
        self.zone_labels.clear()
        
        number = 1
        
        # Iterate monitors deterministically (sorted)
        for mon_id in sorted(self.zone_manager.monitors.keys()):
            zones = self.zone_manager.monitors.get(mon_id, {})
            
            # Iterate zones deterministically (sorted)
            for zone_name in sorted(zones.keys()):
                zone_data = zones[zone_name]
                
                # Assign number (max 9)
                if number <= 9:
                    self.zone_numbers[(mon_id, zone_name)] = number
                    number += 1
                
                # Generate label: prefer zone's configured key, else use number
                label = self._get_zone_label(mon_id, zone_name, zone_data)
                if label:
                    self.zone_labels[(mon_id, zone_name)] = label
    
    def _get_zone_label(self, mon_id: int, zone_name: str, zone_data: dict) -> Optional[str]:
        """
        Get display label for a zone.
        Priority: zone.key from config -> assigned number -> None
        """
        # Check if zone has a configured key
        if 'key' in zone_data:
            key_str = str(zone_data['key']).strip().upper()
            if key_str:
                # Format nicely (e.g., "Q", "Num1", "F5")
                if key_str.startswith("NUM"):
                    return key_str.replace("NUM", "Num")
                return key_str
        
        # Fallback to assigned number
        zone_key = (mon_id, zone_name)
        if zone_key in self.zone_numbers:
            return str(self.zone_numbers[zone_key])
        
        return None
    
    def get_zone_by_number(self, number: int) -> Optional[Tuple[int, str]]:
        """Get (monitor_id, zone_name) for a given number"""
        for (mon_id, zone_name), num in self.zone_numbers.items():
            if num == number:
                return (mon_id, zone_name)
        return None
    
    def get_label(self, mon_id: int, zone_name: str) -> Optional[str]:
        """Get display label for a zone"""
        return self.zone_labels.get((mon_id, zone_name))
    
    def get_number(self, mon_id: int, zone_name: str) -> Optional[int]:
        """Get assigned number for a zone"""
        return self.zone_numbers.get((mon_id, zone_name))