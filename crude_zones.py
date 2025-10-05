import yaml
import win32gui
import win32con
import win32api
from pynput import keyboard
import ctypes
import ctypes.wintypes
import pystray
from PIL import Image, ImageDraw
import threading
import sys
import tkinter as tk
import time
from pynput import keyboard
from pynput.keyboard import Key, KeyCode
from pynput import mouse  # <-- add
user32 = ctypes.windll.user32  # <-- add (for ReleaseCapture)


from overlay_win32 import (
    Win32OverlayManager,
    get_hwnd_under_cursor,
    get_cursor_pos,
    rect_contains,
    zone_rect_to_tuple,
    snap_hwnd_to_zone,
)

# Set DPI awareness
ctypes.windll.shcore.SetProcessDpiAwareness(2)

class MonitorDetector:
    @staticmethod
    def get_monitors():
        """Get all monitor information including position and resolution"""
        monitors = []
        
        # Define callback type
        MonitorEnumProc = ctypes.WINFUNCTYPE(
            ctypes.c_int,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.wintypes.RECT),
            ctypes.c_double
        )
        
        def callback(hMonitor, hdcMonitor, lprcMonitor, dwData):
            # Get monitor info
            class MONITORINFOEX(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.wintypes.DWORD),
                    ("rcMonitor", ctypes.wintypes.RECT),
                    ("rcWork", ctypes.wintypes.RECT),
                    ("dwFlags", ctypes.wintypes.DWORD),
                    ("szDevice", ctypes.wintypes.WCHAR * 32)
                ]
            
            monitor_info = MONITORINFOEX()
            monitor_info.cbSize = ctypes.sizeof(MONITORINFOEX)
            
            ctypes.windll.user32.GetMonitorInfoW(hMonitor, ctypes.byref(monitor_info))
            
            monitor_area = monitor_info.rcMonitor
            work_area = monitor_info.rcWork
            
            monitors.append({
                'id': len(monitors),
                'x': monitor_area.left,
                'y': monitor_area.top,
                'width': monitor_area.right - monitor_area.left,
                'height': monitor_area.bottom - monitor_area.top,
                'work_x': work_area.left,
                'work_y': work_area.top,
                'work_width': work_area.right - work_area.left,
                'work_height': work_area.bottom - work_area.top,
                'is_primary': monitor_info.dwFlags == 1
            })
            return 1  # Continue enumeration
        
        # Create callback
        callback_func = MonitorEnumProc(callback)
        
        # Enumerate monitors
        ctypes.windll.user32.EnumDisplayMonitors(None, None, callback_func, 0)
        
        # Sort by position to ensure consistent ordering (left to right, top to bottom)
        monitors.sort(key=lambda m: (m['x'], m['y']))
        
        # Reassign IDs after sorting
        for i, monitor in enumerate(monitors):
            monitor['id'] = i
        
        return monitors

class WindowStateTracker:
    """Track window states to restore original size and position"""
    def __init__(self):
        self.window_states = {}  # hwnd -> {'x', 'y', 'width', 'height', 'timestamp'}
    
    def save_state(self, hwnd):
        """Save the current window state before snapping to zone"""
        try:
            rect = win32gui.GetWindowRect(hwnd)
            self.window_states[hwnd] = {
                'x': rect[0],
                'y': rect[1],
                'width': rect[2] - rect[0],
                'height': rect[3] - rect[1],
                'timestamp': time.time()
            }
            print(f"Saved window state: {rect[2] - rect[0]}x{rect[3] - rect[1]} at ({rect[0]}, {rect[1]})")
        except Exception as e:
            print(f"Error saving state: {e}")
    
    def restore_state(self, hwnd):
        """Restore window to its saved state"""
        if hwnd not in self.window_states:
            print("No saved state for this window")
            return False
        
        try:
            state = self.window_states[hwnd]
            
            # Check if window is maximized, restore it first
            placement = win32gui.GetWindowPlacement(hwnd)
            if placement[1] == win32con.SW_SHOWMAXIMIZED:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            
            # Restore to original position and size
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOP,
                state['x'],
                state['y'],
                state['width'],
                state['height'],
                win32con.SWP_SHOWWINDOW
            )
            
            print(f"Restored window to: {state['width']}x{state['height']} at ({state['x']}, {state['y']})")
            
            # Clear the saved state after restoration
            del self.window_states[hwnd]
            return True
            
        except Exception as e:
            print(f"Error restoring state: {e}")
            return False
    
    def cleanup_old_states(self):
        """Remove states for windows that no longer exist"""
        to_remove = []
        for hwnd in list(self.window_states.keys()):
            try:
                if not win32gui.IsWindow(hwnd):
                    to_remove.append(hwnd)
            except:
                to_remove.append(hwnd)
        
        for hwnd in to_remove:
            del self.window_states[hwnd]

class ZoneManager:
    def __init__(self, config_path):
        self.config_path = config_path
        self.state_tracker = WindowStateTracker()
        self.load_config()
    
    def load_config(self):
        """Load configuration from YAML file and detect monitors"""
        with open(self.config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Detect actual monitor layout
        self.detected_monitors = MonitorDetector.get_monitors()
        
        print(f"\nDetected {len(self.detected_monitors)} monitor(s):")
        for mon in self.detected_monitors:
            primary = " (PRIMARY)" if mon['is_primary'] else ""
            print(f"  Monitor {mon['id']}: {mon['width']}x{mon['height']} at ({mon['x']}, {mon['y']}){primary}")
            print(f"    Work area: {mon['work_width']}x{mon['work_height']} at ({mon['work_x']}, {mon['work_y']})")
        
        # Get active layout
        self.active_layout = self.config.get('active_layout', 'default')
        print(f"\nActive layout: {self.active_layout}")
        
        # Load monitors from active layout
        self.monitors = self._load_monitors()
        self.hotkeys = self._load_hotkeys()
        self.layout_hotkeys = self.config.get('layout_hotkeys', [])
        self.overlay_config = self._load_overlay_config()
        self.restore_hotkey = self.config.get('restore_hotkey', 'ctrl+alt+r')
        self.reload_config_hotkey = self.config.get('reload_config_hotkey', 'ctrl+alt+shift+r')
    
    def _load_overlay_config(self):
        """Load overlay configuration with defaults"""
        overlay = self.config.get('overlay', {})
        return {
            'hotkey': overlay.get('hotkey', 'ctrl+alt+z'),
            'color': overlay.get('color', 'cyan'),
            'opacity': overlay.get('opacity', 0.3),
            'auto_hide_seconds': overlay.get('auto_hide_seconds', 3)
        }
    
    def _load_monitors(self):
        """Parse monitor zones from config and calculate actual pixel values"""
        monitors = {}
        
        # Get monitor config from active layout
        if 'layouts' in self.config:
            layout_config = self.config['layouts'].get(self.active_layout, {})
            monitor_configs = layout_config.get('monitors', [])
        else:
            # Fallback to old format
            monitor_configs = self.config.get('monitors', [])
        
        for monitor_config in monitor_configs:
            mon_id = monitor_config['id']
            
            # Check if this monitor ID exists in detected monitors
            if mon_id >= len(self.detected_monitors):
                print(f"Warning: Monitor {mon_id} defined in config but not detected. Skipping.")
                continue
            
            detected = self.detected_monitors[mon_id]
            monitors[mon_id] = {}
            
            for zone in monitor_config['zones']:
                respect_taskbar = zone.get('respect_taskbar', True)
                
                # Use work area if respecting taskbar, otherwise use full monitor area
                if respect_taskbar:
                    base_x = detected['work_x']
                    base_y = detected['work_y']
                    base_width = detected['work_width']
                    base_height = detected['work_height']
                else:
                    base_x = detected['x']
                    base_y = detected['y']
                    base_width = detected['width']
                    base_height = detected['height']
                
                # Calculate actual pixel values from percentages
                zone_x = base_x + int(base_width * zone['x_percent'] / 100)
                zone_y = base_y + int(base_height * zone['y_percent'] / 100)
                zone_width = int(base_width * zone['width_percent'] / 100)
                zone_height = int(base_height * zone['height_percent'] / 100)
                
                monitors[mon_id][zone['name']] = {
                    'x': zone_x,
                    'y': zone_y,
                    'width': zone_width,
                    'height': zone_height
                }
                
                print(f"  Zone '{zone['name']}' on Monitor {mon_id}: "
                    f"{zone_width}x{zone_height} at ({zone_x}, {zone_y})")
        
        return monitors
    
    def switch_layout(self, layout_name):
        """Switch to a different layout"""
        if 'layouts' not in self.config:
            print("No layouts defined in config")
            return
        
        if layout_name not in self.config['layouts']:
            print(f"Layout '{layout_name}' not found")
            return
        
        self.active_layout = layout_name
        self.monitors = self._load_monitors()
        print(f"Switched to layout: {layout_name}")
        
    
    def _load_hotkeys(self):
        """Parse hotkey mappings"""
        return self.config['hotkeys']
    
    def get_active_window(self):
        """Get the currently active window handle"""
        return win32gui.GetForegroundWindow()
    
    def move_window_to_zone(self, monitor_id, zone_name):
        """Move active window to specified zone"""
        hwnd = self.get_active_window()
        
        if not hwnd:
            print("No active window")
            return
        
        # Get zone coordinates
        if monitor_id not in self.monitors:
            print(f"Monitor {monitor_id} not found")
            return
        
        if zone_name not in self.monitors[monitor_id]:
            print(f"Zone {zone_name} not found on monitor {monitor_id}")
            return
        
        # Only save state if this window doesn't have a saved state yet
        # This preserves the original position before any snapping
        if hwnd not in self.state_tracker.window_states:
            self.state_tracker.save_state(hwnd)
        else:
            print("Window already has saved state, not updating")
        
        zone = self.monitors[monitor_id][zone_name]
        
        # Check if window is maximized, restore it first
        placement = win32gui.GetWindowPlacement(hwnd)
        if placement[1] == win32con.SW_SHOWMAXIMIZED:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        
        # Move and resize window
        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_TOP,
            zone['x'],
            zone['y'],
            zone['width'],
            zone['height'],
            win32con.SWP_SHOWWINDOW
        )
        
        print(f"Moved window to {zone_name} on monitor {monitor_id}")
        
        # Cleanup old states
        self.state_tracker.cleanup_old_states()
    
    def restore_window(self):
        """Restore the active window to its original size and position"""
        hwnd = self.get_active_window()
        
        if not hwnd:
            print("No active window")
            return
        
        success = self.state_tracker.restore_state(hwnd)
        if not success:
            print("Could not restore window - no saved state found")
            
    def get_monitor_for_window(self, hwnd):
        """Determine which monitor a window is on"""
        try:
            rect = win32gui.GetWindowRect(hwnd)
            window_center_x = (rect[0] + rect[2]) // 2
            window_center_y = (rect[1] + rect[3]) // 2
            
            # Find which monitor contains the center of the window
            for monitor in self.detected_monitors:
                if (monitor['x'] <= window_center_x < monitor['x'] + monitor['width'] and
                    monitor['y'] <= window_center_y < monitor['y'] + monitor['height']):
                    return monitor['id']
            
            # Default to primary monitor
            return 0
        except:
            return 0

    def cycle_zone(self, direction='next'):
        """Cycle the active window through zones on its current monitor"""
        hwnd = self.get_active_window()
        
        if not hwnd:
            print("No active window")
            return
        
        # Determine which monitor the window is on
        monitor_id = self.get_monitor_for_window(hwnd)
        
        if monitor_id not in self.monitors:
            print(f"Monitor {monitor_id} not found")
            return
        
        # Get list of zones for this monitor
        zones = list(self.monitors[monitor_id].keys())
        
        if not zones:
            print(f"No zones defined for monitor {monitor_id}")
            return
        
        # Try to determine current zone or default to first
        current_zone_idx = 0
        try:
            rect = win32gui.GetWindowRect(hwnd)
            current_x, current_y = rect[0], rect[1]
            current_width = rect[2] - rect[0]
            current_height = rect[3] - rect[1]
            
            # Check if window matches any zone (with tolerance)
            tolerance = 10
            for idx, zone_name in enumerate(zones):
                zone = self.monitors[monitor_id][zone_name]
                if (abs(current_x - zone['x']) < tolerance and
                    abs(current_y - zone['y']) < tolerance and
                    abs(current_width - zone['width']) < tolerance and
                    abs(current_height - zone['height']) < tolerance):
                    current_zone_idx = idx
                    break
        except:
            pass
        
        # Calculate next zone index
        if direction == 'next':
            next_zone_idx = (current_zone_idx + 1) % len(zones)
        else:  # previous
            next_zone_idx = (current_zone_idx - 1) % len(zones)
        
        next_zone_name = zones[next_zone_idx]
        
        print(f"Cycling {direction} to zone: {next_zone_name}")
        self.move_window_to_zone(monitor_id, next_zone_name)
        
    def cycle_zone_all_monitors(self, direction='next'):
        """Cycle through all zones across all monitors"""
        hwnd = self.get_active_window()
        
        if not hwnd:
            print("No active window")
            return
        
        # Build a flat list of all (monitor_id, zone_name) tuples
        all_zones = []
        for mon_id in sorted(self.monitors.keys()):
            for zone_name in self.monitors[mon_id].keys():
                all_zones.append((mon_id, zone_name))
        
        if not all_zones:
            print("No zones defined")
            return
        
        # Try to find current position
        current_idx = 0
        try:
            rect = win32gui.GetWindowRect(hwnd)
            current_x, current_y = rect[0], rect[1]
            current_width = rect[2] - rect[0]
            current_height = rect[3] - rect[1]
            
            # Check if window matches any zone
            tolerance = 10
            for idx, (mon_id, zone_name) in enumerate(all_zones):
                zone = self.monitors[mon_id][zone_name]
                if (abs(current_x - zone['x']) < tolerance and
                    abs(current_y - zone['y']) < tolerance and
                    abs(current_width - zone['width']) < tolerance and
                    abs(current_height - zone['height']) < tolerance):
                    current_idx = idx
                    break
        except:
            pass
        
        # Calculate next position
        if direction == 'next':
            next_idx = (current_idx + 1) % len(all_zones)
        else:
            next_idx = (current_idx - 1) % len(all_zones)
        
        next_mon, next_zone = all_zones[next_idx]
        print(f"Cycling {direction} to Monitor {next_mon}, Zone {next_zone}")
        self.move_window_to_zone(next_mon, next_zone)
        

class HotkeyListener:
    def __init__(self, zone_manager, overlay=None, tray_icon=None):
        self.zone_manager = zone_manager
        self.overlay = overlay
        self.tray_icon = tray_icon
        self.listener = None
        self.running = False
        self.current_keys = set()
        self.hotkeys_fired = set()
        self.overlay_visible = False
        
        # Numpad with NumLock ON (VK codes 96-105)
        self.numpad_vk_map = {
            96: 'kp_0', 97: 'kp_1', 98: 'kp_2', 99: 'kp_3', 100: 'kp_4',
            101: 'kp_5', 102: 'kp_6', 103: 'kp_7', 104: 'kp_8', 105: 'kp_9'
        }
        
        # Numpad with NumLock OFF (navigation keys)
        self.numpad_nav_map = {
            'insert': 'kp_0',
            'end': 'kp_1',
            'down': 'kp_2',
            'page_down': 'kp_3',
            'left': 'kp_4',
            12: 'kp_5',  # VK=12 is the Clear key (numpad 5 with NumLock off)
            'right': 'kp_6',
            'home': 'kp_7',
            'up': 'kp_8',
            'page_up': 'kp_9'
        }
        
    def start(self):
        """Start listening for hotkeys"""
        if self.running:
            return
        
        # Build hotkey configurations
        self.hotkey_actions = self._build_hotkey_actions()
        
        print(f"Registered {len(self.hotkey_actions)} hotkey combinations")
        
        # Start listener with manual key tracking
        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        )
        self.listener.start()
        self.running = True
        
        print("Hotkey listener started (with numpad support - works with NumLock ON or OFF)")
        print("\nRegistered hotkeys:")
        for hotkey_str in sorted(self.hotkey_actions.keys()):
            action = self.hotkey_actions[hotkey_str]
            if action['type'] == 'zone':
                print(f"  {hotkey_str} -> Monitor {action['monitor']}, Zone {action['zone']}")
            else:
                print(f"  {hotkey_str} -> {action['type']}")
    
    def stop(self):
        """Stop listening for hotkeys"""
        if self.listener and self.running:
            self.listener.stop()
            self.running = False
            self.current_keys.clear()
            self.hotkeys_fired.clear()
            print("Hotkey listener stopped")
    
    def restart(self):
        """Restart the listener (useful after config reload)"""
        self.stop()
        self.start()
    
    def _normalize_hotkey_config(self, key_string):
        """Convert config hotkey string to internal format for matching"""
        parts = [p.strip().lower() for p in key_string.split('+')]
        
        # Standardize generic modifier names only (leave specific ones as-is)
        normalized = []
        for part in parts:
            if part in ['ctrl', 'control']:
                normalized.append('ctrl')
            elif part == 'alt':
                normalized.append('alt')
            elif part == 'shift':
                normalized.append('shift')
            elif part in ['win', 'cmd', 'super']:
                normalized.append('win')
            # Keep specific modifiers as-is
            elif part in ['ctrl_l', 'ctrl_r', 'alt_l', 'alt_r', 'alt_gr', 'shift_l', 'shift_r', 'win_l', 'win_r']:
                normalized.append(part)
            else:
                normalized.append(part)
        
        # Separate modifiers and non-modifiers
        modifier_keywords = ['ctrl', 'ctrl_l', 'ctrl_r', 'alt', 'alt_l', 'alt_r', 'alt_gr', 
                            'shift', 'shift_l', 'shift_r', 'win', 'win_l', 'win_r']
        modifiers = [k for k in normalized if k in modifier_keywords]
        keys = [k for k in normalized if k not in modifier_keywords]
        
        return '+'.join(sorted(modifiers) + keys)
    
    def _build_hotkey_actions(self):
        """Build a map of hotkey combinations to their actions"""
        actions = {}
        
        # Zone hotkeys
        for hk in self.zone_manager.hotkeys:
            normalized = self._normalize_hotkey_config(hk['keys'])
            actions[normalized] = {
                'type': 'zone',
                'monitor': hk['monitor'],
                'zone': hk['zone']
            }
        
        # Overlay toggle
        if self.overlay:
            normalized = self._normalize_hotkey_config(
                self.zone_manager.overlay_config['hotkey']
            )
            actions[normalized] = {'type': 'overlay'}
        
        # Restore window
        normalized = self._normalize_hotkey_config(self.zone_manager.restore_hotkey)
        actions[normalized] = {'type': 'restore'}
        
        # Reload config
        normalized = self._normalize_hotkey_config(
            self.zone_manager.reload_config_hotkey
        )
        actions[normalized] = {'type': 'reload'}
        
        # Cycle zones
        normalized = self._normalize_hotkey_config(
            self.zone_manager.config.get('cycle_next_hotkey', 'ctrl+alt+]')
        )
        actions[normalized] = {'type': 'cycle', 'direction': 'next'}
        
        normalized = self._normalize_hotkey_config(
            self.zone_manager.config.get('cycle_prev_hotkey', 'ctrl+alt+[')
        )
        actions[normalized] = {'type': 'cycle', 'direction': 'prev'}
        
        # Cycle all monitors
        normalized = self._normalize_hotkey_config(
            self.zone_manager.config.get('cycle_all_next_hotkey', 'ctrl+alt+shift+]')
        )
        actions[normalized] = {'type': 'cycle_all', 'direction': 'next'}

        normalized = self._normalize_hotkey_config(
            self.zone_manager.config.get('cycle_all_prev_hotkey', 'ctrl+alt+shift+[')
        )
        actions[normalized] = {'type': 'cycle_all', 'direction': 'prev'}
        
        # Layout switching
        for layout_hk in self.zone_manager.layout_hotkeys:
            normalized = self._normalize_hotkey_config(layout_hk['keys'])
            actions[normalized] = {
                'type': 'layout',
                'layout': layout_hk['layout']
            }
        
        return actions
    
    def _get_key_name(self, key):
        """Get normalized name for a key, handling both NumLock states"""
        # Check if it's a numpad key with NumLock ON (VK 96-105)
        if hasattr(key, 'vk'):
            if key.vk in self.numpad_vk_map:
                return self.numpad_vk_map[key.vk]
            # Check for numpad 5 with NumLock OFF (VK=12)
            elif key.vk == 12:
                return self.numpad_nav_map[12]
            # Handle letter keys (A-Z are VK 65-90)
            elif 65 <= key.vk <= 90:
                return chr(key.vk).lower()
            # Handle number row keys (0-9 are VK 48-57)
            elif 48 <= key.vk <= 57:
                return chr(key.vk)
            # Handle common punctuation and special keys by VK code
            else:
                vk_map = {
                    186: ';', 187: '=', 188: ',', 189: '-', 190: '.', 191: '/',
                    192: '`', 219: '[', 220: '\\', 221: ']', 222: "'",
                    # Function keys
                    112: 'f1', 113: 'f2', 114: 'f3', 115: 'f4', 116: 'f5', 117: 'f6',
                    118: 'f7', 119: 'f8', 120: 'f9', 121: 'f10', 122: 'f11', 123: 'f12',
                    # Navigation keys
                    33: 'page_up', 34: 'page_down', 35: 'end', 36: 'home',
                    37: 'left', 38: 'up', 39: 'right', 40: 'down',
                    45: 'insert', 46: 'delete',
                    # Other common keys
                    32: 'space', 8: 'backspace', 9: 'tab', 13: 'enter', 27: 'esc',
                    20: 'caps_lock', 145: 'scroll_lock', 144: 'num_lock',
                    91: 'win', 92: 'win', 93: 'menu'
                }
                if key.vk in vk_map:
                    return vk_map[key.vk]
        
        # Check if it's a numpad navigation key with NumLock OFF
        if hasattr(key, 'name'):
            key_name_lower = key.name.lower()
            if key_name_lower in self.numpad_nav_map:
                return self.numpad_nav_map[key_name_lower]
        
        # Handle modifier keys - distinguish left/right
        if key == Key.ctrl_l:
            return 'ctrl_l'
        elif key == Key.ctrl_r:
            return 'ctrl_r'
        elif key == Key.ctrl:
            return 'ctrl'
        elif key == Key.alt_l:
            return 'alt_l'
        elif key == Key.alt_r:
            return 'alt_r'
        elif key == Key.alt:
            return 'alt'
        elif key == Key.shift_l:
            return 'shift_l'
        elif key == Key.shift_r:
            return 'shift_r'
        elif key == Key.shift:
            return 'shift'
        elif key == Key.cmd_l:
            return 'win_l'
        elif key == Key.cmd_r:
            return 'win_r'
        elif key == Key.cmd:
            return 'win'
        
        # Fallback: try char attribute
        if hasattr(key, 'char') and key.char:
            return key.char.lower()
        
        # Fallback: try name attribute
        if hasattr(key, 'name'):
            return key.name.lower()
        
        # If all else fails, log the VK code for debugging
        if hasattr(key, 'vk'):
            print(f"Warning: Unmapped VK code {key.vk}")
        
        return None
    
    def _get_current_combo(self):
        """Get the current key combination as a normalized string"""
        modifiers = []
        non_modifiers = []
        
        # Get ALL keys with their specific modifier types
        for key in self.current_keys:
            key_name = self._get_key_name(key)
            if key_name:
                # Check if it's a modifier (keep specific type)
                if key_name in ['ctrl', 'ctrl_l', 'ctrl_r', 'alt', 'alt_l', 'alt_r', 'alt_gr',
                            'shift', 'shift_l', 'shift_r', 'win', 'win_l', 'win_r']:
                    modifiers.append(key_name)
                else:
                    non_modifiers.append(key_name)
        
        # Sort modifiers and combine with non-modifiers
        all_keys = sorted(modifiers) + non_modifiers
        
        return '+'.join(all_keys) if all_keys else None
    
    def _check_hotkey_match(self, pressed_combo, registered_combo):
        """Check if a pressed combo matches a registered combo, handling generic modifiers"""
        pressed_parts = pressed_combo.split('+')
        registered_parts = registered_combo.split('+')
        
        # Get what's actually pressed
        pressed_ctrl_specific = [p for p in pressed_parts if p in ['ctrl_l', 'ctrl_r']]
        pressed_alt_specific = [p for p in pressed_parts if p in ['alt_l', 'alt_r', 'alt_gr']]
        pressed_shift_specific = [p for p in pressed_parts if p in ['shift_l', 'shift_r']]
        pressed_win_specific = [p for p in pressed_parts if p in ['win_l', 'win_r']]
        
        pressed_ctrl = len(pressed_ctrl_specific) > 0 or 'ctrl' in pressed_parts
        pressed_alt = len(pressed_alt_specific) > 0 or 'alt' in pressed_parts
        pressed_shift = len(pressed_shift_specific) > 0 or 'shift' in pressed_parts
        pressed_win = len(pressed_win_specific) > 0 or 'win' in pressed_parts
        
        pressed_non_mod = [p for p in pressed_parts if p not in ['ctrl', 'ctrl_l', 'ctrl_r', 'alt', 'alt_l', 'alt_r', 'alt_gr', 'shift', 'shift_l', 'shift_r', 'win', 'win_l', 'win_r']]
        
        # Get what's required
        requires_ctrl = 'ctrl' in registered_parts or any(p in ['ctrl_l', 'ctrl_r'] for p in registered_parts)
        requires_alt = 'alt' in registered_parts or any(p in ['alt_l', 'alt_r', 'alt_gr'] for p in registered_parts)
        requires_shift = 'shift' in registered_parts or any(p in ['shift_l', 'shift_r'] for p in registered_parts)
        requires_win = 'win' in registered_parts or any(p in ['win_l', 'win_r'] for p in registered_parts)
        
        # Check modifiers match EXACTLY (no extra, no missing)
        if pressed_ctrl != requires_ctrl:
            return False
        if pressed_alt != requires_alt:
            return False
        if pressed_shift != requires_shift:
            return False
        if pressed_win != requires_win:
            return False
        
        # Check specific modifiers if required
        for part in registered_parts:
            if part in ['ctrl_l', 'ctrl_r']:
                if part not in pressed_ctrl_specific:
                    return False
            elif part in ['alt_l', 'alt_r', 'alt_gr']:
                if part not in pressed_alt_specific:
                    return False
            elif part in ['shift_l', 'shift_r']:
                if part not in pressed_shift_specific:
                    return False
            elif part in ['win_l', 'win_r']:
                if part not in pressed_win_specific:
                    return False
        
        # Check non-modifier keys match exactly
        registered_non_mod = [p for p in registered_parts if p not in ['ctrl', 'ctrl_l', 'ctrl_r', 'alt', 'alt_l', 'alt_r', 'alt_gr', 'shift', 'shift_l', 'shift_r', 'win', 'win_l', 'win_r']]
        
        if set(pressed_non_mod) != set(registered_non_mod):
            return False
        
        return True

    def _on_press(self, key):
        """Handle key press events"""
        #print(f"DEBUG: Key pressed: {key}")
        
        # Only add to current_keys if not already there
        if key in self.current_keys:
            return  # Key repeat, ignore
        
        self.current_keys.add(key)
        
        # Check for matching hotkeys
        combo = self._get_current_combo()
        #print(f"DEBUG: Current combo: {combo}")
        
        if combo:
            # Check all registered actions for matches
            for registered_combo, action in self.hotkey_actions.items():
                if self._check_hotkey_match(combo, registered_combo):
                    # Use combo as the key to prevent re-firing
                    if combo not in self.hotkeys_fired:
                        print(f"DEBUG: MATCH! {combo} matches {registered_combo}")
                        self.hotkeys_fired.add(combo)
                        self._execute_action(action, registered_combo)
                    break  # ADD THIS LINE
    
    def _on_release(self, key):
        """Handle key release events"""
        self.current_keys.discard(key)
        
        # Clear fired hotkeys when modifiers are released
        if key in [Key.ctrl, Key.ctrl_l, Key.ctrl_r, 
                   Key.alt, Key.alt_l, Key.alt_r,
                   Key.shift, Key.shift_l, Key.shift_r,
                   Key.cmd, Key.cmd_l, Key.cmd_r]:
            self.hotkeys_fired.clear()
    
    def _execute_action(self, action, combo):
        """Execute the action associated with a hotkey"""
        try:
            if action['type'] == 'zone':
                print(f"Hotkey [{combo}] triggered: Moving to Monitor {action['monitor']}, Zone {action['zone']}")
                self.zone_manager.move_window_to_zone(
                    action['monitor'],
                    action['zone']
                )
            elif action['type'] == 'overlay':
                print(f"Hotkey [{combo}] triggered: Toggling overlay")
                self._toggle_overlay()
            elif action['type'] == 'restore':
                print(f"Hotkey [{combo}] triggered: Restoring window")
                self.zone_manager.restore_window()
            elif action['type'] == 'reload':
                print(f"Hotkey [{combo}] triggered: Reloading config")
                self._reload_config()
            elif action['type'] == 'cycle':
                print(f"Hotkey [{combo}] triggered: Cycling {action['direction']}")
                self.zone_manager.cycle_zone(action['direction'])
            elif action['type'] == 'cycle_all':
                print(f"Hotkey [{combo}] triggered: Cycling {action['direction']} (all monitors)")
                self.zone_manager.cycle_zone_all_monitors(action['direction'])
            elif action['type'] == 'layout':
                print(f"Hotkey [{combo}] triggered: Switching to layout {action['layout']}")
                self.zone_manager.switch_layout(action['layout'])
        except Exception as e:
            print(f"Error executing hotkey action: {e}")
            import traceback
            traceback.print_exc()
    
    def _toggle_overlay(self):
        """Toggle the zone overlay (Win32 overlay version)"""
        if not self.overlay:
            return
        if not self.overlay_visible:
            self.overlay.show()
            self.overlay.redraw()
            self.overlay_visible = True
        else:
            self.overlay.hide()
            self.overlay_visible = False

    
    def _reload_config(self):
        """Reload configuration"""
        print("\n=== Reloading Configuration (via hotkey) ===")
        try:
            self.zone_manager.load_config()
            self.restart()
            print("Configuration reloaded successfully\n")
            
            if self.tray_icon:
                self.tray_icon.notify(
                    "Configuration reloaded (monitors re-detected)",
                    "Zone Manager"
                )
        except Exception as e:
            print(f"Error reloading config: {e}\n")
            if self.tray_icon:
                self.tray_icon.notify(f"Error reloading config: {e}", "Zone Manager")

class TrayApp:
    def __init__(self, zone_manager, hotkey_listener, config_path, drag_listener=None):
        self.zone_manager = zone_manager
        self.hotkey_listener = hotkey_listener
        self.config_path = config_path
        self.drag_listener = drag_listener  # ADD THIS
        self.icon = None
        
        self.hotkey_listener.tray_icon = None
    
    def create_icon_image(self):
        """Load icon from PNG file"""
        try:
            # Try to load the icon from file
            image = Image.open('icon.png')
            # Resize to standard tray icon size if needed
            image = image.resize((64, 64), Image.Resampling.LANCZOS)
            return image
        except FileNotFoundError:
            print("Warning: icon.png not found, using default icon")
            # Fallback to generated icon
            return self._create_default_icon()

    def _create_default_icon(self):
        """Create a simple default icon if PNG is not found"""
        width = 64
        height = 64
        image = Image.new('RGB', (width, height), 'navy')
        draw = ImageDraw.Draw(image)
        
        # Draw a simple grid pattern
        draw.rectangle([8, 8, 28, 28], fill='white', outline='lightblue', width=2)
        draw.rectangle([36, 8, 56, 28], fill='white', outline='lightblue', width=2)
        draw.rectangle([8, 36, 28, 56], fill='white', outline='lightblue', width=2)
        draw.rectangle([36, 36, 56, 56], fill='white', outline='lightblue', width=2)
        
        return image
    
    def reload_config(self, icon=None, item=None):
        """Reload configuration file and re-detect monitors"""
        try:
            print("\n=== Reloading Configuration ===")
            self.zone_manager.load_config()
            self.hotkey_listener.restart()
            print("Configuration reloaded successfully\n")
            if self.icon:
                self.icon.notify("Configuration reloaded (monitors re-detected)", "Zone Manager")
        except Exception as e:
            print(f"Error reloading config: {e}")
            if self.icon:
                self.icon.notify(f"Error reloading config: {e}", "Zone Manager")
    
    def show_info(self, icon, item):
        """Show information about loaded zones and hotkeys"""
        # Show popup window instead of toast
        info_window = HotkeyInfoWindow(self.zone_manager)
        info_window.show()
    
    def show_monitors(self, icon, item):
        """Show detected monitor information"""
        info = f"Detected {len(self.zone_manager.detected_monitors)} monitor(s):\n"
        for mon in self.zone_manager.detected_monitors:
            primary = " (PRIMARY)" if mon['is_primary'] else ""
            info += f"Monitor {mon['id']}: {mon['width']}x{mon['height']}{primary}\n"
        print(info)
        icon.notify(info, "Zone Manager - Monitors")
    
    def quit_app(self, icon, item):
        """Quit the application"""
        print("Shutting down...")
        self.hotkey_listener.stop()
        if self.drag_listener:  # ADD THIS CHECK
            self.drag_listener.stop()
        icon.stop()
    
    def setup_tray_icon(self):
        """Create and configure system tray icon"""
        menu = pystray.Menu(
            pystray.MenuItem("Show Monitors", self.show_monitors),
            pystray.MenuItem("Show Hotkeys", self.show_info),
            pystray.MenuItem("Reload Config", self.reload_config),
            pystray.MenuItem("Quit", self.quit_app)
        )
        
        self.icon = pystray.Icon(
            "zone_manager",
            self.create_icon_image(),
            "Zone Manager",
            menu=menu
        )
        
        return self.icon
    
    def run(self):
        """Run the tray application"""
        icon = self.setup_tray_icon()
        print("Zone Manager running in system tray")
        print("Right-click the tray icon for options")
        icon.run()
        
        
class HotkeyInfoWindow:
    """Display hotkey information in a popup window"""
    def __init__(self, zone_manager):
        self.zone_manager = zone_manager
        self.dragged_hwnd = None
        self.current_zone = None      # <-- tuple (mon_id, zone_name)

        
    def show(self):
        """Show the hotkey info window"""
        # Create window in a separate thread to avoid blocking
        threading.Thread(target=self._create_window, daemon=True).start()
    
    def _create_window(self):
        """Create and display the info window"""
        root = tk.Tk()
        root.title("Zone Manager - Hotkeys")
        root.geometry("500x600")
        root.resizable(True, True)
        
        # Create main frame with scrollbar
        main_frame = tk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create canvas and scrollbar
        canvas = tk.Canvas(main_frame)
        scrollbar = tk.Scrollbar(main_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Build hotkey info
        info_text = tk.Text(scrollable_frame, wrap=tk.WORD, width=60, height=30, font=('Consolas', 10))
        info_text.pack(fill=tk.BOTH, expand=True)
        
        # Zone hotkeys
        info_text.insert(tk.END, "=== ZONE HOTKEYS ===\n\n", "header")
        for hk in self.zone_manager.hotkeys:
            info_text.insert(tk.END, f"{hk['keys']:<30} ", "key")
            info_text.insert(tk.END, f"-> Monitor {hk['monitor']}, Zone {hk['zone']}\n", "normal")
        
        # Special hotkeys
        info_text.insert(tk.END, "\n=== SPECIAL HOTKEYS ===\n\n", "header")
        
        special_hotkeys = [
            (self.zone_manager.overlay_config['hotkey'], "Show/Hide Zones"),
            (self.zone_manager.restore_hotkey, "Restore Window"),
            (self.zone_manager.reload_config_hotkey, "Reload Configuration"),
            (self.zone_manager.config.get('cycle_next_hotkey', 'ctrl+alt+]'), "Cycle Next Zone"),
            (self.zone_manager.config.get('cycle_prev_hotkey', 'ctrl+alt+['), "Cycle Previous Zone"),
        ]
        
        for hotkey, description in special_hotkeys:
            info_text.insert(tk.END, f"{hotkey:<30} ", "key")
            info_text.insert(tk.END, f"-> {description}\n", "normal")
        
        # Monitor info
        info_text.insert(tk.END, "\n=== MONITORS ===\n\n", "header")
        for mon in self.zone_manager.detected_monitors:
            primary = " (PRIMARY)" if mon['is_primary'] else ""
            info_text.insert(tk.END, f"Monitor {mon['id']}: ", "key")
            info_text.insert(tk.END, f"{mon['width']}x{mon['height']}{primary}\n", "normal")
        
        # Configure tags for styling
        info_text.tag_config("header", foreground="blue", font=('Consolas', 11, 'bold'))
        info_text.tag_config("key", foreground="darkgreen", font=('Consolas', 10, 'bold'))
        info_text.tag_config("normal", foreground="black")
        
        # Make text read-only
        info_text.config(state=tk.DISABLED)
        
        # Pack canvas and scrollbar
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Close button
        close_button = tk.Button(root, text="Close", command=root.destroy, width=15)
        close_button.pack(pady=5)
        
        # Center window on screen
        root.update_idletasks()
        width = root.winfo_width()
        height = root.winfo_height()
        x = (root.winfo_screenwidth() // 2) - (width // 2)
        y = (root.winfo_screenheight() // 2) - (height // 2)
        root.geometry(f'{width}x{height}+{x}+{y}')
        
        # Bring window to front
        root.lift()
        root.attributes('-topmost', True)
        root.after_idle(root.attributes, '-topmost', False)
        
        root.mainloop()
        

class DragZoneListener:
    def __init__(self, zone_manager, overlay):
        self.zone_manager = zone_manager
        self.overlay = overlay
        self.is_dragging = False
        self.drag_thread = None
        self.running = False
        self.drag_key = zone_manager.config.get('drag_show_zones_key', 'shift')
        self.overlay_shown = False
        self.overlay_toggled = False   # <-- RMB toggle state
        self.last_scroll_time = 0
        self.scroll_cooldown = 0.3
        self.dragged_hwnd = None
        self.current_zone = None
        self.dragging_active = False


    def start(self):
        """Start monitoring for window dragging"""
        self.running = True
        self.drag_thread = threading.Thread(target=self._monitor_drag, daemon=True)
        self.drag_thread.start()

        # Mouse listeners: scroll + RIGHT-CLICK toggle
        self.mouse_listener = mouse.Listener(
            on_scroll=self._on_scroll,
            on_click=self._on_click
        )
        self.mouse_listener.start()

        print("Drag zone listener started (with scroll support)")

    def stop(self):
        """Stop monitoring"""
        self.running = False
        if hasattr(self, 'mouse_listener'):
            self.mouse_listener.stop()

    # --------------- input helpers ----------------
    def _is_left_mouse_down(self):
        return win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000 != 0

    def _is_right_mouse_down(self):
        return win32api.GetAsyncKeyState(win32con.VK_RBUTTON) & 0x8000 != 0

    def _is_hotkey_pressed(self):
        # keep SHIFT (or ctrl/alt if you set it in YAML) as "hold to show"
        if self.drag_key == 'shift':
            return win32api.GetAsyncKeyState(win32con.VK_SHIFT) & 0x8000 != 0
        elif self.drag_key == 'ctrl':
            return win32api.GetAsyncKeyState(win32con.VK_CONTROL) & 0x8000 != 0
        elif self.drag_key == 'alt':
            return win32api.GetAsyncKeyState(win32con.VK_MENU) & 0x8000 != 0
        return False

    # --------------- mouse callbacks ----------------
    def _on_click(self, x, y, button, pressed):
        # Right-click toggles overlay, but only if currently dragging with LMB
        if button is mouse.Button.right and pressed:
            if self._is_left_mouse_down():
                # toggle
                self.overlay_toggled = not self.overlay_toggled
                if self.overlay_toggled:
                    # turn on
                    if not self.overlay_shown:
                        self.overlay_shown = True
                        self.dragged_hwnd = get_hwnd_under_cursor()
                        self.overlay.show()
                        self.overlay.redraw()
                        # one-time debug info on activation
                        mon_id = self._monitor_id_at(x, y)
                        initial = self._zone_at_point(x, y, ignore_names={'full'})
                        print(f"[DRAG START] monitor={mon_id}, mouse=({x},{y}), zone={initial[1] if initial else 'None'}")
                else:
                    # turn off
                    if self.overlay_shown:
                        self.overlay.hide()
                        self.overlay.set_highlight(None, None)
                        self.overlay_shown = False
                        self.current_zone = None

    def _on_scroll(self, x, y, dx, dy):
        # Only process scroll during an active LMB drag
        if not self._is_left_mouse_down():
            return
        cur = time.time()
        if cur - self.last_scroll_time < self.scroll_cooldown:
            return
        self.last_scroll_time = cur

        if 'layouts' not in self.zone_manager.config:
            return
        layouts = list(self.zone_manager.config['layouts'].keys())
        if len(layouts) <= 1:
            return

        try:
            current_idx = layouts.index(self.zone_manager.active_layout)
        except ValueError:
            current_idx = 0

        next_idx = (current_idx + 1) % len(layouts) if dy > 0 else (current_idx - 1) % len(layouts)
        next_layout = layouts[next_idx]
        print(f"Scroll: Switching to layout {next_layout}")
        self.zone_manager.switch_layout(next_layout)

        if self.overlay_shown:
            self.current_zone = None
            self.overlay.set_highlight(None, None)
            self.overlay.redraw()

    # --------------- drag loop ----------------
    def _monitor_drag(self):
        left_was_down = False
        while self.running:
            left_down = self._is_left_mouse_down()
            modifier = self._is_hotkey_pressed() or self._is_right_mouse_down()  # keep whatever you use

            # DRAG START cases
            # A) Hold modifier and press LMB -> show overlay and begin drag
            if left_down and modifier and not self.overlay_shown:
                self.overlay_shown = True
                self.dragged_hwnd = get_hwnd_under_cursor()
                self.overlay.show()
                self.overlay.redraw()
                self.dragging_active = True

            # B) Overlay already visible (e.g., RMB toggle) and LMB goes down -> begin drag & capture hwnd
            if left_down and self.overlay_shown and not self.dragging_active:
                self.dragging_active = True
                if not self.dragged_hwnd:
                    self.dragged_hwnd = get_hwnd_under_cursor()

            # While overlay visible, track hover/highlight
            if self.overlay_shown:
                x, y = get_cursor_pos()
                hovered = self._zone_at_point(x, y, ignore_names={'full'})
                if hovered != self.current_zone:
                    self.current_zone = hovered
                    if hovered:
                        self.overlay.set_highlight(hovered[0], hovered[1])
                    else:
                        self.overlay.set_highlight(None, None)

            # If the hotkey is released during drag, just hide overlay visuals,
            # but keep the drag session alive so we can still snap on LMB up.
            if left_down and not modifier and self.overlay_shown:
                self.overlay.hide()
                self.overlay.set_highlight(None, None)
                self.overlay_shown = False
                # keep: self.dragging_active, self.dragged_hwnd

            # LMB RELEASE -> decide & snap if we were dragging
            if left_was_down and not left_down:
                if self.dragging_active:
                    self._finish_drag(do_snap=True)
                else:
                    # not in zone drag mode, just ensure clean state
                    self._finish_drag(do_snap=False)

            left_was_down = left_down
            time.sleep(0.01)


    # --------------- picking helpers ----------------
    def _zone_at_point(self, x, y, ignore_names=None, margin=0):
        if ignore_names is None:
            ignore_names = set()
        mon_id = self._monitor_id_at(x, y)
        if mon_id is None:
            return None
        zones = self.zone_manager.monitors.get(mon_id, {})
        for name, z in zones.items():
            if name in ignore_names:
                continue
            L = z['x'] + margin
            T = z['y'] + margin
            R = z['x'] + z['width']  - margin
            B = z['y'] + z['height'] - margin
            if L <= x <= R and T <= y <= B:
                return (mon_id, name)
        return None

    def _monitor_id_at(self, x, y):
        for mon in self.zone_manager.detected_monitors:
            L, T = mon['x'], mon['y']
            R, B = L + mon['width'], T + mon['height']
            if L <= x < R and T <= y < B:
                return mon['id']
        return None
    
    def _finish_drag(self, do_snap=True):
        try:
            # figure target zone: prefer the live highlight, else compute at release
            target = self.current_zone
            if not target:
                x, y = get_cursor_pos()
                target = self._zone_at_point(x, y, ignore_names={'full'})

            if do_snap and self.dragged_hwnd and target:
                mon_id, zname = target
                zones = self.zone_manager.monitors.get(mon_id, {})
                if zname in zones:
                    snap_hwnd_to_zone(self.dragged_hwnd, zones[zname])
        finally:
            # always cleanup
            if self.overlay_shown:
                self.overlay.hide()
            self.overlay.set_highlight(None, None)
            self.overlay_shown = False
            self.current_zone = None
            self.dragged_hwnd = None
            self.dragging_active = False
            try:
                win32api.ReleaseCapture()
            except:
                pass

        

def main():
    # Configuration file path
    config_path = 'zones.yaml'
    try:
        # Initialize components
        zone_manager = ZoneManager(config_path)

        # Create Win32 overlay first and share it
        overlay = Win32OverlayManager(zone_manager, overlay_alpha=170)
        overlay.start()

        # Listeners get the Win32 overlay
        hotkey_listener = HotkeyListener(zone_manager, overlay)
        hotkey_listener.start()

        # Print registered hotkeys
        print("\nZone Manager started!")
        print("Registered hotkeys:")
        for hk in zone_manager.hotkeys:
            print(f"  {hk['keys']} -> Monitor {hk['monitor']}, Zone {hk['zone']}")
        print(f"  {zone_manager.overlay_config['hotkey']} -> Show/Hide Zones")
        print(f"  {zone_manager.restore_hotkey} -> Restore Window")
        print(f"  {zone_manager.reload_config_hotkey} -> Reload Config")
        print(f"  {zone_manager.config.get('cycle_next_hotkey', 'ctrl+alt+]')} -> Cycle Next Zone")
        print(f"  {zone_manager.config.get('cycle_prev_hotkey', 'ctrl+alt[')} -> Cycle Previous Zone")
        print()

        # Start drag listener
        drag_listener = DragZoneListener(zone_manager, overlay)
        drag_listener.start()

        # Tray app
        tray_app = TrayApp(zone_manager, hotkey_listener, config_path, drag_listener)
        icon = tray_app.setup_tray_icon()
        hotkey_listener.tray_icon = icon
        tray_app.icon = icon

        # Run tray icon (this blocks until quit)
        icon.run()

    except FileNotFoundError:
        print(f"Error: Configuration file '{config_path}' not found!")
        print("Please create a zones.yaml file with your zone definitions.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
