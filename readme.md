# CrudeZones

A lightweight, customizable window tiling manager for Windows with multi-monitor support.

## Features

- **Multi-monitor support** - Independent layouts per monitor
- **Drag & drop snapping** - Hold Shift while dragging or right-click to toggle overlay
- **Keyboard hotkeys** - NumPad-based zone snapping
- **Multiple layouts** - Easily switch between halves, thirds, quarters, or custom layouts
- **Auto-restore** - Windows return to original position when manually moved after snapping
- **Per-monitor DPI awareness** - Crisp visuals on mixed-DPI setups
- **Configurable** - YAML-based configuration for layouts and hotkeys
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

### Drag & Drop Snapping

**Method 1: Shift + Drag**
- Hold **Shift** while dragging a window
- Overlay appears showing available zones
- Release over a zone to snap

**Method 2: Right-click Toggle**
- Start dragging a window
- **Right-click** to toggle overlay on/off (latches)
- Snap to zones while overlay is visible
- Right-click again to turn off

**Scroll to Switch Layouts:**
- While overlay is visible, scroll mouse wheel to cycle layouts for that monitor

### Keyboard Hotkeys

**Zone Snapping (Monitor 0):**
- NumPad layout mirrors zone positions:
  - `Ctrl+Alt+7/8/9` → Top-left/Top/Top-right
  - `Ctrl+Alt+4/5/6` → Left/Full/Right
  - `Ctrl+Alt+1/2/3` → Bottom-left/Bottom/Bottom-right
  - `Ctrl+Alt+0` → Center (thirds layout)

**Monitor 1:** Add `Shift` to the above combos

**Window Management:**
- `Ctrl+Alt+R` → Restore window to original size/position
- `Ctrl+Alt+]` → Cycle to next zone on current monitor
- `Ctrl+Alt+[` → Cycle to previous zone
- `Ctrl+Alt+Shift+]` → Cycle across all monitors

**Layout Switching:**
- `Ctrl+Alt+Shift+1` → Default layout
- `Ctrl+Alt+Shift+2` → Thirds layout
- `Ctrl+Alt+Shift+3` → Quarters layout

**App Control:**
- `Ctrl+Alt+Z` → Toggle overlay visibility
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
│       ├── thirds.yaml
│       └── quarters.yaml
├── resources/
│   └── icon.png
└── core/
    └── ... (modules)
```

### Creating Custom Layouts

Add a new `.yaml` file to `config/layouts/`:

```yaml
name: "myLayout"
description: "Custom layout description"

overlay:
  color: "cyan"
  opacity: 0.3
  auto_hide_seconds: 3

monitors:
  - id: 0
    name: "Main"
    zones:
      - name: "myZone"
        x_percent: 0
        y_percent: 0
        width_percent: 50
        height_percent: 100
        respect_taskbar: true
```

The layout will be automatically loaded on next restart or config reload.

### Customizing Hotkeys

Edit `config/hotkeys.yaml` to change any keyboard shortcuts:

```yaml
overlay_hotkey: "ctrl+alt+z"
restore_hotkey: "ctrl+alt+r"
drag_show_zones_key: "shift"  # or "ctrl" or "alt"

zone_hotkeys:
  - keys: "ctrl+alt+kp_4"
    monitor: 0
    zone: "left"
```

## System Tray

Right-click the tray icon for:
- **Show Monitors** - Display detected monitor info
- **Show Hotkeys** - View all registered hotkeys
- **Reload Config** - Reload YAML files without restarting
- **Quit** - Exit application

## Auto-Restore Feature

When you snap a window to a zone, its original position is saved. If you manually drag it away from the zone (more than 10 pixels), it automatically restores to the saved position. Use `Ctrl+Alt+R` to manually restore at any time.

## Troubleshooting

**Overlay not showing:**
- Ensure you're dragging a valid window (not desktop/taskbar)
- Check that the drag key is correct in `config/hotkeys.yaml`

**Hotkeys not working:**
- Verify no other apps are using the same combinations
- Check console output for registered hotkeys
- Reload config with `Ctrl+Alt+Shift+R`

**Window snapping to wrong position:**
- Check `respect_taskbar: true` in layout zones
- Verify monitor detection in console output

**Config not loading:**
- Ensure YAML syntax is valid (use a YAML linter)
- Check file paths are correct
- View console for error messages

## Requirements

- Windows 10/11
- Python 3.8+
- See `requirements.txt` for dependencies

## License

MIT License - Feel free to modify and distribute

## Contributing

Contributions welcome! Please feel free to submit issues or pull requests.