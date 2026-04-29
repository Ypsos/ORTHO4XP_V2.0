import os
from math import floor, cos, pi
import sys
import queue
import threading
import tkinter as tk
from tkinter import RIDGE, N, S, E, W, NW, NE, SW, SE, LEFT, RIGHT, CENTER, HORIZONTAL, END, ALL, filedialog, messagebox
import tkinter.ttk as ttk
from PIL import Image, ImageTk
import O4_Version
import O4_Imagery_Utils as IMG
import O4_File_Names as FNAMES
import O4_Geo_Utils as GEO
import O4_Vector_Utils as VECT
import O4_Vector_Map as VMAP
import O4_Mesh_Utils as MESH
import O4_Mask_Utils as MASK
import O4_Tile_Utils as TILE
import O4_UI_Utils as UI
import O4_Config_Utils as CFG
import O4_Color_Normalize as CNORM
import O4_Color_Check as CC

OsX = "dar" in sys.platform


class Ortho4XP_GUI(tk.Tk):

    zl_list = ["12", "13", "14", "15", "16", "17", "18"]

    def __init__(self):
        tk.Tk.__init__(self)

        # ── Détection 4K ──────────────────────────────────────────────
        dpi = self.winfo_fpixels('1i')
        self._ui_scale = 1.3  # +30% pour lisibilité 4K macOS
        s = self._ui_scale
        fs = lambda x: int(x * s)

        # ── Styles ttk ────────────────────────────────────────────────
        O4 = ttk.Style()
        O4.theme_use("alt")
        O4.configure("Flat.TButton",
            background="#3b5b49", highlightbackground="#3b5b49",
            selectbackground="#3b5b49", highlightcolor="#3b5b49",
            highlightthickness=0, relief="flat")
        O4.map("Flat.TButton",
            background=[("disabled","pressed","!focus","active","#3b5b49")])
        O4.configure("O4.TCombobox",
            selectbackground="white", selectforeground="#1e3028",
            fieldbackground="white", foreground="#1e3028", background="white")
        O4.map("O4.TCombobox",
            fieldbackground=[("disabled","!focus","focus","active","white")])
        self.option_add("*Font", f"TkFixedFont {fs(11)}")

        # ── UI global ─────────────────────────────────────────────────
        UI.gui = self

        # ── Initialisation providers ──────────────────────────────────
        try:
            IMG.initialize_providers_dict()
            IMG.initialize_combined_providers_dict()
            IMG.initialize_extents_dict()
            IMG.initialize_color_filters_dict()
        except Exception as e:
            print(f"[GUI] initialize_providers: {e}")
        try:
            def _in_gui(p):
                if isinstance(p, dict): return p.get("in_GUI", True)
                return getattr(p, "in_GUI", True)
            full = sorted([
                c for c in set(IMG.providers_dict)
                if _in_gui(IMG.providers_dict[c])
            ] + sorted(set(IMG.combined_providers_dict)))
            for rm in ("OSM", "SEA"):
                try: full.remove(rm)
                except: pass
            self.map_list = full if full else ["BI","GO2","ARC","IGN","SWISSTOPO","ZonePhoto"]
        except:
            self.map_list = ["BI","GO2","ARC","IGN","SWISSTOPO","ZonePhoto"]

        # ── Fenêtre ───────────────────────────────────────────────────
        self.title("Ortho4XP V2.0 - sRGB Roland Edition (Mars 2026)")
        self.geometry(f"{int(1320*s)}x{int(860*s)}")
        self.minsize(1320, 860)
        self.protocol("WM_DELETE_WINDOW", self.exit_prg)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)   # console extensible

        # ── Icônes (GIF natifs Ortho4XP) ─────────────────────────────
        def _load_icon(name):
            try:
                path = os.path.join(FNAMES.Utils_dir, name)
                img = tk.PhotoImage(file=path)
                # Zoom ×2 sur 4K
                if s >= 2.0:
                    img = img.zoom(2, 2)
                return img
            except:
                return None

        self.folder_icon = _load_icon("Folder.gif")
        self.earth_icon  = _load_icon("Earth.gif")
        self.loupe_icon  = _load_icon("Loupe.gif")
        self.config_icon = _load_icon("Config.gif")
        self.stop_icon   = _load_icon("Stop.gif")
        self.exit_icon   = _load_icon("Exit.gif")

        # ── FRAME TOP (lat/lon + Base Folder + boutons + steps + bars) ─
        self.frame_top = tk.Frame(self, border=4, relief=RIDGE, bg="#3b5b49")
        self.frame_top.grid(row=0, column=0, sticky=N+S+W+E)
        self.frame_top.columnconfigure(0, weight=1)

        # ── FRAME TILE (ligne 0 : lat/lon/imagery/zl + icônes) ────────
        self.frame_tile = tk.Frame(self.frame_top, border=0, padx=5, pady=5, bg="#3b5b49")
        self.frame_tile.grid(row=0, column=0, sticky=N+S+W+E)
        self.frame_tile.columnconfigure(5, weight=1)   # imagery s'étire

        self.lat = tk.StringVar()
        self.lat.trace_add("write", self.tile_change)
        tk.Label(self.frame_tile, text="Latitude:",  bg="#3b5b49", fg="#e8f0ec", font=("TkFixedFont", fs(11))).grid(row=0, column=0, padx=5, pady=5, sticky=E+W)
        self.lat_entry = tk.Entry(self.frame_tile, width=5, bg="#f0f4f2", fg="#1e3028", textvariable=self.lat)
        self.lat_entry.grid(row=0, column=1, padx=5, pady=5, sticky=W)

        self.lon = tk.StringVar()
        self.lon.trace_add("write", self.tile_change)
        tk.Label(self.frame_tile, text="Longitude:", bg="#3b5b49", fg="#e8f0ec", font=("TkFixedFont", fs(11))).grid(row=0, column=2, padx=5, pady=5, sticky=E+W)
        self.lon_entry = tk.Entry(self.frame_tile, width=5, bg="#f0f4f2", fg="#1e3028", textvariable=self.lon)
        self.lon_entry.grid(row=0, column=3, padx=5, pady=5, sticky=W)

        tk.Label(self.frame_tile, text="Imagery:", bg="#3b5b49", fg="#e8f0ec", font=("TkFixedFont", fs(11))).grid(row=0, column=4, padx=5, pady=5, sticky=E+W)
        self.default_website = tk.StringVar()
        self.default_website.trace_add("write", self.update_cfg)
        self.img_combo = ttk.Combobox(self.frame_tile, values=self.map_list,
            textvariable=self.default_website, state="readonly", width=40)
        self.img_combo.grid(row=0, column=5, padx=5, pady=5, sticky=W)

        tk.Label(self.frame_tile, text="Zoomlevel:", bg="#3b5b49", fg="#e8f0ec", font=("TkFixedFont", fs(11))).grid(row=0, column=6, padx=5, pady=5, sticky=E+W)
        self.default_zl = tk.StringVar()
        self.default_zl.trace_add("write", self.update_cfg)
        self.zl_combo = ttk.Combobox(self.frame_tile, values=self.zl_list,
            textvariable=self.default_zl, state="readonly", width=5)
        self.zl_combo.grid(row=0, column=7, padx=5, pady=5, sticky=W)

        # Icônes grandes à droite — avec fallback texte si GIF absent
        def _icon_btn(parent, icon, text_fallback, cmd, col):
            kw = dict(takefocus=False, command=cmd)
            if icon:
                kw["image"] = icon
            else:
                kw["text"] = text_fallback
                kw["width"] = 4
            ttk.Button(parent, **kw).grid(row=0, column=col, rowspan=2, padx=4, pady=2)

        _icon_btn(self.frame_tile, self.config_icon, "⚙",  self.open_config_window,   9)
        _icon_btn(self.frame_tile, self.loupe_icon,  "🔍", self.open_custom_zl_window, 10)
        _icon_btn(self.frame_tile, self.earth_icon,  "🌍", self.open_earth_window,     11)
        _icon_btn(self.frame_tile, self.stop_icon,   "🛑", self.set_red_flag,          12)
        _icon_btn(self.frame_tile, self.exit_icon,   "⏻",  self.exit_prg,             13)


        # ── FRAME FOLDER (ligne 1 : Base Folder) ──────────────────────
        self.frame_folder = tk.Frame(self.frame_top, border=0, padx=5, pady=0, bg="#3b5b49")
        self.frame_folder.grid(row=1, column=0, sticky=N+S+W+E)
        self.frame_folder.columnconfigure(1, weight=1)

        tk.Label(self.frame_folder, text="Base Folder:", bg="#3b5b49", fg="#e8f0ec").grid(row=0, column=0, padx=5, pady=5, sticky=E+W)
        self.custom_build_dir = tk.StringVar()
        self.custom_build_dir_entry = tk.Entry(self.frame_folder, bg="#f0f4f2", fg="#1e3028",
            textvariable=self.custom_build_dir)
        self.custom_build_dir_entry.grid(row=0, column=1, padx=0, pady=0, sticky=E+W)
        kw_folder = dict(takefocus=False, command=self.choose_custom_build_dir)
        if self.folder_icon:
            kw_folder["image"] = self.folder_icon
        else:
            kw_folder["text"] = "📁"; kw_folder["width"] = 4
        ttk.Button(self.frame_folder, **kw_folder).grid(row=0, column=2, padx=0, pady=0, sticky=N+S+E+W)

        # ── FRAME STEPS (ligne 2 : 5 boutons build) ───────────────────
        self.frame_steps = tk.Frame(self.frame_top, border=0, padx=5, pady=5, bg="#3b5b49")
        self.frame_steps.grid(row=2, column=0, sticky=N+S+W+E)
        for i in range(5): self.frame_steps.columnconfigure(i, weight=1)

        ttk.Button(self.frame_steps, text="Assemble Vector data", command=self.build_poly_file).grid(
            row=0, column=0, padx=5, pady=0, sticky=N+S+E+W)
        build_mesh_button = ttk.Button(self.frame_steps, text="Triangulate 3D Mesh")
        build_mesh_button.grid(row=0, column=1, padx=5, pady=0, sticky=N+S+E+W)
        build_mesh_button.bind("<ButtonPress-1>",         self.build_mesh)
        build_mesh_button.bind("<Shift-ButtonPress-1>",   self.sort_mesh)
        build_mesh_button.bind("<Control-ButtonPress-1>", self.community_mesh)
        build_masks_button = ttk.Button(self.frame_steps, text=" Draw Water Masks  ")
        build_masks_button.grid(row=0, column=2, padx=5, pady=0, sticky=N+S+E+W)
        build_masks_button.bind("<ButtonPress-1>",       self.build_masks)
        build_masks_button.bind("<Shift-ButtonPress-1>", self.build_masks)
        ttk.Button(self.frame_steps, text=" Build Imagery/DSF ", command=self.build_tile).grid(
            row=0, column=3, padx=5, pady=0, sticky=N+S+E+W)
        ttk.Button(self.frame_steps, text="    All in one     ", command=self.build_all).grid(
            row=0, column=4, padx=5, pady=0, sticky=N+S+E+W)

        # ── FRAME BARS (ligne 3 : barres de progression) ──────────────
        self.frame_bars = tk.Frame(self.frame_top, border=0, padx=5, pady=5, bg="#3b5b49")
        self.frame_bars.grid(row=3, column=0, sticky=N+S+W+E)

        self.pgrb1v = tk.IntVar()
        self.pgrb2v = tk.IntVar()
        self.pgrb3v = tk.IntVar()
        self.pgrbv = {1: self.pgrb1v, 2: self.pgrb2v, 3: self.pgrb3v}
        self.pgrb1 = ttk.Progressbar(self.frame_bars, mode="determinate", orient=HORIZONTAL, variable=self.pgrb1v)
        self.pgrb1.grid(row=0, column=0, padx=5, pady=0)
        self.pgrb2 = ttk.Progressbar(self.frame_bars, mode="determinate", orient=HORIZONTAL, variable=self.pgrb2v)
        self.pgrb2.grid(row=0, column=1, padx=5, pady=0)
        self.pgrb3 = ttk.Progressbar(self.frame_bars, mode="determinate", orient=HORIZONTAL, variable=self.pgrb3v)
        self.pgrb3.grid(row=0, column=2, padx=5, pady=0)

        # ── BARRE COLOR NORMALIZE (ligne 4 — EN BAS des boutons) ──────
        self.frame_cnorm = tk.Frame(self.frame_top, border=3, relief=RIDGE,
                                    padx=8, pady=4, bg="#3b5b49")
        self.frame_cnorm.grid(row=4, column=0, sticky=N+S+W+E)
        for i in range(8): self.frame_cnorm.columnconfigure(i, weight=1)

        # ── LIGNE 1 : Color Normalize | Enable | Strength | slider | % | Réf ──
        for i in range(6): self.frame_cnorm.columnconfigure(i, weight=1)

        tk.Label(self.frame_cnorm, text="Color Normalize", bg="#3b5b49", fg="#a6e3a1",
                 font=("TkFixedFont", fs(11), "bold"), padx=8).grid(
                 row=0, column=0, sticky=W+E, padx=4, pady=2)

        self.cnorm_enabled = tk.IntVar(value=1)
        self.cnorm_checkbox = tk.Checkbutton(self.frame_cnorm, text="Enable",
            fg="#e8f0ec", selectcolor="#2a4035",
            activeforeground="#ffffff", activebackground="#3b5b49",
            variable=self.cnorm_enabled, command=self.toggle_cnorm,
            font=("TkFixedFont", fs(11), "bold"), bg="#3b5b49")
        self.cnorm_checkbox.grid(row=0, column=1, padx=8, sticky=W)

        tk.Label(self.frame_cnorm, text="Strength:", bg="#3b5b49", fg="#e8f0ec",
                 font=("TkFixedFont", fs(11))).grid(row=0, column=2, padx=6, sticky=E)

        self.cnorm_strength = tk.IntVar(value=85)
        self.cnorm_slider = tk.Scale(self.frame_cnorm, from_=0, to=100, orient=HORIZONTAL,
            variable=self.cnorm_strength, command=self.update_cnorm_strength,
            bg="#3b5b49", fg="#e8f0ec", troughcolor="#1a2e25",
            length=int(200*s), showvalue=True)
        self.cnorm_slider.grid(row=0, column=3, padx=6, sticky=W+E)

        self.cnorm_pct_label = tk.Label(self.frame_cnorm, text="85%",
            bg="#3b5b49", fg="#a6e3a1", font=("TkFixedFont", fs(12), "bold"))
        self.cnorm_pct_label.grid(row=0, column=4, padx=6, sticky=W)

        self.cnorm_ref_label = tk.Label(self.frame_cnorm,
            text="Réf: Calibré_48753_JPG_Europe",
            bg="#3b5b49", fg="#a6e3a1",
            font=("TkFixedFont", fs(11), "bold"))
        self.cnorm_ref_label.grid(row=0, column=5, padx=10, sticky=W+E)

        # ── LIGNE 2 :  Color Check ───

               # Bouton Color Check (réduit + désactive Enable avant d'ouvrir)
        ttk.Button(self.frame_cnorm,
            text="RGB adjustments, sharpness, saturation",
            command=self.open_color_check,
            width=32).grid(row=1, column=3, padx=5, pady=(8,4))

        # ── CONSOLE (row=1 principal — extensible) ─────────────────────
        self.frame_console = tk.Frame(self, border=4, relief=RIDGE, bg="#3b5b49")
        self.frame_console.grid(row=1, column=0, sticky=N+S+W+E, padx=4, pady=4)
        self.frame_console.rowconfigure(0, weight=1)
        self.frame_console.columnconfigure(0, weight=1)
        self.console = tk.Text(self.frame_console, bd=0, font=("Courier", fs(13)))
        self.console.grid(row=0, column=0, sticky=N+S+E+W)

        # ── Queues & redirection ───────────────────────────────────────
        self.console_queue = queue.Queue()
        self.console_update()
        self.pgrb_queue = queue.Queue()
        self.pgrb_update()
        self.stdout_orig = sys.stdout
        sys.stdout = self

        # ── Restauration dernière session ──────────────────────────────
        try:
            f = open(os.path.join(FNAMES.Ortho4XP_dir, ".last_gui_params.txt"), "r")
            (lat, lon, default_website, default_zl) = f.readline().split()
            custom_build_dir = f.readline().strip()
            self.lat.set(lat); self.lon.set(lon)
            self.default_website.set(default_website); self.default_zl.set(default_zl)
            self.custom_build_dir.set(custom_build_dir)
            f.close()
        except:
            self.lat.set(48); self.lon.set(-6)
            self.default_website.set("BI"); self.default_zl.set(16)
            self.custom_build_dir.set("")

    # ── Callbacks tile_change / update_cfg (requis par .trace) ────────
    def tile_change(self, *args):
        try:
            CNORM.check_tile_change(int(self.lat.get()), int(self.lon.get()))
            self.cnorm_ref_label.config(
                text="Réf: " + (CNORM.REFERENCE_TEMP_NAME or CNORM.REFERENCE_DEFAULT_NAME),
                fg="darkorange" if CNORM.REFERENCE_TEMP else "#e8f0ec")
        except:
            pass

    def update_cfg(self, *args):
        try:
            CFG.update_tile_cfg(self)
        except:
            pass

    # ── Color Normalize ────────────────────────────────────────────────
    def toggle_cnorm(self):
        CNORM.color_normalization_enabled = bool(self.cnorm_enabled.get())

    def update_cnorm_strength(self, value):
        CNORM.CORRECTION_STRENGTH = int(value) / 100.0
        self.cnorm_pct_label.config(text=str(value) + "%")

    def open_color_check(self):
        # Désactive Color Normalize et décoche la case avant d'ouvrir
        self.cnorm_enabled.set(0)
        CNORM.color_normalization_enabled = False

        lat = int(self.lat.get() or 0)
        lon = int(self.lon.get() or 0)
        custom = self.custom_build_dir.get() or ""
        build_dir = FNAMES.build_dir(lat, lon, custom)
        CC.open_color_check(self, os.path.join(build_dir, "textures"), {"lat": lat, "lon": lon})

    # ── Icônes & navigation ────────────────────────────────────────────
    def choose_custom_build_dir(self):
        d = filedialog.askdirectory()
        if d: self.custom_build_dir.set(d + "/")

    def open_simulator_window(self):
        if hasattr(self, "_sim_win") and self._sim_win and \
                self._sim_win.winfo_exists():
            self._sim_win.lift()
            self._sim_win.focus_force()
            return
        try:
            lat = int(self.lat.get() or 46)
            lon = int(self.lon.get() or -3)
            custom = self.custom_build_dir.get() or ""
            self._sim_win = Ortho4XP_Simulator(self, lat, lon, custom)
        except Exception as e:
            messagebox.showinfo("Simulateur", f"Erreur : {e}")

    def open_config_window(self):
        # Ne pas ouvrir plusieurs fois la même fenêtre
        if hasattr(self, "_config_win") and self._config_win and                 self._config_win.winfo_exists():
            self._config_win.lift()
            self._config_win.focus_force()
            return
        try:
            self._config_win = CFG.Ortho4XP_Config(self)
        except Exception as e:
            messagebox.showinfo("Config", f"Fenêtre de configuration\n({e})")

    def open_custom_zl_window(self):
        try:
            if hasattr(self, 'custom_zl_window') and self.custom_zl_window.winfo_exists():
                self.custom_zl_window.lift()
                return
            lat = int(self.lat.get() or 48); lon = int(self.lon.get() or 6)
            self.custom_zl_window = Ortho4XP_Custom_ZL(self, lat, lon)
        except Exception as e: messagebox.showinfo("Custom ZL", f"Erreur : {e}")

    def open_earth_window(self):
        try:
            if hasattr(self, 'earth_window') and self.earth_window.winfo_exists():
                self.earth_window.lift()
                return
            lat = int(self.lat.get() or 48); lon = int(self.lon.get() or 6)
            self.earth_window = Ortho4XP_Earth_Preview(self, lat, lon)
        except Exception as e: messagebox.showinfo("Earth", f"Erreur : {e}")

    def set_red_flag(self):
        UI.red_flag = True
        messagebox.showinfo("Red Flag", "Red flag activé")

    def exit_prg(self):
        try:
            f = open(os.path.join(FNAMES.Ortho4XP_dir, ".last_gui_params.txt"), "w")
            website = self.default_website.get() or "BI"
            f.write(f"{self.lat.get()} {self.lon.get()} {website} {self.default_zl.get()}\n")
            f.write(self.custom_build_dir.get() + "\n")
            f.close()
        except: pass
        self.destroy()

    # ── Build ──────────────────────────────────────────────────────────
    def build_poly_file(self):
        threading.Thread(target=VMAP.build_poly_file, args=[self.tile_from_interface()]).start()

    def build_mesh(self, event=None):
        threading.Thread(target=MESH.build_mesh, args=[self.tile_from_interface()]).start()

    def sort_mesh(self, event=None):
        try: threading.Thread(target=MESH.sort_mesh, args=[self.tile_from_interface()]).start()
        except: pass

    def community_mesh(self, event=None):
        try: threading.Thread(target=MESH.community_mesh, args=[self.tile_from_interface()]).start()
        except: pass

    def build_masks(self, event=None):
        threading.Thread(target=MASK.build_masks, args=[self.tile_from_interface()]).start()

    def build_tile(self):
        threading.Thread(target=TILE.build_tile, args=[self.tile_from_interface()]).start()

    def build_all(self):
        threading.Thread(target=TILE.build_all, args=[self.tile_from_interface()]).start()

    def get_lat_lon(self):
        lat = int(self.lat.get() or 48)
        lon = int(self.lon.get() or -6)
        return (lat, lon)

    def tile_from_interface(self):
        lat = int(self.lat.get() or 48)
        lon = int(self.lon.get() or -6)
        tile = CFG.Tile(lat, lon, self.custom_build_dir.get() or "")
        tile.default_website = self.default_website.get() or "BI"
        tile.default_zl = int(self.default_zl.get() or 16)
        return tile

    # ── Console & progress ─────────────────────────────────────────────
    def write(self, line):
        self.console_queue.put(line)

    def console_update(self):
        try:
            while True:
                line = self.console_queue.get_nowait()
                self.console.insert(END, str(line))
                self.console.see(END)
        except queue.Empty:
            pass
        self.after(100, self.console_update)

    def pgrb_update(self):
        try:
            while True:
                (bar_id, value) = self.pgrb_queue.get_nowait()
                if bar_id in self.pgrbv:
                    self.pgrbv[bar_id].set(value)
        except queue.Empty:
            pass
        self.after(100, self.pgrb_update)

if __name__ == "__main__":
    Ortho4XP_GUI().mainloop()

class Ortho4XP_Custom_ZL(tk.Toplevel):

    dico_color = {
        15: "#4a9e8e",   # bleu-vert Roland foncé
        16: "#5ab88a",   # vert Roland moyen
        17: "#7eca7e",   # vert Roland
        18: "#a6d96a",   # vert Roland clair
        19: "#c8e65a",   # vert-jaune Roland très clair
    }
    zl_list = ["10", "11", "12", "13"]
    points = []
    coords = []
    polygon_list = []
    polyobj_list = []

    def __init__(self, parent, lat, lon):
        self.parent = parent
        self.lat = lat
        self.lon = lon
        def _in_gui(p):
            if isinstance(p, dict): return p.get("in_GUI", True)
            return getattr(p, "in_GUI", True)
        self.map_list = sorted(
            [
                provider_code
                for provider_code in set(IMG.providers_dict)
                if _in_gui(IMG.providers_dict[provider_code])
            ]
            + sorted(set(IMG.combined_providers_dict))
        )
        self.map_list = [
            provider_code
            for provider_code in self.map_list
            if provider_code != "SEA"
        ]
        self.reduced_map_list = [
            provider_code
            for provider_code in self.map_list
            if provider_code != "OSM"
        ]
        self.points = []
        self.coords = []
        self.polygon_list = []
        self.polyobj_list = []

        # Init valeurs par défaut — seront recalculées à chaque preview_tile
        self.xmin = 0
        self.ymin = 0
        self.xmax = 256
        self.ymax = 256
        self.zoomlevel = 11
        self.poly_curr = None

        tk.Toplevel.__init__(self)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.title("Preview / Custom zoomlevels")
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # Constants

        self.map_choice = tk.StringVar()
        self.map_choice.set("OSM")
        self.zl_choice = tk.StringVar()
        self.zl_choice.set("11")
        self.progress_preview = tk.IntVar()
        self.progress_preview.set(0)
        self.zmap_choice = tk.StringVar()
        self.zmap_choice.set(self.parent.default_website.get())

        self.zlpol = tk.IntVar()
        try:  # default_zl might still be empty
            self.zlpol.set(
                max(min(int(self.parent.default_zl.get()) + 1, 19), 15)
            )
        except:
            self.zlpol.set(17)
        self.gb = tk.StringVar()
        self.gb.set("0Gb")

        # Frames
        self.frame_left = tk.Frame(
            self, border=4, relief=RIDGE, bg="#3b5b49"
        )
        self.frame_left.grid(row=0, column=0, sticky=N + S + W + E)

        self.frame_right = tk.Frame(
            self, border=4, relief=RIDGE, bg="#3b5b49"
        )
        self.frame_right.grid(row=0, column=1, sticky=N + S + W + E)
        self.frame_right.rowconfigure(0, weight=1)
        self.frame_right.columnconfigure(0, weight=1)

        # Widgets
        row = 0
        tk.Label(
            self.frame_left,
            anchor=W,
            text="Preview params ",
            fg="#a6e3a1",
            bg="#2a4035",
            font="Helvetica 16 bold italic",
        ).grid(row=row, column=0, sticky=W + E)
        row += 1

        tk.Label(
            self.frame_left, anchor=W, text="Source : ", bg="#3b5b49", fg="#e8f0ec")
        self.map_combo = ttk.Combobox(
            self.frame_left,
            textvariable=self.map_choice,
            values=self.map_list,
            width=40,
            state="readonly",
        )
        self.map_combo.grid(row=row, column=0, padx=5, pady=3, sticky=E)
        row += 1

        tk.Label(
            self.frame_left, anchor=W, text="Zoomlevel : ", bg="#3b5b49", fg="#e8f0ec")
        self.zl_combo = ttk.Combobox(
            self.frame_left,
            textvariable=self.zl_choice,
            values=self.zl_list,
            width=3,
            state="readonly",
        )
        self.zl_combo.grid(row=2, column=0, padx=5, pady=3, sticky=E)
        row += 1

        ttk.Button(
            self.frame_left,
            text="Preview",
            command=lambda: self.preview_tile(lat, lon),
        ).grid(row=row, padx=5, column=0, sticky=N + S + E + W)
        row += 1
        tk.Label(
            self.frame_left,
            anchor=W,
            text="Zone params ",
            fg="#a6e3a1",
            bg="#2a4035",
            font="Helvetica 16 bold italic",
        ).grid(row=row, column=0, pady=10, sticky=W + E)
        row += 1

        tk.Label(
            self.frame_left, anchor=W, text="Source : ", bg="#3b5b49", fg="#e8f0ec")
        self.zmap_combo = ttk.Combobox(
            self.frame_left,
            textvariable=self.zmap_choice,
            values=self.reduced_map_list,
            width=40,
            state="readonly",
        )
        self.zmap_combo.grid(row=row, column=0, padx=5, pady=10, sticky=E)
        row += 1

        self.frame_zlbtn = tk.Frame(self.frame_left, border=0, bg="#3b5b49")
        for i in range(5):
            self.frame_zlbtn.columnconfigure(i, weight=1)
        self.frame_zlbtn.grid(
            row=row, column=0, columnspan=1, sticky=N + S + W + E
        )
        row += 1
        for zl in range(15, 20):
            col = zl - 15
            tk.Radiobutton(
                self.frame_zlbtn,
                bd=2,
                bg=self.dico_color[zl],
                activebackground=self.dico_color[zl],
                selectcolor=self.dico_color[zl],
                fg="#ffffff",
                activeforeground="#ffffff",
                font=("Arial", 11, "bold"),
                relief="flat",
                height=2,
                indicatoron=0,
                text="ZL" + str(zl),
                variable=self.zlpol,
                value=zl,
                command=self.redraw_poly,
            ).grid(row=0, column=col, padx=1, pady=1, sticky=N + S + E + W)

        tk.Label(
            self.frame_left,
            anchor=W,
            text="Approx. Add. Size : ",
            bg="#3b5b49", fg="#e8f0ec").grid(row=row, column=0, padx=5, pady=10, sticky=W)
        tk.Entry(
            self.frame_left,
            width=7,
            justify=RIGHT,
            bg="#1a2e25",
            fg="#a6e3a1",
            textvariable=self.gb,
        ).grid(row=row, column=0, padx=5, pady=10, sticky=E)
        row += 1

        ttk.Button(
            self.frame_left, text="  Save zone  ", command=self.save_zone_cmd
        ).grid(row=row, column=0, padx=5, pady=3, sticky=N + S + E + W)
        row += 1
        ttk.Button(
            self.frame_left, text="Delete ZL zone", command=self.delete_zone_cmd
        ).grid(row=row, column=0, padx=5, pady=3, sticky=N + S + E + W)
        row += 1
        ttk.Button(
            self.frame_left,
            text="Make GeoTiffs",
            command=self.build_geotiffs_ifc,
        ).grid(row=row, column=0, padx=5, pady=3, sticky=N + S + E + W)
        row += 1
        ttk.Button(
            self.frame_left, text="Extract Mesh ", command=self.extract_mesh_ifc
        ).grid(row=row, column=0, padx=5, pady=3, sticky=N + S + E + W)
        row += 1
        tk.Label(
            self.frame_left,
            text="Ctrl+B1 : add texture\nShift+B1: add zone point\n" + \
                 "Ctrl+B2 : delete zone",
            bg="#3b5b49",
            justify=LEFT, fg="#e8f0ec").grid(row=row, column=0, padx=5, pady=20, sticky=N + S + E + W)
        row += 1
        ttk.Button(
            self.frame_left, text="    Apply    ", command=self.save_zone_list
        ).grid(row=row, column=0, padx=5, pady=3, sticky=N + S + E + W)
        row += 1
        ttk.Button(
            self.frame_left, text="    Reset    ", command=self.delAll
        ).grid(row=row, column=0, padx=5, pady=3, sticky=N + S + E + W)
        row += 1
        ttk.Button(
            self.frame_left, text="    Exit     ", command=self.destroy
        ).grid(row=row, column=0, padx=5, pady=3, sticky=N + S + E + W)
        row += 1
        self.canvas = tk.Canvas(self.frame_right, bd=0, height=750, width=750)
        self.canvas.grid(row=0, column=0, sticky=N + S + E + W)

    def preview_tile(self, lat, lon):
        # Recharger les zones depuis le .cfg de la tuile
        try:
            _tile = CFG.Tile(lat, lon,
                             self.parent.custom_build_dir.get()
                             if hasattr(self.parent, "custom_build_dir") else "")
            _tile.read_from_config()
            CFG.zone_list = _tile.zone_list
        except Exception:
            pass
        self.zoomlevel = int(self.zl_combo.get())
        zoomlevel = self.zoomlevel
        provider_code = self.map_combo.get()
        (tilxleft, tilytop) = GEO.wgs84_to_gtile(lat + 1, lon, zoomlevel)
        (self.latmax, self.lonmin) = GEO.gtile_to_wgs84(
            tilxleft, tilytop, zoomlevel
        )
        (self.xmin, self.ymin) = GEO.wgs84_to_pix(
            self.latmax, self.lonmin, zoomlevel
        )
        (tilxright, tilybot) = GEO.wgs84_to_gtile(lat, lon + 1, zoomlevel)
        (self.latmin, self.lonmax) = GEO.gtile_to_wgs84(
            tilxright + 1, tilybot + 1, zoomlevel
        )
        (self.xmax, self.ymax) = GEO.wgs84_to_pix(
            self.latmin, self.lonmax, zoomlevel
        )
        filepreview = FNAMES.preview(lat, lon, zoomlevel, provider_code)
        if os.path.isfile(filepreview) != True:
            fargs_ctp = [lat, lon, zoomlevel, provider_code]
            self.ctp_thread = threading.Thread(
                target=IMG.create_tile_preview, args=fargs_ctp
            )
            self.ctp_thread.start()
            fargs_dispp = [filepreview, lat, lon]
            dispp_thread = threading.Thread(
                target=self.show_tile_preview, args=fargs_dispp
            )
            dispp_thread.start()
        else:
            # Fond de carte en cache : lancer show_tile_preview en thread
            # pour que tag_raise() des aéroports OACI fonctionne correctement
            threading.Thread(
                target=self.show_tile_preview,
                args=(filepreview, lat, lon),
                daemon=True
            ).start()
        return

    def show_tile_preview(self, filepreview, lat, lon):
        for item in self.polyobj_list:
            try:
                self.canvas.delete(item)
            except:
                pass
        try:
            self.canvas.delete(self.img_map)
        except:
            pass
        try:
            self.canvas.delete(self.boundary)
        except:
            pass
        try:
            self.ctp_thread.join()
        except:
            pass
        # Attendre que le fichier existe (max 30s)
        import time
        for _ in range(60):
            if os.path.isfile(filepreview):
                break
            time.sleep(0.5)
        if not os.path.isfile(filepreview):
            UI.vprint(0, "Preview non générée :", filepreview)
            return
        self.image = Image.open(filepreview)
        self.photo = ImageTk.PhotoImage(self.image)
        self.map_x_res = self.photo.width()
        self.map_y_res = self.photo.height()
        self.img_map = self.canvas.create_image(
            0, 0, anchor=NW, image=self.photo
        )
        self.canvas.config(scrollregion=self.canvas.bbox(ALL))
        if "dar" in sys.platform:
            self.canvas.bind("<ButtonPress-2>", self.scroll_start)
            self.canvas.bind("<B2-Motion>", self.scroll_move)
            self.canvas.bind("<Control-ButtonPress-2>", self.delPol)
        else:
            self.canvas.bind("<ButtonPress-3>", self.scroll_start)
            self.canvas.bind("<B3-Motion>", self.scroll_move)
            self.canvas.bind("<Control-ButtonPress-3>", self.delPol)
        # Déplacement carte → bouton DROIT (Button-3 / B3-Motion)
        # Bouton gauche réservé aux actions (newPoint, newPol, etc.)
        self.canvas.bind("<ButtonPress-3>", self.scroll_start)
        self.canvas.bind("<B3-Motion>", self.scroll_move)
        self.canvas.bind("<Shift-ButtonPress-1>", self.newPoint)
        self.canvas.bind("<Control-Shift-ButtonPress-1>", self.newPointGrid)
        self.canvas.bind("<Control-ButtonPress-1>", self.newPol)
        self.canvas.bind("<ButtonPress-1>", self.newPoint)
        # Note : clic gauche simple = newPoint (glisser = pas de déplacement accidentel)
        self.canvas.focus_set()
        self.canvas.bind("p", self.newPoint)
        self.canvas.bind("d", self.delete_zone_cmd)
        self.canvas.bind("n", self.save_zone_cmd)
        self.canvas.bind("<BackSpace>", self.delLast)
        self.polygon_list = []
        self.polyobj_list = []
        self.poly_curr = []
        bdpoints = []
        for [latp, lonp] in [
            [lat, lon],
            [lat, lon + 1],
            [lat + 1, lon + 1],
            [lat + 1, lon],
        ]:
            [x, y] = self.latlon_to_xy(latp, lonp, self.zoomlevel)
            bdpoints += [int(x), int(y)]
        self.boundary = self.canvas.create_polygon(
            bdpoints, outline="black", fill="", width=2
        )
        for zone in CFG.zone_list:
            self.coords = zone[0][0:-2]
            self.zlpol.set(zone[1])
            self.zmap_combo.set(zone[2])
            self.points = []
            for idxll in range(0, len(self.coords) // 2):
                latp = self.coords[2 * idxll]
                lonp = self.coords[2 * idxll + 1]
                [x, y] = self.latlon_to_xy(latp, lonp, self.zoomlevel)
                self.points += [int(x), int(y)]
            self.redraw_poly()
            self.save_zone_cmd()
        # ── Overlay aeroports via Overpass ────────────────────────────────
        self._airports_pending = []
        self._airports_drawn   = False
        self._airports_retry   = 0
        threading.Thread(
            target=self._fetch_airports_overpass,
            args=(lat, lon),
            daemon=True
        ).start()
        self.canvas.after(500, self._draw_airports_when_ready)
        # ──────────────────────────────────────────────────────────────────
        return

    def _fetch_airports_overpass(self, lat, lon):
        import urllib.request, json
        q = (
            "[out:json][timeout:25];("
            + 'node["aeroway"="aerodrome"](%d,%d,%d,%d);' % (lat, lon, lat+1, lon+1)
            + 'way["aeroway"="aerodrome"](%d,%d,%d,%d);'  % (lat, lon, lat+1, lon+1)
            + 'rel["aeroway"="aerodrome"](%d,%d,%d,%d);'  % (lat, lon, lat+1, lon+1)
            + ");out center;"
        )
        servers = [
            "https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter",
            "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
        ]
        data = None
        for server in servers:
            try:
                req = urllib.request.Request(
                    server,
                    data=q.encode("utf-8"),
                    headers={"User-Agent": "Ortho4XP/2.0 airport-preview"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.loads(r.read().decode("utf-8"))
                break
            except Exception as e:
                print(f"Overpass {server}: {e}")
                continue
        if not data:
            return
        result = []
        for el in data.get("elements", []):
            tags = el.get("tags", {})
            if el["type"] == "node":
                alat, alon = el["lat"], el["lon"]
            else:
                c = el.get("center", {})
                if not c:
                    continue
                alat, alon = c["lat"], c["lon"]
            icao  = tags.get("icao") or tags.get("iata") or tags.get("ref") or ""
            name  = tags.get("name", "")
            label = icao if icao else (name[:14] if name else "APT")
            result.append((alat, alon, label))
        self._airports_pending = result

    def _draw_airports_when_ready(self):
        """Appelé depuis canvas.after() → thread principal tkinter.
        Attend que les données Overpass soient disponibles puis dessine.
        Sécurisé même si show_tile_preview tourne dans un thread secondaire.
        """
        if self._airports_drawn:
            return
        if not self._airports_pending:
            self._airports_retry += 1
            if self._airports_retry < 120:  # 60s max (120 × 500ms)
                self.canvas.after(500, self._draw_airports_when_ready)
            return
        self._airports_drawn = True
        new_items = []
        for (alat, alon, label) in self._airports_pending:
            try:
                px, py = self.latlon_to_xy(alat, alon, self.zoomlevel)
                r = 13
                new_items.append(self.canvas.create_oval(
                    px-r, py-r, px+r, py+r,
                    outline="#FFD700", fill="#333333", width=2))
                new_items.append(self.canvas.create_text(
                    px, py, text="✈",
                    fill="#FFD700", font=("Arial", 11, "bold"), anchor="center"))
                new_items.append(self.canvas.create_text(
                    px+1, py+r+4, text=label,
                    fill="#000000", font=("Arial", 8, "bold"), anchor="n"))
                new_items.append(self.canvas.create_text(
                    px, py+r+3, text=label,
                    fill="#FFD700", font=("Arial", 8, "bold"), anchor="n"))
            except Exception as e:
                print(f"Draw error {label}: {e}")
                continue
        # tag_raise via after(0) pour thread-safety tkinter
        def _raise_all():
            for item in new_items:
                try:
                    self.canvas.tag_raise(item)
                except Exception:
                    pass
        self.canvas.after(0, _raise_all)
        self.polyobj_list += new_items

    def scroll_start(self, event):
        self.canvas.focus_set()
        self.canvas.scan_mark(event.x, event.y)
        return

    def scroll_move(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)
        return

    def redraw_poly(self):
        try:
            self.canvas.delete(self.poly_curr)
        except:
            pass
        try:
            color = self.dico_color[self.zlpol.get()]
            if len(self.points) >= 4:
                self.poly_curr = self.canvas.create_polygon(
                    self.points, outline="#742374", fill="", width=2
                )
            else:
                self.poly_curr = self.canvas.create_polygon(
                    self.points, outline=color, fill="", width=5
                )
        except:
            pass
        return

    def newPoint(self, event):
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        self.points += [x, y]
        [latp, lonp] = self.xy_to_latlon(x, y, self.zoomlevel)
        self.coords += [latp, lonp]
        self.redraw_poly()
        return

    def newPointGrid(self, event):
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        [latp, lonp] = self.xy_to_latlon(x, y, self.zoomlevel)
        [a, b] = GEO.wgs84_to_orthogrid(latp, lonp, self.zlpol.get())
        [aa, bb] = GEO.wgs84_to_gtile(latp, lonp, self.zlpol.get())
        a = a + 16 if aa - a >= 8 else a
        b = b + 16 if bb - b >= 8 else b
        [latp, lonp] = GEO.gtile_to_wgs84(a, b, self.zlpol.get())
        self.coords += [latp, lonp]
        [x, y] = self.latlon_to_xy(latp, lonp, self.zoomlevel)
        self.points += [int(x), int(y)]
        self.redraw_poly()
        return

    def newPol(self, event):
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        [latp, lonp] = self.xy_to_latlon(x, y, self.zoomlevel)
        [a, b] = GEO.wgs84_to_orthogrid(latp, lonp, self.zlpol.get())
        [latmax, lonmin] = GEO.gtile_to_wgs84(a, b, self.zlpol.get())
        [latmin, lonmax] = GEO.gtile_to_wgs84(a + 16, b + 16, self.zlpol.get())
        self.coords = [
            latmin,
            lonmin,
            latmin,
            lonmax,
            latmax,
            lonmax,
            latmax,
            lonmin,
        ]
        self.points = []
        for i in range(4):
            [x, y] = self.latlon_to_xy(
                self.coords[2 * i], self.coords[2 * i + 1], self.zoomlevel
            )
            self.points += [int(x), int(y)]
        self.redraw_poly()
        self.save_zone_cmd()
        return

    def delPol(self, event):
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        copy = self.polygon_list[:]
        for poly in copy:
            if poly[2] != self.zlpol.get():
                continue
            if VECT.point_in_polygon([x, y], poly[0]):
                idx = self.polygon_list.index(poly)
                self.polygon_list.pop(idx)
                self.canvas.delete(self.polyobj_list[idx])
                self.polyobj_list.pop(idx)
        return

    def delAll(self):
        copy = self.polygon_list[:]
        for poly in copy:
            idx = self.polygon_list.index(poly)
            self.polygon_list.pop(idx)
            self.canvas.delete(self.polyobj_list[idx])
            self.polyobj_list.pop(idx)
        try:
            self.canvas.delete(self.poly_curr)
        except:
            pass
        self.compute_size()
        return

    def xy_to_latlon(self, x, y, zoomlevel):
        pix_x = x + self.xmin
        pix_y = y + self.ymin
        return GEO.pix_to_wgs84(pix_x, pix_y, zoomlevel)

    def latlon_to_xy(self, lat, lon, zoomlevel):
        [pix_x, pix_y] = GEO.wgs84_to_pix(lat, lon, zoomlevel)
        return [pix_x - self.xmin, pix_y - self.ymin]

    def delLast(self, event):
        self.points = self.points[0:-2]
        self.coords = self.coords[0:-2]
        self.redraw_poly()
        return

    def compute_size(self):
        total_size = 0
        for polygon in self.polygon_list:
            polyp = polygon[0] + polygon[0][0:2]
            area = 0
            x1 = polyp[0]
            y1 = polyp[1]
            for j in range(1, len(polyp) // 2):
                x2 = polyp[2 * j]
                y2 = polyp[2 * j + 1]
                area += (x2 - x1) * (y2 + y1)
                x1 = x2
                y1 = y2
            total_size += (
                abs(area)
                / 2
                * (
                    (
                        40000
                        * cos(pi / 180 * polygon[1][0])
                        / 2 ** (int(self.zl_combo.get()) + 8)
                    )
                    ** 2
                )
                * 2 ** (2 * (int(polygon[2]) - 17))
                / 1024
            )
        self.gb.set("{:.1f}".format(total_size) + "Gb")
        return

    def save_zone_cmd(self):
        if len(self.points) < 6:
            return
        self.polyobj_list.append(self.poly_curr)
        self.polygon_list.append(
            [self.points, self.coords, self.zlpol.get(), self.zmap_combo.get()]
        )
        self.compute_size()
        self.poly_curr = []
        self.points = []
        self.coords = []
        return

    def build_geotiffs_ifc(self):
        texture_attributes_list = []
        fake_zone_list = []
        for polygon in self.polygon_list:
            lat_bar = (polygon[1][0] + polygon[1][4]) / 2
            lon_bar = (polygon[1][1] + polygon[1][3]) / 2
            zoomlevel = int(polygon[2])
            provider_code = polygon[3]
            til_x_left, til_y_top = GEO.wgs84_to_orthogrid(
                lat_bar, lon_bar, zoomlevel
            )
            texture_attributes_list.append(
                (til_x_left, til_y_top, zoomlevel, provider_code)
            )
            fake_zone_list.append(("", "", provider_code))
        UI.vprint(1, "\nBuilding geotiffs.\n------------------\n")
        tile = CFG.Tile(self.lat, self.lon, "")
        tile.zone_list = fake_zone_list
        IMG.initialize_local_combined_providers_dict(tile)
        fargs_build_geotiffs = [tile, texture_attributes_list]
        build_geotiffs_thread = threading.Thread(
            target=IMG.build_geotiffs, args=fargs_build_geotiffs
        )
        build_geotiffs_thread.start()
        return

    def extract_mesh_ifc(self):
        polygon = self.polygon_list[0]
        lat_bar = (polygon[1][0] + polygon[1][4]) / 2
        lon_bar = (polygon[1][1] + polygon[1][3]) / 2
        zoomlevel = int(polygon[2])
        provider_code = polygon[3]
        til_x_left, til_y_top = GEO.wgs84_to_orthogrid(
            lat_bar, lon_bar, zoomlevel
        )
        build_dir = FNAMES.build_dir(
            self.lat, self.lon, self.parent.custom_build_dir.get()
        )
        mesh_file = FNAMES.mesh_file(build_dir, self.lat, self.lon)
        UI.vprint(
            1,
            "Extracting part of ",
            mesh_file,
            "to",
            FNAMES.obj_file(til_x_left, til_y_top, zoomlevel, provider_code),
            "(Wavefront)",
        )
        fargs_extract_mesh = [
            mesh_file,
            til_x_left,
            til_y_top,
            zoomlevel,
            provider_code,
        ]
        extract_mesh_thread = threading.Thread(
            target=MESH.extract_mesh_to_obj, args=fargs_extract_mesh
        )
        extract_mesh_thread.start()
        return

    def delete_zone_cmd(self):
        try:
            self.canvas.delete(self.poly_curr)
            self.poly_curr = self.polyobj_list[-1]
            self.points = self.polygon_list[-1][0]
            self.coords = self.polygon_list[-1][1]
            self.zlpol.set(self.polygon_list[-1][2])
            self.zmap_combo.set(self.polygon_list[-1][3])
            self.polygon_list.pop(-1)
            self.polyobj_list.pop(-1)
            self.compute_size()
        except:
            self.points = []
            self.coords = []
        return

    def save_zone_list(self):
        ordered_list = sorted(
            self.polygon_list, key=lambda item: item[2], reverse=True
        )
        zone_list = []
        for item in ordered_list:
            tmp = []
            for pt in item[1]:
                tmp.append(pt)
            for pt in item[1][
                0:2
            ]:  # repeat first point for point_in_polygon algo
                tmp.append(pt)
            zone_list.append([tmp, item[2], item[3]])
        CFG.zone_list = zone_list
        # Sauvegarde dans le fichier .cfg de la tuile
        # → les zones sont rechargées au prochain démarrage
        # → makedirs garantit que le dossier existe même avant le premier build
        try:
            tile = CFG.Tile(self.lat, self.lon,
                            self.parent.custom_build_dir.get()
                            if hasattr(self.parent, "custom_build_dir") else "")
            tile.zone_list = zone_list
            # Créer le dossier build_dir si nécessaire avant d'écrire le cfg
            import os as _os
            _os.makedirs(tile.build_dir, exist_ok=True)
            tile.write_to_config()
            UI.vprint(1, f"Zones sauvegardées dans cfg tuile {self.lat},{self.lon}")
        except Exception as e:
            UI.vprint(0, f"Avertissement save_zone_list: {e}")
        return

################################################################################
class Ortho4XP_Earth_Preview(tk.Toplevel):

    earthzl = 6
    resolution = 2 ** earthzl * 256

    list_del_ckbtn = [
        "OSM data",
        "Mask data",
        "Jpeg imagery",
        "Tile (whole)",
        "Tile (textures)",
    ]
    list_do_ckbtn = [
        "Assemble vector data",
        "Triangulate 3D mesh",
        "Draw water masks",
        "Build imagery/DSF",
        "Extract overlays",
        "Read per tile cfg",
    ]

    canvas_min_x = 900
    canvas_min_y = 700

    def __init__(self, parent, lat, lon):
        tk.Toplevel.__init__(self)
        self.title("Tiles collection and management")
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # Parent derived data
        self.parent = parent
        self.set_working_dir()

        # Constants/Variable
        self.dico_tiles_todo = {}
        self.dico_tiles_done = {}
        self.v_ = {}
        for item in self.list_del_ckbtn + self.list_do_ckbtn:
            self.v_[item] = tk.IntVar()
        self.latlon = tk.StringVar()

        # Frames
        self.frame_left = tk.Frame(
            self, border=4, relief=RIDGE, bg="#3b5b49"
        )
        self.frame_left.grid(row=0, column=0, sticky=N + S + W + E)
        self.frame_right = tk.Frame(
            self, border=4, relief=RIDGE, bg="#3b5b49"
        )
        self.frame_right.grid(row=0, rowspan=60, column=1, sticky=N + S + W + E)
        self.frame_right.rowconfigure(0, weight=1, minsize=self.canvas_min_y)
        self.frame_right.columnconfigure(0, weight=1, minsize=self.canvas_min_x)

        # Widgets
        row = 0
        tk.Label(
            self.frame_left,
            anchor=W,
            text="Active tile",
            fg="#a6e3a1",
            bg="#2a4035",
            font="Helvetica 16 bold italic",
        ).grid(row=row, column=0, sticky=W + E)
        row += 1
        self.latlon_entry = tk.Entry(
            self.frame_left,
            width=8,
            bg="#1a2e25",
            fg="#a6e3a1",
            textvariable=self.latlon,
        )
        self.latlon_entry.grid(row=row, column=0, padx=5, pady=5, sticky=N + S)
        row += 1
        # Trash
        tk.Label(
            self.frame_left,
            anchor=W,
            text="Erase cached data",
            fg="#a6e3a1",
            bg="#2a4035",
            font="Helvetica 16 bold italic",
        ).grid(row=row, column=0, sticky=W + E)
        row += 1
        for item in self.list_del_ckbtn:
            tk.Checkbutton(
                self.frame_left,
                text=item,
                anchor=W,
                variable=self.v_[item],
                bg="#3b5b49",
                fg="#e8f0ec",
                selectcolor="#2a4035",
                activebackground="#3b5b49",
                activeforeground="#ffffff",
                highlightthickness=0,
            ).grid(row=row, column=0, padx=5, pady=5, sticky=N + S + E + W)
            row += 1
        ttk.Button(
            self.frame_left, text="  Delete    ", command=self.trash
        ).grid(row=row, column=0, padx=5, pady=5, sticky=N + S + E + W)
        row += 1
        # Batch build
        tk.Label(
            self.frame_left,
            anchor=W,
            text="Batch build tiles",
            fg="#a6e3a1",
            bg="#2a4035",
            font="Helvetica 16 bold italic",
        ).grid(row=row, column=0, sticky=W + E)
        row += 1
        for item in self.list_do_ckbtn:
            tk.Checkbutton(
                self.frame_left,
                text=item,
                anchor=W,
                variable=self.v_[item],
                bg="#3b5b49",
                fg="#e8f0ec",
                selectcolor="#2a4035",
                activebackground="#3b5b49",
                activeforeground="#ffffff",
                highlightthickness=0,
            ).grid(row=row, column=0, padx=5, pady=5, sticky=N + S + E + W)
            row += 1
        ttk.Button(
            self.frame_left, text="  Batch Build   ", command=self.batch_build
        ).grid(row=row, column=0, padx=5, pady=5, sticky=N + S + E + W)
        row += 1
        # Refresh window
        ttk.Button(
            self.frame_left, text="    Refresh     ", command=self.refresh
        ).grid(row=row, column=0, padx=5, pady=5, sticky=N + S + E + W)
        row += 1
        # Exit
        ttk.Button(
            self.frame_left, text="      Exit      ", command=self.exit
        ).grid(row=row, column=0, padx=5, pady=5, sticky=N + S + E + W)
        row += 1
        tk.Label(
            self.frame_left,
            text="Shortcuts :\n-----------------\nB2-press+hold=move map\n" + \
                 "B1-double-click=select active\n" + \
                 "Shift+B1=add to batch build\nCtrl+B1=link in Custom Scenery",
            bg="#3b5b49", fg="#e8f0ec").grid(row=row, column=0, padx=0, pady=5, sticky=N + S + E + W)
        row += 1

        self.canvas = tk.Canvas(self.frame_right, bd=0)
        self.canvas.grid(row=0, column=0, sticky=N + S + E + W)

        self.canvas.config(
            scrollregion=(
                1,
                1,
                2 ** self.earthzl * 256 - 1,
                2 ** self.earthzl * 256 - 1,
            )
        )  # self.canvas.bbox(ALL))
        (x0, y0) = GEO.wgs84_to_pix(lat + 0.5, lon + 0.5, self.earthzl)
        x0 = max(1, x0 - self.canvas_min_x / 2)
        y0 = max(1, y0 - self.canvas_min_y / 2)
        self.canvas.xview_moveto(x0 / self.resolution)
        self.canvas.yview_moveto(y0 / self.resolution)
        self.nx0 = int((8 * x0) // self.resolution)
        self.ny0 = int((8 * y0) // self.resolution)
        if "dar" in sys.platform:
            self.canvas.bind("<ButtonPress-2>", self.scroll_start)
            self.canvas.bind("<B2-Motion>", self.scroll_move)
        else:
            self.canvas.bind("<ButtonPress-3>", self.scroll_start)
            self.canvas.bind("<B3-Motion>", self.scroll_move)
        self.canvas.bind("<Double-Button-1>", self.select_tile)
        self.canvas.bind("<Shift-ButtonPress-1>", self.add_tile)
        self.canvas.bind("<Control-ButtonPress-1>", self.toggle_to_custom)
        # Refocus automatique au survol — ne pas binder ButtonPress-1
        # car il interfère avec Double-Button-1 sur macOS
        self.canvas.bind("<Enter>", lambda e: self.canvas.focus_set())
        self.canvas.focus_set()
        self.draw_canvas(self.nx0, self.ny0)
        self.active_lat = lat
        self.active_lon = lon
        self.latlon.set(FNAMES.short_latlon(self.active_lat, self.active_lon))
        [x0, y0] = GEO.wgs84_to_pix(
            self.active_lat + 1, self.active_lon, self.earthzl
        )
        [x1, y1] = GEO.wgs84_to_pix(
            self.active_lat, self.active_lon + 1, self.earthzl
        )
        self.active_tile = self.canvas.create_rectangle(
            x0, y0, x1, y1, fill="", outline="yellow", width=3
        )
        self.threaded_preview()
        return

    def set_working_dir(self):
        self.custom_build_dir = self.parent.custom_build_dir.get()
        self.grouped = (
            self.custom_build_dir and self.custom_build_dir[-1] != "/"
        )
        self.working_dir = (
            self.custom_build_dir if self.custom_build_dir else FNAMES.Tile_dir
        )

    def refresh(self):
        self.set_working_dir()
        self.threaded_preview()
        return

    def threaded_preview(self):
        threading.Thread(target=self.preview_existing_tiles).start()

    def preview_existing_tiles(self):
        dico_color = {
            11: "#1e3028",
            12: "#1e3028",
            13: "#1e3028",
            14: "#1e3028",
            15: "cyan",
            16: "#50fa7b",
            17: "yellow",
            18: "orange",
            19: "red",
        }
        if self.dico_tiles_done:
            for tile in self.dico_tiles_done:
                for objid in self.dico_tiles_done[tile][:2]:
                    self.canvas.delete(objid)
            self.dico_tiles_done = {}
        if not self.grouped:
            for dir_name in os.listdir(self.working_dir):
                if "XP_" in dir_name:
                    try:
                        lat = int(dir_name.split("XP_")[1][:3])
                        lon = int(dir_name.split("XP_")[1][3:7])
                    except:
                        continue
                    # With the enlarged accepetance rule for directory name 
                    # there might be more than one tile for the same (lat,lon),
                    # we skip all but the first encountered.
                    if (lat, lon) in self.dico_tiles_done:
                        continue
                    [x0, y0] = GEO.wgs84_to_pix(lat + 1, lon, self.earthzl)
                    [x1, y1] = GEO.wgs84_to_pix(lat, lon + 1, self.earthzl)
                    if os.path.isfile(
                        os.path.join(
                            self.working_dir,
                            dir_name,
                            "Earth nav data",
                            FNAMES.long_latlon(lat, lon) + ".dsf",
                        )
                    ):
                        color = "#1e3028"
                        content = ""
                        try:
                            tmpf = open(
                                os.path.join(
                                    self.working_dir,
                                    dir_name,
                                    "Ortho4XP_"
                                    + FNAMES.short_latlon(lat, lon)
                                    + ".cfg",
                                ),
                                "r",
                                encoding="latin-1",
                            )
                            found_config = True
                        except:
                            try:
                                tmpf = open(
                                    os.path.join(
                                        self.working_dir,
                                        dir_name,
                                        "Ortho4XP.cfg",
                                    ),
                                    "r",
                                    encoding="latin-1",
                                )
                                found_config = True
                            except:
                                found_config = False
                        if found_config:
                            prov = zl = ""
                            for line in tmpf.readlines():
                                if line[:15] == "default_website":
                                    prov = line.strip().split("=")[1][:4]
                                elif line[:10] == "default_zl":
                                    zl = int(line.strip().split("=")[1])
                                    break
                            tmpf.close()
                            if not prov:
                                prov = "?"
                            if zl:
                                color = dico_color[zl]
                            else:
                                zl = "?"
                            content = prov + "\n" + str(zl)
                        else:
                            content = "?"
                        self.dico_tiles_done[(lat, lon)] = (
                            self.canvas.create_rectangle(
                                x0, y0, x1, y1, fill=color, stipple="gray12"
                            )
                            if not OsX
                            else self.canvas.create_rectangle(
                                x0, y0, x1, y1, outline="black"
                            ),
                            self.canvas.create_text(
                                (x0 + x1) // 2,
                                (y0 + y1) // 2,
                                justify=CENTER,
                                text=content,
                                fill="black",
                                font=("Helvetica", "12", "normal"),
                            ),
                            dir_name,
                        )
                        link = os.path.join(
                            CFG.custom_scenery_dir,
                            "zOrtho4XP_" + FNAMES.short_latlon(lat, lon),
                        )
                        if os.path.isdir(link):
                            if os.path.samefile(
                                os.path.realpath(link),
                                os.path.realpath(
                                    os.path.join(self.working_dir, dir_name)
                                ),
                            ):
                                if not OsX:
                                    self.canvas.itemconfig(
                                        self.dico_tiles_done[(lat, lon)][0],
                                        stipple="gray50",
                                    )
                                else:
                                    self.canvas.itemconfig(
                                        self.dico_tiles_done[(lat, lon)][1],
                                        font=(
                                            "Helvetica",
                                            "12",
                                            "bold underline",
                                        ),
                                    )
        elif self.grouped and os.path.isdir(
            os.path.join(self.working_dir, "Earth nav data")
        ):
            for dir_name in os.listdir(
                os.path.join(self.working_dir, "Earth nav data")
            ):
                for file_name in os.listdir(
                    os.path.join(self.working_dir, "Earth nav data", dir_name)
                ):
                    try:
                        lat = int(file_name[0:3])
                        lon = int(file_name[3:7])
                    except:
                        continue
                    [x0, y0] = GEO.wgs84_to_pix(lat + 1, lon, self.earthzl)
                    [x1, y1] = GEO.wgs84_to_pix(lat, lon + 1, self.earthzl)
                    color = "#1e3028"
                    content = ""
                    try:
                        tmpf = open(
                            os.path.join(
                                self.working_dir,
                                "Ortho4XP_"
                                + FNAMES.short_latlon(lat, lon)
                                + ".cfg",
                            ),
                            "r",
                            encoding="latin-1",
                        )
                        found_config = True
                    except:
                        found_config = False
                    if found_config:
                        prov = zl = ""
                        for line in tmpf.readlines():
                            if line[:15] == "default_website":
                                prov = line.strip().split("=")[1][:4]
                            elif line[:10] == "default_zl":
                                zl = int(line.strip().split("=")[1])
                                break
                        tmpf.close()
                        if not prov:
                            prov = "?"
                        if zl:
                            color = dico_color[zl]
                        else:
                            zl = "?"
                        content = prov + "\n" + str(zl)
                    else:
                        content = "?"
                    self.dico_tiles_done[(lat, lon)] = (
                        self.canvas.create_rectangle(
                            x0, y0, x1, y1, fill=color, stipple="gray12"
                        )
                        if not OsX
                        else self.canvas.create_rectangle(
                            x0, y0, x1, y1, outline="black"
                        ),
                        self.canvas.create_text(
                            (x0 + x1) // 2,
                            (y0 + y1) // 2,
                            justify=CENTER,
                            text=content,
                            fill="black",
                            font=("Helvetica", "12", "normal"),
                        ),
                        dir_name,
                    )
            link = os.path.join(
                CFG.custom_scenery_dir,
                "zOrtho4XP_" + os.path.basename(self.working_dir),
            )
            if os.path.isdir(link):
                if os.path.samefile(
                    os.path.realpath(link), os.path.realpath(self.working_dir)
                ):
                    for (lat0, lon0) in self.dico_tiles_done:
                        if "dar" not in sys.platform:
                            self.canvas.itemconfig(
                                self.dico_tiles_done[(lat, lon)][0],
                                stipple="gray50",
                            )
                        else:
                            self.canvas.itemconfig(
                                self.dico_tiles_done[(lat, lon)][1],
                                font=("Helvetica", "12", "bold underline"),
                            )
        for (lat, lon) in self.dico_tiles_todo:
            [x0, y0] = GEO.wgs84_to_pix(lat + 1, lon, self.earthzl)
            [x1, y1] = GEO.wgs84_to_pix(lat, lon + 1, self.earthzl)
            self.canvas.delete(self.dico_tiles_todo[(lat, lon)])
            self.dico_tiles_todo[(lat, lon)] = (
                self.canvas.create_rectangle(
                    x0, y0, x1, y1, fill="red", stipple="gray12"
                )
                if not OsX
                else self.canvas.create_rectangle(
                    x0, y0, x1, y1, outline="red", width=2
                )
            )
        return

    def trash(self):
        if self.v_["OSM data"].get():
            try:
                shutil.rmtree(FNAMES.osm_dir(self.active_lat, self.active_lon))
            except Exception as e:
                UI.vprint(3, e)
        if self.v_["Mask data"].get():
            try:
                shutil.rmtree(FNAMES.mask_dir(self.active_lat, self.active_lon))
            except Exception as e:
                UI.vprint(3, e)
        if self.v_["Jpeg imagery"].get():
            try:
                shutil.rmtree(
                    os.path.join(
                        FNAMES.Imagery_dir,
                        FNAMES.long_latlon(self.active_lat, self.active_lon),
                    )
                )
            except Exception as e:
                UI.vprint(3, e)
        if self.v_["Tile (whole)"].get() and not self.grouped:
            try:
                shutil.rmtree(
                    FNAMES.build_dir(
                        self.active_lat, self.active_lon, self.custom_build_dir
                    )
                )
            except Exception as e:
                UI.vprint(3, e)
            if (self.active_lat, self.active_lon) in self.dico_tiles_done:
                for objid in self.dico_tiles_done[
                    (self.active_lat, self.active_lon)
                ][:2]:
                    self.canvas.delete(objid)
                del self.dico_tiles_done[(self.active_lat, self.active_lon)]
        if self.v_["Tile (textures)"].get() and not self.grouped:
            try:
                shutil.rmtree(
                    os.path.join(
                        FNAMES.build_dir(
                            self.active_lat,
                            self.active_lon,
                            self.custom_build_dir,
                        ),
                        "textures",
                    )
                )
            except Exception as e:
                UI.vprint(3, e)
        return

    def select_tile(self, event):
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        (lat, lon) = [floor(t) for t in GEO.pix_to_wgs84(x, y, self.earthzl)]
        self.active_lat = lat
        self.active_lon = lon
        self.latlon.set(FNAMES.short_latlon(lat, lon))
        try:
            self.canvas.delete(self.active_tile)
        except:
            pass
        [x0, y0] = GEO.wgs84_to_pix(lat + 1, lon, self.earthzl)
        [x1, y1] = GEO.wgs84_to_pix(lat, lon + 1, self.earthzl)
        self.active_tile = self.canvas.create_rectangle(
            x0, y0, x1, y1, fill="", outline="yellow", width=3
        )
        self.parent.lat.set(lat)
        self.parent.lon.set(lon)
        return

    def toggle_to_custom(self, event):
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        (lat, lon) = [floor(t) for t in GEO.pix_to_wgs84(x, y, self.earthzl)]
        if (lat, lon) not in self.dico_tiles_done:
            return
        if not self.grouped:
            link = os.path.join(
                CFG.custom_scenery_dir,
                "zOrtho4XP_" + FNAMES.short_latlon(lat, lon),
            )
            # target=os.path.realpath(os.path.join(self.working_dir,
            # 'zOrtho4XP_'+FNAMES.short_latlon(lat,lon)))
            target = os.path.realpath(
                os.path.join(
                    self.working_dir, self.dico_tiles_done[(lat, lon)][-1]
                )
            )
            if os.path.isdir(link) and os.path.samefile(
                os.path.realpath(link), target
            ):
                os.remove(link)
                if not OsX:
                    self.canvas.itemconfig(
                        self.dico_tiles_done[(lat, lon)][0], stipple="gray12"
                    )
                else:
                    self.canvas.itemconfig(
                        self.dico_tiles_done[(lat, lon)][1],
                        font=("Helvetica", "12", "normal"),
                    )
                return
        elif self.grouped:
            link = os.path.join(
                CFG.custom_scenery_dir,
                "zOrtho4XP_" + os.path.basename(self.working_dir),
            )
            target = os.path.realpath(self.working_dir)
            if os.path.isdir(link) and os.path.samefile(
                os.path.realpath(link), os.path.realpath(self.working_dir)
            ):
                os.remove(link)
                for (lat0, lon0) in self.dico_tiles_done:
                    if not OsX:
                        self.canvas.itemconfig(
                            self.dico_tiles_done[(lat, lon)][0],
                            stipple="gray12",
                        )
                    else:
                        self.canvas.itemconfig(
                            self.dico_tiles_done[(lat, lon)][1],
                            font=("Helvetica", "12", "normal"),
                        )
                return
        # in case this was a broken link
        try:
            os.remove(link)
        except:
            pass
        if ("dar" in sys.platform) or (
            "win" not in sys.platform
        ):  # Mac and Linux
            os.system("ln -s " + ' "' + target + '" "' + link + '"')
        else:
            os.system('MKLINK /J "' + link + '" "' + target + '"')
        if not self.grouped:
            if not OsX:
                self.canvas.itemconfig(
                    self.dico_tiles_done[(lat, lon)][0], stipple="gray50"
                )
            else:
                self.canvas.itemconfig(
                    self.dico_tiles_done[(lat, lon)][1],
                    font=("Helvetica", "12", "bold underline"),
                )
        else:
            for (lat0, lon0) in self.dico_tiles_done:
                if not OsX:
                    self.canvas.itemconfig(
                        self.dico_tiles_done[(lat0, lon0)][0], stipple="gray50"
                    )
                else:
                    self.canvas.itemconfig(
                        self.dico_tiles_done[(lat, lon)][1],
                        font=("Helvetica", "12", "bold underline"),
                    )
        return

    def add_tile(self, event):
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        (lat, lon) = [floor(t) for t in GEO.pix_to_wgs84(x, y, self.earthzl)]
        if (lat, lon) not in self.dico_tiles_todo:
            [x0, y0] = GEO.wgs84_to_pix(lat + 1, lon, self.earthzl)
            [x1, y1] = GEO.wgs84_to_pix(lat, lon + 1, self.earthzl)
            if not OsX:
                self.dico_tiles_todo[(lat, lon)] = self.canvas.create_rectangle(
                    x0, y0, x1, y1, fill="red", stipple="gray12"
                )
            else:
                self.dico_tiles_todo[(lat, lon)] = self.canvas.create_rectangle(
                    x0 + 2, y0 + 2, x1 - 2, y1 - 2, outline="red", width=1
                )
        else:
            self.canvas.delete(self.dico_tiles_todo[(lat, lon)])
            self.dico_tiles_todo.pop((lat, lon), None)
        return

    def batch_build(self):
        list_lat_lon = sorted(self.dico_tiles_todo.keys())
        if not list_lat_lon:
            return
        (lat, lon) = list_lat_lon[0]
        try:
            tile = CFG.Tile(lat, lon, self.custom_build_dir)
        except:
            return 0
        args = [
            tile,
            list_lat_lon,
            self.v_["Assemble vector data"].get(),
            self.v_["Triangulate 3D mesh"].get(),
            self.v_["Draw water masks"].get(),
            self.v_["Build imagery/DSF"].get(),
            self.v_["Extract overlays"].get(),
            self.v_["Read per tile cfg"].get(),
        ]
        threading.Thread(target=TILE.build_tile_list, args=args).start()
        return

    def scroll_start(self, event):
        self.canvas.scan_mark(event.x, event.y)
        return

    def scroll_move(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)
        self.redraw_canvas()
        return

    def redraw_canvas(self):
        x0 = self.canvas.canvasx(0)
        y0 = self.canvas.canvasy(0)
        if x0 < 0:
            x0 = 0
        if y0 < 0:
            y0 = 0
        nx0 = int((8 * x0) // self.resolution)
        ny0 = int((8 * y0) // self.resolution)
        if nx0 == self.nx0 and ny0 == self.ny0:
            return
        else:
            self.nx0 = nx0
            self.ny0 = ny0
            try:
                self.canvas.delete(self.canv_imgNW)
            except:
                pass
            try:
                self.canvas.delete(self.canv_imgNE)
            except:
                pass
            try:
                self.canvas.delete(self.canv_imgSW)
            except:
                pass
            try:
                self.canvas.delete(self.canv_imgSE)
            except:
                pass
            fargs_rc = [nx0, ny0]
            self.rc_thread = threading.Thread(
                target=self.draw_canvas, args=fargs_rc
            )
            self.rc_thread.start()
            return

    def draw_canvas(self, nx0, ny0):
        fileprefix = os.path.join(
            FNAMES.Utils_dir, "Earth", "Earth2_ZL" + str(self.earthzl) + "_"
        )
        filepreviewNW = fileprefix + str(nx0) + "_" + str(ny0) + ".jpg"
        try:
            self.imageNW = Image.open(filepreviewNW)
            self.photoNW = ImageTk.PhotoImage(self.imageNW)
            self.canv_imgNW = self.canvas.create_image(
                nx0 * 2 ** self.earthzl * 256 / 8,
                ny0 * 2 ** self.earthzl * 256 / 8,
                anchor=NW,
                image=self.photoNW,
            )
            self.canvas.tag_lower(self.canv_imgNW)
        except:
            UI.lvprint(
                0,
                "Could not find Earth preview file",
                filepreviewNW,
                ", please update your installation from a fresh copy.",
            )
            # Fond gris couvrant TOUTE la scrollregion — indispensable pour
            # que canvasx/canvasy retournent des coords correctes même sans carte
            res = 2 ** self.earthzl * 256
            self.canvas.create_rectangle(
                0, 0, res, res,
                fill="#3a3a3a", outline="", tags="background"
            )
            # Message centré sur la zone visible
            cx = nx0 * res // 8 + self.canvas_min_x // 2
            cy = ny0 * res // 8 + self.canvas_min_y // 2
            self.canvas.create_text(
                cx, cy,
                text="Carte Earth non disponible\n"
                     "Copiez Utils/Earth/ depuis Ortho4XP 2.00\n\n"
                     "Double-clic = sélectionner tuile\n"
                     "Shift+clic = ajouter au batch",
                fill="white", font=("TkFixedFont", 13),
                justify="center"
            )
        if nx0 < 2 ** (self.earthzl - 3) - 1:
            filepreviewNE = fileprefix + str(nx0 + 1) + "_" + str(ny0) + ".jpg"
            self.imageNE = Image.open(filepreviewNE)
            self.photoNE = ImageTk.PhotoImage(self.imageNE)
            self.canv_imgNE = self.canvas.create_image(
                (nx0 + 1) * 2 ** self.earthzl * 256 / 8,
                ny0 * 2 ** self.earthzl * 256 / 8,
                anchor=NW,
                image=self.photoNE,
            )
            self.canvas.tag_lower(self.canv_imgNE)
        if ny0 < 2 ** (self.earthzl - 3) - 1:
            filepreviewSW = fileprefix + str(nx0) + "_" + str(ny0 + 1) + ".jpg"
            self.imageSW = Image.open(filepreviewSW)
            self.photoSW = ImageTk.PhotoImage(self.imageSW)
            self.canv_imgSW = self.canvas.create_image(
                nx0 * 2 ** self.earthzl * 256 / 8,
                (ny0 + 1) * 2 ** self.earthzl * 256 / 8,
                anchor=NW,
                image=self.photoSW,
            )
            self.canvas.tag_lower(self.canv_imgSW)
        if (
            nx0 < 2 ** (self.earthzl - 3) - 1
            and ny0 < 2 ** (self.earthzl - 3) - 1
        ):
            filepreviewSE = (
                fileprefix + str(nx0 + 1) + "_" + str(ny0 + 1) + ".jpg"
            )
            self.imageSE = Image.open(filepreviewSE)
            self.photoSE = ImageTk.PhotoImage(self.imageSE)
            self.canv_imgSE = self.canvas.create_image(
                (nx0 + 1) * 2 ** self.earthzl * 256 / 8,
                (ny0 + 1) * 2 ** self.earthzl * 256 / 8,
                anchor=NW,
                image=self.photoSE,
            )
            self.canvas.tag_lower(self.canv_imgSE)
        return

    def exit(self):
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════════════
# SIMULATEUR VISUEL — Ortho4XP V2  (Étape 1 : tous paramètres cfg)
# ═══════════════════════════════════════════════════════════════════════════════

class Ortho4XP_Simulator(tk.Toplevel):
    """
    Fenêtre simulateur visuel.
    Affiche l'effet de chaque paramètre du cfg avec curseurs et canvas animé.
    Organisée en onglets thématiques. Lecture/écriture cfg via boutons.
    """

    BG       = "#1a2a20"
    BG2      = "#22342a"
    BG3      = "#2a4035"
    FG       = "#e8f0ec"
    FG2      = "#a6e3a1"
    FG3      = "#607d6b"
    TROUGH   = "#0d1f17"
    ACC      = "#4fc3f7"

    def __init__(self, parent, lat, lon, custom_build_dir=""):
        tk.Toplevel.__init__(self, parent)
        self.parent = parent
        self.lat = lat
        self.lon = lon
        self.custom_build_dir = custom_build_dir
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.title(f"🎚  Simulateur Ortho4XP — tuile {lat:+d}/{lon:+d}")
        self.configure(bg=self.BG)
        self.resizable(False, False)
        self._anim_running = True
        self._t = 0
        self._vars = {}
        self._canvases = {}
        self._tile = CFG.Tile(lat, lon, custom_build_dir)
        self._tile.read_from_config()
        self._build_ui()
        self._load_values()
        self._anim_loop()

    def _on_close(self):
        self._anim_running = False
        self.destroy()

    # ── Construction UI ────────────────────────────────────────────────
    def _build_ui(self):
        s = 1.0
        try:
            if self.winfo_fpixels("1i") > 120:
                s = 1.2
        except Exception:
            pass
        fs = lambda x: int(x * s)

        # Titre
        hdr = tk.Frame(self, bg=self.BG, padx=10, pady=8)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"Simulateur visuel — Ortho4XP V2",
            bg=self.BG, fg=self.FG2,
            font=("TkFixedFont", fs(13), "bold")).pack(side="left")
        tk.Label(hdr,
            text=f"tuile {self.lat:+d}/{self.lon:+d}",
            bg=self.BG, fg=self.FG3,
            font=("TkFixedFont", fs(10))).pack(side="left", padx=12)

        # Notebook onglets
        style = ttk.Style()
        style.configure("Sim.TNotebook", background=self.BG, borderwidth=0)
        style.configure("Sim.TNotebook.Tab",
            background=self.BG3, foreground=self.FG,
            padding=[12, 4], font=("TkFixedFont", fs(10)))
        style.map("Sim.TNotebook.Tab",
            background=[("selected", self.BG2)],
            foreground=[("selected", self.FG2)])

        nb = ttk.Notebook(self, style="Sim.TNotebook")
        nb.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        # Onglets
        self._tab_mer(nb, fs)
        self._tab_cote(nb, fs)
        self._tab_terrain(nb, fs)
        self._tab_mesh(nb, fs)
        self._tab_imagerie(nb, fs)

        # Barre boutons bas
        btn_fr = tk.Frame(self, bg=self.BG, padx=10, pady=8)
        btn_fr.pack(fill="x")

        ttk.Button(btn_fr, text="↺  Recharger depuis cfg",
            command=self._load_values).pack(side="left", padx=4)
        ttk.Button(btn_fr, text="✅  Write Tile cfg",
            command=self._write_tile).pack(side="left", padx=4)
        ttk.Button(btn_fr, text="🌍  Write App cfg",
            command=self._write_app).pack(side="left", padx=4)

        self._status = tk.Label(btn_fr, text="", bg=self.BG,
            fg=self.FG2, font=("TkFixedFont", fs(10)))
        self._status.pack(side="left", padx=16)

        ttk.Button(btn_fr, text="✖  Fermer",
            command=self._on_close).pack(side="right", padx=4)

    # ── Helper : créer un onglet avec canvas en haut + curseurs en bas ─
    def _make_tab(self, nb, title, canvas_height=200):
        frame = tk.Frame(nb, bg=self.BG2)
        nb.add(frame, text=title)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=0)  # canvas fixe
        frame.rowconfigure(1, weight=1)  # curseurs extensibles

        # Canvas en haut — pleine largeur
        cv_frame = tk.Frame(frame, bg="#0a1628", relief="flat", bd=1)
        cv_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=(8,4))
        cv = tk.Canvas(cv_frame, bg="#0a1628",
            highlightthickness=0, height=canvas_height)
        cv.pack(fill="both", expand=True)
        # Forcer redraw quand le canvas est redimensionné
        cv.bind("<Configure>", lambda e: self.after(10, self._redraw_all))

        # Zone curseurs en bas — frame fixe, sans scrollbar
        inner = tk.Frame(frame, bg=self.BG2)
        inner.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0,4))
        inner.columnconfigure(0, weight=1)

        # Explication dynamique — sous le canvas
        exp_fr = tk.Frame(frame, bg=self.BG)
        exp_fr.grid(row=2, column=0, sticky="ew", padx=8, pady=(0,2))
        exp_lbl = tk.Label(exp_fr, text="Survolez un curseur.",
            bg=self.BG, fg=self.FG3, font=("TkFixedFont", 9),
            wraplength=860, justify="left", anchor="w")
        exp_lbl.pack(fill="x", padx=4, pady=3)

        return cv, inner, exp_lbl

    # ── Helper : ajouter un groupe + curseurs ─────────────────────────
    def _add_group(self, parent, title, sliders, exp_lbl, fs=lambda x:x):
        grp = tk.LabelFrame(parent, text=title,
            bg=self.BG3, fg=self.FG2,
            font=("TkFixedFont", fs(10), "bold"),
            padx=6, pady=4)
        grp.pack(fill="x", padx=6, pady=(4,2))
        grp.columnconfigure(0, weight=0)
        grp.columnconfigure(1, weight=1)
        grp.columnconfigure(2, weight=0)

        for row_i, (key, label, vmin, vmax, step, typ, hint, values) \
                in enumerate(sliders):

            tk.Label(grp, text=label, bg=self.BG3, fg=self.FG,
                font=("TkFixedFont", fs(9)), width=18,
                anchor="e").grid(row=row_i, column=0,
                padx=(2,6), pady=2, sticky="e")

            val_lbl = tk.Label(grp, text="—", bg=self.BG3,
                fg=self.ACC, font=("TkFixedFont", fs(10), "bold"),
                width=7)
            val_lbl.grid(row=row_i, column=2, padx=4, sticky="w")

            if values:
                # Combobox pour les valeurs discrètes
                var = tk.StringVar()
                self._vars[key] = var
                cb = ttk.Combobox(grp, values=values,
                    textvariable=var, state="readonly", width=12)
                cb.grid(row=row_i, column=1, padx=2, pady=2,
                    sticky="ew")
                val_lbl.config(textvariable=var)

                def _cb_hint(e, h=hint, lbl=exp_lbl):
                    lbl.config(text=h)
                cb.bind("<<ComboboxSelected>>", _cb_hint)
                cb.bind("<Enter>",
                    lambda e, h=hint, lbl=exp_lbl: lbl.config(text=h))
            else:
                # Slider
                if typ == int:
                    var = tk.IntVar()
                else:
                    var = tk.DoubleVar()
                self._vars[key] = var

                def _make_cb(lbl, k, t):
                    def cb(*_):
                        v = self._vars[k].get()
                        lbl.config(text=str(v) if t==int
                            else f"{v:.3f}".rstrip('0').rstrip('.'))
                    return cb

                var.trace_add("write", _make_cb(val_lbl, key, typ))

                sl = tk.Scale(grp,
                    from_=vmin, to=vmax, resolution=step,
                    orient=HORIZONTAL, variable=var,
                    bg=self.BG3, fg=self.FG,
                    troughcolor=self.TROUGH,
                    highlightthickness=0, showvalue=False,
                    length=320)
                sl.grid(row=row_i, column=1, padx=2, pady=1,
                    sticky="ew")
                sl.bind("<Enter>",
                    lambda e, h=hint, lbl=exp_lbl: lbl.config(text=h))

    # ══════════════════════════════════════════════════════════════════
    # ONGLET 1 — MER & TRANSPARENCE
    # ══════════════════════════════════════════════════════════════════
    def _tab_mer(self, nb, fs):
        cv, inner, exp_lbl = self._make_tab(nb, "💧 Mer & Eau")
        self._canvases["mer"] = cv

        sliders = [
            ("ratio_water",    "ratio_water",    0, 1,    0.01, float,
             "ratio_water : 0 = JPG satellite opaque sur mer (photo fixe, pas de vagues). "
             "1 = eau XP12 entièrement visible (vagues dynamiques, reflets, bathymétrie). "
             "Recommandé : 0.10 pour Vendée/Atlantique.", None),
            ("ratio_bathy",    "ratio_bathy",    0, 1,    0.05, float,
             "ratio_bathy : dégradé de profondeur XP12. "
             "0 = couleur mer uniforme. "
             "1 = eau profonde sombre au large → turquoise côtier. Recommandé : 1.0.", None),
            ("sea_texture_blur","sea_texture_blur",0,2000,50,  float,
             "sea_texture_blur : flou appliqué à la texture mer (couches mask). "
             "0 = texture nette. 500-1000m = atténue les motifs répétitifs. "
             "2000m = mer très lisse, idéal si la source satellite a des reflets parasites.", None),
            ("water_tech",     "water_tech",     0, 0,    1,    str,
             "water_tech : XP12 = eau dynamique avec vagues, reflets et bathymétrie native. "
             "XP11+bathy = rendu eau ancien, moins réaliste.",
             ["XP12","XP11 + bathy"]),
            ("overlay_lod",    "overlay_lod (m)",5000,50000,1000,float,
             "overlay_lod : distance en mètres jusqu'où XPlane affiche l'imagerie sur la mer. "
             "5000 = courte portée (économise VRAM). 30000 = recommandé. 50000 = très loin.", None),
            ("water_smoothing","water_smoothing",0, 5,    1,    int,
             "water_smoothing : lissage du maillage eau intérieure. "
             "0 = pas de lissage. 2 = recommandé. 5 = très lisse.", None),
        ]
        self._add_group(inner, "Eau & Transparence", sliders, exp_lbl, fs)

    # ══════════════════════════════════════════════════════════════════
    # ONGLET 2 — CÔTE & MASQUES
    # ══════════════════════════════════════════════════════════════════
    def _tab_cote(self, nb, fs):
        cv, inner, exp_lbl = self._make_tab(nb, "🌊 Côte & Masques")
        self._canvases["cote"] = cv

        sliders = [
            ("masks_width",    "masks_width (px)",512,16384,512,int,
             "masks_width : largeur en pixels de la zone de dégradé côtier. "
             "512 = transition très étroite, bord net visible. "
             "6144 = ~500m réels à ZL17, transition naturelle (recommandé Vendée). "
             "16384 = dégradé très large, côte très progressive.", None),
            ("mask_zl",        "mask_zl",        14,20,   1,    int,
             "mask_zl : zoom level des masques PNG côtiers. "
             "14-15 = basse résolution, contours grossiers. "
             "17 = bon équilibre résolution/poids de fichier (recommandé). "
             "19-20 = très haute résolution, falaises détaillées, fichiers lourds.", None),
            ("masking_mode",   "masking_mode",   0, 0,    1,    str,
             "masking_mode : algorithme de génération des masques. "
             "sand = dégradé naturel côtier (recommandé). "
             "3steps = 3 étapes avec seuils. "
             "low_res = basse résolution rapide.",
             ["sand","3steps","low_res"]),
            ("use_masks_for_inland","use_inland", 0, 0,   1,    str,
             "use_masks_for_inland : applique les masques aussi sur l'eau intérieure "
             "(lacs, rivières). True = recommandé pour rendu cohérent.",
             ["True","False"]),
            ("imprint_masks_to_dds","imprint DDS",0,0,   1,    str,
             "imprint_masks_to_dds : intègre le canal alpha directement dans le DDS (BC3). "
             "True = nécessaire pour la transparence XP12 (recommandé).",
             ["True","False"]),
            ("distance_masks_too","distance masks",0,0,  1,    str,
             "distance_masks_too : utilise aussi les masques de distance pour affiner "
             "la bathymétrie près de la côte.",
             ["False","True"]),
            ("masks_use_DEM_too","DEM pour masques",0,0,1,str,
             "masks_use_DEM_too : utilise le DEM (altimétrie) pour améliorer les masques "
             "en zone côtière. Utile sur les côtes avec falaises.",
             ["False","True"]),
            ("coast_curv_tol", "coast_curv_tol", 0.5,5, 0.5,  float,
             "coast_curv_tol : tolérance de courbure spécifique pour la ligne de côte. "
             "Valeur basse = côte plus précise, plus de triangles. "
             "1.5 = recommandé pour Vendée.", None),
            ("coast_curv_ext", "coast_curv_ext", 0.5,3, 0.5,  float,
             "coast_curv_ext : extension de la zone de précision côtière en km. "
             "1.0 = 1km autour de la côte avec tolérance réduite.", None),
            ("sea_smoothing_mode","sea_smoothing",0,0,  1,    str,
             "sea_smoothing_mode : lissage du bord de mer dans le mesh. "
             "none = pas de lissage (recommandé avec masques). "
             "LAPLACE = lissage Laplacien.",
             ["none","LAPLACE"]),
        ]
        self._add_group(inner, "Masques côtiers", sliders[:5], exp_lbl, fs)
        self._add_group(inner, "Courbure côte", sliders[5:], exp_lbl, fs)

    # ══════════════════════════════════════════════════════════════════
    # ONGLET 3 — TERRAIN & RELIEF
    # ══════════════════════════════════════════════════════════════════
    def _tab_terrain(self, nb, fs):
        cv, inner, exp_lbl = self._make_tab(nb, "⛰ Terrain & Relief")
        self._canvases["terrain"] = cv

        sliders = [
            ("normal_map_strength","normal_map",  0, 2,   0.1,  float,
             "normal_map_strength : intensité de l'ombrage terrain. "
             "0 = terrain plat visuellement. "
             "1.0 = ombrage exact (recommandé). "
             "2.0 = ombrage très marqué, peut sembler exagéré sur terrain plat.", None),
            ("terrain_casts_shadows","ombres terrain",0,0,1,str,
             "terrain_casts_shadows : le terrain projette des ombres sur lui-même. "
             "True = ombres réalistes (recommandé). "
             "False = moins réaliste mais gain de performances.",
             ["True","False"]),
            ("use_decal_on_terrain","décals terrain",0,0,1,str,
             "use_decal_on_terrain : applique des décals de texture (herbe/roche) "
             "sur le terrain pour améliorer le rendu au sol à basse altitude. "
             "True = recommandé pour la Vendée.",
             ["True","False"]),
            ("fill_nodata",    "fill_nodata",    0, 0,    1,    str,
             "fill_nodata : remplit les zones sans données altimétriques "
             "par interpolation du voisin le plus proche. "
             "True = recommandé pour les DEM avec trous sur la mer.",
             ["True","False"]),
            ("min_area",       "min_area (°²)",  0.00001,0.01,0.00001,float,
             "min_area : surface minimum d'un polygone vectoriel (en degrés²). "
             "Les polygones plus petits sont ignorés. "
             "0.0001 = recommandé (élimine les micro-polygones parasites).", None),
            ("max_area",       "max_area (°²)",  1,200,  5,    float,
             "max_area : surface maximum d'un polygone vectoriel. "
             "Les polygones plus grands sont découpés. "
             "100 = recommandé.", None),
            ("water_simplification","water_simpl",0,1,  0.05, float,
             "water_simplification : simplification des polygones eau. "
             "0 = pas de simplification (précis). "
             "0.5 = simplification modérée. "
             "1.0 = très simplifié (rapide mais moins précis).", None),
        ]
        self._add_group(inner, "Terrain & Ombrage", sliders[:3], exp_lbl, fs)
        self._add_group(inner, "Altimétrie & Vecteurs", sliders[3:], exp_lbl, fs)

    # ══════════════════════════════════════════════════════════════════
    # ONGLET 4 — MESH 3D
    # ══════════════════════════════════════════════════════════════════
    def _tab_mesh(self, nb, fs):
        cv, inner, exp_lbl = self._make_tab(nb, "🗺 Mesh 3D")
        self._canvases["mesh"] = cv

        sliders = [
            ("mesh_zl",        "mesh_zl",        14,20,  1,    int,
             "mesh_zl : zoom level du maillage 3D. "
             "14-16 = mesh grossier, relief approximatif. "
             "19 = mesh très précis, côtes et falaises détaillées (recommandé). "
             "20 = très lourd, rarement nécessaire.", None),
            ("curvature_tol",  "curvature_tol",  1,30,   0.5,  float,
             "curvature_tol : tolérance de courbure générale du mesh. "
             "Valeur basse = plus de triangles, relief plus précis. "
             "16 = recommandé. 1 = très dense (lent). 30 = grossier.", None),
            ("limit_tris",     "limit_tris (M)", 1,50,   1,    float,
             "limit_tris : limite du nombre de triangles en millions. "
             "15 = recommandé. Augmenter pour les zones très complexes.", None),
            ("min_angle",      "min_angle (°)",  0.1,2,  0.1,  float,
             "min_angle : angle minimum des triangles du mesh. "
             "0.5 = recommandé. Valeur basse = meilleure qualité géométrique.", None),
            ("iterate",        "iterate",        0, 3,   1,    int,
             "iterate : nombre d'itérations de raffinement du mesh. "
             "0 = pas d'itération (rapide). "
             "1-2 = meilleure qualité côtière. 3 = très long.", None),
            ("clean_bad_geometries","clean_geom",0,0,   1,    str,
             "clean_bad_geometries : supprime les géométries vectorielles invalides "
             "avant la triangulation. True = recommandé.",
             ["True","False"]),
        ]
        self._add_group(inner, "Paramètres Mesh", sliders[:4], exp_lbl, fs)
        self._add_group(inner, "Qualité & Nettoyage", sliders[4:], exp_lbl, fs)

    # ══════════════════════════════════════════════════════════════════
    # ONGLET 5 — IMAGERIE & AÉROPORTS
    # ══════════════════════════════════════════════════════════════════
    def _tab_imagerie(self, nb, fs):
        cv, inner, exp_lbl = self._make_tab(nb, "📷 Imagerie & Aéroports")
        self._canvases["imagerie"] = cv

        sliders = [
            ("default_zl",     "default_zl",     14,20,  1,    int,
             "default_zl : niveau de zoom de l'imagerie principale. "
             "14-15 = faible résolution, flou. "
             "17 = résolution standard, recommandé. "
             "19-20 = très haute résolution, très lourd en VRAM.", None),
            ("cover_zl",       "cover_zl airports",14,20,1,   int,
             "cover_zl : zoom level haute résolution autour des aéroports. "
             "18 = recommandé pour voir les marquages et taxiways.", None),
            ("cover_extent",   "cover_extent (km)",0,5, 0.5,  float,
             "cover_extent : rayon en km autour des aéroports pour la haute résolution. "
             "1.0 = recommandé. 3.0 = large zone haute résolution.", None),
            ("cover_airports_with_highres","HiRes airports",0,0,1,str,
             "cover_airports_with_highres : active la haute résolution autour des aéroports. "
             "True = recommandé si un aéroport est présent sur la tuile.",
             ["False","True"]),
            ("apt_smoothing_pix","apt_smooth (px)",0,30, 1,   int,
             "apt_smoothing_pix : lissage en pixels de la zone aéroport dans le mesh. "
             "8 = recommandé pour éviter les bosses sur les pistes.", None),
            ("apt_curv_tol",   "apt_curv_tol",   0.5,5, 0.5,  float,
             "apt_curv_tol : tolérance de courbure spécifique aux aéroports. "
             "1.5 = recommandé. Valeur basse = géométrie aéroport plus précise.", None),
            ("apt_curv_ext",   "apt_curv_ext (km)",0.5,3,0.5, float,
             "apt_curv_ext : extension de la zone de précision autour des aéroports. "
             "1.0 = recommandé.", None),
            ("road_level",     "road_level",     0, 4,   1,    int,
             "road_level : densité des routes intégrées dans le mesh. "
             "0 = aucune route. 4 = toutes les routes (recommandé).", None),
            ("max_levelled_segs","levelled_segs",0,500000,10000,int,
             "max_levelled_segs : nombre maximum de segments de route nivelés. "
             "200000 = recommandé.", None),
        ]
        self._add_group(inner, "Imagerie", sliders[:4], exp_lbl, fs)
        self._add_group(inner, "Aéroports", sliders[4:7], exp_lbl, fs)
        self._add_group(inner, "Routes", sliders[7:], exp_lbl, fs)

    # ── Forcer redraw de tous les canvas ────────────────────────────
    def _redraw_all(self):
        try:
            self._draw_mer()
            self._draw_cote()
            self._draw_terrain()
            self._draw_mesh()
            self._draw_imagerie()
        except Exception:
            pass

    # ── Animation canvas (simple, non bloquant) ────────────────────
    def _anim_loop(self):
        if not self._anim_running:
            return
        self._t += 1
        try:
            self._draw_mer()
            self._draw_cote()
            self._draw_terrain()
            self._draw_mesh()
            self._draw_imagerie()
        except Exception:
            pass
        self.after(50, self._anim_loop)

    def _cv_size(self, key):
        cv = self._canvases.get(key)
        if not cv:
            return 400, 220
        return max(200, cv.winfo_width()), max(100, cv.winfo_height())

    def _get(self, key, default=0):
        v = self._vars.get(key)
        if v is None:
            return default
        try:
            val = v.get()
            if isinstance(val, str):
                try:
                    return float(val)
                except Exception:
                    return val
            return val
        except Exception:
            return default

    # ── Noyau isométrique partagé ──────────────────────────────────
    def _iso_terrain(self, W, H, params):
        """
        Génère une liste de polygones isométriques représentant le terrain.
        params = dict avec les valeurs des curseurs de l'onglet actif.
        Retourne une liste de (polygon_pts, fill_color, outline_color, outline_w).
        """
        import math, random
        polys = []

        ratio_w  = params.get("ratio_water",  0.1)
        ratio_b  = params.get("ratio_bathy",  1.0)
        mw       = params.get("masks_width",  6144)
        mzl      = params.get("mask_zl",      17)
        ctol     = params.get("curvature_tol",16)
        msh_zl   = params.get("mesh_zl",      19)
        limit_t  = params.get("limit_tris",   15)
        nm       = params.get("normal_map_strength", 1.0)
        shad     = params.get("terrain_casts_shadows", "True")
        dzl      = params.get("default_zl",   17)
        wt       = params.get("water_tech",   "XP12")
        coast_ct = params.get("coast_curv_tol", 1.0)
        wire_on  = params.get("_wire",        False)

        # ── Projection isométrique ────────────────────────────────
        # Grille NX x NY cases, chaque case → quadrilatère projeté
        NX, NY = 22, 14
        ox = W * 0.50   # origine projection
        oy = H * 0.18
        sx = W / (NX + NY) * 1.05   # taille cellule horizontale
        sy = H / (NX + NY) * 0.52   # taille cellule verticale

        def iso(gx, gy, gz=0):
            px = ox + (gx - gy) * sx
            py = oy + (gx + gy) * sy - gz * (H * 0.012)
            return px, py

        # ── Heightmap : montagnes nord + vallée + lac + plaine + mer ─
        rng = random.Random(42)

        def height(gx, gy):
            # Montagnes au nord-ouest
            mx = gx / NX; my = gy / NY
            mtn  = math.exp(-((mx-0.15)**2 + (my-0.20)**2)*18) * 9.5
            mtn += math.exp(-((mx-0.30)**2 + (my-0.10)**2)*22) * 7.0
            mtn += math.exp(-((mx-0.10)**2 + (my-0.35)**2)*14) * 6.0
            # Vallée centrale vers le lac
            valley = -3.5 * math.exp(-((mx-0.48)**2)*8 - ((my-0.55)**2)*6)
            # Lac (dépression)
            lake_d = math.sqrt((mx-0.52)**2 + (my-0.52)**2)
            lake = -4.0 if lake_d < 0.13 else 0.0
            # Plaine côtière → descente vers mer
            plain = -2.5 * max(0, mx - 0.68)
            # Mer (bord droit)
            sea = -5.5 * max(0, mx - 0.80)
            # Crête entre montagnes : relief escarpé
            ridge = math.exp(-((mx-0.22)**2)*30 - ((my-0.30)**2)*50) * 5.0
            # Bruit micro
            noise = (rng.random()-0.5)*0.4
            raw = mtn + valley + lake + plain + sea + ridge + noise
            return raw

        # Influence curvature_tol sur le bruit de la heightmap
        def height_final(gx, gy):
            h = height(gx, gy)
            # curvature_tol haut = terrain lissé, bas = pics acérés
            smooth = max(0.3, 1.0 - (30 - ctol) / 30.0 * 0.6)
            return h * smooth

        # ── Couleur par biome + paramètres ───────────────────────
        def cell_color(gx, gy, h):
            mx = gx / NX; my = gy / NY
            # Lac
            lake_d = math.sqrt((mx-0.52)**2 + (my-0.52)**2)
            if lake_d < 0.13 or h < -3.2:
                # Couleur eau lac = influence ratio_water + ratio_bathy
                r = int(15  + ratio_b*15)
                g = int(90  + ratio_b*60 + ratio_w*30)
                b = int(160 + ratio_b*40 + ratio_w*20)
                return f"#{min(255,r):02x}{min(255,g):02x}{min(255,b):02x}"
            # Mer (gx élevé, h très bas)
            if h < -4.0 or mx > 0.84:
                depth = min(1.0, max(0, (-h-4.0)/2.0 + (mx-0.82)/0.2))
                if "XP12" in str(wt):
                    r = int(8  + depth*10 + ratio_b*12)
                    g = int(50 + depth*30 + ratio_b*70)
                    b = int(120+ depth*40 + ratio_b*40)
                else:
                    r = int(40 + depth*10)
                    g = int(70 + depth*20)
                    b = int(110+ depth*30)
                return f"#{min(255,r):02x}{min(255,g):02x}{min(255,b):02x}"
            # Plage
            if mx > 0.76 and h > -4.0 and h < 0.5:
                return "#d4b882"
            # Neige sommet (lié à normal_map_strength pour la brillance)
            snow_thr = 7.5 - nm * 1.5
            if h > snow_thr:
                bright = min(255, int(220 + nm*25))
                return f"#{bright:02x}{bright:02x}{min(255,bright+5):02x}"
            # Roche haute
            if h > 5.5:
                return "#8a8070"
            # Forêt (versants)
            if h > 1.5 and my < 0.55:
                g = int(70 + h*8)
                return f"#3a{min(255,g):02x}28"
            # Prairie (plaine)
            if h > 0.2:
                return "#5a8a38"
            # Bocage bas
            return "#4a7228"

        def shadow_factor(gx, gy, h):
            if shad != "True":
                return 1.0
            # Ombrage directionnel depuis nord-ouest
            dh = height_final(max(0,gx-1), max(0,gy-1)) - h
            return max(0.55, 1.0 - max(0, dh)*0.09)

        # ── Génération des polygones (arrière → avant) ────────────
        for gy in range(NY-1, -1, -1):
            for gx in range(NX-1, -1, -1):
                h00 = height_final(gx,   gy  )
                h10 = height_final(gx+1, gy  )
                h01 = height_final(gx,   gy+1)
                h11 = height_final(gx+1, gy+1)
                hm  = (h00+h10+h01+h11)/4

                p00 = iso(gx,   gy,   h00)
                p10 = iso(gx+1, gy,   h10)
                p11 = iso(gx+1, gy+1, h11)
                p01 = iso(gx,   gy+1, h01)

                fill = cell_color(gx+0.5, gy+0.5, hm)
                sf   = shadow_factor(gx, gy, hm)

                # Assombrir selon shadow
                if sf < 0.99:
                    r = int(int(fill[1:3],16)*sf)
                    g = int(int(fill[3:5],16)*sf)
                    b = int(int(fill[5:7],16)*sf)
                    fill = f"#{min(255,r):02x}{min(255,g):02x}{min(255,b):02x}"

                pts = [p00[0],p00[1], p10[0],p10[1],
                       p11[0],p11[1], p01[0],p01[1]]

                # Maillage visible si wire_on
                if wire_on:
                    ow = 0.5; oc = "#00ff88"
                else:
                    ow = 0; oc = ""

                polys.append((pts, fill, oc, ow))

        return polys

    def _iso_draw(self, cv, W, H, params, t=0, extra_fn=None):
        """Dessine les polygones isométriques sur le canvas."""
        polys = self._iso_terrain(W, H, params)
        for pts, fill, oc, ow in polys:
            if ow > 0:
                cv.create_polygon(pts, fill=fill, outline=oc, width=ow)
            else:
                cv.create_polygon(pts, fill=fill, outline="")
        if extra_fn:
            extra_fn(cv, W, H, params, t)

    # ── Canvas MER ────────────────────────────────────────────────
    def _draw_mer(self):
        cv = self._canvases.get("mer")
        if not cv or not cv.winfo_exists():
            return
        W, H = self._cv_size("mer")
        if W < 10 or H < 10:
            return
        cv.delete("all")
        import math, random
        t  = self._t
        rw = float(self._get("ratio_water", 0.1))
        rb = float(self._get("ratio_bathy", 1.0))
        wt = str(self._get("water_tech", "XP12"))

        # Vue 3D isométrique — mer, côte, terrain
        def _extra_mer(cv, W, H, params, t):
            import math
            rw2 = params.get("ratio_water", 0.1)
            rb2 = params.get("ratio_bathy", 1.0)
            wt2 = params.get("water_tech", "XP12")
            # Vagues animées sur la mer (en bas à droite de la vue iso)
            if rw2 > 0.1 and "XP12" in str(wt2):
                vis = min(1.0, rw2 * 1.5)
                for k in range(4):
                    y0 = int(H*(0.72 + k*0.06))
                    x0 = int(W*0.60); x1 = int(W*0.98)
                    wpts = []
                    for x in range(x0, x1, 3):
                        wy = y0 + int(math.sin(x*0.05 + t*0.02 + k)*2.5*vis)
                        wpts.extend([x, wy])
                    if len(wpts) >= 4:
                        bv = int(140 + vis*80)
                        gv = int(170 + vis*60)
                        cv.create_line(wpts,
                            fill=f"#60{min(255,gv):02x}{min(255,bv):02x}",
                            width=1, smooth=True)
            # Étiquette
            if rw2 < 0.2:
                st = "sat opaque"; sc = "#aaaaaa"
            elif rw2 < 0.5:
                st = "fondu XP12"; sc = "#88ccff"
            else:
                st = "eau XP12 dynamique"; sc = "#20e0a0"
            cv.create_rectangle(0, H-20, W, H, fill="#060e06", outline="")
            cv.create_text(W//2, H-10,
                text=f"ratio_water {int(rw2*100)}%  ratio_bathy {int(rb2*100)}%  — {st}",
                fill=sc, font=("TkFixedFont", 9))
            tc = "#20e0a0" if "XP12" in str(wt2) else "#e0a020"
            cv.create_rectangle(2, 2, 70, 18, fill="#060e06", outline="")
            cv.create_text(5, 10, text=str(wt2), fill=tc,
                anchor="w", font=("TkFixedFont", 8, "bold"))

        params = {
            "ratio_water": rw, "ratio_bathy": rb, "water_tech": wt,
            "curvature_tol": 16, "normal_map_strength": 1.0,
            "terrain_casts_shadows": "True",
        }
        self._iso_draw(cv, W, H, params, t, extra_fn=_extra_mer)

    # ── Canvas CÔTE ────────────────────────────────────────────────
    def _draw_cote(self):
        cv = self._canvases.get("cote")
        if not cv or not cv.winfo_exists():
            return
        W, H = self._cv_size("cote")
        cv.delete("all")
        t = self._t
        import math

        mw  = float(self._get("masks_width", 6144))
        mzl = int(self._get("mask_zl", 17))
        rw  = float(self._get("ratio_water", 0.1))
        cct = float(self._get("coast_curv_tol", 1.0))

        # Vue 3D isométrique — côte, masques, dégradé
        def _extra_cote(cv2, W2, H2, params2, t2):
            import math
            mw2  = params2.get("masks_width", 6144)
            mzl2 = params2.get("mask_zl", 17)
            rw2  = params2.get("ratio_water", 0.1)
            # Ligne de côte projetée sur le terrain iso (approximation visuelle)
            # On dessine un ruban blanc semi-transparent sur les cellules côtières
            prec = "très précis" if mzl2>=19 else "précis" if mzl2>=17 else "approx."
            cv2.create_rectangle(0, H2-20, W2, H2, fill="#060e06", outline="")
            grad_m = int(mw2 / 16384 * 500)
            cv2.create_text(W2//2, H2-10,
                text=f"mask_zl {mzl2} — {prec}  |  masks_width ~{grad_m}m  |  ratio_water {int(rw2*100)}%",
                fill="#b0d8ff", font=("TkFixedFont", 9))

        params = {
            "ratio_water": rw, "masks_width": mw, "mask_zl": mzl,
            "coast_curv_tol": cct, "curvature_tol": 16,
            "normal_map_strength": 1.0, "terrain_casts_shadows": "True",
        }
        self._iso_draw(cv, W, H, params, t, extra_fn=_extra_cote)

    # ── Canvas TERRAIN ─────────────────────────────────────────────
    def _draw_terrain(self):
        cv = self._canvases.get("terrain")
        if not cv or not cv.winfo_exists():
            return
        W, H = self._cv_size("terrain")
        cv.delete("all")

        nm   = float(self._get("normal_map_strength", 1.0))
        shad = str(self._get("terrain_casts_shadows", "True"))
        dcl  = str(self._get("use_decal_on_terrain", "True"))

        def _extra_terrain(cv2, W2, H2, params2, t2):
            nm2  = params2.get("normal_map_strength", 1.0)
            shad2= params2.get("terrain_casts_shadows", "True")
            dcl2 = params2.get("use_decal_on_terrain", "True")
            cv2.create_rectangle(0, H2-20, W2, H2, fill="#060e06", outline="")
            cv2.create_text(W2//2, H2-10,
                text=(f"normal_map {int(nm2*100)}%  "
                      f"ombres={'✓' if shad2=='True' else '✗'}  "
                      f"décals={'✓' if dcl2=='True' else '✗'}"),
                fill="#e0d8a0", font=("TkFixedFont", 9))

        params = {
            "normal_map_strength": nm, "terrain_casts_shadows": shad,
            "use_decal_on_terrain": dcl, "curvature_tol": 16,
            "ratio_water": float(self._get("ratio_water", 0.1)),
        }
        self._iso_draw(cv, W, H, params, self._t, extra_fn=_extra_terrain)

    # ── Canvas MESH ────────────────────────────────────────────────
    def _draw_mesh(self):
        cv = self._canvases.get("mesh")
        if not cv or not cv.winfo_exists():
            return
        W, H = self._cv_size("mesh")
        cv.delete("all")

        mzl  = int(self._get("mesh_zl", 19))
        ctol = float(self._get("curvature_tol", 16))
        lt   = float(self._get("limit_tris", 15))

        def _extra_mesh(cv2, W2, H2, params2, t2):
            mzl2 = params2.get("mesh_zl", 19)
            ct2  = params2.get("curvature_tol", 16)
            lt2  = params2.get("limit_tris", 15)
            prec = "très précis" if mzl2>=19 else "précis" if mzl2>=17 else "moyen" if mzl2>=15 else "grossier"
            cv2.create_rectangle(0, H2-20, W2, H2, fill="#060e06", outline="")
            cv2.create_text(W2//2, H2-10,
                text=f"mesh_zl {mzl2} — {prec}  |  courbure {ct2}  |  limite {lt2}M triangles",
                fill="#80ff88", font=("TkFixedFont", 9))

        # Le maillage est visible en overlay sur la vue 3D
        params = {
            "curvature_tol": ctol, "mesh_zl": mzl, "limit_tris": lt,
            "normal_map_strength": 1.0, "terrain_casts_shadows": "True",
            "_wire": True,  # affiche le wireframe
            "ratio_water": float(self._get("ratio_water", 0.1)),
        }
        self._iso_draw(cv, W, H, params, self._t, extra_fn=_extra_mesh)

    # ── Canvas IMAGERIE ────────────────────────────────────────────
    def _draw_imagerie(self):
        cv = self._canvases.get("imagerie")
        if not cv or not cv.winfo_exists():
            return
        W, H = self._cv_size("imagerie")
        cv.delete("all")
        import math, random

        dzl  = int(self._get("default_zl", 17))
        czl  = int(self._get("cover_zl", 18))
        cext = float(self._get("cover_extent", 1.0))
        apt  = str(self._get("cover_airports_with_highres", "False"))
        rl   = int(self._get("road_level", 4))

        def _extra_imagerie(cv2, W2, H2, params2, t2):
            dzl2  = params2.get("default_zl", 17)
            czl2  = params2.get("cover_zl", 18)
            apt2  = params2.get("cover_airports_with_highres", "False")
            rl2   = params2.get("road_level", 4)
            cext2 = params2.get("cover_extent", 1.0)

            # Zone aéroport : cercle en projection iso sur la plaine
            if apt2 == "True":
                ax = int(W2*0.55); ay = int(H2*0.55)
                ar = int(cext2*20 + 12)
                cv2.create_oval(ax-ar, ay-ar//2, ax+ar, ay+ar//2,
                    outline="#88ff44", width=1.5, dash=(4,2))
                cv2.create_rectangle(ax-18, ay-4, ax+18, ay+4,
                    fill="#606060", outline="#aaaaaa")
                cv2.create_text(ax, ay-ar//2-8,
                    text=f"ZL{czl2}", fill="#88ff44",
                    font=("TkFixedFont", 8, "bold"))

            # Routes : lignes obliques en iso sur la plaine
            rng2 = random.Random(rl2)
            for i in range(rl2):
                y_r = int(H2*(0.45 + i*0.05))
                x0 = int(W2*0.25); x1 = int(W2*0.75)
                road_pts = []
                for x in range(x0, x1, 5):
                    ry = y_r + int(math.sin(x*0.04 + i)*2)
                    road_pts.extend([x, ry])
                if len(road_pts) >= 4:
                    cv2.create_line(road_pts,
                        fill="#c8b068", width=max(0.5, rl2*0.3),
                        smooth=True)

            qual_lbl = "HD" if dzl2>=19 else "SD" if dzl2>=17 else "LD"
            cv2.create_rectangle(0, H2-20, W2, H2, fill="#060e06", outline="")
            cv2.create_text(W2//2, H2-10,
                text=(f"ZL{dzl2} — {qual_lbl}  |  "
                      f"routes niv.{rl2}  |  "
                      f"aéroport={'ZL'+str(czl2) if apt2=='True' else '✗'}"),
                fill="#e0c080", font=("TkFixedFont", 9))

        params = {
            "default_zl": dzl, "cover_zl": czl, "cover_extent": cext,
            "cover_airports_with_highres": apt, "road_level": rl,
            "curvature_tol": 16, "normal_map_strength": 1.0,
            "terrain_casts_shadows": "True",
            "ratio_water": float(self._get("ratio_water", 0.1)),
        }
        self._iso_draw(cv, W, H, params, self._t, extra_fn=_extra_imagerie)

    # ── Ouverture fenêtre Vue Tuile ───────────────────────────────
    def _open_tile_view(self):
        if hasattr(self, "_tile_view_win") and self._tile_view_win and                 self._tile_view_win.winfo_exists():
            self._tile_view_win.lift()
            self._tile_view_win.focus_force()
            return
        self._tile_view_win = Ortho4XP_TileView(
            self, self.lat, self.lon,
            self.custom_build_dir, self._vars)

    # ── Chargement valeurs depuis cfg ──────────────────────────────
    def _load_values(self):
        self._tile = CFG.Tile(self.lat, self.lon, self.custom_build_dir)
        self._tile.read_from_config()
        bool_map = {True:"True", False:"False"}
        for key, var in self._vars.items():
            try:
                val = getattr(self._tile, key, None)
                if val is None:
                    continue
                if isinstance(var, tk.StringVar):
                    if isinstance(val, bool):
                        var.set(bool_map[val])
                    else:
                        var.set(str(val))
                else:
                    var.set(val)
            except Exception:
                pass
        self._status.config(
            text="✓ Valeurs chargées depuis le cfg.", fg=self.FG2)

    # ── Écriture cfg tuile ─────────────────────────────────────────
    def _write_tile(self):
        try:
            self._apply_to_tile()
            self._tile.write_to_config()
            self._status.config(
                text="✅ Sauvegardé dans cfg tuile.", fg=self.FG2)
        except Exception as e:
            self._status.config(text=f"❌ {e}", fg="#ff6b6b")

    # ── Écriture cfg app global ────────────────────────────────────
    def _write_app(self):
        try:
            self._apply_to_tile()
            # Écrire le cfg global Ortho4XP
            import O4_Config_Utils as _CFG
            cfg_path = os.path.join(
                FNAMES.Ortho4XP_dir, "Ortho4XP.cfg")
            self._tile.write_to_config(cfg_path)
            self._status.config(
                text="✅ Sauvegardé dans cfg global.", fg=self.FG2)
        except Exception as e:
            self._status.config(text=f"❌ {e}", fg="#ff6b6b")

    def _apply_to_tile(self):
        bool_keys = {
            "use_masks_for_inland","imprint_masks_to_dds",
            "distance_masks_too","masks_use_DEM_too",
            "cover_airports_with_highres","terrain_casts_shadows",
            "use_decal_on_terrain","fill_nodata","clean_bad_geometries"
        }
        for key, var in self._vars.items():
            try:
                raw = var.get()
                if key in bool_keys:
                    setattr(self._tile, key, raw == "True")
                elif isinstance(raw, str):
                    try:
                        setattr(self._tile, key, float(raw)
                            if '.' in raw else int(raw))
                    except Exception:
                        setattr(self._tile, key, raw)
                else:
                    setattr(self._tile, key, raw)
            except Exception:
                pass
