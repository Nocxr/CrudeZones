# overlay_win32.py
import threading, time, ctypes, math
from ctypes import wintypes as wt
import win32con as wc
import win32gui as wg
import win32api as wa
import win32ui as wu

# ---- Helpers for frame/dpi -----------------
user32  = ctypes.windll.user32
gdi32   = ctypes.windll.gdi32
shcore  = ctypes.windll.shcore if hasattr(ctypes.windll, "shcore") else None

MONITOR_DEFAULTTONEAREST = 2
AWT_DPI_AWARE_PER_MONITOR = 2

try:
    # Per-monitor aware for correct scaling
    ctypes.windll.shcore.SetProcessDpiAwareness(AWT_DPI_AWARE_PER_MONITOR)
except Exception:
    pass

AdjustWindowRectExForDpi = getattr(user32, "AdjustWindowRectExForDpi", None)

def get_dpi_for_monitor(x, y):
    if not shcore: return 96
    pt = wt.POINT(x, y)
    hmon = user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)
    dpix = ctypes.c_uint()
    dpiy = ctypes.c_uint()
    # MDT_EFFECTIVE_DPI = 0
    if shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dpix), ctypes.byref(dpiy)) == 0:
        return dpix.value
    return 96

def adjust_for_frame(target_rect, style, exstyle, dpi):
    # Given a desired *client* rect, expand so the whole window (frame+client) fills the target.
    left, top, right, bottom = target_rect
    rect = wt.RECT(left, top, right, bottom)
    if AdjustWindowRectExForDpi:
        AdjustWindowRectExForDpi(ctypes.byref(rect), style, False, exstyle, dpi)
    else:
        user32.AdjustWindowRectEx(ctypes.byref(rect), style, False, exstyle)
    return rect.left, rect.top, rect.right, rect.bottom

# ---- Overlay window class per monitor -------
WC_NAME = "CZ_Overlay_Class"

class OverlayWindow:
    def __init__(self, mon_rect, alpha=180):
        self.mon = mon_rect  # (x, y, w, h)
        self.alpha = alpha
        self.hwnd = None
        self.dc = None
        self.memdc = None
        self.bmp = None
        self.pen = None
        self.visible = False
        self._create()

    def _create(self):
        hinst = wa.GetModuleHandle(None)

        # NEW (always try to register; ignore "already exists")
        wndclass = wg.WNDCLASS()
        wndclass.hInstance = hinst
        wndclass.lpszClassName = WC_NAME
        wndclass.style = wc.CS_HREDRAW | wc.CS_VREDRAW
        wndclass.hCursor = wa.LoadCursor(0, wc.IDC_ARROW)
        # Use default window proc; we blit manually.
        wndclass.lpfnWndProc = wg.DefWindowProc

        try:
            wg.RegisterClass(wndclass)
        except wg.error as e:
            # 1410 = class already exists; safe to ignore
            if getattr(e, "winerror", None) != 1410:
                raise

        ex = wc.WS_EX_LAYERED | wc.WS_EX_TRANSPARENT | wc.WS_EX_TOOLWINDOW | 0x08000000  # NOACTIVATE
        style = wc.WS_POPUP

        x, y, w, h = self.mon
        self.hwnd = wg.CreateWindowEx(
            ex, WC_NAME, "CrudeZonesOverlay", style,
            x, y, w, h, 0, 0, hinst, None
        )
        # topmost and hidden initially
        wg.SetWindowPos(self.hwnd, wc.HWND_TOPMOST, x, y, w, h,
                        wc.SWP_NOACTIVATE | wc.SWP_SHOWWINDOW)
        wg.ShowWindow(self.hwnd, wc.SW_HIDE)

        # Create drawing resources
        self.dc = wu.CreateDCFromHandle(wg.GetDC(self.hwnd))
        self.memdc = self.dc.CreateCompatibleDC()
        self.bmp = wu.CreateBitmap()
        self.bmp.CreateCompatibleBitmap(self.dc, w, h)
        self.memdc.SelectObject(self.bmp)

        # Pens/brushes
        self.pen = wu.CreatePen(wc.PS_SOLID, 3, 0x00FFFFFF)   # white (BGR)

        # Global alpha for whole window
        wg.SetLayeredWindowAttributes(self.hwnd, 0, self.alpha, wc.LWA_ALPHA)

    def destroy(self):
        if self.visible: self.hide()
        if self.memdc: self.memdc.DeleteDC()
        if self.dc: self.dc.DeleteDC()
        if self.bmp: self.bmp.DeleteObject()
        if self.pen: self.pen.DeleteObject()
        if self.hwnd: wg.DestroyWindow(self.hwnd)
        self.hwnd = None

    def show(self):
        if self.visible: return
        wg.ShowWindow(self.hwnd, wc.SW_SHOWNA)
        self.visible = True

    def hide(self):
        if not self.visible: return
        wg.ShowWindow(self.hwnd, wc.SW_HIDE)
        self.visible = False

    def draw(self, zones, highlight_name=None, color_bgr=0x00FFFFFF):
        # zones: list of dicts each with x,y,width,height,name in *desktop* coords
        x0, y0, w, h = self.mon
        memdc = self.memdc

        # NEW: clear the backbuffer to transparent black
        memdc.FillSolidRect((0, 0, w, h), 0x00000000)
        
        # Draw each zone
        pen = wu.CreatePen(wc.PS_SOLID, 3, color_bgr)
        old_pen = memdc.SelectObject(pen)

        font = wu.CreateFont({"name": "Segoe UI", "height": -22, "weight": 700})
        old_font = memdc.SelectObject(font)

        for z in zones:
            rx = z["x"] - x0
            ry = z["y"] - y0
            rw = z["width"]
            rh = z["height"]

            # fill highlight first (under border)
            if z.get("name") == highlight_name:
                memdc.FillSolidRect((rx, ry, rx + rw, ry + rh), 0x004080FF)

            # draw border with lines (for every zone)
            x1, y1 = rx, ry
            x2, y2 = rx + rw - 1, ry + rh - 1
            memdc.MoveTo(x1, y1); memdc.LineTo(x2, y1)
            memdc.LineTo(x2, y2)
            memdc.LineTo(x1, y2)
            memdc.LineTo(x1, y1)

            # centered label (optional)
            text = z.get("name", "")
            if text:
                memdc.SetTextColor(color_bgr)
                memdc.SetBkMode(wc.TRANSPARENT)
                memdc.DrawText(text, (rx, ry, rx + rw, ry + rh),
                            wc.DT_CENTER | wc.DT_VCENTER | wc.DT_SINGLELINE)


        # restore GDI objects
        memdc.SelectObject(old_pen)
        try:
            wg.DeleteObject(pen.GetHandle())         # pen cleanup
        except Exception:
            pass

        memdc.SelectObject(old_font)
        try:
            wg.DeleteObject(font.GetHandle())        # font cleanup
        except Exception:
            pass



    def _on_paint(self, hwnd, msg, wparam, lparam):
        ps = wg.BeginPaint(hwnd)
        wg.EndPaint(hwnd, ps)
        return 0

# ---- Manager tying it together --------------
class Win32OverlayManager:
    def __init__(self, zone_manager, overlay_alpha=180):
        """
        zone_manager:
          - must expose .detected_monitors: list of {id,x,y,width,height}
          - must expose .monitors[mon_id] -> dict of zone_name -> {x,y,width,height,name}
        """
        self.zm = zone_manager
        self.alpha = overlay_alpha
        self.windows = []  # [OverlayWindow]
        self.active = False
        self.highlight = None
        self.thread = None
        self._cmd = []
        self._lock = threading.Lock()

    def start(self):
        if self.thread: return
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        # give it a moment to build
        for _ in range(50):
            if self.windows: break
            time.sleep(0.01)

    def show(self):
        with self._lock: self._cmd.append(("show", None))

    def hide(self):
        with self._lock: self._cmd.append(("hide", None))

    def redraw(self):
        with self._lock: self._cmd.append(("redraw", None))

    def set_highlight(self, mon_id, zone_name):
        with self._lock:
            self.highlight = (mon_id, zone_name) if zone_name is not None else None
            self._cmd.append(("redraw", None))

    def _loop(self):
        # prebuild windows
        for mon in self.zm.detected_monitors:
            ow = OverlayWindow((mon["x"], mon["y"], mon["width"], mon["height"]), self.alpha)
            self.windows.append(ow)

        # message pump + light timer
        while True:
            # handle commands
            todo = []
            with self._lock:
                todo, self._cmd = self._cmd, []
            if todo:
                for op, _ in todo:
                    if op == "show":
                        for w in self.windows: w.show()
                        self._do_draw()
                    elif op == "hide":
                        for w in self.windows: w.hide()
                    elif op == "redraw":
                        self._do_draw()

            time.sleep(0.01)

    def _do_draw(self):
        color = 0x00FFFFFF  # BGR white
        for w in self.windows:
            # find this window's monitor id
            mon_id = None
            for m in self.zm.detected_monitors:
                if (m["x"], m["y"], m["width"], m["height"]) == (w.mon[0], w.mon[1], w.mon[2], w.mon[3]):
                    mon_id = m["id"]; break

            zones_dict = self.zm.monitors.get(mon_id, {})
            zones = []
            for name, z in zones_dict.items():
                zz = dict(z); zz["name"] = name
                zones.append(zz)

            # compute this window's highlight (only if it matches this monitor)
            hl = None
            if self.highlight and self.highlight[0] == mon_id:
                hl = self.highlight[1]

            w.draw(zones, highlight_name=hl, color_bgr=color)


# ---- Window snapping helpers ----------------
def get_cursor_pos():
    pt = wa.GetCursorPos()
    return pt[0], pt[1]

def get_hwnd_under_cursor():
    x, y = get_cursor_pos()
    return wg.WindowFromPoint((x, y))

def rect_contains(rect, x, y):
    L,T,R,B = rect
    return (x >= L) and (x < R) and (y >= T) and (y < B)

def zone_rect_to_tuple(z):
    return (z["x"], z["y"], z["x"]+z["width"], z["y"]+z["height"])

def snap_hwnd_to_zone(hwnd, z):
    # Move the *whole* window so its client area aligns to z
    style  = wg.GetWindowLong(hwnd, wc.GWL_STYLE)
    exstyle= wg.GetWindowLong(hwnd, wc.GWL_EXSTYLE)
    # Desired client rect:
    L,T,R,B = zone_rect_to_tuple(z)
    dpi = get_dpi_for_monitor(L, T)
    winL, winT, winR, winB = adjust_for_frame((L,T,R,B), style, exstyle, dpi)
    wg.SetWindowPos(hwnd, None, winL, winT, winR-winL, winB-winT,
                    wc.SWP_NOZORDER | wc.SWP_NOACTIVATE)
