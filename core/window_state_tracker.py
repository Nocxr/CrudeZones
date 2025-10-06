# window_state_tracker.py
import win32gui
import win32con
import threading
import time

class WindowStateTracker:
    """Track window states to restore original size and position"""
    def __init__(self):
        self.window_states = {}  # hwnd -> {'x', 'y', 'width', 'height', 'timestamp'}
        self.snapped_windows = {}  # hwnd -> last snapped position (x,y,w,h)
        self.monitoring = False
        self.monitor_thread = None
    
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
    
    def mark_as_snapped(self, hwnd):
        """Mark a window as snapped, store its current position"""
        try:
            rect = win32gui.GetWindowRect(hwnd)
            self.snapped_windows[hwnd] = (rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1])
        except:
            pass
    
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
    
    def start_monitoring(self):
        """Start monitoring for manual moves"""
        if self.monitoring:
            return
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        print("Window movement monitoring started")
    
    def _monitor_loop(self):
        """Check snapped windows for movement"""
        while self.monitoring:
            for hwnd in list(self.snapped_windows.keys()):
                try:
                    if not win32gui.IsWindow(hwnd):
                        del self.snapped_windows[hwnd]
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