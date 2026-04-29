#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════╗
║   ORTHO4XP V2.0 — INSTALLATION PRÉREQUIS              ║
║   Bootstrap autonome multiplateforme                 ║
║   Roland (Ypsos) — Mars 2026                 ║
║   macOS (Apple Silicon + Intel) / Windows / Linux    ║
╚══════════════════════════════════════════════════════╝

Ce script est le PREMIER fichier lancé par l'utilisateur.
Il ne dépend d'aucun module externe — uniquement stdlib Python.
Compatible Python 3.8+ (détecte et installe 3.12 si absent).
"""

import os
import sys
import platform
import subprocess
import shutil
import threading
import webbrowser
from pathlib import Path

# ── tkinter : présent dans toute stdlib Python standard ──────────────────────
try:
    import tkinter as tk
    from tkinter import messagebox
    HAS_TK = True
except ImportError:
    HAS_TK = False

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION VISUELLE — identique au Launcher
# ══════════════════════════════════════════════════════════════════════════════
BG_GLOBAL    = "#3b5b49"
BTN_COLOR    = "#4a6b59"
BTN_HOVER    = "#5a7b69"
BTN_TEXT     = "white"
SHADOW_COLOR = "#2a4235"
GREEN_OK     = "#a6e3a1"
RED_ERR      = "#ff5555"
YELLOW_WARN  = "#f1fa8c"
TEXT_BG      = "#0f0f1a"
TEXT_FG      = "#50fa7b"

# ══════════════════════════════════════════════════════════════════════════════
#  CHEMINS — VERSION UNIVERSELLE MULTI-OS (Correction principale)
# ══════════════════════════════════════════════════════════════════════════════
# Détection robuste du dossier de base (fonctionne avec .app sur macOS)
if getattr(sys, 'frozen', False) and platform.system() == "Darwin":
    # Cas lancé depuis l'application bundle INSTALL_Prerequis.app
    BASE_DIR = Path(sys.executable).resolve().parent.parent.parent
else:
    # Cas normal (lancé directement avec python)
    BASE_DIR = Path(os.path.dirname(os.path.realpath(__file__))).resolve()

BASE_DIR = BASE_DIR.resolve()   # Assure un chemin propre

SYSTEM    = platform.system()          # "Darwin" / "Windows" / "Linux"
MACHINE   = platform.machine().lower() # "arm64" / "x86_64" / "amd64"

LAUNCHER_PY = BASE_DIR / "Ortho4XP_Launcher.py"
VENV_DIR    = BASE_DIR / "venv"

if SYSTEM == "Windows":
    VENV_PY = VENV_DIR / "Scripts" / "python.exe"
else:
    VENV_PY = VENV_DIR / "bin" / "python3"

# ══════════════════════════════════════════════════════════════════════════════
#  UTILITAIRES SYSTÈME
# ══════════════════════════════════════════════════════════════════════════════

def find_python312():
    """Cherche python3.12 sur le système. Retourne le chemin ou None."""
    candidates = []
    if SYSTEM == "Darwin":
        candidates = [
            "/opt/homebrew/bin/python3.12",   # Apple Silicon Homebrew
            "/usr/local/bin/python3.12",       # Intel Homebrew
            "/opt/homebrew/opt/python@3.12/bin/python3.12",
            "/usr/local/opt/python@3.12/bin/python3.12",
        ]
    elif SYSTEM == "Windows":
        # Cherche dans les chemins PATH standard
        for name in ["python3.12", "python"]:
            path = shutil.which(name)
            if path:
                try:
                    result = subprocess.run([path, "--version"],
                                            capture_output=True, text=True, timeout=5)
                    if "3.12" in result.stdout + result.stderr:
                        return path
                except Exception:
                    pass
        candidates = [
            r"C:\Python312\python.exe",
            r"C:\Users\{}\AppData\Local\Programs\Python\Python312\python.exe".format(
                os.environ.get("USERNAME", "user")),
        ]
    else:  # Linux
        candidates = [
            "/usr/bin/python3.12",
            "/usr/local/bin/python3.12",
        ]
        path = shutil.which("python3.12")
        if path:
            return path

    for c in candidates:
        p = Path(c)
        if p.exists():
            return str(p)
    return None


def find_homebrew():
    """Retourne le chemin de brew ou None."""
    for p in ["/opt/homebrew/bin/brew", "/usr/local/bin/brew"]:
        if Path(p).exists():
            return p
    return shutil.which("brew")


def run_cmd(cmd, log_fn=print, env=None, cwd=None):
    """Lance une commande, streame la sortie vers log_fn. Retourne le code retour."""
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, env=env, cwd=cwd,
            encoding="utf-8", errors="replace"
        )
        for line in proc.stdout:
            log_fn(line.rstrip())
        proc.wait()
        return proc.returncode
    except FileNotFoundError as e:
        log_fn(f"❌ Commande introuvable : {e}")
        return 1
    except Exception as e:
        log_fn(f"❌ Erreur : {e}")
        return 1


# ══════════════════════════════════════════════════════════════════════════════
#  LOGIQUE D'INSTALLATION PAR PLATEFORME
# ══════════════════════════════════════════════════════════════════════════════
class Installer:
    """Encapsule toute la logique d'installation."""

    def __init__(self, log_fn=print, progress_fn=None, done_fn=None):
        self.log      = log_fn
        self.progress = progress_fn
        self.done_fn  = done_fn
        self.python312 = None

    def _show_tkinter_status_dialog(self, is_present):
        if not HAS_TK:
            if is_present:
                print("\n✅ Tkinter est installé.")
                input("Appuyez sur Entrée pour continuer...")
            else:
                print("\n❌ Tkinter est absent.")
                print("Veuillez exécuter cette commande dans le Terminal :")
                print("   brew install python-tk@3.12")
                print("\nPuis relancez l'application.")
                input("Appuyez sur Entrée pour quitter...")
            return

        dialog = tk.Toplevel()
        dialog.title("Vérification Tkinter - macOS")
        dialog.configure(bg=BG_GLOBAL)
        dialog.geometry("650x420")
        dialog.resizable(False, False)

        if is_present:
            title = "✅ Tkinter est installé"
            color = GREEN_OK
            msg = "Tkinter est OK.\n\nCliquez sur le bouton pour continuer l'installation."
            btn_text = "✅ Continuer l'installation"
        else:
            title = "❌ Tkinter est absent"
            color = RED_ERR
            msg = (
                "Tkinter n'est pas installé.\n\n"
                "Copiez cette commande dans le Terminal :\n\n"
                "   brew install python-tk@3.12\n\n"
                "Puis relancez l'application après l'installation."
            )
            btn_text = "📋 Copier la commande"

        tk.Label(dialog, text=title, font=("Helvetica", 16, "bold"), fg=color, bg=BG_GLOBAL).pack(pady=25)

        txt = tk.Text(dialog, height=10, bg=TEXT_BG, fg=TEXT_FG, font=("Courier", 11), wrap="word")
        txt.pack(padx=40, pady=10, fill="both", expand=True)
        txt.insert("1.0", msg)
        txt.config(state="disabled")

        def action():
            if not is_present:
                dialog.clipboard_clear()
                dialog.clipboard_append("brew install python-tk@3.12")
                dialog.update()
                btn.config(text="✅ Commande copiée !")
                dialog.after(2000, lambda: btn.config(text=btn_text))
            else:
                dialog.destroy()

        btn = tk.Button(dialog, text=btn_text, command=action,
                        bg="#4a6b59", fg="black", font=("Helvetica", 13, "bold"), height=2)
        btn.pack(pady=20)

        dialog.grab_set()
        dialog.wait_window()

    def _check_tkinter_mac(self):
        if SYSTEM != "Darwin":
            return True

        self.log("── 🔍 Vérification de Tkinter sur macOS ──────────────────────")

        python_to_check = self.python312 or find_python312()
        if not python_to_check:
            return True

        tk_present = False
        try:
            result = subprocess.run([python_to_check, "-c", "import tkinter"], capture_output=True, text=True, timeout=8)
            tk_present = result.returncode == 0
        except:
            pass

        self._show_tkinter_status_dialog(tk_present)

        if not tk_present:
            self._finish(False, "Installation arrêtée : Tkinter requis sur macOS")
            return False

        return True

    def run(self):
        self.log(f"🖥  Plateforme : {SYSTEM} / {MACHINE}")
        self.log(f"📍 Dossier    : {BASE_DIR}")
        self.log("")

        if not self._check_tkinter_mac():
            return

        if SYSTEM == "Darwin":
            self._install_mac()
        elif SYSTEM == "Windows":
            self._install_windows()
        elif SYSTEM == "Linux":
            self._install_linux()
        else:
            self._finish(False, f"Plateforme non supportée : {SYSTEM}")

    # ── macOS ─────────────────────────────────────────────────────────────────
    def _install_mac(self):
        self.log("── 🍎 macOS détecté ──────────────────────────")

        self.python312 = find_python312()
        if self.python312:
            self.log(f"✅ Python 3.12 trouvé : {self.python312}")
            self._set_progress(25)
        else:
            self.log("⚠️  Python 3.12 absent. Installation via Homebrew...")
            brew = find_homebrew()
            if not brew:
                self.log("⚠️  Homebrew absent. Installation en cours...")
                rc = run_cmd(["/bin/bash", "-c", 'curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh | bash'], self.log)
                brew = find_homebrew()
                if not brew:
                    self._finish(False, "❌ Impossible d'installer Homebrew. Installez-le manuellement : https://brew.sh")
                    return
            self.log(f"✅ Homebrew trouvé : {brew}")
            self._set_progress(20)

            self.log("📦 Installation python@3.12 et python-tk@3.12...")
            rc = run_cmd([brew, "install", "python@3.12", "python-tk@3.12"], self.log)
            self.python312 = find_python312()
            if not self.python312 or rc != 0:
                self._finish(False, "❌ Échec installation Python 3.12.\nOuvrez un Terminal et tapez :\nbrew install python@3.12 python-tk@3.12")
                return
            self.log(f"✅ Python 3.12 installé : {self.python312}")
            self._set_progress(40)

        self._create_venv()
        if not self._venv_ok():
            return
        self._set_progress(60)

        self._install_requirements()
        self._set_progress(80)

        self._install_gdal_mac(find_homebrew())
        self._set_progress(90)

        self._launch_launcher()

    # ── Windows ───────────────────────────────────────────────────────────────
    def _install_windows(self):
        self.log("── 🪟 Windows détecté ────────────────────────")
        self.python312 = find_python312()
        if self.python312:
            self.log(f"✅ Python 3.12 trouvé : {self.python312}")
            self._set_progress(25)
        else:
            self.log("⚠️  Python 3.12 absent. Tentative via winget...")
            rc = run_cmd(["winget", "install", "--id", "Python.Python.3.12", "--silent", "--accept-package-agreements", "--accept-source-agreements"], self.log)
            self.python312 = find_python312()
            if not self.python312:
                webbrowser.open("https://www.python.org/downloads/release/python-3120/")
                self._finish(False, "⚠️ Installation automatique impossible.\nLa page de téléchargement Python 3.12 vient de s'ouvrir.\nInstallez-le puis relancez ce programme.\n⚠️ Cochez 'Add Python to PATH' !")
                return
            self.log(f"✅ Python 3.12 installé : {self.python312}")
            self._set_progress(40)

        self._create_venv()
        if not self._venv_ok():
            return
        self._set_progress(60)
        self._install_requirements()
        self._set_progress(85)
        self._launch_launcher()

    # ── Linux ─────────────────────────────────────────────────────────────────
    def _install_linux(self):
        self.log("── 🐧 Linux détecté ──────────────────────────")
        self.python312 = find_python312()
        if not self.python312:
            self.log("⚠️  Python 3.12 absent. Installation via gestionnaire de paquets...")
            if shutil.which("apt-get"):
                run_cmd(["sudo", "apt-get", "update", "-y"], self.log)
                run_cmd(["sudo", "apt-get", "install", "-y", "python3.12", "python3.12-venv", "python3-pip", "python3-tk", "p7zip-full"], self.log)
            elif shutil.which("dnf"):
                run_cmd(["sudo", "dnf", "install", "-y", "python3.12", "python3-tkinter"], self.log)
            elif shutil.which("pacman"):
                run_cmd(["sudo", "pacman", "-S", "--noconfirm", "python", "tk"], self.log)
            self.python312 = find_python312()
            if not self.python312:
                self._finish(False, "❌ Python 3.12 introuvable après installation.\nInstallez-le manuellement puis relancez.")
                return
        self._create_venv()
        if not self._venv_ok():
            return
        self._install_requirements()
        self._set_progress(85)
        self._launch_launcher()

    def _create_venv(self):
        if VENV_DIR.exists():
            self.log(f"♻️  Venv existant trouvé : {VENV_DIR}")
            return
        self.log(f"🔧 Création du venv Python 3.12...")
        rc = run_cmd([self.python312, "-m", "venv", str(VENV_DIR)], self.log)
        if rc != 0:
            self._finish(False, "❌ Échec création du venv.")

    def _venv_ok(self):
        if not VENV_PY.exists():
            self._finish(False, "❌ Venv introuvable après création.")
            return False
        return True

    def _install_requirements(self):
        req_file = BASE_DIR / "requirements.txt"
        self.log("📦 Mise à jour pip...")
        run_cmd([str(VENV_PY), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], self.log)
        if req_file.exists():
            self.log("📦 Installation modules depuis requirements.txt...")
            rc = run_cmd([str(VENV_PY), "-m", "pip", "install", "-r", str(req_file)], self.log)
        else:
            modules = ["psutil", "numpy", "Pillow", "requests", "Shapely", "pyproj", "fiona", "scipy", "customtkinter", "rtree", "scikit-fmm"]
            rc = run_cmd([str(VENV_PY), "-m", "pip", "install"] + modules, self.log)
        if rc != 0:
            self.log("⚠️ Certains modules n'ont pas pu être installés.")
        else:
            self.log("✅ Modules installés.")

    def _install_gdal_mac(self, brew):
        self.log("── 🗺️ GDAL macOS ───────────────────────────")
        if not brew:
            return
        run_cmd([brew, "install", "gdal"], self.log)

    def _launch_launcher(self):
        if not LAUNCHER_PY.exists():
            self._finish(False, f"❌ Ortho4XP_Launcher.py introuvable.")
            return
        self.log("\n✅ Installation Prérequis terminée ! Lancement du Launcher...")
        py_exe = str(VENV_PY) if VENV_PY.exists() else self.python312
        env = os.environ.copy()
        env["PYTHONPATH"] = str(BASE_DIR / "src")
        try:
            subprocess.Popen([py_exe, str(LAUNCHER_PY)], cwd=str(BASE_DIR), env=env)
            self._finish(True, "✅ Ortho4XP Launcher lancé !")
        except Exception as e:
            self._finish(False, f"❌ Impossible de lancer le Launcher : {e}")

    def _set_progress(self, value):
        if self.progress:
            self.progress(value)

    def _finish(self, success, message):
        self.log("")
        self.log(message)
        if self.done_fn:
            self.done_fn(success, message)



# ══════════════════════════════════════════════════════════════════════════════
#  INTERFACE GRAPHIQUE tkinter (uniquement si disponible)
# ══════════════════════════════════════════════════════════════════════════════

if HAS_TK:
    class HoverButton(tk.Canvas):
        def __init__(self, parent, text, command, width=380, height=55, font_size=13):
            super().__init__(parent, width=width + 15, height=height + 15,
                             bg=BG_GLOBAL, highlightthickness=0, cursor="hand2")
            self.command = command
            self.width, self.height = width, height
            self.create_rounded_rect(8, 8, width + 5, height + 5, 12, fill=SHADOW_COLOR)
            self.rect = self.create_rounded_rect(2, 2, width, height, 12, fill=BTN_COLOR)
            self.label_id = self.create_text(
                width // 2 + 2, height // 2 + 2, text=text,
                fill=BTN_TEXT, font=("Helvetica", font_size, "bold"),
                width=width - 20
            )
            self.bind("<Button-1>", lambda e: self.on_click())
            self.bind("<Enter>",    lambda e: self.itemconfig(self.rect, fill=BTN_HOVER))
            self.bind("<Leave>",    lambda e: self.itemconfig(self.rect, fill=BTN_COLOR))
        def create_rounded_rect(self, x1, y1, x2, y2, r, **kwargs):
            pts = [x1+r, y1,  x1+r, y1,  x2-r, y1,  x2-r, y1,
                   x2,   y1,  x2,   y1+r, x2,   y1+r, x2,   y2-r,
                   x2,   y2-r, x2,  y2,   x2-r, y2,   x2-r, y2,
                   x1+r, y2,  x1+r, y2,  x1,   y2,   x1,   y2-r,
                   x1,   y2-r, x1,  y1+r, x1,   y1+r, x1,   y1]
            return self.create_polygon(pts, **kwargs, smooth=True)
        def set_enabled(self, enabled):
            color = BTN_COLOR if enabled else "#2a3d33"
            self.itemconfig(self.rect, fill=color)
            self.itemconfig(self.label_id, fill=BTN_TEXT if enabled else "#667766")
            self.configure(cursor="hand2" if enabled else "arrow")
            self._enabled = enabled
        def on_click(self):
            if not getattr(self, "_enabled", True):
                return
            self.move(self.rect, 3, 3)
            self.after(100, lambda: [self.move(self.rect, -3, -3), self.command()])
    class InstallApp(tk.Tk):
        def __init__(self):
            super().__init__()
            # ── Tailles identiques à Ortho4XP_Launcher — macOS scale auto en 4K ──
            fsize_title  = 36
            fsize_sub    = 14
            fsize_log    = 12
            fsize_btn    = 13
            fsize_launch = 20
            self.title("Ortho4XP V2.0 — Installation Prérequis")
            self.configure(bg=BG_GLOBAL)
            self.resizable(True, True)
            self.geometry("950x950")
            self.minsize(950, 950)
            # ── Titre ───────────────────────────────────────────────────────────
            tk.Label(self, text="✈  Ortho4XP V2.0",
                     font=("Helvetica", fsize_title, "bold"),
                     fg=GREEN_OK, bg=BG_GLOBAL).pack(pady=(20, 0))
            tk.Label(self, text="Version : Mac • Linux • Windows",
                     font=("Helvetica", fsize_sub), fg=GREEN_OK, bg=BG_GLOBAL).pack(pady=(2, 8))
            # ── Barre de progression ─────────────────────────────────────────────
            prog_frame = tk.Frame(self, bg=BG_GLOBAL)
            prog_frame.pack(fill="x", padx=30, pady=(0, 5))
            tk.Label(prog_frame, text="Progression :", fg=GREEN_OK, bg=BG_GLOBAL,
                     font=("Helvetica", fsize_sub)).pack(side="left")
            self.prog_var = tk.IntVar(value=0)
            self.prog_bar = tk.Canvas(prog_frame, height=18, bg="#1a2a22",
                                      highlightthickness=1,
                                      highlightbackground="#4a6b59")
            self.prog_bar.pack(side="left", fill="x", expand=True, padx=(10, 0))
            self.prog_bar.bind("<Configure>", self._redraw_progress)
            self._prog_rect = None
            # ── Console log ─────────────────────────────────────────────────────
            self.log_widget = tk.Text(
                self, height=12, bg=TEXT_BG, fg=TEXT_FG,
                font=("Courier", fsize_log), relief="flat",
                padx=12, pady=12, state="disabled"
            )
            self.log_widget.pack(pady=8, padx=30, fill="both", expand=True)
            # Tags de couleur
            self.log_widget.tag_config("ok",   foreground=GREEN_OK)
            self.log_widget.tag_config("err",  foreground=RED_ERR)
            self.log_widget.tag_config("warn", foreground=YELLOW_WARN)
            # ── Boutons ─────────────────────────────────────────────────────────
            btn_frame = tk.Frame(self, bg=BG_GLOBAL)
            btn_frame.pack(pady=10)
            plat_label = {"Darwin": "macOS", "Windows": "Windows", "Linux": "Linux"}.get(SYSTEM, SYSTEM)
            arch_label = "Apple Silicon" if MACHINE == "arm64" else "Intel/x86"
            btn_text   = f"🚀  Lancer l'Installation ({plat_label} {arch_label})"
            self.btn_install = HoverButton(btn_frame, btn_text, self.start_install,
                                           width=800, height=70, font_size=fsize_launch)
            self.btn_install.pack(pady=6)
            self.btn_quit = HoverButton(btn_frame, "✖  Quitter", self.destroy,
                                        width=180, height=55, font_size=fsize_btn)
            self.btn_quit.pack(pady=4)
            # ── Statut ──────────────────────────────────────────────────────────
            self.status_var = tk.StringVar(value="Prêt — cliquez sur le bouton pour commencer.")
            tk.Label(self, textvariable=self.status_var,
                     fg=YELLOW_WARN, bg=BG_GLOBAL,
                     font=("Helvetica", fsize_sub, "italic")).pack(pady=(4, 12))
            # Affichage info plateforme au démarrage
            self._log(f"Plateforme détectée : {SYSTEM} / {MACHINE}")
            self._log(f"Dossier Ortho4XP   : {BASE_DIR}")
            self._log("")
            self._check_existing()
        # ── Vérification état initial ────────────────────────────────────────────
        def _check_existing(self):
            py = find_python312()
            brew = find_homebrew() if SYSTEM == "Darwin" else None
            venv_ok = VENV_PY.exists()
            launcher_ok = LAUNCHER_PY.exists()

            self._log(f"{'✅' if py        else '❌'} Python 3.12  : {py or 'non trouvé'}")
            if SYSTEM == "Darwin":
                self._log(f"{'✅' if brew     else '❌'} Homebrew     : {brew or 'non trouvé'}")
            self._log(f"{'✅' if venv_ok   else '⭕'} Venv         : {'présent' if venv_ok else 'à créer'}")
            self._log(f"{'✅' if launcher_ok else '❌'} Launcher     : {'présent' if launcher_ok else 'MANQUANT'}")
            self._log("")

            # ── Cas 1 : TOUT déjà prêt → lancer directement sans rien faire ─
            # Vérifier modules dans le venv
            modules_ok = False
            if venv_ok:
                try:
                    r = subprocess.run(
                        [str(VENV_PY), "-c", "import psutil, numpy, PIL, customtkinter"],
                        capture_output=True, timeout=5)
                    modules_ok = r.returncode == 0
                except Exception:
                    modules_ok = False
            self._log(f"{'✅' if modules_ok else '⭕'} Modules      : {'présents' if modules_ok else 'à installer'}")

            if py and venv_ok and launcher_ok and modules_ok:
                self._log("✅ Python 3.12 et venv déjà présents.", tag="ok")
                self._log("✅ Tout est configuré — lancement d'Ortho4XP...", tag="ok")
                self.status_var.set("✅ Tout est prêt — lancement dans 3 secondes...")
                self.set_progress(100)
                self.btn_install.set_enabled(False)
                self.after(1500, self._auto_launch)
                return

            # ── Cas 2 : Launcher manquant → bloquer ─────────────────────────
            if not launcher_ok:
                self._log("❌ Ortho4XP_Launcher.py introuvable !", tag="err")
                self._log("   Vérifiez que l'archive est bien décompressée.", tag="warn")

        def _auto_launch(self):
            """Lancement direct quand tout est déjà installé.
            Ferme la fenêtre AVANT de lancer le Launcher."""
            py = find_python312()
            py_exe = str(VENV_PY) if VENV_PY.exists() else py
            env = os.environ.copy()
            env["PYTHONPATH"] = str(BASE_DIR / "src")
            if SYSTEM == "Darwin":
                brew = find_homebrew()
                if brew:
                    try:
                        r = subprocess.run([brew, "--prefix", "gdal"],
                                           capture_output=True, text=True)
                        gdal_lib = r.stdout.strip() + "/lib"
                        env["DYLD_LIBRARY_PATH"] = (
                            gdal_lib + ":" + env.get("DYLD_LIBRARY_PATH", ""))
                    except Exception:
                        pass
            # Fermer la fenêtre EN PREMIER puis lancer le Launcher
            self.destroy()
            try:
                subprocess.Popen([py_exe, str(LAUNCHER_PY)],
                                 cwd=str(BASE_DIR), env=env)
            except Exception as e:
                print(f"❌ Erreur lancement : {e}")

        # ── Démarrage installation ───────────────────────────────────────────────
        def start_install(self):
            self.btn_install.set_enabled(False)
            self.status_var.set("Installation en cours…")
            self._log("", tag=None)
            self._log("════════ DÉMARRAGE INSTALLATION ════════")
            installer = Installer(
                log_fn=self._log,
                progress_fn=self.set_progress,
                done_fn=self._on_done
            )
            t = threading.Thread(target=installer.run, daemon=True)
            t.start()
        def _on_done(self, success, message):
            self.after(0, lambda: self._finish_ui(success, message))
        def _finish_ui(self, success, message):
            if success:
                self.status_var.set("✅ Installation terminée — Launcher lancé !")
                self.set_progress(100)
                self.after(2500, self.destroy)
            else:
                self.status_var.set("⚠️  Voir les messages ci-dessus.")
                self.btn_install.set_enabled(True)
        # ── Barre de progression ─────────────────────────────────────────────────
        def set_progress(self, value):
            self.after(0, lambda: self._update_progress(value))
        def _update_progress(self, value):
            self.prog_var.set(value)
            self._redraw_progress()
        def _redraw_progress(self, event=None):
            w = self.prog_bar.winfo_width()
            h = self.prog_bar.winfo_height()
            if w < 2:
                return
            self.prog_bar.delete("all")
            filled = int(w * self.prog_var.get() / 100)
            if filled > 0:
                self.prog_bar.create_rectangle(0, 0, filled, h,
                                               fill=GREEN_OK, outline="")
            pct = self.prog_var.get()
            self.prog_bar.create_text(w // 2, h // 2,
                                      text=f"{pct}%",
                                      fill="white" if pct < 50 else "#0f0f1a",
                                      font=("Helvetica", 9, "bold"))
        # ── Logging ─────────────────────────────────────────────────────────────
        def _log(self, msg, tag=None):
            def _insert():
                self.log_widget.config(state="normal")
                # Auto-tag selon contenu
                t = tag
                if t is None:
                    low = msg.lower()
                    if any(x in low for x in ["✅", "ok", "créé", "trouvé", "installé", "terminé"]):
                        t = "ok"
                    elif any(x in low for x in ["❌", "erreur", "impossible", "échec", "manquant"]):
                        t = "err"
                    elif any(x in low for x in ["⚠", "absent", "non trouvé", "attention"]):
                        t = "warn"
                if t:
                    self.log_widget.insert("end", f"{msg}\n", t)
                else:
                    self.log_widget.insert("end", f"{msg}\n")
                self.log_widget.see("end")
                self.log_widget.config(state="disabled")
                self.update_idletasks()
            self.after(0, _insert)

# ══════════════════════════════════════════════════════════════════════════════
#  FALLBACK CONSOLE (si tkinter absent)
# ══════════════════════════════════════════════════════════════════════════════

def run_console():
    print("=" * 55)
    print("  ORTHO4XP V2.0 — INSTALLATION PRÉREQUIS (mode texte)")
    print("=" * 55)
    print(f"Plateforme : {SYSTEM} / {MACHINE}")
    print(f"Dossier    : {BASE_DIR}")
    print()
    installer = Installer(log_fn=print)
    installer.run()
    input("\nAppuyez sur Entrée pour quitter...")


# ══════════════════════════════════════════════════════════════════════════════
#  POINT D'ENTRÉE
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # ── Si tout est déjà OK → lancer le Launcher directement, sans fenêtre ──
    py      = find_python312()
    venv_ok = VENV_PY.exists()
    launcher_ok = LAUNCHER_PY.exists()

    # Vérifier que les modules essentiels sont dans le venv
    modules_ok = False
    if venv_ok:
        try:
            r = subprocess.run(
                [str(VENV_PY), "-c", "import psutil, numpy, PIL, customtkinter"],
                capture_output=True, timeout=5)
            modules_ok = r.returncode == 0
        except Exception:
            modules_ok = False

    if py and venv_ok and launcher_ok and modules_ok:
        # Tout est prêt → lancer Ortho4XP_Launcher.py directement
        py_exe = str(VENV_PY) if VENV_PY.exists() else py
        env = os.environ.copy()
        env["PYTHONPATH"] = str(BASE_DIR / "src")
        if SYSTEM == "Darwin":
            brew = find_homebrew()
            if brew:
                try:
                    r = subprocess.run([brew, "--prefix", "gdal"],
                                       capture_output=True, text=True)
                    gdal_lib = r.stdout.strip() + "/lib"
                    env["DYLD_LIBRARY_PATH"] = gdal_lib + ":" + env.get("DYLD_LIBRARY_PATH", "")
                except Exception:
                    pass
        subprocess.Popen([py_exe, str(LAUNCHER_PY)], cwd=str(BASE_DIR), env=env)
        sys.exit(0)   # ← fermeture immédiate, aucune fenêtre

    # ── Sinon → ouvrir la fenêtre d'installation ────────────────────────────
    if HAS_TK:
        app = InstallApp()
        app.mainloop()
    else:
        print("⚠️  tkinter absent — mode console activé.")
        run_console()
