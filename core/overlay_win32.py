# overlay_win32.py - Fixed callback version with zone numbers
import threading, time, ctypes
from ctypes import wintypes as wt
import win32con as wc
import win32gui as wg
import win32api as wa

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
shcore = ctypes.windll.shcore if hasattr(ctypes.windll, "shcore") else None

MONITOR_DEFAULTTONEAREST = 2
AWT_DPI_AWARE_PER_MONITOR = 2

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(AWT_DPI_AWARE_PER_MONITOR)
except Exception:
    pass

def get_dpi_for_monitor(x, y):
    if not shcore: return 96
    pt = wt.POINT(x, y)
    hmon = user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)
    dpix = ctypes.c_uint()
    dpiy = ctypes.c_uint()
    if shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dpix), ctypes.byref(dpiy)) == 0:
        return dpix.value
    return 96

# ---- Simple Overlay Window with proper callback ----
class OverlayWindow:
    def __init__(self, mon_rect, alpha=180, mon_id=0):
        self.mon = mon_rect  # (x, y, w, h)
        self.mon_id = mon_id  # Store which monitor this overlay belongs to
        self.alpha = alpha
        self.hwnd = None
        self.visible = False
        self.zones = []
        self.highlight_name = None
        self.zone_numbers = {}  # Maps (mon_id, zone_name) -> number
        self.zone_key_labels = {}  # {(mon_id, zone_name): "Q" / "Num1" / "2" ...}
        self._create()

    def _create(self):
        # Use PyWin32's window class registration (simpler)
        x, y, w, h = self.mon
        
        ex = wc.WS_EX_LAYERED | wc.WS_EX_TRANSPARENT | wc.WS_EX_TOOLWINDOW | wc.WS_EX_TOPMOST | 0x08000000
        style = wc.WS_POPUP
        
        self.hwnd = wg.CreateWindowEx(
            ex, 
            "STATIC",  # Use built-in STATIC class (simpler than custom)
            "CrudeZones", 
            style,
            x, y, w, h, 
            0, 0, 0, None
        )
        
        if not self.hwnd:
            raise Exception("Failed to create window")
        
        # Set layered attributes
        wg.SetLayeredWindowAttributes(self.hwnd, 0, self.alpha, wc.LWA_ALPHA)
        wg.SetWindowPos(self.hwnd, wc.HWND_TOPMOST, 0, 0, 0, 0,
                       wc.SWP_NOMOVE | wc.SWP_NOSIZE | wc.SWP_NOACTIVATE)

    def show(self):
        if not self.visible:
            wg.ShowWindow(self.hwnd, wc.SW_SHOWNA)
            self.visible = True

    def hide(self):
        if self.visible:
            wg.ShowWindow(self.hwnd, wc.SW_HIDE)
            self.visible = False

    def redraw(self):
        """
        Repaint THIS overlay window only. All required data is already on self:
          - self.zones           : list[dict] each with "x","y","width","height","name"
          - self.zone_numbers    : {(mon_id, zone_name): number}
          - self.mon_id          : this window's monitor id
          - self.highlight_name  : (optional) name of highlighted zone
        """
        # If manager set a generic 'highlight' attr, mirror it to highlight_name
        if getattr(self, "highlight", None) is not None and not getattr(self, "highlight_name", None):
            self.highlight_name = self.highlight

        # Paint immediately to avoid relying on WM_PAINT for this transparent window
        hdc = wg.GetDC(self.hwnd)
        try:
            self._paint_direct(hdc)
        finally:
            wg.ReleaseDC(self.hwnd, hdc)

    def set_zone_numbers(self, zone_numbers):
        """Update zone number mappings"""
        self.zone_numbers = zone_numbers

    def _paint_direct(self, hdc):
        """Paint directly to DC without WM_PAINT"""
        x0, y0, w, h = self.mon
        
        # Clear background
        brush = gdi32.CreateSolidBrush(0x00000000)
        rect = wt.RECT(0, 0, w, h)
        user32.FillRect(hdc, ctypes.byref(rect), brush)
        gdi32.DeleteObject(brush)
        
        # Create drawing objects
        white_pen = gdi32.CreatePen(wc.PS_SOLID, 3, 0x00FFFFFF)
        highlight_brush = gdi32.CreateSolidBrush(0x004080FF)
        null_brush = wg.GetStockObject(wc.NULL_BRUSH)
        
        old_pen = gdi32.SelectObject(hdc, white_pen)
        gdi32.SetBkMode(hdc, wc.TRANSPARENT)
        gdi32.SetTextColor(hdc, 0x00FFFFFF)
        
        # Create larger font for zone numbers
        number_font = gdi32.CreateFontW(
            72, 0, 0, 0, 700, 0, 0, 0, 0, 0, 0, 0, 0, "Arial"
        )
        old_font = gdi32.SelectObject(hdc, number_font)
        
        for z in self.zones:
            rx = z["x"] - x0
            ry = z["y"] - y0
            rw = z["width"]
            rh = z["height"]
            
            # Fill or outline
            if z.get("name") == self.highlight_name:
                old_brush = gdi32.SelectObject(hdc, highlight_brush)
            else:
                old_brush = gdi32.SelectObject(hdc, null_brush)
            
            gdi32.Rectangle(hdc, rx, ry, rx + rw, ry + rh)
            gdi32.SelectObject(hdc, old_brush)
            
            # Choose label: prefer per-zone key label; else the assigned number
            zone_label = None
            zone_name_to_find = z.get("name")

            # If caller provided labels dict, try it first
            if hasattr(self, "zone_key_labels"):
                zone_label = self.zone_key_labels.get((self.mon_id, zone_name_to_find))

            # Fallback: search number map
            if not zone_label:
                zone_num = None
                for (mon_id_key, zone_name_key), num in self.zone_numbers.items():
                    if zone_name_key == zone_name_to_find and mon_id_key == self.mon_id:
                        zone_num = num
                        break
                if zone_num is not None:
                    zone_label = str(zone_num)

            # Draw label if we have one
            if zone_label:
                text_rect = wt.RECT(rx, ry, rx + rw, ry + rh)
                user32.DrawTextW(hdc, zone_label, -1, ctypes.byref(text_rect),
                                wc.DT_CENTER | wc.DT_VCENTER | wc.DT_SINGLELINE)
        
        # Cleanup
        gdi32.SelectObject(hdc, old_font)
        gdi32.DeleteObject(number_font)
        gdi32.SelectObject(hdc, old_pen)
        gdi32.DeleteObject(white_pen)
        gdi32.DeleteObject(highlight_brush)

    def destroy(self):
        if self.hwnd:
            wg.DestroyWindow(self.hwnd)
            self.hwnd = None

# ---- Manager ----
class Win32OverlayManager:
    def __init__(self, zone_manager, overlay_alpha=180):
        self.zm = zone_manager
        self.alpha = overlay_alpha
        self.windows = []
        self.active = False
        self.highlight = None
        self.zone_numbers = {}  # Maps (mon_id, zone_name) -> number
        self.zone_key_labels = {}  # {(mon_id, zone_name): "Q", "Num1", ...}
        self._build_windows()

    def _build_windows(self):
        for mon in self.zm.detected_monitors:
            ow = OverlayWindow(
                (mon["x"], mon["y"], mon["width"], mon["height"]),
                self.alpha,
                mon_id=mon["id"]
            )
            self.windows.append(ow)

    def start(self):
        pass  # Nothing needed

    def show(self):
        for w in self.windows:
            w.show()
        self.redraw()

    def hide(self):
        for w in self.windows:
            w.hide()

    def redraw(self):
        for w in self.windows:
            mon_id = self._get_monitor_id_for_window(w)
            zones_dict = self.zm.monitors.get(mon_id, {})
            zones = []
            for name, z in zones_dict.items():
                zz = dict(z)
                zz["name"] = name
                zones.append(zz)
            
            hl = None
            if self.highlight and self.highlight[0] == mon_id:
                 hl = self.highlight[1]
            
            # CRITICAL: update each window's maps BEFORE calling redraw
            w.zone_numbers = self.zone_numbers
            w.zone_key_labels = getattr(self, "zone_key_labels", {})

            # Provide everything the OverlayWindow expects during redraw:
            w.zones = zones
            w.highlight = hl
            w.zones = zones
            w.highlight_name = hl     # the window paints by checking self.highlight_name
            w.windows = self.windows          # some OverlayWindow code references self.windows
            w.monitor_id = mon_id             # make monitor id directly available
            w.zm = self.zm                    # if window code reads zone manager directly

            # Satisfy code paths that call self._get_monitor_id_for_window(...) on the window:
            # Bind a small helper that returns this window's monitor id (ignores arg if passed).
            def _ow_get_mon_id(*_args, **_kwargs):
                return w.monitor_id
            w._get_monitor_id_for_window = _ow_get_mon_id
            # (Optional) Satisfy legacy code paths that might call this on the window:
            if not hasattr(w, "_get_monitor_id_for_window"):
                def _ow_get_mon_id(*_args, **_kwargs):
                    return w.monitor_id
                w._get_monitor_id_for_window = _ow_get_mon_id

            try:
                w.redraw()
            except Exception as e:
                # Prevent the overlay from getting stranded white if one window fails to paint
                print(f"[CLICK ERR] {e}")

    def set_highlight(self, mon_id, zone_name):
        self.highlight = (mon_id, zone_name) if zone_name is not None else None
        self.redraw()

    def _get_monitor_id_for_window(self, w):
        for m in self.zm.detected_monitors:
            if (m["x"], m["y"], m["width"], m["height"]) == w.mon:
                return m["id"]
        return 0

# ---- Window snapping helpers ----
def get_cursor_pos():
    pt = wa.GetCursorPos()
    return pt[0], pt[1]

def get_hwnd_under_cursor():
    x, y = get_cursor_pos()
    return wg.WindowFromPoint((x, y))

def rect_contains(rect, x, y):
    L, T, R, B = rect
    return (x >= L) and (x < R) and (y >= T) and (y < B)

def zone_rect_to_tuple(z):
    return (z["x"], z["y"], z["x"]+z["width"], z["y"]+z["height"])

def snap_hwnd_outer_to_zone_with_workarea(hwnd, z, work_area):
    L, T, R, B = zone_rect_to_tuple(z)
    waL, waT, waR, waB = work_area

    if L < waL:
        d = waL - L; L += d; R += d
    if T < waT:
        d = waT - T; T += d; B += d
    if R > waR:
        d = R - waR; L -= d; R -= d
    if B > waB:
        d = B - waB; T -= d; B -= d

    wg.SetWindowPos(hwnd, None, L, T, R - L, B - T,
                    wc.SWP_NOZORDER | wc.SWP_NOACTIVATE)