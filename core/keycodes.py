# core/keycodes.py
import win32con

# Top row digits
VK_BY_NAME = {
    **{str(i): ord(str(i)) for i in range(0, 10)},  # '0'..'9' -> 0x30..0x39
    **{chr(c): ord(chr(c)) for c in range(ord('A'), ord('Z') + 1)},  # 'A'..'Z'
    
    # Special characters
    "MINUS": 0xBD, "-": 0xBD,
    "EQUALS": 0xBB, "=": 0xBB,
    "`": 0xC0, "BACKTICK": 0xC0, "TILDE": 0xC0,
    "[": 0xDB, "LEFTBRACKET": 0xDB,
    "]": 0xDD, "RIGHTBRACKET": 0xDD,
    "\\": 0xDC, "BACKSLASH": 0xDC,
    ";": 0xBA, "SEMICOLON": 0xBA,
    "'": 0xDE, "QUOTE": 0xDE, "APOSTROPHE": 0xDE,
    ",": 0xBC, "COMMA": 0xBC,
    ".": 0xBE, "PERIOD": 0xBE,
    "/": 0xBF, "SLASH": 0xBF,
    
    # Navigation keys
    "TAB": 0x09,
    "CAPSLOCK": 0x14, "CAPS": 0x14,
    "SPACE": 0x20,
    "ENTER": 0x0D, "RETURN": 0x0D,
    "BACKSPACE": 0x08,
    "ESC": 0x1B, "ESCAPE": 0x1B,
    "DELETE": 0x2E, "DEL": 0x2E,
    "INSERT": 0x2D, "INS": 0x2D,
    "HOME": 0x24,
    "END": 0x23,
    "PAGEUP": 0x21, "PGUP": 0x21,
    "PAGEDOWN": 0x22, "PGDN": 0x22,
    "LEFT": 0x25,
    "UP": 0x26,
    "RIGHT": 0x27,
    "DOWN": 0x28,
}

# Function keys
for i in range(1, 25):  # F1-F24
    VK_BY_NAME[f"F{i}"] = getattr(win32con, f"VK_F{i}")

# Numpad
for i in range(0, 10):
    VK_BY_NAME[f"NUM{i}"] = getattr(win32con, f"VK_NUMPAD{i}")
    VK_BY_NAME[f"NUMPAD{i}"] = getattr(win32con, f"VK_NUMPAD{i}")

def parse_key_to_vk(key_str: str):
    """Return (vk_code, label) or (None, None) if unknown."""
    if not key_str:
        return (None, None)
    key = key_str.strip().upper()
    vk = VK_BY_NAME.get(key)
    if vk is None:
        return (None, None)
    # Render a friendly label on the overlay
    if key.startswith("NUM"):
        label = key.replace("NUM", "Num").replace("NUMPAD", "Num")
    elif key in ["`", "BACKTICK", "TILDE"]:
        label = "`"
    elif key == "TAB":
        label = "Tab"
    elif key in ["CAPSLOCK", "CAPS"]:
        label = "Caps"
    elif key == "SPACE":
        label = "Space"
    else:
        label = key
    return (vk, label)