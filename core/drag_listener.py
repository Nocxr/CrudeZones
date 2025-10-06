# core/drag_listener.py (Refactored - no hardcoded values)
import threading
import time
import win32gui
import win32con
from pynput import mouse
from typing import Optional, Tuple

from .overlay_win32 import (
    get_hwnd_under_cursor,
    get_cursor_pos,
    snap_hwnd_outer_to_zone_with_workarea,
)
from .input_handler import InputHandler
from .zone_numbering import ZoneNumbering


class DragZoneListener:
    """Handles drag-to-snap behavior with configurable inputs"""
    
    def __init__(self, zone_manager, overlay, config_manager):
        self.zone_manager = zone_manager
        self.overlay = overlay
        self.config = config_manager
        
        # Input handling (no hardcoded keys)
        self.input = InputHandler(config_manager)
        
        # Zone numbering system
        self.numbering = ZoneNumbering(zone_manager)
        
        # Thread control
        self.running = False
        self.drag_thread = None
        self.mouse_listener = None
        
        # Timing/cooldown (from config)
        drag_cfg = self.config.get_drag_config()
        self.scroll_cooldown = drag_cfg['scroll_cooldown']
        self.number_snap_cooldown = drag_cfg['number_snap_cooldown']
        self.hover_margin = drag_cfg['hover_margin']
        self.ignore_fullscreen = drag_cfg['ignore_fullscreen']
        
        self.last_scroll_time = 0.0
        self.last_number_snap_time = 0.0
        
        # State tracking
        self.overlay_shown = False
        self.overlay_toggled = False
        self.dragged_hwnd = None
        self.current_zone: Optional[Tuple[int, str]] = None
        self.number_snap_occurred = False
    
    def start(self) -> None:
        """Start the drag listener"""
        self.running = True
        
        # Start monitoring thread
        self.drag_thread = threading.Thread(target=self._monitor_drag, daemon=True)
        self.drag_thread.start()
        
        # Start mouse listener for scroll and right-click
        drag_cfg = self.config.get_drag_config()
        if drag_cfg['scroll_enabled']:
            self.mouse_listener = mouse.Listener(
                on_scroll=self._on_scroll,
                on_click=self._on_click
            )
            self.mouse_listener.start()
            print("Drag zone listener started (with scroll support)")
        else:
            print("Drag zone listener started (scroll disabled)")
    
    def stop(self) -> None:
        """Stop the drag listener"""
        self.running = False
        if self.mouse_listener:
            self.mouse_listener.stop()
    
    def _assign_zone_numbers(self) -> None:
        """Refresh zone numbering and update overlay"""
        self.numbering.assign_numbers_and_labels()
        
        # Update overlay with new mappings
        if hasattr(self.overlay, 'zone_numbers'):
            self.overlay.zone_numbers = self.numbering.zone_numbers
        if hasattr(self.overlay, 'zone_key_labels'):
            self.overlay.zone_key_labels = self.numbering.zone_labels
        
        # Debug output
        for (mon_id, zone_name), label in self.numbering.zone_labels.items():
            num = self.numbering.get_number(mon_id, zone_name)
            print(f"[ZONE] {label} -> Monitor {mon_id}, Zone {zone_name} (#{num})")
    
    # ===== Mouse event handlers =====
    
    def _on_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        """Handle scroll wheel for layout switching"""
        # Only when overlay visible and dragging
        if not self.input.is_mouse_button_down('left') or not self.overlay_shown:
            return
        
        # Cooldown check
        now = time.time()
        if now - self.last_scroll_time < self.scroll_cooldown:
            return
        self.last_scroll_time = now
        
        # Need multiple layouts to switch
        if len(self.zone_manager.layouts) <= 1:
            return
        
        mon_id = self._get_monitor_at_point(x, y)
        if mon_id is None:
            return
        
        # Cycle layouts
        layouts = list(self.zone_manager.layouts.keys())
        current_layout = self.zone_manager.per_monitor_layouts.get(
            mon_id, self.zone_manager.active_layout
        )
        
        try:
            idx = layouts.index(current_layout)
        except ValueError:
            idx = 0
        
        next_idx = (idx + 1) % len(layouts) if dy > 0 else (idx - 1) % len(layouts)
        next_layout = layouts[next_idx]
        
        print(f"Scroll: Switching Monitor {mon_id} to layout {next_layout}")
        self.zone_manager.switch_layout_for_monitor(mon_id, next_layout)
        
        # Refresh
        self._assign_zone_numbers()
        if self.overlay_shown:
            self.current_zone = None
            self.overlay.set_highlight(None, None)
            self.overlay.redraw()
    
    def _on_click(self, x: int, y: int, button, pressed: bool) -> None:
        """Handle right-click to toggle overlay during drag"""
        if button != mouse.Button.right or not pressed:
            return
        
        # Only respond during active drag
        if not self.input.is_mouse_button_down('left'):
            return
        
        if self.overlay_shown:
            # Toggle OFF
            self.overlay.hide()
            self.overlay.set_highlight(None, None)
            self.overlay_shown = False
            self.overlay_toggled = False
            self.current_zone = None
            self.dragged_hwnd = None
            print("[OVERLAY] Toggled OFF")
        else:
            # Toggle ON
            self.overlay_toggled = True
            self._assign_zone_numbers()
            self.overlay.show()
            self.overlay.redraw()
            self.overlay_shown = True
            
            if self.input.is_mouse_button_down('left'):
                self.dragged_hwnd = self._capture_drag_target()
            
            print("[OVERLAY] Toggled ON")
    
    # ===== Drag detection =====
    
    def _capture_drag_target(self):
        """Get the window handle being dragged"""
        x, y = get_cursor_pos()
        hwnd = get_hwnd_under_cursor()
        
        # Skip overlay windows
        overlay_hwnds = {w.hwnd for w in self.overlay.windows} if hasattr(self.overlay, 'windows') else set()
        
        if hwnd in overlay_hwnds:
            # Temporarily hide overlays to get underlying window
            try:
                for w in self.overlay.windows:
                    win32gui.ShowWindow(w.hwnd, win32con.SW_HIDE)
                hwnd = win32gui.WindowFromPoint((x, y))
            finally:
                for w in self.overlay.windows:
                    win32gui.ShowWindow(w.hwnd, win32con.SW_SHOWNA)
        
        # Get top-level window
        try:
            GA_ROOT = 2
            hwnd = win32gui.GetAncestor(hwnd, GA_ROOT)
        except Exception:
            pass
        
        return hwnd if self._is_valid_drag_target(hwnd) else None
    
    def _is_valid_drag_target(self, hwnd) -> bool:
        """Check if window is valid for snapping"""
        if not hwnd or hwnd == 0:
            return False
        
        try:
            class_name = win32gui.GetClassName(hwnd)
            window_text = win32gui.GetWindowText(hwnd)
            
            # Invalid classes (configurable in future version)
            invalid_classes = [
                "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
                "Windows.UI.Core.CoreWindow", "ApplicationFrameWindow",
                "Windows.UI.Input.InputSite.WindowClass", "SysListView32",
                "ToolbarWindow32", "ReBarWindow32", "MSTaskSwWClass",
                "TaskListThumbnailWnd", "Button",
            ]
            
            if class_name in invalid_classes:
                return False
            if hwnd == win32gui.GetDesktopWindow():
                return False
            if not win32gui.IsWindowVisible(hwnd):
                return False
            
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            
            if not (style & win32con.WS_CAPTION):
                return False
            if ex_style & win32con.WS_EX_TOOLWINDOW:
                return False
            if not window_text or len(window_text.strip()) == 0:
                return False
            if not (style & win32con.WS_SYSMENU):
                return False
            
            return True
        except Exception:
            return False
    
    def _is_window_being_dragged(self, hwnd) -> bool:
        """Check if window is actively being moved"""
        if not hwnd:
            return False
        
        try:
            # Check for mouse capture
            if win32gui.GetCapture() == hwnd:
                return True
            
            # Check for movement
            if not hasattr(self, '_last_positions'):
                self._last_positions = {}
            
            L, T, R, B = win32gui.GetWindowRect(hwnd)
            pos = (L, T)
            
            if hwnd in self._last_positions:
                if pos != self._last_positions[hwnd]:
                    self._last_positions[hwnd] = pos
                    return True
            
            self._last_positions[hwnd] = pos
            return False
        except Exception:
            return False
    
    # ===== Zone detection =====
    
    def _get_monitor_at_point(self, x: int, y: int) -> Optional[int]:
        """Get monitor ID at coordinates"""
        for mon in self.zone_manager.detected_monitors:
            L, T = mon["x"], mon["y"]
            R, B = L + mon["width"], T + mon["height"]
            if L <= x < R and T <= y < B:
                return mon["id"]
        return None
    
    def _get_zone_at_point(self, x: int, y: int) -> Optional[Tuple[int, str]]:
        """Get (monitor_id, zone_name) at coordinates"""
        mon_id = self._get_monitor_at_point(x, y)
        if mon_id is None:
            return None
        
        zones = self.zone_manager.monitors.get(mon_id, {})
        ignore_set = {"full"} if self.ignore_fullscreen else set()
        
        for zone_name, z in zones.items():
            if zone_name in ignore_set:
                continue
            
            L = z["x"] + self.hover_margin
            T = z["y"] + self.hover_margin
            R = z["x"] + z["width"] - self.hover_margin
            B = z["y"] + z["height"] - self.hover_margin
            
            if L <= x <= R and T <= y <= B:
                return (mon_id, zone_name)
        
        return None
    
    def _get_work_area(self, mon_id: int) -> Tuple[int, int, int, int]:
        """Get work area rect for monitor"""
        m = self.zone_manager.detected_monitors[mon_id]
        return (
            m["work_x"],
            m["work_y"],
            m["work_x"] + m["work_width"],
            m["work_y"] + m["work_height"],
        )
    
    # ===== Snap handling =====
    
    def _check_for_snap_input(self) -> Optional[Tuple[int, str]]:
        """
        Check all possible snap inputs (zone keys and number keys).
        Returns (monitor_id, zone_name) if snap should occur, else None.
        
        Two-stage hotkey system:
        Stage 1 (optional): Monitor selection key (`, 1, 2, etc.)
        Stage 2: Zone key (Q, W, etc.)
        
        Examples:
        - Hold ` then press Q = Monitor 0's zone with key "Q"
        - Hold 1 then press Q = Monitor 1's zone with key "Q"  
        - Press Q alone = Uses default_monitor_for_zone_keys behavior
        - Press 3 alone (not a monitor key) = Zone number 3
        """
        # Check if a monitor selection key (stage 1) is pressed
        pressed_monitor_id = self.input.get_pressed_monitor_key()
        
        # Get default behavior for when no monitor key is pressed
        default_behavior = self.config.get_default_monitor_behavior()
        
        # Determine fallback monitor if no stage-1 key pressed
        fallback_mon_id = None
        if default_behavior == 'context_aware':
            # Use mouse position during drag, or window position otherwise
            if self.dragged_hwnd:
                x, y = get_cursor_pos()
                fallback_mon_id = self._get_monitor_at_point(x, y)
            else:
                hwnd = self.zone_manager.get_active_window()
                if hwnd:
                    fallback_mon_id = self.zone_manager.get_monitor_for_window(hwnd)
        elif default_behavior == 'primary':
            # Find primary monitor
            for mon in self.zone_manager.detected_monitors:
                if mon.get('is_primary', False):
                    fallback_mon_id = mon['id']
                    break
        elif isinstance(default_behavior, int):
            # Specific monitor ID
            fallback_mon_id = default_behavior
        
        # Priority 1: Zone-specific hotkeys with two-stage logic
        for mon_id, zones in self.zone_manager.monitors.items():
            for zone_name, zone_data in zones.items():
                if isinstance(zone_data, dict) and 'key' in zone_data:
                    key_str = zone_data.get('key', '').strip()
                    if key_str:
                        is_pressed, label = self.input.is_zone_key_pressed(key_str)
                        if is_pressed:
                            # Zone key pressed - determine which monitor
                            target_mon_id = None
                            
                            if pressed_monitor_id is not None:
                                # Stage 1 key pressed - use that monitor
                                if pressed_monitor_id == mon_id:
                                    target_mon_id = mon_id
                                    print(f"[INPUT] Two-stage: Mon{mon_id} key + '{label}' -> {zone_name} (mon {mon_id})")
                            else:
                                # No stage 1 key - use fallback behavior
                                if mon_id == fallback_mon_id:
                                    target_mon_id = mon_id
                                    print(f"[INPUT] Zone key '{label}' -> {zone_name} (mon {mon_id}) [fallback]")
                            
                            if target_mon_id is not None:
                                return (target_mon_id, zone_name)
        
        # Priority 2: Number keys (1-9 fallback)
        # CRITICAL: Don't check numbers if a monitor selection key is held down
        # (user is in two-stage mode waiting to press zone key)
        if pressed_monitor_id is None:
            pressed_num = self.input.get_pressed_number()
            if pressed_num is not None:
                target = self.numbering.get_zone_by_number(pressed_num)
                if target:
                    mon_id, zone_name = target
                    print(f"[INPUT] Number {pressed_num} pressed -> {zone_name} (mon {mon_id})")
                    return target
        
        return None
        
    
    def _snap_window_to_zone(self, hwnd, mon_id: int, zone_name: str) -> None:
        """Execute the snap operation"""
        zones_map = self.zone_manager.monitors.get(mon_id, {})
        if zone_name not in zones_map:
            print(f"[SNAP] Zone {zone_name} not found on monitor {mon_id}")
            return
        
        # Check if re-snapping
        is_resnap = hwnd in self.zone_manager.state_tracker.snapped_windows
        
        # Unmark as dragging before snap
        self.zone_manager.state_tracker.unmark_as_dragging(hwnd)
        
        # Save state (force on re-snap to capture manual resize)
        self.zone_manager.state_tracker.save_state(hwnd, force=is_resnap)
        
        # Mark operation in progress to prevent auto-restore
        self.zone_manager.state_tracker.mark_operation_in_progress(hwnd)
        
        # End drag first, THEN snap (prevents Windows from restoring old position)
        wa = self._get_work_area(mon_id)
        zrect = zones_map[zone_name]
        self._end_drag_then_snap(hwnd, zrect, wa)
        
        # Mark as snapped
        self.zone_manager.state_tracker.mark_as_snapped(hwnd)
        
        print(f"[SNAP] Window snapped to {zone_name} on monitor {mon_id}")
        
        # Notify window (some apps honor this)
        try:
            WM_EXITSIZEMOVE = 0x0232
            win32gui.PostMessage(hwnd, WM_EXITSIZEMOVE, 0, 0)
        except Exception:
            pass
    
    def _end_drag_then_snap(self, hwnd, zone_rect: dict, work_area: Tuple[int, int, int, int]) -> None:
        """End the drag cleanly, then snap to zone"""
        try:
            # Release mouse button to end drag
            import win32api
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        except Exception:
            pass
        
        # Let Windows settle
        time.sleep(0.03)
        
        # Snap to zone
        snap_hwnd_outer_to_zone_with_workarea(hwnd, zone_rect, work_area)
        
        # Set cooldown
        self.number_snap_occurred = True
        self.last_number_snap_time = time.time()
    
    # ===== Main drag monitoring loop =====
    
    def _monitor_drag(self) -> None:
        """Main monitoring loop for drag operations"""
        left_was_down = False
        mod_was_down = False
        drag_active_hwnd = None
        drag_start_time = None
        
        while self.running:
            # Poll input state
            left_down = self.input.is_mouse_button_down('left')
            mod_down = self.input.is_drag_show_key_pressed()
            
            # === LMB PRESSED (new drag starts) ===
            if left_down and not left_was_down:
                # Cooldown after number snap
                if time.time() - self.last_number_snap_time < self.number_snap_cooldown:
                    print("[DRAG] Ignoring LMB - too soon after snap")
                    left_was_down = left_down
                    mod_was_down = mod_down
                    time.sleep(0.01)
                    continue
                
                # Clear snap flag on new drag
                self.number_snap_occurred = False
                
                # Capture target window
                potential = self._capture_drag_target()
                if potential:
                    drag_active_hwnd = potential
                    drag_start_time = time.time()
                    self.dragged_hwnd = drag_active_hwnd
                    
                    # If snapped, restore size for smooth dragging
                    if drag_active_hwnd in self.zone_manager.state_tracker.snapped_windows:
                        try:
                            rect = win32gui.GetWindowRect(drag_active_hwnd)
                            current_size = (rect[2] - rect[0], rect[3] - rect[1])
                            snapped_size = self.zone_manager.state_tracker.snapped_windows[drag_active_hwnd][2:4]
                            
                            # Update saved state if manually resized
                            if current_size != snapped_size:
                                self.zone_manager.state_tracker.save_state(drag_active_hwnd, force=True)
                                print("[DRAG] Updated saved state (window was resized)")
                        except Exception:
                            pass
                        
                        self.zone_manager.state_tracker.mark_as_dragging(drag_active_hwnd)
                        self.zone_manager.state_tracker.restore_size_only(drag_active_hwnd)
                        print(f"[DRAG] Started - restored size for window {drag_active_hwnd}")
                else:
                    drag_active_hwnd = None
                    self.dragged_hwnd = None
            
            # === MODIFIER PRESSED (show overlay) ===
            if mod_down and not mod_was_down and drag_active_hwnd and left_down and not self.overlay_shown:
                if self._is_window_being_dragged(drag_active_hwnd):
                    self._assign_zone_numbers()
                    self.overlay.show()
                    self.overlay.redraw()
                    self.overlay_shown = True
                    print("[OVERLAY] Shown via modifier key")
            
            # === OVERLAY ACTIVE - handle hover and snap inputs ===
            if self.overlay_shown:
                # Ensure we have the drag target
                if not self.dragged_hwnd and left_down:
                    self.dragged_hwnd = self._capture_drag_target()
                
                x, y = get_cursor_pos()
                
                # Update hover highlight
                hovered = self._get_zone_at_point(x, y)
                if hovered != self.current_zone:
                    self.current_zone = hovered
                    if hovered:
                        self.overlay.set_highlight(hovered[0], hovered[1])
                    else:
                        self.overlay.set_highlight(None, None)
                
                # === CRITICAL FIX: Check snap inputs EVERY frame, not just on hover change ===
                snap_target = self._check_for_snap_input()
                
                if snap_target is not None:
                    mon_id, zone_name = snap_target
                    
                    if not self.dragged_hwnd:
                        self.dragged_hwnd = self._capture_drag_target()
                    
                    if self.dragged_hwnd:
                        # Execute snap
                        self._snap_window_to_zone(self.dragged_hwnd, mon_id, zone_name)
                        
                        # Clean up overlay
                        try:
                            self.overlay.hide()
                            self.overlay.set_highlight(None, None)
                        except Exception:
                            pass
                        
                        self.overlay_shown = False
                        self.overlay_toggled = False
                        self.current_zone = None
                        self.dragged_hwnd = None
                        
                        # Debounce to prevent key repeat
                        time.sleep(0.2)
                        continue
            
            # === LMB RELEASED (end drag) ===
            if left_was_down and not left_down:
                if drag_active_hwnd:
                    self.zone_manager.state_tracker.unmark_as_dragging(drag_active_hwnd)
                
                drag_active_hwnd = None
                drag_start_time = None
                
                # If overlay shown and zone selected, snap on release
                if self.overlay_shown and self.current_zone and self.dragged_hwnd:
                    mon_id, zone_name = self.current_zone
                    zones_map = self.zone_manager.monitors.get(mon_id, {})
                    
                    if zone_name in zones_map:
                        is_resnap = self.dragged_hwnd in self.zone_manager.state_tracker.snapped_windows
                        self.zone_manager.state_tracker.save_state(self.dragged_hwnd, force=is_resnap)
                        
                        wa = self._get_work_area(mon_id)
                        snap_hwnd_outer_to_zone_with_workarea(self.dragged_hwnd, zones_map[zone_name], wa)
                        
                        self.zone_manager.state_tracker.mark_as_snapped(self.dragged_hwnd)
                        print(f"[SNAP] Released on zone {zone_name} (mon {mon_id})")
                
                # Hide overlay
                if self.overlay_shown:
                    self.overlay.hide()
                    self.overlay.set_highlight(None, None)
                    self.overlay_shown = False
                    self.overlay_toggled = False
                
                self.current_zone = None
                self.dragged_hwnd = None
            
            # Update state
            left_was_down = left_down
            mod_was_down = mod_down
            
            time.sleep(0.01)