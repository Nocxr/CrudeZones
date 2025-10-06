# window_state_tracker.py
import win32gui
import win32con
import win32api
import threading
import time

class WindowStateTracker:
    """Track window states to restore original size and position"""
    def __init__(self):
        self.window_states = {}  # hwnd -> {'x', 'y', 'width', 'height', 'timestamp'}
        self.snapped_windows = {}  # hwnd -> last snapped position (x,y,w,h)
        self.monitoring = False
        self.monitor_thread = None
        self.drag_exempt_hwnds = set()  # Windows currently being dragged - DON'T auto-restore these
        self.operation_exempt_hwnds = set()  # Windows being moved by hotkey operations - DON'T auto-restore these
    
    def save_state(self, hwnd, force=False):
        """Save the current window state before snapping to zone
        
        Args:
            hwnd: Window handle
            force: If True, always save even if state exists. If False, only save if no state exists.
        """
        try:
            # Skip if state already exists and not forcing
            if not force and hwnd in self.window_states:
                return
                
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
    
    def mark_as_snapped(self, hwnd):
        """Mark a window as snapped, store its current position"""
        try:
            rect = win32gui.GetWindowRect(hwnd)
            self.snapped_windows[hwnd] = (rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1])
        except:
            pass
    
    def mark_as_dragging(self, hwnd):
        """Mark a window as being actively dragged - exempt from auto-restore"""
        if hwnd:
            self.drag_exempt_hwnds.add(hwnd)
    
    def unmark_as_dragging(self, hwnd):
        """Remove drag exemption"""
        self.drag_exempt_hwnds.discard(hwnd)
    
    def mark_operation_in_progress(self, hwnd):
        """Mark a window as being moved by a hotkey operation - exempt from auto-restore temporarily"""
        if hwnd:
            self.operation_exempt_hwnds.add(hwnd)
    
    def unmark_operation_in_progress(self, hwnd):
        """Remove operation exemption after a short delay"""
        if hwnd:
            # Use a thread to remove after delay (allows animation to complete)
            def delayed_unmark():
                time.sleep(2.0)  # Wait 2 seconds - enough time for user to release mouse after number snap
                self.operation_exempt_hwnds.discard(hwnd)
            threading.Thread(target=delayed_unmark, daemon=True).start()
    
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
            if hwnd in self.snapped_windows:
                del self.snapped_windows[hwnd]
            return True
            
        except Exception as e:
            print(f"Error restoring state: {e}")
            return False
    
    def restore_size_only(self, hwnd):
        """Restore window to its saved SIZE but keep current position (for drag-restore)"""
        if hwnd not in self.window_states:
            return False
        
        try:
            state = self.window_states[hwnd]
            
            # Get current position
            current_rect = win32gui.GetWindowRect(hwnd)
            current_x, current_y = current_rect[0], current_rect[1]
            
            # Check if window is maximized, restore it first
            placement = win32gui.GetWindowPlacement(hwnd)
            if placement[1] == win32con.SW_SHOWMAXIMIZED:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            
            # Restore ONLY the size, keep current position
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOP,
                current_x,
                current_y,
                state['width'],
                state['height'],
                win32con.SWP_SHOWWINDOW | win32con.SWP_NOMOVE  # Don't move, just resize
            )
            
            print(f"Restored window SIZE to: {state['width']}x{state['height']} (kept position)")
            
            # Clear from snapped list but KEEP the saved state for later full restore
            if hwnd in self.snapped_windows:
                del self.snapped_windows[hwnd]
            
            return True
            
        except Exception as e:
            print(f"Error restoring size: {e}")
            return False
    
    def start_monitoring(self):
        """Start monitoring for manual moves"""
        if self.monitoring:
            return
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        print("Window movement monitoring started")
    
    def _is_being_dragged(self, hwnd):
        """Check if a window is currently being dragged by the user"""
        try:
            # Check if left mouse button is down
            if win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000:
                # Check if this window has capture (being dragged)
                captured = win32gui.GetCapture()
                if captured == hwnd:
                    return True
                
                # Also check if the window is the foreground window and mouse is down
                if win32gui.GetForegroundWindow() == hwnd:
                    return True
            
            return False
        except:
            return False
    
    def _monitor_loop(self):
        """Check snapped windows for movement"""
        while self.monitoring:
            for hwnd in list(self.snapped_windows.keys()):
                try:
                    # Skip if window is in drag-exempt list
                    if hwnd in self.drag_exempt_hwnds:
                        continue
                    
                    # Skip if window is being moved by a hotkey operation
                    if hwnd in self.operation_exempt_hwnds:
                        continue
                    
                    if not win32gui.IsWindow(hwnd):
                        del self.snapped_windows[hwnd]
                        continue
                    
                    # Skip if actively being dragged
                    if self._is_being_dragged(hwnd):
                        continue
                    
                    rect = win32gui.GetWindowRect(hwnd)
                    current = (rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1])
                    snapped = self.snapped_windows[hwnd]
                    
                    # If moved significantly (more than 10 pixels)
                    if (abs(current[0] - snapped[0]) > 10 or 
                        abs(current[1] - snapped[1]) > 10 or
                        abs(current[2] - snapped[2]) > 10 or
                        abs(current[3] - snapped[3]) > 10):
                        
                        print(f"Window {hwnd} moved manually, auto-restoring...")
                        if self.restore_state(hwnd):
                            if hwnd in self.snapped_windows:
                                del self.snapped_windows[hwnd]
                
                except Exception:
                    pass
            
            time.sleep(0.1)
    
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