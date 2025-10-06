# CrudeZones

A lightweight, customizable window tiling manager for Windows with multi-monitor support and flexible two-stage hotkey system.

Heavily inspired by PowerToys FancyZones, CrudeZones reimplements the core functionality with added features like customizable hotkeys and zone numbering that have been requested for years. Built with Python, focusing on maximum configurability and responsiveness.

## Features

- **Multi-monitor support** - Layouts automatically apply to all monitors
- **Two-stage hotkey system** - Use any key as monitor selector + zone key for precise control
- **Drag & drop snapping** - Toggle overlay with Shift or right-click during drag
- **Zone key labels** - Assign custom keys (Q, W, E, etc.) to zones for quick access
- **Number snapping** - Press 1-9 to snap to zones sequentially across monitors
- **Multiple layouts** - Easily switch between different zone arrangements
- **Auto-restore size** - Windows restore to original size when dragged away from zones
- **Manual full restore** - Restore both size and position with hotkey
- **DPI-aware** - Works correctly on multi-monitor setups with different DPI settings
- **Fully configurable** - YAML-based configuration for layouts and hotkeys
- **System tray integration** - Minimal UI, runs in background

## Installation

1. **Clone or download** this repository
2. **Install Python 3.8+** if not already installed
3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Run from the project root:
```bash
python main.py
```

The app will:
- Load layouts from `config/layouts/`
- Load hotkeys from `config/hotkeys.yaml`
- Start minimized to system tray
- Begin listening for hotkeys and drag events

### Two-Stage Hotkey System

The primary way to snap windows is using **two-stage hotkeys**:

**Stage 1:** Hold a monitor selection key  
**Stage 2:** Press a zone key

**Example with default config:**
```yaml
monitor_keys:
  0: "`"    # Backtick for Monitor 0
  1: "1"    # Number 1 for Monitor 1
  2: "2"    # Number 2 for Monitor 2

zones:
  - name: "left"
    key: "Q"
  - name: "right"
    key: "W"
```

**Usage:**
- Hold `` ` `` then press `Q` → Snap to left zone on Monitor 0
- Hold `1` then press `Q` → Snap to left zone on Monitor 1
- Hold `2` then press `Q` → Snap to left zone on Monitor 2
- Hold `` ` `` then press `W` → Snap to right zone on Monitor 0

**Pressing zone key alone (no monitor key):**
- Uses `context_aware` mode by default
- During drag: snaps to zone on monitor where mouse is
- Hotkey snap: snaps to zone on monitor where window currently is

**Supported monitor keys:** Any key can be used - letters, numbers, function keys, special characters, etc. See Configuration section for details.

### Number Key Snapping

Press numbers 1-9 to snap directly to zones in sequential order across all monitors:
- Zones are numbered left-to-right, top-to-bottom on Monitor 0, then Monitor 1, etc.
- `1` → First zone defined (e.g., Monitor 0, left zone)
- `2` → Second zone (e.g., Monitor 0, right zone)
- `3` → Third zone (e.g., Monitor 1, left zone)
- And so on...

Numbers are assigned automatically based on zone order in your layout files. The overlay shows the assigned number on each zone.

**Note:** Numbers configured as monitor keys won't trigger number snapping - they only work as stage-1 keys in the two-stage system.

### Drag & Drop Snapping

**Method 1: Shift Toggle**
- Start dragging a window
- Press **Shift** to toggle overlay on/off
- Overlay shows available zones with labels
- Hover over zone or press zone key to snap
- Release mouse to confirm

**Method 2: Right-click Toggle**
- Start dragging a window
- **Right-click** to toggle overlay on/off
- Use zone keys or hover to select
- Right-click again to turn off

**Scroll to Switch Layouts:**
- While overlay is visible during drag, scroll mouse wheel to cycle layouts for that monitor

### Window Management Hotkeys

**Basic Controls:**
- `Ctrl+Alt+R` → Restore window to original size/position
- `Ctrl+Alt+]` → Cycle to next zone on current monitor
- `Ctrl+Alt+[` → Cycle to previous zone
- `Ctrl+Alt+Shift+]` → Cycle across all monitors
- `Ctrl+Alt+Shift+[` → Cycle backwards across all monitors

**Layout Switching:**
- `Ctrl+Alt+Shift+1` → Switch to first layout (e.g., default)
- `Ctrl+Alt+Shift+2` → Switch to second layout (e.g., thirds)
- `Ctrl+Alt+Shift+3` → Switch to third layout (e.g., quarters)

**App Control:**
- `Ctrl+Alt+` ` → Toggle overlay visibility
- `Ctrl+Alt+Shift+R` → Reload configuration

## Configuration

### Project Structure
```
crude_zones/
├── main.py
├── config/
│   ├── hotkeys.yaml
│   └── layouts/
│       ├── default.yaml
│       ├── layout2.yaml
│       └── layout3.yaml
├── resources/
│   └── icon.png
└── core/
    ├── config_manager.py
    ├── input_handler.py
    ├── zone_numbering.py
    ├── drag_listener.py
    └── ... (other modules)
```

### Creating Custom Layouts

Layouts are now simplified - zones apply to ALL monitors automatically.

Add a new `.yaml` file to `config/layouts/`:

```yaml
name: "myLayout"
description: "Custom layout description"

overlay:
  color: "cyan"
  opacity: 0.3
  auto_hide_seconds: 3

# Zones apply to all monitors
zones:
  - name: "left"
    x_percent: 0
    y_percent: 0
    width_percent: 50
    height_percent: 100
    key: "Q"              # Optional: assign a key to this zone
    # respect_taskbar: true is the default - only specify if you want false
  
  - name: "right"
    x_percent: 50
    y_percent: 0
    width_percent: 50
    height_percent: 100
    key: "W"
  
  - name: "fullscreen"
    x_percent: 0
    y_percent: 0
    width_percent: 100
    height_percent: 100
    respect_taskbar: false  # Only needed to override default
    key: "F"
```

**Notes:**
- `respect_taskbar` defaults to `true` - only specify when you want `false`
- `key` is optional but recommended for quick access
- Layouts automatically apply to all detected monitors
- The layout will be automatically loaded on next restart or config reload

### Customizing Hotkeys

Edit `config/hotkeys.yaml`:

```yaml
# Monitor selection keys (stage 1 of two-stage system)
# Can use ANY key: letters, numbers, F-keys, special chars, etc.
monitor_keys:
  0: "`"        # Backtick/tilde
  1: "1"        # Number keys
  2: "2"
  3: "tab"      # Navigation keys
  4: "f1"       # Function keys
  # Examples of other usable keys:
  # "[", "]", ";", "'", ",", ".", "/"
  # "capslock", "space", "num0"-"num9"
  # Any letter a-z

# Fallback behavior when no monitor key is pressed
default_monitor_for_zone_keys: "context_aware"
# Options: "context_aware", "primary", or monitor ID (0, 1, 2...)

# Overlay control
overlay_hotkey: "ctrl+alt+`"

# Window management
restore_hotkey: "ctrl+alt+r"
reload_config_hotkey: "ctrl+alt+shift+r"
cycle_next_hotkey: "ctrl+alt+]"
cycle_prev_hotkey: "ctrl+alt+["

# Drag behavior (optional - all have defaults)
drag_behavior:
  show_zones_key: "shift"                    # shift, ctrl, or alt
  scroll_layout_switch_enabled: true
  scroll_cooldown_seconds: 0.30
  number_snap_cooldown_seconds: 0.5
  zone_hover_margin_pixels: 6
  ignore_fullscreen_zone: true

# State tracking (optional - all have defaults)
state_tracking:
  auto_restore_enabled: true
  movement_threshold_pixels: 10
  monitoring_interval_seconds: 0.1
  operation_exempt_delay_seconds: 2.0

# Layout switching hotkeys
layout_switches:
  - keys: "ctrl+alt+shift+1"
    layout: "default"
  - keys: "ctrl+alt+shift+2"
    layout: "thirds"
  - keys: "ctrl+alt+shift+3"
    layout: "quarters"

# Legacy zone hotkeys (optional - use two-stage system instead)
zone_hotkeys:
  - keys: "ctrl+alt+kp_4"
    monitor: 0
    zone: "left"
  # ... etc
```

### Monitor Key Selection Tips

**For 2-3 monitors (one-handed):**
```yaml
monitor_keys:
  0: "`"    # Pinky
  1: "1"    # Ring finger
  2: "2"    # Middle finger
```

**For 4+ monitors (function keys):**
```yaml
monitor_keys:
  0: "f1"
  1: "f2"
  2: "f3"
  3: "f4"
  # Up to F24 supported!
```

**For left-hand operation:**
```yaml
monitor_keys:
  0: "z"
  1: "x"
  2: "c"
  3: "v"
```

Choose keys that:
- You rarely use in normal workflow
- Are comfortable to hold
- Don't conflict with your zone keys

## System Tray

Right-click the tray icon for:
- **Show Monitors** - Display detected monitor info
- **Show Hotkeys** - View all registered hotkeys and zones
- **Reload Config** - Reload YAML files without restarting
- **Quit** - Exit application

## Auto-Restore Feature

When you snap a window to a zone, its original size and position are saved:

- **Auto size restore:** If you manually drag the window away from the zone (more than 10 pixels), it automatically restores to its original **size** at the new position
- **Manual full restore:** Press `Ctrl+Alt+R` to restore both size **and** position back to where it was before snapping

To disable auto size restore, set `auto_restore_enabled: false` in the `state_tracking` section of `hotkeys.yaml`.

## Troubleshooting

**Two-stage hotkeys not working:**
- Make sure you're HOLDING the monitor key, not just pressing it
- Check console output for `[INPUT] Two-stage:` messages
- Verify your monitor keys don't conflict with zone keys

**Number keys snap instantly instead of waiting for zone key:**
- This is correct if the number is NOT configured as a monitor key
- Numbers used as monitor keys (e.g., 1, 2) wait for zone key
- Other numbers (3-9) trigger direct zone snapping

**Overlay not showing:**
- Ensure you're dragging a valid window (not desktop/taskbar)
- Check that the drag key is correct in `config/hotkeys.yaml`
- Verify overlay_hotkey doesn't conflict with other apps

**Hotkeys not working:**
- Verify no other apps are using the same combinations
- Check console output for registered hotkeys
- Reload config with `Ctrl+Alt+Shift+R`

**Window snapping to wrong position:**
- Check `respect_taskbar: true` in layout zones (it's the default)
- Verify monitor detection in console output
- Make sure zone percentages add up correctly

**Config not loading:**
- Ensure YAML syntax is valid (use a YAML linter)
- Check file paths are correct
- View console for error messages

## Requirements

- Windows 10/11
- Python 3.8+
- See `requirements.txt` for dependencies:
  - pynput
  - pyyaml
  - pywin32
  - pystray
  - pillow

## Architecture

CrudeZones uses a modular architecture:
- **ConfigManager** - Centralized configuration loading with defaults
- **InputHandler** - Keyboard/mouse input detection (no hardcoded keys)
- **ZoneNumbering** - Zone numbering and label assignment
- **DragZoneListener** - Drag-to-snap behavior with two-stage hotkeys
- **ZoneManager** - Window movement and zone calculations
- **WindowStateTracker** - Auto-restore functionality

All behavior is configurable via YAML - no hardcoded values in the code.

## License

MIT License - Feel free to modify and distribute