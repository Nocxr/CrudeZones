import threading
import time
import win32gui
import win32con
import win32api
from pynput import mouse
from .overlay_win32 import (
    get_hwnd_under_cursor,
    get_cursor_pos,
    snap_hwnd_outer_to_zone_with_workarea,
)

class DragZoneListener:
    def __init__(self, zone_manager, overlay):
        self.zone_manager = zone_manager
        self.overlay = overlay
        self.running = False
        self.drag_thread = None
        self.drag_key = zone_manager.config.get('drag_show_zones_key', 'shift')
        self.scroll_cooldown = 0.30
        self.overlay_shown = False
        self.overlay_toggled = False
        self.last_scroll_time = 0.0
        self.dragged_hwnd = None
        self.current_zone = None

    def _is_left_mouse_down(self):
        return win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000 != 0

    def _is_right_mouse_down(self):
        return win32api.GetAsyncKeyState(win32con.VK_RBUTTON) & 0x8000 != 0

    def _is_hotkey_pressed(self):
        if self.drag_key == 'shift':
            return win32api.GetAsyncKeyState(win32con.VK_SHIFT) & 0x8000 != 0
        elif self.drag_key == 'ctrl':
            return win32api.GetAsyncKeyState(win32con.VK_CONTROL) & 0x8000 != 0
        elif self.drag_key == 'alt':
            return win32api.GetAsyncKeyState(win32con.VK_MENU) & 0x8000 != 0
        return False

    def _on_scroll(self, x, y, dx, dy):
        # Only allow scrolling when overlay is visible AND dragging
        if not self._is_left_mouse_down() or not self.overlay_shown:
            return

        now = time.time()
        if now - self.last_scroll_time < self.scroll_cooldown:
            return
        self.last_scroll_time = now

        # Check if layouts exist
        if not self.zone_manager.layouts or len(self.zone_manager.layouts) <= 1:
            return
        
        layouts = list(self.zone_manager.layouts.keys())

        mon_id = self._monitor_id_at(x, y)
        if mon_id is None:
            return
        
        current_layout = self.zone_manager.per_monitor_layouts.get(mon_id, self.zone_manager.active_layout)
        
        try:
            idx = layouts.index(current_layout)
        except ValueError:
            idx = 0

        next_idx = (idx + 1) % len(layouts) if dy > 0 else (idx - 1) % len(layouts)
        next_layout = layouts[next_idx]
        print(f"Scroll: Switching Monitor {mon_id} to layout {next_layout}")
        self.zone_manager.switch_layout_for_monitor(mon_id, next_layout)

        if self.overlay_shown:
            self.current_zone = None
            self.overlay.set_highlight(None, None)
            self.overlay.redraw()

    def _on_click(self, x, y, button, pressed):
        """Right-click toggles overlay on/off - but only during a drag"""
        try:
            from pynput import mouse
            if button == mouse.Button.right and pressed:
                # Only respond to right-click if we're currently dragging (LMB is down)
                if not self._is_left_mouse_down():
                    return
                
                # If overlay is currently shown, always toggle it off
                if self.overlay_shown:
                    self.overlay.hide()
                    self.overlay.set_highlight(None, None)
                    self.overlay_shown = False
                    self.overlay_toggled = False
                    self.current_zone = None
                    self.dragged_hwnd = None
                    print("[OVERLAY TOGGLE OFF]")
                else:
                    # Overlay not shown, turn it on and latch
                    self.overlay_toggled = True
                    self.overlay.show()
                    self.overlay.redraw()
                    self.overlay_shown = True
                    mon_id = self._monitor_id_at(x, y)
                    initial = self._zone_at_point(x, y, ignore_names={'full'}, margin=6)
                    print(f"[OVERLAY TOGGLE ON] monitor={mon_id}, mouse=({x},{y}), zone={initial[1] if initial else 'None'}")

                    if self._is_left_mouse_down():
                        self.dragged_hwnd = self._capture_drag_target()
        except Exception as e:
            print(f"[CLICK ERR] {e}")

    def _capture_drag_target(self):
        """Return the top-level HWND under the cursor"""
        x, y = get_cursor_pos()
        hwnd = get_hwnd_under_cursor()

        overlay_hwnds = set()
        try:
            overlay_hwnds = {w.hwnd for w in self.overlay.windows}
        except Exception:
            pass

        if hwnd in overlay_hwnds:
            try:
                for w in self.overlay.windows:
                    win32gui.ShowWindow(w.hwnd, win32con.SW_HIDE)
                hwnd = win32gui.WindowFromPoint((x, y))
            finally:
                for w in self.overlay.windows:
                    win32gui.ShowWindow(w.hwnd, win32con.SW_SHOWNA)

        try:
            GA_ROOT = 2
            hwnd = win32gui.GetAncestor(hwnd, GA_ROOT)
        except Exception:
            pass

        return hwnd

    def _is_valid_drag_target(self, hwnd):
        """Check if this is a valid window to drag"""
        if not hwnd or hwnd == 0:
            return False
        
        try:
            # Get window class and title
            class_name = win32gui.GetClassName(hwnd)
            window_text = win32gui.GetWindowText(hwnd)
            
            # Expanded list of invalid classes (desktop, taskbar, start menu, etc)
            invalid_classes = [
                'Progman', 'WorkerW', 'Shell_TrayWnd', 'Button',
                'Shell_SecondaryTrayWnd', 'Windows.UI.Core.CoreWindow',
                'ApplicationFrameWindow', 'Windows.UI.Input.InputSite.WindowClass',
                'SysListView32', 'ToolbarWindow32', 'ReBarWindow32',
                'MSTaskSwWClass', 'TaskListThumbnailWnd'
            ]
            
            if class_name in invalid_classes:
                return False
            
            # Desktop window specifically
            desktop_hwnd = win32gui.GetDesktopWindow()
            if hwnd == desktop_hwnd:
                return False
            
            # Must be visible
            if not win32gui.IsWindowVisible(hwnd):
                return False
            
            # Get window style
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            
            # Must have a title bar (WS_CAPTION)
            if not (style & win32con.WS_CAPTION):
                return False
            
            # Must NOT be a tool window (like tooltips, menus)
            if ex_style & win32con.WS_EX_TOOLWINDOW:
                return False
            
            # Must have a non-empty title (filters out many system windows)
            if not window_text or len(window_text.strip()) == 0:
                return False
            
            # Must have minimize/maximize/close buttons (typical app window)
            if not (style & win32con.WS_SYSMENU):
                return False
            
            return True
            
        except Exception as e:
            # If we can't inspect it, assume invalid
            return False

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
            R = z['x'] + z['width'] - margin
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
        
    def _work_area_for_monitor(self, mon_id):
        m = self.zone_manager.detected_monitors[mon_id]
        return (
            m['work_x'],
            m['work_y'],
            m['work_x'] + m['work_width'],
            m['work_y'] + m['work_height'],
        )

    def start(self):
        """Start background loop + mouse listener"""
        self.running = True
        self.drag_thread = threading.Thread(target=self._monitor_drag, daemon=True)
        self.drag_thread.start()

        self.mouse_listener = mouse.Listener(on_scroll=self._on_scroll, on_click=self._on_click)
        self.mouse_listener.start()
        print("Drag zone listener started (with scroll support)")

    def stop(self):
        self.running = False
        if hasattr(self, 'mouse_listener'):
            self.mouse_listener.stop()

    def _monitor_drag(self):
        """Main drag monitoring loop"""
        left_was_down = False
        shift_was_down = False
        drag_active_hwnd = None  # Track which window is being actively dragged
        drag_start_time = None
        drag_restored_size = False  # Track if we've already restored size during this drag

        while self.running:
            left_down = self._is_left_mouse_down()
            mod_down = self._is_hotkey_pressed()

            # When LMB is first pressed, check if we're starting a drag
            if left_down and not left_was_down:
                potential_hwnd = self._capture_drag_target()
                if potential_hwnd and self._is_valid_drag_target(potential_hwnd):
                    drag_active_hwnd = potential_hwnd
                    drag_start_time = time.time()
                    drag_restored_size = False
                    
                    # Check if this window is currently snapped
                    if drag_active_hwnd in self.zone_manager.state_tracker.snapped_windows:
                        # BEFORE restoring, check if window was manually resized while snapped
                        try:
                            rect = win32gui.GetWindowRect(drag_active_hwnd)
                            current_size = (rect[2] - rect[0], rect[3] - rect[1])
                            snapped_size = self.zone_manager.state_tracker.snapped_windows[drag_active_hwnd][2:4]
                            
                            # If resized, update the saved state to current size
                            if current_size != snapped_size:
                                self.zone_manager.state_tracker.save_state(drag_active_hwnd, force=True)
                                print(f"[DRAG START] Window was resized while snapped, updated saved state")
                        except Exception as e:
                            print(f"Error checking window size: {e}")
                        
                        # Mark as being dragged so auto-restore won't interfere
                        self.zone_manager.state_tracker.mark_as_dragging(drag_active_hwnd)
                        # Restore SIZE only (keep position under cursor)
                        self.zone_manager.state_tracker.restore_size_only(drag_active_hwnd)
                        drag_restored_size = True
                        print(f"[DRAG STARTED] Restored size for snapped window {drag_active_hwnd}")
                else:
                    drag_active_hwnd = None
                    drag_start_time = None

            # Shift was JUST pressed (not held before drag)
            # AND we have an active drag
            # AND overlay not already shown
            if (mod_down and not shift_was_down and 
                drag_active_hwnd and 
                left_down and 
                not self.overlay_shown):
                
                # Verify the window is actually moving
                if self._is_window_being_dragged(drag_active_hwnd):
                    self.overlay.show()
                    self.overlay.redraw()
                    self.overlay_shown = True
                    x, y = get_cursor_pos()
                    mon_id = self._monitor_id_at(x, y)
                    initial = self._zone_at_point(x, y, ignore_names={'full'}, margin=6)
                    print(f"[DRAG START] monitor={mon_id}, mouse=({x},{y}), zone={initial[1] if initial else 'None'}")
                    self.dragged_hwnd = drag_active_hwnd

            if self.overlay_shown and left_down and not left_was_down:
                self.dragged_hwnd = self._capture_drag_target()

            if self.overlay_shown:
                x, y = get_cursor_pos()
                hovered = self._zone_at_point(x, y, ignore_names={'full'}, margin=6)

                if hovered != self.current_zone:
                    if self.current_zone and hovered:
                        print(f"[HOVER] left {self.current_zone[1]} (mon {self.current_zone[0]}) -> entered {hovered[1]} (mon {hovered[0]})")
                    elif self.current_zone and not hovered:
                        print(f"[HOVER] left {self.current_zone[1]} (mon {self.current_zone[0]}) -> now in no zone")
                    elif not self.current_zone and hovered:
                        print(f"[HOVER] entered {hovered[1]} (mon {hovered[0]})")
                    self.current_zone = hovered
                    if hovered:
                        self.overlay.set_highlight(hovered[0], hovered[1])
                    else:
                        self.overlay.set_highlight(None, None)

            # LMB released
            if left_was_down and not left_down:
                # Unmark drag exemption
                if drag_active_hwnd:
                    self.zone_manager.state_tracker.unmark_as_dragging(drag_active_hwnd)
                
                drag_active_hwnd = None
                drag_start_time = None
                drag_restored_size = False
                
                if self.overlay_shown:
                    chosen = self.current_zone
                    if not chosen:
                        x, y = get_cursor_pos()
                        chosen = self._zone_at_point(x, y, ignore_names={'full'}, margin=6)
                        if chosen:
                            print(f"[RELEASE] mouse=({x},{y}) -> picked zone {chosen[1]} (mon {chosen[0]})")
                        else:
                            print(f"[RELEASE] mouse=({x},{y}) -> no zone")
                    else:
                        print(f"[RELEASE] using highlighted zone {chosen[1]} (mon {chosen[0]})")

                    if not self.dragged_hwnd:
                        self.dragged_hwnd = self._capture_drag_target()

                    if self.dragged_hwnd and self.current_zone:
                        mon_id, zname = self.current_zone
                        zones = self.zone_manager.monitors.get(mon_id, {})
                        if zname in zones:
                            # Check if this is a re-snap (window currently snapped to a zone)
                            is_resnap = self.dragged_hwnd in self.zone_manager.state_tracker.snapped_windows
                            
                            # Always save/update state before snapping
                            # Use force=True if re-snapping to capture any manual resize
                            self.zone_manager.state_tracker.save_state(self.dragged_hwnd, force=is_resnap)
                            
                            wa = self._work_area_for_monitor(mon_id)
                            snap_hwnd_outer_to_zone_with_workarea(self.dragged_hwnd, zones[zname], wa)
                            
                            self.zone_manager.state_tracker.mark_as_snapped(self.dragged_hwnd)
                            
                            print(f"[SNAP] hwnd={self.dragged_hwnd} -> {zname} (mon {mon_id})")

                    if not self.overlay_toggled:
                        self.overlay.hide()
                        self.overlay.set_highlight(None, None)
                        self.overlay_shown = False
                    else:
                        self.overlay.hide()
                        self.overlay.set_highlight(None, None)
                        self.overlay_shown = False
                        self.overlay_toggled = False

                self.current_zone = None
                self.dragged_hwnd = None

            left_was_down = left_down
            shift_was_down = mod_down
            time.sleep(0.01)
            
    def _is_window_being_dragged(self, hwnd):
        """Check if Windows is actively dragging this window"""
        if not hwnd:
            return False
        
        try:
            # Check if the window is being moved/sized
            # When dragging, the window enters a modal loop
            # We can detect this by checking if GetCapture returns the window
            captured = win32gui.GetCapture()
            if captured == hwnd:
                return True
            
            # Alternative: check if the window's position is changing
            # Store last known position and compare
            if not hasattr(self, '_last_positions'):
                self._last_positions = {}
            
            try:
                rect = win32gui.GetWindowRect(hwnd)
                current_pos = (rect[0], rect[1])
                
                if hwnd in self._last_positions:
                    last_pos = self._last_positions[hwnd]
                    if current_pos != last_pos:
                        self._last_positions[hwnd] = current_pos
                        return True
                
                self._last_positions[hwnd] = current_pos
            except:
                pass
            
            return False
        except:
            return False