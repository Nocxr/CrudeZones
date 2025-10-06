# zone_manager.py
import yaml
import win32gui
import win32con
import os
import glob
from .monitor_detection import MonitorDetector
from .window_state_tracker import WindowStateTracker

class ZoneManager:
    def __init__(self, config_dir='config'):
        self.config_dir = config_dir
        self.state_tracker = WindowStateTracker()
        self.load_config()
    
    def load_config(self):
        """Load configuration from YAML files"""
        # Load hotkeys
        hotkeys_path = os.path.join(self.config_dir, 'hotkeys.yaml')
        with open(hotkeys_path, 'r') as f:
            hotkeys_config = yaml.safe_load(f)
        
        # Load all layouts from layouts folder
        layouts_dir = os.path.join(self.config_dir, 'layouts')
        self.layouts = {}
        
        for layout_file in glob.glob(os.path.join(layouts_dir, '*.yaml')):
            with open(layout_file, 'r') as f:
                layout_data = yaml.safe_load(f)
                layout_name = layout_data.get('name', os.path.splitext(os.path.basename(layout_file))[0])
                self.layouts[layout_name] = layout_data
        
        print(f"\nLoaded {len(self.layouts)} layouts: {', '.join(self.layouts.keys())}")
        
        # Detect monitors
        self.detected_monitors = MonitorDetector.get_monitors()
        
        print(f"\nDetected {len(self.detected_monitors)} monitor(s):")
        for mon in self.detected_monitors:
            primary = " (PRIMARY)" if mon['is_primary'] else ""
            print(f"  Monitor {mon['id']}: {mon['width']}x{mon['height']} at ({mon['x']}, {mon['y']}){primary}")
            print(f"    Work area: {mon['work_width']}x{mon['work_height']} at ({mon['work_x']}, {mon['work_y']})")
        
        # Set default layout (use first available or 'default')
        self.active_layout = 'default' if 'default' in self.layouts else list(self.layouts.keys())[0]
        self.per_monitor_layouts = {}
        print(f"\nDefault layout: {self.active_layout}")
        
        # Store hotkey config
        self.config = hotkeys_config
        self.hotkeys = hotkeys_config.get('zone_hotkeys', [])
        self.layout_hotkeys = hotkeys_config.get('layout_switches', [])
        self.overlay_config = self._load_overlay_config()
        self.restore_hotkey = hotkeys_config.get('restore_hotkey', 'ctrl+alt+r')
        self.reload_config_hotkey = hotkeys_config.get('reload_config_hotkey', 'ctrl+alt+shift+r')
        
        # Load zone data
        self.monitors = self._load_monitors()
    
    def _load_overlay_config(self):
        """Load overlay configuration with defaults"""
        # Try to get from current layout, fallback to defaults
        current_layout = self.layouts.get(self.active_layout, {})
        overlay = current_layout.get('overlay', {})
        
        return {
            'hotkey': self.config.get('overlay_hotkey', 'ctrl+alt+z'),
            'color': overlay.get('color', 'cyan'),
            'opacity': overlay.get('opacity', 0.3),
            'auto_hide_seconds': overlay.get('auto_hide_seconds', 3)
        }
    
    def _load_monitors(self):
        """Parse monitor zones from layouts and calculate actual pixel values"""
        monitors = {}
        
        for detected_mon in self.detected_monitors:
            mon_id = detected_mon['id']
            
            # Get layout for this specific monitor
            layout_name = self.per_monitor_layouts.get(mon_id, self.active_layout)
            
            if layout_name not in self.layouts:
                print(f"Warning: Layout '{layout_name}' not found. Using default.")
                layout_name = self.active_layout
            
            layout_data = self.layouts[layout_name]
            monitor_configs = layout_data.get('monitors', [])
            
            # Find config for this monitor ID
            monitor_config = None
            for mc in monitor_configs:
                if mc['id'] == mon_id:
                    monitor_config = mc
                    break
            
            if not monitor_config:
                print(f"Warning: Monitor {mon_id} not defined in layout '{layout_name}'. Skipping.")
                continue
            
            monitors[mon_id] = {}
            
            for zone in monitor_config['zones']:
                respect_taskbar = zone.get('respect_taskbar', True)
                
                # Use work area if respecting taskbar
                if respect_taskbar:
                    base_x = detected_mon['work_x']
                    base_y = detected_mon['work_y']
                    base_width = detected_mon['work_width']
                    base_height = detected_mon['work_height']
                else:
                    base_x = detected_mon['x']
                    base_y = detected_mon['y']
                    base_width = detected_mon['width']
                    base_height = detected_mon['height']
                
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
                
                print(f"  Zone '{zone['name']}' on Monitor {mon_id} ({layout_name}): "
                    f"{zone_width}x{zone_height} at ({zone_x}, {zone_y})")
        
        return monitors
    
    def switch_layout_for_monitor(self, monitor_id, layout_name):
        """Switch layout for a specific monitor"""
        if layout_name not in self.layouts:
            print(f"Layout '{layout_name}' not found")
            return
        
        self.per_monitor_layouts[monitor_id] = layout_name
        self.monitors = self._load_monitors()
        print(f"Switched Monitor {monitor_id} to layout: {layout_name}")
    
    def switch_layout(self, layout_name):
        """Switch to a different layout (global fallback)"""
        if layout_name not in self.layouts:
            print(f"Layout '{layout_name}' not found")
            return
        
        self.active_layout = layout_name
        self.monitors = self._load_monitors()
        print(f"Switched default layout to: {layout_name}")
    
    def get_active_window(self):
        """Get the currently active window handle"""
        return win32gui.GetForegroundWindow()
    
    def move_window_to_zone(self, monitor_id, zone_name):
        """Move active window to specified zone"""
        hwnd = self.get_active_window()
        
        if not hwnd:
            print("No active window")
            return
        
        if monitor_id not in self.monitors:
            print(f"Monitor {monitor_id} not found")
            return
        
        if zone_name not in self.monitors[monitor_id]:
            print(f"Zone {zone_name} not found on monitor {monitor_id}")
            return
        
        # Mark operation in progress to prevent auto-restore during snap
        self.state_tracker.mark_operation_in_progress(hwnd)
        
        # Check if window is currently snapped
        is_currently_snapped = hwnd in self.state_tracker.snapped_windows
        
        # If NOT currently snapped, save state for first time
        # If currently snapped, update the saved state to current size/position
        if not is_currently_snapped:
            # First snap - save current state
            self.state_tracker.save_state(hwnd, force=False)
        else:
            # Re-snapping - get current rect and update saved state
            try:
                rect = win32gui.GetWindowRect(hwnd)
                current_size = (rect[2] - rect[0], rect[3] - rect[1])
                snapped_size = self.state_tracker.snapped_windows[hwnd][2:4]
                
                # Only update saved state if window was manually resized
                # (current size differs from snapped size)
                if current_size != snapped_size:
                    self.state_tracker.save_state(hwnd, force=True)
                    print(f"Updated saved state (window was resized before re-snap)")
            except Exception as e:
                print(f"Error checking window size: {e}")
        
        zone = self.monitors[monitor_id][zone_name]
        
        # Restore if maximized
        placement = win32gui.GetWindowPlacement(hwnd)
        if placement[1] == win32con.SW_SHOWMAXIMIZED:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        
        # Move and resize
        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_TOP,
            zone['x'],
            zone['y'],
            zone['width'],
            zone['height'],
            win32con.SWP_SHOWWINDOW
        )
        
        # Mark as snapped
        self.state_tracker.mark_as_snapped(hwnd)
        
        print(f"Moved window to {zone_name} on monitor {monitor_id}")
        self.state_tracker.cleanup_old_states()
        
        # Unmark operation (with delay to allow animation to complete)
        self.state_tracker.unmark_operation_in_progress(hwnd)
    
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
            
            for monitor in self.detected_monitors:
                if (monitor['x'] <= window_center_x < monitor['x'] + monitor['width'] and
                    monitor['y'] <= window_center_y < monitor['y'] + monitor['height']):
                    return monitor['id']
            
            return 0
        except:
            return 0

    def cycle_zone(self, direction='next'):
        """Cycle the active window through zones on its current monitor"""
        hwnd = self.get_active_window()
        
        if not hwnd:
            print("No active window")
            return
        
        monitor_id = self.get_monitor_for_window(hwnd)
        
        if monitor_id not in self.monitors:
            print(f"Monitor {monitor_id} not found")
            return
        
        zones = list(self.monitors[monitor_id].keys())
        
        if not zones:
            print(f"No zones defined for monitor {monitor_id}")
            return
        
        # Find current zone
        current_zone_idx = 0
        try:
            rect = win32gui.GetWindowRect(hwnd)
            current_x, current_y = rect[0], rect[1]
            current_width = rect[2] - rect[0]
            current_height = rect[3] - rect[1]
            
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
        
        # Calculate next zone (wrapping around)
        if direction == 'next':
            next_zone_idx = (current_zone_idx + 1) % len(zones)
        else:  # prev
            next_zone_idx = (current_zone_idx - 1) % len(zones)
        
        next_zone_name = zones[next_zone_idx]
        
        print(f"Cycling {direction}: zone {current_zone_idx} -> {next_zone_idx} ({next_zone_name})")
        self.move_window_to_zone(monitor_id, next_zone_name)
        
    def cycle_zone_all_monitors(self, direction='next'):
        """Cycle through all zones across all monitors"""
        hwnd = self.get_active_window()
        
        if not hwnd:
            print("No active window")
            return
        
        all_zones = []
        for mon_id in sorted(self.monitors.keys()):
            for zone_name in self.monitors[mon_id].keys():
                all_zones.append((mon_id, zone_name))
        
        if not all_zones:
            print("No zones defined")
            return
        
        current_idx = 0
        try:
            rect = win32gui.GetWindowRect(hwnd)
            current_x, current_y = rect[0], rect[1]
            current_width = rect[2] - rect[0]
            current_height = rect[3] - rect[1]
            
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
        
        if direction == 'next':
            next_idx = (current_idx + 1) % len(all_zones)
        else:
            next_idx = (current_idx - 1) % len(all_zones)
        
        next_mon, next_zone = all_zones[next_idx]
        print(f"Cycling {direction} to Monitor {next_mon}, Zone {next_zone}")
        self.move_window_to_zone(next_mon, next_zone)