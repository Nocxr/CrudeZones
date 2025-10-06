# hotkey_listener.py
from pynput import keyboard
from pynput.keyboard import Key, KeyCode

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
        
        self.numpad_vk_map = {
            96: 'kp_0', 97: 'kp_1', 98: 'kp_2', 99: 'kp_3', 100: 'kp_4',
            101: 'kp_5', 102: 'kp_6', 103: 'kp_7', 104: 'kp_8', 105: 'kp_9'
        }
        
        self.numpad_nav_map = {
            'insert': 'kp_0', 'end': 'kp_1', 'down': 'kp_2', 'page_down': 'kp_3',
            'left': 'kp_4', 12: 'kp_5', 'right': 'kp_6', 'home': 'kp_7',
            'up': 'kp_8', 'page_up': 'kp_9'
        }
        
    def start(self):
        """Start listening for hotkeys"""
        if self.running:
            return
        
        self.hotkey_actions = self._build_hotkey_actions()
        
        print(f"Registered {len(self.hotkey_actions)} hotkey combinations")
        
        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        )
        self.listener.start()
        self.running = True
        
        print("Hotkey listener started (with numpad support - works with NumLock ON or OFF)")
    
    def stop(self):
        """Stop listening for hotkeys"""
        if self.listener and self.running:
            self.listener.stop()
            self.running = False
            self.current_keys.clear()
            self.hotkeys_fired.clear()
            print("Hotkey listener stopped")
    
    def restart(self):
        """Restart the listener"""
        self.stop()
        self.start()
    
    def _normalize_hotkey_config(self, key_string):
        """Convert config hotkey string to internal format"""
        parts = [p.strip().lower() for p in key_string.split('+')]
        
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
            elif part in ['ctrl_l', 'ctrl_r', 'alt_l', 'alt_r', 'alt_gr', 'shift_l', 'shift_r', 'win_l', 'win_r']:
                normalized.append(part)
            else:
                normalized.append(part)
        
        modifier_keywords = ['ctrl', 'ctrl_l', 'ctrl_r', 'alt', 'alt_l', 'alt_r', 'alt_gr', 
                            'shift', 'shift_l', 'shift_r', 'win', 'win_l', 'win_r']
        modifiers = [k for k in normalized if k in modifier_keywords]
        keys = [k for k in normalized if k not in modifier_keywords]
        
        return '+'.join(sorted(modifiers) + keys)
    
    def _build_hotkey_actions(self):
        """Build a map of hotkey combinations to actions"""
        actions = {}
        
        for hk in self.zone_manager.hotkeys:
            normalized = self._normalize_hotkey_config(hk['keys'])
            actions[normalized] = {
                'type': 'zone',
                'monitor': hk['monitor'],
                'zone': hk['zone']
            }
        
        if self.overlay:
            normalized = self._normalize_hotkey_config(self.zone_manager.overlay_config['hotkey'])
            actions[normalized] = {'type': 'overlay'}
        
        normalized = self._normalize_hotkey_config(self.zone_manager.restore_hotkey)
        actions[normalized] = {'type': 'restore'}
        
        normalized = self._normalize_hotkey_config(self.zone_manager.reload_config_hotkey)
        actions[normalized] = {'type': 'reload'}
        
        normalized = self._normalize_hotkey_config(self.zone_manager.config.get('cycle_next_hotkey', 'ctrl+alt+]'))
        actions[normalized] = {'type': 'cycle', 'direction': 'next'}
        
        normalized = self._normalize_hotkey_config(self.zone_manager.config.get('cycle_prev_hotkey', 'ctrl+alt+['))
        actions[normalized] = {'type': 'cycle', 'direction': 'prev'}
        
        normalized = self._normalize_hotkey_config(self.zone_manager.config.get('cycle_all_next_hotkey', 'ctrl+alt+shift+]'))
        actions[normalized] = {'type': 'cycle_all', 'direction': 'next'}

        normalized = self._normalize_hotkey_config(self.zone_manager.config.get('cycle_all_prev_hotkey', 'ctrl+alt+shift+['))
        actions[normalized] = {'type': 'cycle_all', 'direction': 'prev'}
        
        for layout_hk in self.zone_manager.layout_hotkeys:
            normalized = self._normalize_hotkey_config(layout_hk['keys'])
            actions[normalized] = {
                'type': 'layout',
                'layout': layout_hk['layout']
            }
        
        return actions
    
    def _get_key_name(self, key):
        """Get normalized name for a key"""
        if hasattr(key, 'vk'):
            if key.vk in self.numpad_vk_map:
                return self.numpad_vk_map[key.vk]
            elif key.vk == 12:
                return self.numpad_nav_map[12]
            elif 65 <= key.vk <= 90:
                return chr(key.vk).lower()
            elif 48 <= key.vk <= 57:
                return chr(key.vk)
            else:
                vk_map = {
                    186: ';', 187: '=', 188: ',', 189: '-', 190: '.', 191: '/',
                    192: '`', 219: '[', 220: '\\', 221: ']', 222: "'",
                    112: 'f1', 113: 'f2', 114: 'f3', 115: 'f4', 116: 'f5', 117: 'f6',
                    118: 'f7', 119: 'f8', 120: 'f9', 121: 'f10', 122: 'f11', 123: 'f12',
                    33: 'page_up', 34: 'page_down', 35: 'end', 36: 'home',
                    37: 'left', 38: 'up', 39: 'right', 40: 'down',
                    45: 'insert', 46: 'delete',
                    32: 'space', 8: 'backspace', 9: 'tab', 13: 'enter', 27: 'esc',
                    20: 'caps_lock', 145: 'scroll_lock', 144: 'num_lock',
                    91: 'win', 92: 'win', 93: 'menu'
                }
                if key.vk in vk_map:
                    return vk_map[key.vk]
        
        if hasattr(key, 'name'):
            key_name_lower = key.name.lower()
            if key_name_lower in self.numpad_nav_map:
                return self.numpad_nav_map[key_name_lower]
        
        # Handle modifiers
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
        
        if hasattr(key, 'char') and key.char:
            return key.char.lower()
        
        if hasattr(key, 'name'):
            return key.name.lower()
        
        return None
    
    def _get_current_combo(self):
        """Get the current key combination as a normalized string"""
        modifiers = []
        non_modifiers = []
        
        for key in self.current_keys:
            key_name = self._get_key_name(key)
            if key_name:
                if key_name in ['ctrl', 'ctrl_l', 'ctrl_r', 'alt', 'alt_l', 'alt_r', 'alt_gr',
                            'shift', 'shift_l', 'shift_r', 'win', 'win_l', 'win_r']:
                    modifiers.append(key_name)
                else:
                    non_modifiers.append(key_name)
        
        all_keys = sorted(modifiers) + non_modifiers
        return '+'.join(all_keys) if all_keys else None
    
    def _check_hotkey_match(self, pressed_combo, registered_combo):
        """Check if a pressed combo matches a registered combo"""
        pressed_parts = pressed_combo.split('+')
        registered_parts = registered_combo.split('+')
        
        pressed_ctrl_specific = [p for p in pressed_parts if p in ['ctrl_l', 'ctrl_r']]
        pressed_alt_specific = [p for p in pressed_parts if p in ['alt_l', 'alt_r', 'alt_gr']]
        pressed_shift_specific = [p for p in pressed_parts if p in ['shift_l', 'shift_r']]
        pressed_win_specific = [p for p in pressed_parts if p in ['win_l', 'win_r']]
        
        pressed_ctrl = len(pressed_ctrl_specific) > 0 or 'ctrl' in pressed_parts
        pressed_alt = len(pressed_alt_specific) > 0 or 'alt' in pressed_parts
        pressed_shift = len(pressed_shift_specific) > 0 or 'shift' in pressed_parts
        pressed_win = len(pressed_win_specific) > 0 or 'win' in pressed_parts
        
        pressed_non_mod = [p for p in pressed_parts if p not in ['ctrl', 'ctrl_l', 'ctrl_r', 'alt', 'alt_l', 'alt_r', 'alt_gr', 'shift', 'shift_l', 'shift_r', 'win', 'win_l', 'win_r']]
        
        requires_ctrl = 'ctrl' in registered_parts or any(p in ['ctrl_l', 'ctrl_r'] for p in registered_parts)
        requires_alt = 'alt' in registered_parts or any(p in ['alt_l', 'alt_r', 'alt_gr'] for p in registered_parts)
        requires_shift = 'shift' in registered_parts or any(p in ['shift_l', 'shift_r'] for p in registered_parts)
        requires_win = 'win' in registered_parts or any(p in ['win_l', 'win_r'] for p in registered_parts)
        
        if pressed_ctrl != requires_ctrl or pressed_alt != requires_alt or pressed_shift != requires_shift or pressed_win != requires_win:
            return False
        
        for part in registered_parts:
            if part in ['ctrl_l', 'ctrl_r'] and part not in pressed_ctrl_specific:
                return False
            elif part in ['alt_l', 'alt_r', 'alt_gr'] and part not in pressed_alt_specific:
                return False
            elif part in ['shift_l', 'shift_r'] and part not in pressed_shift_specific:
                return False
            elif part in ['win_l', 'win_r'] and part not in pressed_win_specific:
                return False
        
        registered_non_mod = [p for p in registered_parts if p not in ['ctrl', 'ctrl_l', 'ctrl_r', 'alt', 'alt_l', 'alt_r', 'alt_gr', 'shift', 'shift_l', 'shift_r', 'win', 'win_l', 'win_r']]
        
        return set(pressed_non_mod) == set(registered_non_mod)

    def _on_press(self, key):
        """Handle key press events"""
        if key in self.current_keys:
            return
        
        self.current_keys.add(key)
        combo = self._get_current_combo()
        
        if combo:
            for registered_combo, action in self.hotkey_actions.items():
                if self._check_hotkey_match(combo, registered_combo):
                    if combo not in self.hotkeys_fired:
                        self.hotkeys_fired.add(combo)
                        self._execute_action(action, registered_combo)
                    break
    
    def _on_release(self, key):
        """Handle key release events"""
        self.current_keys.discard(key)
        
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
                self.zone_manager.move_window_to_zone(action['monitor'], action['zone'])
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
        """Toggle the zone overlay"""
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
                self.tray_icon.notify("Configuration reloaded", "Zone Manager")
        except Exception as e:
            print(f"Error reloading config: {e}\n")
            if self.tray_icon:
                self.tray_icon.notify(f"Error reloading config: {e}", "Zone Manager")