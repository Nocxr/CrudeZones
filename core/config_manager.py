# core/config_manager.py
"""Centralized configuration management - no hardcoded values"""

import yaml
import os
import glob
from typing import Dict, List, Any, Optional


class ConfigManager:
    """Manages all configuration loading and validation"""
    
    # Default configuration values (only place defaults should exist)
    DEFAULTS = {
        'overlay': {
            'hotkey': 'ctrl+alt+`',
            'color': 'cyan',
            'opacity': 0.3,
            'alpha': 180,
            'auto_hide_seconds': 3
        },
        'monitor_keys': {
            0: '`',
            1: '1',
            2: '2'
        },
        'default_monitor_for_zone_keys': 'context_aware',
        'window_management': {
            'restore_hotkey': 'ctrl+alt+r',
            'reload_config_hotkey': 'ctrl+alt+shift+r',
            'cycle_next_hotkey': 'ctrl+alt+]',
            'cycle_prev_hotkey': 'ctrl+alt+[',
            'cycle_all_next_hotkey': 'ctrl+alt+shift+]',
            'cycle_all_prev_hotkey': 'ctrl+alt+shift+['
        },
        'drag_behavior': {
            'show_zones_key': 'shift',  # shift, ctrl, or alt
            'scroll_layout_switch_enabled': True,
            'scroll_cooldown_seconds': 0.30,
            'number_snap_cooldown_seconds': 0.5,
            'zone_hover_margin_pixels': 6,
            'ignore_fullscreen_zone': True
        },
        'state_tracking': {
            'auto_restore_enabled': True,
            'movement_threshold_pixels': 10,
            'monitoring_interval_seconds': 0.1,
            'operation_exempt_delay_seconds': 2.0
        }
    }
    
    def __init__(self, config_dir: str = 'config'):
        self.config_dir = config_dir
        self.hotkeys_config: Dict[str, Any] = {}
        self.layouts: Dict[str, Any] = {}
        self.active_layout: str = 'default'
        
    def load_all(self) -> None:
        """Load all configuration files"""
        self._load_hotkeys()
        self._load_layouts()
        
    def _load_hotkeys(self) -> None:
        """Load hotkey configuration"""
        hotkeys_path = os.path.join(self.config_dir, 'hotkeys.yaml')
        with open(hotkeys_path, 'r') as f:
            self.hotkeys_config = yaml.safe_load(f) or {}
            
    def _load_layouts(self) -> None:
        """Load all layout configurations"""
        layouts_dir = os.path.join(self.config_dir, 'layouts')
        self.layouts.clear()
        
        for layout_file in glob.glob(os.path.join(layouts_dir, '*.yaml')):
            with open(layout_file, 'r') as f:
                layout_data = yaml.safe_load(f)
                layout_name = layout_data.get('name', 
                    os.path.splitext(os.path.basename(layout_file))[0])
                self.layouts[layout_name] = layout_data
        
        # Set default layout
        if 'default' in self.layouts:
            self.active_layout = 'default'
        elif self.layouts:
            self.active_layout = list(self.layouts.keys())[0]
        else:
            raise ValueError("No layouts found in layouts directory")
            
    def get_overlay_config(self, layout_name: Optional[str] = None) -> Dict[str, Any]:
        """Get overlay configuration with defaults"""
        layout_name = layout_name or self.active_layout
        layout = self.layouts.get(layout_name, {})
        overlay_cfg = layout.get('overlay', {})
        
        return {
            'hotkey': self.hotkeys_config.get('overlay_hotkey', 
                self.DEFAULTS['overlay']['hotkey']),
            'color': overlay_cfg.get('color', self.DEFAULTS['overlay']['color']),
            'opacity': overlay_cfg.get('opacity', self.DEFAULTS['overlay']['opacity']),
            'alpha': overlay_cfg.get('alpha', self.DEFAULTS['overlay']['alpha']),
            'auto_hide_seconds': overlay_cfg.get('auto_hide_seconds', 
                self.DEFAULTS['overlay']['auto_hide_seconds'])
        }
    
    def get_window_management_config(self) -> Dict[str, str]:
        """Get window management hotkeys"""
        defaults = self.DEFAULTS['window_management']
        return {
            'restore': self.hotkeys_config.get('restore_hotkey', defaults['restore_hotkey']),
            'reload': self.hotkeys_config.get('reload_config_hotkey', defaults['reload_config_hotkey']),
            'cycle_next': self.hotkeys_config.get('cycle_next_hotkey', defaults['cycle_next_hotkey']),
            'cycle_prev': self.hotkeys_config.get('cycle_prev_hotkey', defaults['cycle_prev_hotkey']),
            'cycle_all_next': self.hotkeys_config.get('cycle_all_next_hotkey', defaults['cycle_all_next_hotkey']),
            'cycle_all_prev': self.hotkeys_config.get('cycle_all_prev_hotkey', defaults['cycle_all_prev_hotkey'])
        }
    
    def get_drag_config(self) -> Dict[str, Any]:
        """Get drag behavior configuration"""
        defaults = self.DEFAULTS['drag_behavior']
        drag_cfg = self.hotkeys_config.get('drag_behavior', {})
        
        return {
            'show_zones_key': drag_cfg.get('show_zones_key', 
                self.hotkeys_config.get('drag_show_zones_key', defaults['show_zones_key'])),
            'scroll_enabled': drag_cfg.get('scroll_layout_switch_enabled', 
                defaults['scroll_layout_switch_enabled']),
            'scroll_cooldown': drag_cfg.get('scroll_cooldown_seconds', 
                defaults['scroll_cooldown_seconds']),
            'number_snap_cooldown': drag_cfg.get('number_snap_cooldown_seconds', 
                defaults['number_snap_cooldown_seconds']),
            'hover_margin': drag_cfg.get('zone_hover_margin_pixels', 
                defaults['zone_hover_margin_pixels']),
            'ignore_fullscreen': drag_cfg.get('ignore_fullscreen_zone', 
                defaults['ignore_fullscreen_zone'])
        }
    
    def get_state_tracking_config(self) -> Dict[str, Any]:
        """Get state tracking configuration"""
        defaults = self.DEFAULTS['state_tracking']
        state_cfg = self.hotkeys_config.get('state_tracking', {})
        
        return {
            'enabled': state_cfg.get('auto_restore_enabled', defaults['auto_restore_enabled']),
            'threshold': state_cfg.get('movement_threshold_pixels', defaults['movement_threshold_pixels']),
            'interval': state_cfg.get('monitoring_interval_seconds', defaults['monitoring_interval_seconds']),
            'exempt_delay': state_cfg.get('operation_exempt_delay_seconds', defaults['operation_exempt_delay_seconds'])
        }
        
    def get_monitor_keys(self) -> dict:
        """Get monitor selection keys for two-stage hotkeys"""
        defaults = self.DEFAULTS['monitor_keys']
        configured = self.hotkeys_config.get('monitor_keys', {})
        
        # Merge configured with defaults
        result = dict(defaults)
        result.update(configured)
        return result

    def get_default_monitor_behavior(self) -> str:
        """Get default monitor behavior when no stage-1 key is pressed"""
        return self.hotkeys_config.get('default_monitor_for_zone_keys', 
            self.DEFAULTS['default_monitor_for_zone_keys'])
    
    def get_zone_hotkeys(self) -> List[Dict[str, Any]]:
        """Get zone-specific hotkey assignments"""
        return self.hotkeys_config.get('zone_hotkeys', [])
    
    def get_layout_switches(self) -> List[Dict[str, Any]]:
        """Get layout switching hotkeys"""
        return self.hotkeys_config.get('layout_switches', [])