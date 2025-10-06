# monitor_detection.py
import ctypes
import ctypes.wintypes

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
        
        # Sort by position to ensure consistent ordering
        monitors.sort(key=lambda m: (m['x'], m['y']))
        
        # Reassign IDs after sorting
        for i, monitor in enumerate(monitors):
            monitor['id'] = i
        
        return monitors