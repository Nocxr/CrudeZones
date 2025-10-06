import sys
import ctypes
import atexit
import signal

# Set DPI awareness early
ctypes.windll.shcore.SetProcessDpiAwareness(2)

from core.zone_manager import ZoneManager
from core.overlay_win32 import Win32OverlayManager
from core.hotkey_listener import HotkeyListener
from core.drag_listener import DragZoneListener
from core.tray_app import TrayApp

# Global reference for cleanup
overlay_manager = None

def cleanup_overlays():
    """Emergency cleanup function"""
    global overlay_manager
    if overlay_manager:
        try:
            print("\n[CLEANUP] Destroying overlay windows...")
            for w in overlay_manager.windows:
                w.destroy()
        except Exception as e:
            print(f"[CLEANUP ERROR] {e}")

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print("\n[SIGNAL] Caught interrupt signal, cleaning up...")
    cleanup_overlays()
    sys.exit(0)

def main():
    global overlay_manager
    
    try:
        # Register cleanup handlers
        atexit.register(cleanup_overlays)
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Initialize core components
        zone_manager = ZoneManager(config_dir='config')

        # Create overlay
        overlay = Win32OverlayManager(zone_manager, overlay_alpha=170)
        overlay.start()
        overlay_manager = overlay  # Store globally for cleanup

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

        # Start drag listener (UPDATED: pass config_manager)
        drag_listener = DragZoneListener(
            zone_manager, 
            overlay, 
            zone_manager.config_manager  # Pass the config manager
        )
        drag_listener.start()

        # Start tray app (pass overlay reference)
        tray_app = TrayApp(zone_manager, hotkey_listener, 'config', drag_listener, overlay)
        icon = tray_app.setup_tray_icon()
        hotkey_listener.tray_icon = icon
        tray_app.icon = icon

        # Run (blocks until quit)
        icon.run()

    except FileNotFoundError as e:
        print(f"Error: Configuration file not found: {e}")
        print("Make sure you have a 'config' folder with 'hotkeys.yaml' and 'layouts/' subfolder")
        cleanup_overlays()
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        cleanup_overlays()
        sys.exit(1)
    finally:
        # Final cleanup on any exit
        cleanup_overlays()

if __name__ == "__main__":
    main()