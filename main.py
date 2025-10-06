# main.py
import sys
import ctypes

# Set DPI awareness early
ctypes.windll.shcore.SetProcessDpiAwareness(2)

from zone_manager import ZoneManager
from overlay_win32 import Win32OverlayManager
from hotkey_listener import HotkeyListener
from drag_listener import DragZoneListener
from tray_app import TrayApp

def main():
    try:
        # Initialize core components (config folder is at project root)
        zone_manager = ZoneManager(config_dir='config')

        # Create overlay
        overlay = Win32OverlayManager(zone_manager, overlay_alpha=170)
        overlay.start()

        # Start auto-restore monitoring
        zone_manager.state_tracker.start_monitoring()

        # Start hotkey listener
        hotkey_listener = HotkeyListener(zone_manager, overlay)
        hotkey_listener.start()

        print("\nZone Manager started!")
        print("Registered hotkeys:")
        for hk in zone_manager.hotkeys:
            print(f"  {hk['keys']} -> Monitor {hk['monitor']}, Zone {hk['zone']}")
        print(f"  {zone_manager.overlay_config['hotkey']} -> Show/Hide Zones")
        print(f"  {zone_manager.restore_hotkey} -> Restore Window")
        print(f"  {zone_manager.reload_config_hotkey} -> Reload Config")
        print()

        # Start drag listener
        drag_listener = DragZoneListener(zone_manager, overlay)
        drag_listener.start()

        # Start tray app
        tray_app = TrayApp(zone_manager, hotkey_listener, 'config', drag_listener)
        icon = tray_app.setup_tray_icon()
        hotkey_listener.tray_icon = icon
        tray_app.icon = icon

        # Run (blocks until quit)
        icon.run()

    except FileNotFoundError as e:
        print(f"Error: Configuration file not found: {e}")
        print("Make sure you have a 'config' folder with 'hotkeys.yaml' and 'layouts/' subfolder")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()