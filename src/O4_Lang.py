# ============================================================
#  O4_Lang.py  —  ORTHO4XP V2  —  Moteur de traduction
#
#  La langue est sauvegardée dans Ortho4XP.cfg (racine)
#  sous la clé :  language=EN   ou   language=FR
#
#  Usage dans les autres fichiers :
#      from O4_Lang import tr
#      button = ttk.Button(frame, text=tr("Assemble Vector data"))
#
#  Au 1er lancement (clé absente de Ortho4XP.cfg) → dialogue de choix.
#  Depuis l'interface → bouton dans Outils : "🌐 Changer la langue…"
# ============================================================

import os
import tkinter as tk
from tkinter import ttk

# ── Chemin du fichier de config global ────────────────────────────
try:
    import O4_File_Names as FNAMES
    _cfg_path = os.path.join(FNAMES.Ortho4XP_dir, "Ortho4XP.cfg")
except Exception:
    # O4_Lang.py est dans src/ — remonter d'un niveau pour trouver Ortho4XP.cfg
    _src_dir  = os.path.dirname(os.path.abspath(__file__))
    _root_dir = os.path.dirname(_src_dir)
    _cfg_path = os.path.join(_root_dir, "Ortho4XP.cfg")

# ── Langues disponibles ────────────────────────────────────────────
AVAILABLE_LANGS = {
    "EN": "O4_Lang_EN",
    "FR": "O4_Lang_FR",
}

# ── État interne ───────────────────────────────────────────────────
_current_lang = "EN"
_translations  = {}


# ──────────────────────────────────────────────────────────────────
#  LECTURE / ÉCRITURE dans Ortho4XP.cfg
# ──────────────────────────────────────────────────────────────────

def _read_lang_from_cfg():
    """
    Lit la valeur de la clé 'language' dans Ortho4XP.cfg.
    Retourne le code ('EN' ou 'FR') ou None si absent / illisible.
    Format du fichier : une variable par ligne  ->  language=FR
    """
    if not os.path.isfile(_cfg_path):
        return None
    try:
        with open(_cfg_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("language="):
                    code = line.split("=", 1)[1].strip().upper()
                    if code in AVAILABLE_LANGS:
                        return code
    except Exception as e:
        print("[O4_Lang] Cannot read {}: {}".format(_cfg_path, e))
    return None


def _write_lang_to_cfg(code):
    """
    Ecrit (ou met a jour) la cle 'language=XX' dans Ortho4XP.cfg.
    Si le fichier existe, remplace la ligne language= existante
    ou ajoute la ligne en fin de fichier. Conserve tout le reste intact.
    """
    code = code.upper().strip()
    try:
        lines = []
        found = False
        if os.path.isfile(_cfg_path):
            with open(_cfg_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for i, line in enumerate(lines):
                if line.strip().startswith("language="):
                    lines[i] = "language={}\n".format(code)
                    found = True
                    break
        if not found:
            lines.append("language={}\n".format(code))
        with open(_cfg_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception as e:
        print("[O4_Lang] Cannot write language to {}: {}".format(_cfg_path, e))


# ──────────────────────────────────────────────────────────────────
#  CHARGEMENT DU DICTIONNAIRE
# ──────────────────────────────────────────────────────────────────

def _load_lang(code):
    """Charge le fichier O4_Lang_XX.py correspondant au code."""
    global _current_lang, _translations
    code = code.upper().strip()
    if code not in AVAILABLE_LANGS:
        code = "EN"
    module_name = AVAILABLE_LANGS[code]
    try:
        import importlib
        mod = importlib.import_module(module_name)
        _translations = mod.T
        _current_lang = code
    except Exception as e:
        print("[O4_Lang] Cannot load {}: {}".format(module_name, e))
        _translations = {}
        _current_lang = "EN"


# ──────────────────────────────────────────────────────────────────
#  FONCTION DE TRADUCTION
# ──────────────────────────────────────────────────────────────────

def tr(key):
    """
    Retourne la traduction de `key` dans la langue active.
    Si la cle est absente du dictionnaire, retourne `key` tel quel
    (aucun crash, l'interface reste lisible).
    """
    return _translations.get(key, key)


def current_lang():
    """Retourne le code de langue actif ('EN' ou 'FR')."""
    return _current_lang


# ──────────────────────────────────────────────────────────────────
#  DIALOGUE DE CHOIX DE LANGUE
# ──────────────────────────────────────────────────────────────────

def show_language_dialog(parent=None, on_change=None):
    """
    Affiche une fenetre modale pour choisir la langue.
    Sauvegarde le choix dans Ortho4XP.cfg (cle language=).
    - parent    : fenetre Tk parente (optionnel)
    - on_change : callable() appele apres le changement
    """
    win = tk.Toplevel(parent) if parent else tk.Tk()
    win.title(tr("language_dialog_title"))
    win.resizable(False, False)
    win.configure(bg="#1e2d1e")
    if parent:
        win.grab_set()

    # Centrage
    win.update_idletasks()
    w, h = 340, 190
    try:
        px = parent.winfo_rootx() + (parent.winfo_width()  - w) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
    except Exception:
        px, py = 300, 200
    win.geometry("{}x{}+{}+{}".format(w, h, px, py))

    tk.Label(
        win,
        text="  " + tr("language_dialog_message"),
        bg="#1e2d1e", fg="#a6e3a1",
        font=("TkFixedFont", 13, "bold"),
        pady=18,
    ).pack(fill=tk.X)

    btn_frame = tk.Frame(win, bg="#1e2d1e")
    btn_frame.pack(pady=4)

    def _choose(code):
        _load_lang(code)
        _write_lang_to_cfg(code)   # <- sauvegarde dans Ortho4XP.cfg
        win.destroy()
        # Message informatif — relancement requis
        msg_win = tk.Toplevel(parent) if parent else tk.Tk()
        msg_win.title("Ortho4XP")
        msg_win.configure(bg="#1e2d1e")
        msg_win.resizable(False, False)
        try:
            px2 = parent.winfo_rootx() + (parent.winfo_width()  - 480) // 2
            py2 = parent.winfo_rooty() + (parent.winfo_height() - 200) // 2
            msg_win.geometry("480x200+{}+{}".format(px2, py2))
        except Exception:
            msg_win.geometry("480x200")
        lbl_text = (
            "Language saved / Langue sauvegardée.\n\n"
            "Relancez Ortho4XP pour appliquer.\n"
            "Restart Ortho4XP to apply."
        )
        tk.Label(msg_win, text=lbl_text,
                 bg="#1e2d1e", fg="#a6e3a1",
                 font=("TkFixedFont", 11),
                 justify="center", pady=10).pack(expand=True)
        btn_style = ttk.Style(msg_win)
        btn_style.configure("Msg.TButton",
                            font=("TkFixedFont", 12, "bold"),
                            foreground="#000000",
                            background="#3b5b49",
                            padding=12)
        btn_txt = "  ✅  OK  — Click here to close  " if _current_lang == "EN" else "  ✅  OK  — Cliquez ici pour fermer  "
        ttk.Button(msg_win, text=btn_txt,
                   style="Msg.TButton",
                   command=msg_win.destroy).pack(pady=(0, 16), fill="x", padx=20)
        if callable(on_change):
            on_change()

    style = ttk.Style(win)
    style.configure("Lang.TButton", font=("TkFixedFont", 12), padding=8)

    ttk.Button(
        btn_frame,
        text=tr("language_btn_en"),
        style="Lang.TButton",
        command=lambda: _choose("EN"),
    ).pack(side=tk.LEFT, padx=16)

    ttk.Button(
        btn_frame,
        text=tr("language_btn_fr"),
        style="Lang.TButton",
        command=lambda: _choose("FR"),
    ).pack(side=tk.LEFT, padx=16)

    # Indicateur langue courante + nom du fichier cfg
    cfg_short = os.path.basename(_cfg_path)
    tk.Label(
        win,
        text="(current: {}  -  saved in {})".format(_current_lang, cfg_short),
        bg="#1e2d1e", fg="#c0c0c0",
        font=("TkFixedFont", 9),
    ).pack(pady=(10, 0))

    if parent:
        parent.wait_window(win)
    else:
        win.mainloop()


# ──────────────────────────────────────────────────────────────────
#  BOUTON REUTILISABLE
# ──────────────────────────────────────────────────────────────────

def make_language_button(parent, on_change=None):
    """
    Cree et retourne un bouton ttk pret a etre place dans un frame.

    Exemple :
        from O4_Lang import make_language_button
        make_language_button(frame_tools, on_change=rebuild_cb).pack(
            side=tk.LEFT, padx=8, pady=4)
    """
    return ttk.Button(
        parent,
        text="  " + tr("language_menu_change_lang"),
        command=lambda: show_language_dialog(parent, on_change=on_change),
    )


# ──────────────────────────────────────────────────────────────────
#  INITIALISATION AU DEMARRAGE
# ──────────────────────────────────────────────────────────────────

def init(parent=None, on_change=None):
    """
    A appeler UNE SEULE FOIS au demarrage (avant root.mainloop()).

    Comportement :
    - Lit la cle 'language=' dans Ortho4XP.cfg
    - Si presente -> charge silencieusement la langue sauvegardee
    - Si absente  -> affiche le dialogue de choix (1er lancement)
    """
    saved = _read_lang_from_cfg()
    if saved:
        _load_lang(saved)
    else:
        # Premier lancement : EN par defaut, puis dialogue
        _load_lang("EN")
        show_language_dialog(parent=parent, on_change=on_change)


# ──────────────────────────────────────────────────────────────────
#  AUTO-INIT silencieux (si importe sans appel a init())
# ──────────────────────────────────────────────────────────────────
_saved = _read_lang_from_cfg()
if _saved:
    _load_lang(_saved)
else:
    _load_lang("EN")


# ──────────────────────────────────────────────────────────────────
#  GUIDE D'INTEGRATION
# ──────────────────────────────────────────────────────────────────
#
#  1. DEMARRAGE (script principal ou O4_GUI_Utils.py)
#  ---------------------------------------------------
#     import O4_Lang
#     O4_Lang.init(parent=root)   # AVANT root.mainloop()
#
#
#  2. TRADUCTION D'UN TEXTE
#  -------------------------
#     from O4_Lang import tr
#     ttk.Button(frame, text=tr("Assemble Vector data"), ...)
#     tk.Label(frame,   text=tr("Latitude:"), ...)
#
#
#  3. BOUTON "CHANGER LA LANGUE" DANS L'ONGLET OUTILS
#  ----------------------------------------------------
#     from O4_Lang import make_language_button
#     make_language_button(frame_outils).pack(side=tk.LEFT, padx=8)
#
#
#  4. FORMAT DANS Ortho4XP.cfg
#  ----------------------------
#     language=FR      <- ajoute automatiquement par O4_Lang
#     (ligne unique, mise a jour a chaque changement de langue)
#     Les autres variables du cfg ne sont jamais touchees.
#
# ──────────────────────────────────────────────────────────────────
