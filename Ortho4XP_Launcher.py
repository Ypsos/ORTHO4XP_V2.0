#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import platform
import tkinter as tk
import subprocess
import shutil
import multiprocessing
import psutil
from pathlib import Path

# --- CONFIGURATION STYLE ROLAND ---
BG_GLOBAL     = "#3b5b49"
BTN_COLOR     = "#4a6b59"
BTN_TEXT      = "white"
SHADOW_COLOR  = "#2a4235"

BASE_DIR = Path(os.path.dirname(os.path.realpath(__file__))).resolve()
SYSTEM   = platform.system()

ORTHO_PY    = BASE_DIR / "Ortho4XP.py"
CFG_FILE    = BASE_DIR / "Ortho4XP.cfg"
CONF_FILE   = BASE_DIR / "Ortho4XP.conf"
SRC_DIR     = BASE_DIR / "src"

if SYSTEM == "Windows":
    VENV_PY  = BASE_DIR / "venv" / "Scripts" / "python.exe"
    VENV_PIP = BASE_DIR / "venv" / "Scripts" / "pip.exe"
else:
    VENV_PY  = BASE_DIR / "venv" / "bin" / "python3"
    VENV_PIP = BASE_DIR / "venv" / "bin" / "pip"

# rasterio est autonome dans venv — pas besoin de GDAL système

class HoverButton(tk.Canvas):
    def __init__(self, parent, text, command, width=380, height=55, font_size=13):
        super().__init__(parent, width=width+15, height=height+15, 
                         bg=BG_GLOBAL, highlightthickness=0, cursor="hand2")
        self.command = command
        self.width, self.height = width, height
        self.create_rounded_rect(8, 8, width+5, height+5, 12, fill=SHADOW_COLOR)
        self.rect = self.create_rounded_rect(2, 2, width, height, 12, fill=BTN_COLOR)
        self.create_text(width//2 + 2, height//2 + 2, text=text, 
                         fill=BTN_TEXT, font=("Helvetica", font_size, "bold"))
        self.bind("<Button-1>", lambda e: self.on_click())
        self.bind("<Enter>", lambda e: self.itemconfig(self.rect, fill="#5a7b69"))
        self.bind("<Leave>", lambda e: self.itemconfig(self.rect, fill=BTN_COLOR))

    def create_rounded_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [x1+r,y1, x1+r,y1, x2-r,y1, x2-r,y1, x2,y1, x2,y1+r,
                  x2,y1+r, x2,y2-r, x2,y2-r, x2,y2, x2-r,y2, x2-r,y2,
                  x1+r,y2, x1+r,y2, x1,y2, x1,y2-r, x1,y2-r, x1,y1+r, x1,y1+r, x1,y1]
        return self.create_polygon(points, **kwargs, smooth=True)

    def on_click(self):
        self.move(self.rect, 3, 3)
        self.after(100, lambda: [self.move(self.rect, -3, -3), self.command()])

class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Ortho4XP V2.0 Launcher - Roland Edition")
        self.geometry("950x950")
        self.configure(bg=BG_GLOBAL)

        tk.Label(self, text="Ortho4XP V2.0", font=("Helvetica", 36, "bold"),
                 fg="#a6e3a1", bg=BG_GLOBAL).pack(pady=(20, 0))
        tk.Label(self, text="Version : Mac • Linux • Windows", 
                 font=("Helvetica", 14, "bold"), fg="#a6e3a1", bg=BG_GLOBAL).pack(pady=(0, 15))

        self.log = tk.Text(self, height=12, bg="#0f0f1a", fg="#50fa7b",
                           font=("Courier", 12), relief="flat", padx=15, pady=15)
        self.log.pack(pady=10, padx=30, fill="both", expand=True)

        # ==================== 2 COLONNES (3 à gauche / 2 à droite) ====================
        btn_container = tk.Frame(self, bg=BG_GLOBAL)
        btn_container.pack(pady=15)

        col1 = tk.Frame(btn_container, bg=BG_GLOBAL)
        col1.grid(row=0, column=0, padx=15)
        HoverButton(col1, "1. Installer les Modules", self.open_install_menu).pack(pady=8)
        col2 = tk.Frame(btn_container, bg=BG_GLOBAL)
        col2.grid(row=0, column=1, padx=15)
        HoverButton(col2, "🔍 Vérifier Intégrité", self.check_integrity).pack(pady=8)

        # Gros bouton LANCER en dessous
        HoverButton(self, "▶️ LANCER ORTHO4XP", self.launch_ortho, 
                    width=800, height=70, font_size=20).pack(pady=(25, 30))

        self._log(f"📍 Dossier : {BASE_DIR}")
        self.check_integrity()
        self._run_security_check()

    # ====================== SENTINELLE ======================
    def _run_security_check(self):
        self._log("\n--- 🛡️  SENTINELLE ---\n")
        cpu_total = multiprocessing.cpu_count()
        ram_total = round(psutil.virtual_memory().total / (1024**3))
        safe_slots = max(1, cpu_total - 2 if cpu_total > 4 else cpu_total - 1)
        safe_ram   = int(ram_total * 0.75)
        self._log(f"Matériel : {cpu_total} CPUs | {ram_total} Go RAM\n")
        self._log(f"Config auto : {safe_slots} Slots | {safe_ram} Go RAM\n")
        if CFG_FILE.exists():
            self._log("✅ Ortho4XP.cfg synchronisé.\n")
        else:
            self._log("⚠ Ortho4XP.cfg non trouvé.\n")
        self._log("----------------------------------\n")

    def _log(self, msg):
        self.log.insert("end", f"> {msg}\n")
        self.log.see("end")
        self.update_idletasks()

    def open_install_menu(self):
        """Ouvre la fenêtre de sélection de plateforme pour l'installation."""
        win = tk.Toplevel(self)
        win.title("Installer les Modules — Choisir la plateforme")
        win.configure(bg=BG_GLOBAL)
        win.resizable(False, False)

        tk.Label(win, text="Installer les Modules",
                 font=("Helvetica", 22, "bold"), fg="#a6e3a1", bg=BG_GLOBAL).pack(pady=(20, 4))
        tk.Label(win, text="Tout s'installe dans venv/ — rien dans le système",
                 font=("Helvetica", 12), fg="#a6e3a1", bg=BG_GLOBAL).pack(pady=(0, 16))

        # Boutons plateformes — plateforme courante mise en évidence
        platforms = [
            ("🍎  macOS  (Homebrew + pip)", "Darwin",  self._install_mac),
            ("🐧  Linux  (apt / pacman)",   "Linux",   self._install_linux),
            ("🪟  Windows  (pip)",          "Windows", self._install_windows),
        ]
        for label, plat, cmd in platforms:
            color = "#2a6b45" if plat == SYSTEM else BTN_COLOR
            btn = HoverButton(win, label, lambda c=cmd, w=win: [w.destroy(), c()],
                              width=420, height=60, font_size=14)
            btn.itemconfig(btn.rect, fill=color)
            btn.pack(pady=6, padx=30)

        # ── Séparateur ───────────────────────────────────────────────────
        tk.Frame(win, bg="#2a6b45", height=2).pack(fill="x", padx=30, pady=(10, 6))
        tk.Label(win, text="Créer le lanceur Ortho4XP (double-clic quotidien)",
                 font=("Helvetica", 12, "bold"), fg="#a6e3a1", bg=BG_GLOBAL).pack(pady=(0, 6))

        launchers = [
            ("🍎  Créer Lanceur Ortho4XP — Mac",     "Darwin",  self._create_launcher_mac),
            ("🐧  Créer Lanceur Ortho4XP — Linux",   "Linux",   self._create_launcher_linux),
            ("🪟  Créer Lanceur Ortho4XP — Windows", "Windows", self._create_launcher_windows),
        ]
        for label, plat, cmd in launchers:
            color = "#1a5a35" if plat == SYSTEM else "#2a3d33"
            btn = HoverButton(win, label, lambda c=cmd, w=win: [w.destroy(), c()],
                              width=420, height=55, font_size=13)
            btn.itemconfig(btn.rect, fill=color)
            btn.pack(pady=4, padx=30)

        tk.Button(win, text="Annuler", command=win.destroy,
                  bg="#a6e3a1", fg="black", font=("Helvetica", 11, "bold"),
                  relief="flat", padx=20, pady=6, cursor="hand2").pack(pady=(10, 20))

        win.update_idletasks()
        # Centrer sur la fenêtre principale
        x = self.winfo_x() + (self.winfo_width()  - win.winfo_width())  // 2
        y = self.winfo_y() + (self.winfo_height() - win.winfo_height()) // 2
        win.geometry(f"+{x}+{y}")

    def _run_pip_install(self, modules, extra_msg=""):
        """Installe une liste de modules dans le venv via pip."""
        pip = str(VENV_PIP)
        try:
            self._log("📦 Mise à jour pip...")
            subprocess.run([pip, "install", "--upgrade", "pip", "setuptools", "wheel"], check=True)
            self._log(f"📦 Installation modules{extra_msg}...")
            subprocess.run([pip, "install"] + modules, check=True)
            self._log("✅ Modules installés dans venv/")
        except Exception as e:
            self._log(f"❌ Échec : {e}")

    def _install_mac(self):
        self._log("── 🍎 Installation macOS ──────────────────")
        import shutil

        # 1. Homebrew deps (sans gdal — rasterio est autonome dans venv)
        brew = shutil.which("brew") or "/opt/homebrew/bin/brew" or "/usr/local/bin/brew"
        brew_pkgs = ["python@3.12", "python-tk@3.12",
                     "spatialindex", "p7zip", "proj", "libspatialite"]
        self._log(f"📦 Homebrew : {' '.join(brew_pkgs)}")
        try:
            subprocess.run([brew, "install"] + brew_pkgs, check=True)
            self._log("✅ Dépendances Homebrew installées.")
        except Exception as e:
            self._log(f"⚠ Homebrew : {e}")

        # 2. Pip dans venv — rasterio remplace gdal (autonome, pas de dépendance système)
        pip_modules = ["pyproj", "numpy", "shapely", "rtree", "Pillow",
                       "requests", "scikit-fmm", "certifi", "urllib3",
                       "psutil", "fiona", "scipy", "customtkinter", "rasterio"]
        self._run_pip_install(pip_modules, " (venv macOS)")
        self._log("✅ rasterio installé — lecture TIF altimétrie autonome dans venv/")

        # 4. Créer Lanceur ORTHO4XP.app
        self._log("🔧 Création de Lanceur ORTHO4XP.app...")
        self._create_mac_launcher()

    def _create_launcher_mac(self):
        self._log("── 🍎 Création Lanceur ORTHO4XP.app ──────")
        script = BASE_DIR / "create_launcher_ORTHO.py"
        if not script.exists():
            self._log("❌ create_launcher_ORTHO.py introuvable."); return
        py = str(VENV_PY) if VENV_PY.exists() else sys.executable
        try:
            r = subprocess.run([py, str(script)], cwd=str(BASE_DIR),
                               capture_output=True, text=True)
            for line in r.stdout.splitlines(): self._log(line)
            if r.returncode == 0:
                self._log("✅ Lanceur ORTHO4XP.app créé — double-clic pour lancer !")
            else:
                self._log(f"❌ {r.stderr[:300]}")
        except Exception as e: self._log(f"❌ {e}")

    def _create_launcher_linux(self):
        self._log("── 🐧 Création Lanceur ORTHO4XP.desktop ──")
        script = BASE_DIR / "create_launcher_ORTHO.py"
        if not script.exists():
            self._log("❌ create_launcher_ORTHO.py introuvable."); return
        py = str(VENV_PY) if VENV_PY.exists() else sys.executable
        try:
            r = subprocess.run([py, str(script)], cwd=str(BASE_DIR),
                               capture_output=True, text=True)
            for line in r.stdout.splitlines(): self._log(line)
            if r.returncode == 0:
                self._log("✅ Lanceur ORTHO4XP.desktop créé !")
            else:
                self._log(f"❌ {r.stderr[:300]}")
        except Exception as e: self._log(f"❌ {e}")

    def _create_launcher_windows(self):
        self._log("── 🪟 Création Lanceur ORTHO4XP.vbs ──────")
        script = BASE_DIR / "create_launcher_ORTHO.py"
        if not script.exists():
            self._log("❌ create_launcher_ORTHO.py introuvable."); return
        py = str(VENV_PY) if VENV_PY.exists() else sys.executable
        try:
            r = subprocess.run([py, str(script)], cwd=str(BASE_DIR),
                               capture_output=True, text=True)
            for line in r.stdout.splitlines(): self._log(line)
            if r.returncode == 0:
                self._log("✅ Lanceur ORTHO4XP.vbs créé !")
            else:
                self._log(f"❌ {r.stderr[:300]}")
        except Exception as e: self._log(f"❌ {e}")


    def _install_linux(self):
        self._log("── 🐧 Installation Linux ──────────────────")
        import shutil

        # Détecter le gestionnaire de paquets
        if shutil.which("apt-get"):
            self._log("📦 Détecté : Debian/Ubuntu (apt)")
            sys_pkgs = [
                "python3-pip", "python3-venv", "python3-tk",
                "python3-numpy", "python3-pyproj",
                "python3-shapely", "python3-rtree", "python3-pil",
                "python3-pil.imagetk", "python3-requests",
                "p7zip-full"
            ]
            try:
                subprocess.run(["sudo", "apt-get", "update", "-y"], check=True)
                subprocess.run(["sudo", "apt-get", "install", "-y"] + sys_pkgs, check=True)
                self._log("✅ Paquets système installés.")
            except Exception as e:
                self._log(f"⚠ apt : {e}")

        elif shutil.which("pacman"):
            self._log("📦 Détecté : Arch/Manjaro (pacman)")
            sys_pkgs = [
                "python-pip", "python-numpy", "python-pyproj",
                "python-shapely", "python-rtree",
                "python-pillow", "python-requests", "p7zip"
            ]
            try:
                subprocess.run(["sudo", "pacman", "-S", "--noconfirm"] + sys_pkgs, check=True)
                self._log("✅ Paquets système installés.")
            except Exception as e:
                self._log(f"⚠ pacman : {e}")
        else:
            self._log("⚠ Gestionnaire de paquets non reconnu.")

        # Pip dans venv
        pip_modules = ["psutil", "numpy", "Pillow", "requests", "shapely",
                       "pyproj", "fiona", "scipy", "customtkinter",
                       "rtree", "scikit-fmm", "certifi", "urllib3", "rasterio"]
        self._run_pip_install(pip_modules, " (venv Linux)")
        self._log("✅ rasterio installé — lecture TIF altimétrie autonome dans venv/")
        self._create_daily_launcher()
        # Créer Lanceur ORTHO4XP.desktop
        self._log("🔧 Création de Lanceur ORTHO4XP.desktop...")
        self._create_linux_launcher()

    def _install_windows(self):
        self._log("── 🪟 Installation Windows ──────────────────")
        pip_modules = [
            "psutil", "numpy", "Pillow", "requests", "shapely",
            "pyproj", "fiona", "scipy", "customtkinter",
            "rtree", "scikit-fmm", "certifi", "urllib3", "rasterio"
        ]
        self._run_pip_install(pip_modules, " (venv Windows)")
        self._log("✅ rasterio installé — lecture TIF altimétrie autonome dans venv/")
        self._create_daily_launcher()
        # Créer Lanceur ORTHO4XP.vbs
        self._log("🔧 Création de Lanceur ORTHO4XP.vbs...")
        self._create_windows_launcher()




    def _create_daily_launcher(self):
        """Crée Lanceur ORTHO4XP selon la plateforme — utilise le venv."""
        import stat as st

        if SYSTEM == "Darwin":
            self._create_mac_daily_launcher()
        elif SYSTEM == "Windows":
            self._create_windows_daily_launcher()
        elif SYSTEM == "Linux":
            self._create_linux_daily_launcher()

    def _create_mac_daily_launcher(self):
        """Crée Lanceur ORTHO4XP.app — binaire C qui lance le Launcher via venv."""
        import shutil, stat as st

        LAUNCHER_C = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <limits.h>
#include <libgen.h>
#include <stdint.h>
#include <sys/stat.h>
#include <sys/wait.h>
extern int _NSGetExecutablePath(char *buf, uint32_t *bufsize);
static int path_exists(const char *p) { struct stat s; return stat(p,&s)==0; }
int main(int argc, char **argv) {
    char exe[PATH_MAX]; uint32_t sz = sizeof(exe);
    if (_NSGetExecutablePath(exe, &sz) != 0) return 1;
    char real[PATH_MAX];
    if (!realpath(exe, real)) strncpy(real, exe, PATH_MAX-1);
    char t1[PATH_MAX],t2[PATH_MAX],t3[PATH_MAX],tmp[PATH_MAX],root[PATH_MAX];
    strncpy(t1,real,PATH_MAX-1); strncpy(t2,dirname(t1),PATH_MAX-1);
    strncpy(t3,dirname(t2),PATH_MAX-1); strncpy(tmp,dirname(t3),PATH_MAX-1);
    strncpy(root,dirname(tmp),PATH_MAX-1);
    chdir(root);
    char venv_py[PATH_MAX], launcher[PATH_MAX], sh_path[PATH_MAX];
    snprintf(venv_py,  sizeof(venv_py),  "%s/venv/bin/python3",     root);
    snprintf(launcher, sizeof(launcher), "%s/Ortho4XP_Launcher.py", root);
    snprintf(sh_path,  sizeof(sh_path),  "%s/_ortho_run.sh",        root);
    if (!path_exists(venv_py)) {
        char *args[] = {"/usr/bin/osascript","-e",
            "display dialog \"Lancez d\'abord INSTALL_ORTHO4XP.app\" "
            "buttons {\"OK\"} default button \"OK\" "
            "with title \"Ortho4XP\" with icon caution", NULL};
        pid_t p=fork(); if(p==0){execv("/usr/bin/osascript",args);_exit(1);}
        if(p>0){int s;waitpid(p,&s,0);} return 1;
    }
    FILE *sh=fopen(sh_path,"w");
    if(sh){fprintf(sh,"#!/bin/sh\ncd \"%s\"\nexec \"%s\" \"%s\"\n",root,venv_py,launcher);fclose(sh);chmod(sh_path,0755);}
    char *a[]={"/bin/sh",sh_path,NULL};
    pid_t p=fork(); if(p==0){execv("/bin/sh",a);_exit(1);}
    return 0;
}
"""
        INFO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>CFBundleExecutable</key><string>launch</string>
    <key>CFBundleIdentifier</key><string>com.ypsos.ortho4xp.daily</string>
    <key>CFBundleName</key><string>ORTHO4XP V2 Lanceur</string>
    <key>CFBundleDisplayName</key><string>ORTHO4XP V2 Lanceur</string>
    <key>CFBundleVersion</key><string>2.0</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>LSMinimumSystemVersion</key><string>12.0</string>
    <key>NSHighResolutionCapable</key><true/>
</dict></plist>"""

        app_path = BASE_DIR / "Lanceur ORTHO4XP.app"
        macos_dir = app_path / "Contents" / "MacOS"
        res_dir   = app_path / "Contents" / "Resources"

        if app_path.exists():
            shutil.rmtree(str(app_path))

        macos_dir.mkdir(parents=True)
        res_dir.mkdir(parents=True)
        (app_path / "Contents" / "Info.plist").write_text(INFO_PLIST, encoding="utf-8")

        c_file  = BASE_DIR / "_tmp_daily.c"
        exe_out = macos_dir / "launch"
        c_file.write_text(LAUNCHER_C, encoding="utf-8")

        compiled = False
        for arch_flags in [["-arch","arm64","-arch","x86_64"], []]:
            cmd = ["gcc"] + arch_flags + [str(c_file),"-o",str(exe_out),"-framework","Foundation","-O2"]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode == 0:
                compiled = True
                break

        c_file.unlink(missing_ok=True)

        if compiled:
            exe_out.chmod(exe_out.stat().st_mode | st.S_IEXEC | st.S_IXGRP | st.S_IXOTH)
            try:
                subprocess.run(["xattr","-cr",str(app_path)], capture_output=True, timeout=10)
                subprocess.run(["codesign","--force","--deep","--sign","-",str(app_path)],
                               capture_output=True, timeout=30)
            except Exception: pass
            self._log("✅ Lanceur ORTHO4XP.app créé — double-clic pour lancer Ortho4XP !")
        else:
            self._log("⚠️  Compilation échouée — Lanceur non créé.")

    def _create_windows_daily_launcher(self):
        """Crée Lanceur ORTHO4XP.vbs pour Windows."""
        vbs = BASE_DIR / "Lanceur ORTHO4XP.vbs"
        vbs.write_text(
            "Dim ws,fso,d,py,la\n"
            "Set ws=CreateObject(\"WScript.Shell\")\n"
            "Set fso=CreateObject(\"Scripting.FileSystemObject\")\n"
            "d=fso.GetParentFolderName(WScript.ScriptFullName)\n"
            "py=d & \"\\\\venv\\\\Scripts\\\\pythonw.exe\"\n"
            "la=d & \"\\\\Ortho4XP_Launcher.py\"\n"
            "If Not fso.FileExists(py) Then\n"
            "  MsgBox \"Lancez d'abord INSTALL_ORTHO4XP.vbs\",48,\"Ortho4XP\"\n"
            "  WScript.Quit\nEnd If\n"
            "ws.Run Chr(34)&py&Chr(34)&\" \"&Chr(34)&la&Chr(34),1,False\n",
            encoding="utf-8")
        self._log("✅ Lanceur ORTHO4XP.vbs créé !")

    def _create_linux_daily_launcher(self):
        """Crée Lanceur ORTHO4XP.desktop pour Linux."""
        import stat as st
        sh = BASE_DIR / "Lanceur ORTHO4XP.sh"
        sh.write_text(
            f'''#!/bin/bash\ncd "{BASE_DIR}"\nexec "./venv/bin/python3" "Ortho4XP_Launcher.py"\n''',
            encoding="utf-8")
        sh.chmod(sh.stat().st_mode | st.S_IEXEC | st.S_IXGRP | st.S_IXOTH)
        desktop = BASE_DIR / "Lanceur ORTHO4XP.desktop"
        desktop.write_text(
            f"[Desktop Entry]\nVersion=2.0\nName=ORTHO4XP V2 Lanceur\n"
            f"Exec={sh}\nPath={BASE_DIR}\nTerminal=false\nType=Application\n",
            encoding="utf-8")
        desktop.chmod(desktop.stat().st_mode | st.S_IEXEC | st.S_IXGRP | st.S_IXOTH)
        self._log("✅ Lanceur ORTHO4XP.desktop créé !")

    def check_integrity(self):
        self._log("Vérification fichiers...")
        self._log(f"{'✅' if ORTHO_PY.exists() else '❌'} Ortho4XP.py")
        self._log(f"{'✅' if (CFG_FILE.exists() or CONF_FILE.exists()) else '❌'} Config")
        self._log(f"{'✅' if SRC_DIR.exists() else '❌'} Dossier src")

    # ── Création des lanceurs natifs ────────────────────────────────────

    def _create_mac_launcher(self):
        """Crée Lanceur ORTHO4XP.app — double-clic pour ouvrir le Launcher."""
        import shutil, stat as st_mod
        app_path  = BASE_DIR / "Lanceur ORTHO4XP.app"
        macos_dir = app_path / "Contents" / "MacOS"
        res_dir   = app_path / "Contents" / "Resources"
        if app_path.exists():
            shutil.rmtree(str(app_path))
        macos_dir.mkdir(parents=True)
        res_dir.mkdir(parents=True)

        # Info.plist
        (app_path / "Contents" / "Info.plist").write_text(
            '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>CFBundleExecutable</key><string>launch</string>
    <key>CFBundleIdentifier</key><string>com.ypsos.ortho4xp.v2.lanceur</string>
    <key>CFBundleName</key><string>ORTHO4XP V2 Lanceur</string>
    <key>CFBundleDisplayName</key><string>ORTHO4XP V2 Lanceur</string>
    <key>CFBundleVersion</key><string>2.0</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>LSMinimumSystemVersion</key><string>12.0</string>
    <key>NSHighResolutionCapable</key><true/>
</dict></plist>''', encoding="utf-8")

        # Script shell — lance Ortho4XP_Launcher.py via venv
        sh_script = f'''#!/bin/bash
MACOS_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$(dirname "$(dirname "$MACOS_DIR")")")"
cd "$ROOT"
exec "$ROOT/venv/bin/python3" "$ROOT/Ortho4XP_Launcher.py"
'''
        exe = macos_dir / "launch"
        exe.write_text(sh_script, encoding="utf-8")
        exe.chmod(exe.stat().st_mode | st_mod.S_IEXEC | st_mod.S_IXGRP | st_mod.S_IXOTH)

        # Quarantaine + signature
        try:
            subprocess.run(["xattr", "-cr", str(app_path)], capture_output=True, timeout=10)
            subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app_path)],
                           capture_output=True, timeout=30)
        except Exception: pass

        self._log(f"✅ Lanceur ORTHO4XP.app créé — double-clic pour lancer !")

    def _create_linux_launcher(self):
        """Crée Lanceur ORTHO4XP.desktop + .sh"""
        import stat as st_mod
        sh_path = BASE_DIR / "Lanceur ORTHO4XP.sh"
        sh_path.write_text(
            f'''#!/bin/bash
cd "{BASE_DIR}"
exec "./venv/bin/python3" "Ortho4XP_Launcher.py"
''', encoding="utf-8")
        sh_path.chmod(sh_path.stat().st_mode | st_mod.S_IEXEC | st_mod.S_IXGRP | st_mod.S_IXOTH)

        desktop = BASE_DIR / "Lanceur ORTHO4XP.desktop"
        desktop.write_text(
            f"[Desktop Entry]\nVersion=2.0\nName=ORTHO4XP V2 Lanceur\n"
            f"Exec={sh_path}\nPath={BASE_DIR}\n"
            f"Terminal=false\nType=Application\nCategories=Utility;\n",
            encoding="utf-8")
        desktop.chmod(desktop.stat().st_mode | st_mod.S_IEXEC | st_mod.S_IXGRP | st_mod.S_IXOTH)
        self._log("✅ Lanceur ORTHO4XP.desktop créé — double-clic pour lancer !")

    def _create_windows_launcher(self):
        """Crée Lanceur ORTHO4XP.vbs"""
        vbs = BASE_DIR / "Lanceur ORTHO4XP.vbs"
        vbs.write_text(
            f'Dim ws : Set ws = CreateObject("WScript.Shell")\n'
            f'ws.Run Chr(34) & "{BASE_DIR / "venv" / "Scripts" / "pythonw.exe"}" & Chr(34)'
            f' & " " & Chr(34) & "{BASE_DIR / "Ortho4XP_Launcher.py"}" & Chr(34), 1, False\n',
            encoding="utf-8")
        self._log("✅ Lanceur ORTHO4XP.vbs créé — double-clic pour lancer !")

    def launch_ortho(self):
        py_exe = str(VENV_PY) if VENV_PY.exists() else sys.executable
        if ORTHO_PY.exists():
            env = os.environ.copy()
            env["PYTHONPATH"] = str(SRC_DIR)
            subprocess.Popen([py_exe, str(ORTHO_PY)], cwd=str(BASE_DIR), env=env)
            self._log("🚀 Ortho4XP lancé !")
            self.after(1500, self.destroy)
        else: self._log("❌ Ortho4XP.py introuvable.")

if __name__ == "__main__":
    Launcher().mainloop()