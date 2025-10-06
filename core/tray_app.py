# tray_app.py
import pystray
from PIL import Image, ImageDraw
import threading
import tkinter as tk
import os

class TrayApp:
    def __init__(self, zone_manager, hotkey_listener, config_dir, drag_listener=None, overlay=None):
        self.zone_manager = zone_manager
        self.hotkey_listener = hotkey_listener
        self.config_dir = config_dir
        self.drag_listener = drag_listener
        self.overlay = overlay  # ADD THIS
        self.icon = None
        self.hotkey_listener.tray_icon = None
    
    def create_icon_image(self):
        """Load icon from PNG file"""
        try:
            project_root = os.path.dirname(os.path.dirname(__file__))
            icon_path = os.path.join(project_root, 'resources', 'icon.png')
            image = Image.open(icon_path)
            image = image.resize((64, 64), Image.Resampling.LANCZOS)
            return image
        except FileNotFoundError:
            print("Warning: icon.png not found, using default icon")
            return self._create_default_icon()

    def _create_default_icon(self):
        """Create a simple default icon if PNG is not found"""
        width = 64
        height = 64
        image = Image.new('RGB', (width, height), 'navy')
        draw = ImageDraw.Draw(image)
        
        draw.rectangle([8, 8, 28, 28], fill='white', outline='lightblue', width=2)
        draw.rectangle([36, 8, 56, 28], fill='white', outline='lightblue', width=2)
        draw.rectangle([8, 36, 28, 56], fill='white', outline='lightblue', width=2)
        draw.rectangle([36, 36, 56, 56], fill='white', outline='lightblue', width=2)
        
        return image
    
    def reload_config(self, icon=None, item=None):
        """Reload configuration file and re-detect monitors"""
        try:
            print("\n=== Reloading Configuration ===")
            self.zone_manager.load_config()
            self.hotkey_listener.restart()
            print("Configuration reloaded successfully\n")
            if self.icon:
                self.icon.notify("Configuration reloaded", "Zone Manager")
        except Exception as e:
            print(f"Error reloading config: {e}")
            if self.icon:
                self.icon.notify(f"Error reloading config: {e}", "Zone Manager")
    
    def show_info(self, icon, item):
        """Show information about loaded zones and hotkeys"""
        info_window = HotkeyInfoWindow(self.zone_manager)
        info_window.show()
    
    def show_monitors(self, icon, item):
        """Show detected monitor information"""
        info = f"Detected {len(self.zone_manager.detected_monitors)} monitor(s):\n"
        for mon in self.zone_manager.detected_monitors:
            primary = " (PRIMARY)" if mon['is_primary'] else ""
            info += f"Monitor {mon['id']}: {mon['width']}x{mon['height']}{primary}\n"
        print(info)
        icon.notify(info, "Zone Manager - Monitors")
    
    def quit_app(self, icon, item):
        """Quit the application"""
        print("Shutting down...")
        
        # CRITICAL: Clean up overlay windows first
        if self.overlay:
            try:
                print("Destroying overlay windows...")
                for w in self.overlay.windows:
                    w.destroy()
            except Exception as e:
                print(f"Error destroying overlays: {e}")
        
        # Stop listeners
        self.hotkey_listener.stop()
        if self.drag_listener:
            self.drag_listener.stop()
        
        # Stop tray icon
        icon.stop()
        print("Shutdown complete")
    
    def setup_tray_icon(self):
        """Create and configure system tray icon"""
        menu = pystray.Menu(
            pystray.MenuItem("Show Monitors", self.show_monitors),
            pystray.MenuItem("Show Hotkeys", self.show_info),
            pystray.MenuItem("Reload Config", self.reload_config),
            pystray.MenuItem("Quit", self.quit_app)
        )
        
        self.icon = pystray.Icon(
            "zone_manager",
            self.create_icon_image(),
            "Zone Manager",
            menu=menu
        )
        
        return self.icon
    
    def run(self):
        """Run the tray application"""
        icon = self.setup_tray_icon()
        print("Zone Manager running in system tray")
        print("Right-click the tray icon for options")
        icon.run()


class HotkeyInfoWindow:
    """Display hotkey information in a popup window"""
    def __init__(self, zone_manager):
        self.zone_manager = zone_manager
        
    def show(self):
        """Show the hotkey info window"""
        threading.Thread(target=self._create_window, daemon=True).start()
    
    def _create_window(self):
        """Create and display the info window"""
        root = tk.Tk()
        root.title("Zone Manager - Hotkeys")
        root.geometry("500x600")
        root.resizable(True, True)
        
        main_frame = tk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        canvas = tk.Canvas(main_frame)
        scrollbar = tk.Scrollbar(main_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)
        
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        info_text = tk.Text(scrollable_frame, wrap=tk.WORD, width=60, height=30, font=('Consolas', 10))
        info_text.pack(fill=tk.BOTH, expand=True)
        
        info_text.insert(tk.END, "=== ZONE HOTKEYS ===\n\n", "header")
        for hk in self.zone_manager.hotkeys:
            info_text.insert(tk.END, f"{hk['keys']:<30} ", "key")
            info_text.insert(tk.END, f"-> Monitor {hk['monitor']}, Zone {hk['zone']}\n", "normal")
        
        info_text.insert(tk.END, "\n=== SPECIAL HOTKEYS ===\n\n", "header")
        
        special_hotkeys = [
            (self.zone_manager.overlay_config['hotkey'], "Show/Hide Zones"),
            (self.zone_manager.restore_hotkey, "Restore Window"),
            (self.zone_manager.reload_config_hotkey, "Reload Configuration"),
            (self.zone_manager.config.get('cycle_next_hotkey', 'ctrl+alt+]'), "Cycle Next Zone"),
            (self.zone_manager.config.get('cycle_prev_hotkey', 'ctrl+alt+['), "Cycle Previous Zone"),
        ]
        
        for hotkey, description in special_hotkeys:
            info_text.insert(tk.END, f"{hotkey:<30} ", "key")
            info_text.insert(tk.END, f"-> {description}\n", "normal")
        
        info_text.insert(tk.END, "\n=== MONITORS ===\n\n", "header")
        for mon in self.zone_manager.detected_monitors:
            primary = " (PRIMARY)" if mon['is_primary'] else ""
            info_text.insert(tk.END, f"Monitor {mon['id']}: ", "key")
            info_text.insert(tk.END, f"{mon['width']}x{mon['height']}{primary}\n", "normal")
        
        info_text.tag_config("header", foreground="blue", font=('Consolas', 11, 'bold'))
        info_text.tag_config("key", foreground="darkgreen", font=('Consolas', 10, 'bold'))
        info_text.tag_config("normal", foreground="black")
        
        info_text.config(state=tk.DISABLED)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        close_button = tk.Button(root, text="Close", command=root.destroy, width=15)
        close_button.pack(pady=5)
        
        root.update_idletasks()
        width = root.winfo_width()
        height = root.winfo_height()
        x = (root.winfo_screenwidth() // 2) - (width // 2)
        y = (root.winfo_screenheight() // 2) - (height // 2)
        root.geometry(f'{width}x{height}+{x}+{y}')
        
        root.lift()
        root.attributes('-topmost', True)
        root.after_idle(root.attributes, '-topmost', False)
        
        root.mainloop()