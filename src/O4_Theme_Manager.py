# O4_Theme_Manager.py
# Gestionnaire de thème couleurs pour ORTHO4XP V3
# Rôle : permet de changer les couleurs de l'interface (fond, boutons,
#        texte, console) sans toucher aux fichiers UI existants.
# Compatible V2 : ne modifie RIEN dans les fichiers existants.
# Multiplateforme : Windows, macOS (dar), Linux.
# ------------------------------------------------------------------
# LIMITATION CONNUE (documentée dans a_integrer.txt) :
#   HoverButton, Console (bg hardcodé #1e1e1e), Earth Preview canvas
#   et certains tk.Frame/Label/Button avec bg littéral ne répondent
#   pas au thème dynamique. Ils sont gérés via patch au démarrage
#   uniquement (pas en cours d'exécution).
# ------------------------------------------------------------------

import sys
import json
import os
from pathlib import Path
from typing import Dict, Optional

# Détection OS — même logique que O4_Imagery_Utils.py
if "dar" in sys.platform:
    _OS = "mac"
elif "win" in sys.platform:
    _OS = "windows"
else:
    _OS = "linux"


# ------------------------------------------------------------------
# Thèmes prédéfinis
# ------------------------------------------------------------------
THEMES: Dict[str, Dict] = {

    "roland": {
        "name":          "Roland",
        "bg":            "#3b5b49",
        "bg_secondary":  "#2a4235",
        "fg":            "#e8f0ec",
        "fg_secondary":  "#a6e3a1",
        "btn_bg":        "#4a6b59",
        "btn_fg":        "#ffffff",
        "btn_hover":     "#5a7b69",
        "btn_active":    "#a6e3a1",
        "console_bg":    "#0f0f1a",
        "console_fg":    "#50fa7b",
        "accent":        "#a6e3a1",
        "warning":       "#e5c07b",
        "error":         "#e06c75",
        "success":       "#a6e3a1",
        "canvas_bg":     "#2a4235",
        "border":        "#4a6b59",
        "shadow":        "#2a4235",
    },

    "custom": {
        "name":          "Personnalisée",
        "bg":            "#3b5b49",
        "bg_secondary":  "#2a4235",
        "fg":            "#e8f0ec",
        "fg_secondary":  "#a6e3a1",
        "btn_bg":        "#4a6b59",
        "btn_fg":        "#ffffff",
        "btn_hover":     "#5a7b69",
        "btn_active":    "#a6e3a1",
        "console_bg":    "#0f0f1a",
        "console_fg":    "#50fa7b",
        "accent":        "#a6e3a1",
        "warning":       "#e5c07b",
        "error":         "#e06c75",
        "success":       "#a6e3a1",
        "canvas_bg":     "#2a4235",
        "border":        "#4a6b59",
        "shadow":        "#2a4235",
    },

    "ardoise": {
        "name":          "Ardoise",
        "bg":            "#2e3440",
        "bg_secondary":  "#3b4252",
        "fg":            "#eceff4",
        "fg_secondary":  "#d8dee9",
        "btn_bg":        "#4c566a",
        "btn_fg":        "#eceff4",
        "btn_hover":     "#5e81ac",
        "btn_active":    "#88c0d0",
        "console_bg":    "#2e3440",
        "console_fg":    "#a3be8c",
        "accent":        "#88c0d0",
        "warning":       "#ebcb8b",
        "error":         "#bf616a",
        "success":       "#a3be8c",
        "canvas_bg":     "#242933",
        "border":        "#4c566a",
        "shadow":        "#242933",
    },

    "sable": {
        "name":          "Sable",
        "bg":            "#4a3728",
        "bg_secondary":  "#3a2a1e",
        "fg":            "#f5e6d0",
        "fg_secondary":  "#d4b896",
        "btn_bg":        "#6b5040",
        "btn_fg":        "#f5e6d0",
        "btn_hover":     "#7d6050",
        "btn_active":    "#d4a574",
        "console_bg":    "#2a1e14",
        "console_fg":    "#d4b896",
        "accent":        "#d4a574",
        "warning":       "#e8c070",
        "error":         "#c0504a",
        "success":       "#80b060",
        "canvas_bg":     "#3a2a1e",
        "border":        "#6b5040",
        "shadow":        "#2a1e14",
    },

    "ocean": {
        "name":          "Océan",
        "bg":            "#0a2040",
        "bg_secondary":  "#0d2d58",
        "fg":            "#c8e0f8",
        "fg_secondary":  "#8ab4d8",
        "btn_bg":        "#1a4a7a",
        "btn_fg":        "#c8e0f8",
        "btn_hover":     "#2060a0",
        "btn_active":    "#40a0d0",
        "console_bg":    "#060f20",
        "console_fg":    "#40c0e0",
        "accent":        "#40a0d0",
        "warning":       "#e0c060",
        "error":         "#e05050",
        "success":       "#40c080",
        "canvas_bg":     "#060f20",
        "border":        "#1a4a7a",
        "shadow":        "#060f20",
    },
}

# Thème actif par défaut
_active_theme_name: str = "roland"
_active_theme: Dict    = THEMES["roland"]

# Fichier de sauvegarde préférences utilisateur
# Placé dans le dossier utilisateur — fonctionne sur les 3 OS
_PREFS_FILE = Path.home() / ".ortho4xp_theme.json"


# ------------------------------------------------------------------
# Chargement / sauvegarde préférences
# ------------------------------------------------------------------
def _load_prefs():
    """Charge le thème sauvegardé au dernier lancement."""
    global _active_theme_name, _active_theme
    try:
        # 1. Charger custom_theme.json si présent
        root = Path(__file__).resolve().parent.parent
        custom_file = root / "custom_theme.json"
        if custom_file.exists():
            data = json.loads(custom_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "bg" in data:
                for k, v in data.items():
                    THEMES["custom"][k] = v
                THEMES["custom"]["name"] = "Personnalisée"
    except Exception:
        pass
    try:
        # 2. Charger le nom du thème actif
        if _PREFS_FILE.exists():
            data = json.loads(_PREFS_FILE.read_text(encoding="utf-8"))
            name = data.get("theme", "roland")
            if name in THEMES:
                _active_theme_name = name
                _active_theme      = THEMES[name]
    except Exception:
        pass

def _save_prefs():
    """Sauvegarde le thème choisi pour le prochain lancement."""
    try:
        _PREFS_FILE.write_text(
            json.dumps({"theme": _active_theme_name}, indent=2),
            encoding="utf-8"
        )
    except Exception:
        pass  # lecture seule ou autre erreur → on ignore

_load_prefs()


# ------------------------------------------------------------------
# API publique
# ------------------------------------------------------------------
def get_theme() -> Dict:
    """Retourne le dictionnaire du thème actif."""
    return dict(_active_theme)


def get_color(key: str, fallback: str = "#ffffff") -> str:
    """
    Retourne une couleur du thème actif.
    key : ex. 'bg', 'btn_bg', 'accent', 'error' …
    fallback : couleur si la clé n'existe pas.
    """
    return _active_theme.get(key, fallback)


def set_theme(name: str) -> bool:
    """
    Change le thème actif.
    name : 'dark', 'light', 'blue', 'green' ou nom d'un thème custom.
    Retourne True si trouvé, False sinon.
    """
    global _active_theme_name, _active_theme
    if name not in THEMES:
        print(f"[Theme] Thème '{name}' inconnu. Disponibles : {list(THEMES.keys())}")
        return False
    _active_theme_name = name
    _active_theme      = THEMES[name]
    _save_prefs()
    print(f"[Theme] Thème activé : {_active_theme['name']} (OS: {_OS})")
    return True


def list_themes() -> Dict[str, str]:
    """Retourne un dict {id: nom_lisible} de tous les thèmes disponibles."""
    return {k: v["name"] for k, v in THEMES.items()}


def add_custom_theme(theme_id: str, theme_dict: Dict) -> bool:
    """
    Ajoute un thème personnalisé (couleurs définies par l'utilisateur).
    theme_id  : identifiant unique (ex: 'mon_theme')
    theme_dict: dictionnaire avec les mêmes clés que les thèmes existants.
    """
    required = ["bg", "fg", "btn_bg", "btn_fg", "console_bg", "console_fg"]
    for key in required:
        if key not in theme_dict:
            print(f"[Theme] Clé manquante dans le thème custom : '{key}'")
            return False
    if "name" not in theme_dict:
        theme_dict["name"] = theme_id
    THEMES[theme_id] = theme_dict
    print(f"[Theme] Thème custom '{theme_id}' ajouté.")
    return True


def apply_to_widget(widget, role: str = "bg"):
    """
    Applique une couleur du thème à un widget tkinter.
    role : 'bg', 'btn_bg', 'console_bg', etc.

    Exemple :
        apply_to_widget(mon_bouton, role='btn_bg')

    NOTE : fonctionne sur les widgets standards tk.
           HoverButton et Console hardcodés nécessitent
           un patch au démarrage (voir apply_to_root).
    """
    color = get_color(role)
    try:
        widget.configure(bg=color)
    except Exception:
        try:
            widget.configure(background=color)
        except Exception:
            pass  # widget non configurable → on ignore silencieusement


def apply_to_root(root):
    """
    Applique le thème à toute la fenêtre tkinter principale
    et à tous ses enfants de façon récursive.
    Gère les widgets standards ET tente le patch sur Console/HoverButton.

    root : la fenêtre principale tkinter (tk.Tk ou tk.Toplevel)

    Utilisation :
        import O4_Theme_Manager as THEME
        THEME.apply_to_root(ma_fenetre)
    """
    theme = get_theme()

    def _apply_recursive(widget):
        wclass = widget.winfo_class()
        try:
            if wclass in ("Frame", "LabelFrame", "Toplevel", "Canvas"):
                widget.configure(bg=theme["bg"])
            elif wclass == "Label":
                if getattr(widget, '_color_protected', False):
                    pass
                else:
                    widget.configure(bg=theme["bg"], fg=theme["fg"])
            elif wclass == "Button":
                widget.configure(
                    bg=theme["btn_bg"], fg=theme["btn_fg"],
                    activebackground=theme["btn_active"],
                    relief="flat"
                )
            elif wclass == "Entry":
                widget.configure(
                    bg=theme["bg_secondary"], fg=theme["fg"],
                    insertbackground=theme["fg"]
                )
            elif wclass == "Text":
                # Console et autres zones de texte
                widget.configure(
                    bg=theme["console_bg"], fg=theme["console_fg"],
                    insertbackground=theme["fg"]
                )
            elif wclass in ("Scrollbar",):
                widget.configure(bg=theme["bg_secondary"])
            elif wclass == "Scale":
                widget.configure(
                    bg=theme["bg"], fg=theme["fg"],
                    troughcolor=theme["bg_secondary"],
                    activebackground=theme["accent"]
                )
            elif wclass == "Checkbutton":
                widget.configure(
                    bg=theme["bg"], fg=theme["fg"],
                    activebackground=theme["bg"],
                    selectcolor=theme["bg_secondary"]
                )
            elif wclass == "OptionMenu":
                widget.configure(
                    bg=theme["btn_bg"], fg=theme["btn_fg"],
                    activebackground=theme["btn_hover"]
                )
        except Exception:
            pass  # widget non configurable → on ignore

        # Récursion sur les enfants
        try:
            for child in widget.winfo_children():
                _apply_recursive(child)
        except Exception:
            pass

    _apply_recursive(root)
    print(f"[Theme] Thème '{_active_theme['name']}' appliqué à la fenêtre ({_OS}).")


def set_custom_color(key: str, value: str) -> bool:
    """
    Modifie une couleur du thème Custom et l'active.
    key   : ex. 'bg', 'btn_bg', 'accent' …
    value : code hex ex. '#3b5b49'
    Retourne True si OK.

    Exemple :
        set_custom_color('bg', '#1a2030')
        set_custom_color('btn_bg', '#2a3a5a')
        set_theme('custom')
    """
    global _active_theme_name, _active_theme
    required = ['#', ]
    if not value.startswith('#') or len(value) not in (4, 7):
        print(f"[Theme] Couleur invalide : '{value}' (format attendu : #rrggbb)")
        return False
    THEMES["custom"][key] = value
    if _active_theme_name == "custom":
        _active_theme = THEMES["custom"]
    _save_prefs()
    return True


def get_custom_theme() -> Dict:
    """Retourne le dictionnaire du thème Custom (modifiable par l'utilisateur)."""
    return dict(THEMES["custom"])


def reset_custom_to_roland():
    """Remet le thème Custom aux couleurs Roland (point de départ conseillé)."""
    for k, v in THEMES["roland"].items():
        THEMES["custom"][k] = v
    THEMES["custom"]["name"] = "Personnalisée"
    _save_prefs()
    print("[Theme] Thème Custom réinitialisé aux couleurs Roland.")


def save_custom_theme_to_file() -> bool:
    """
    Sauvegarde le thème Personnalisée dans custom_theme.json
    à la racine du dossier Ortho4XP (venv/bulle autonome).
    Retourne True si OK, False si erreur.
    """
    try:
        root = Path(__file__).resolve().parent.parent
        dest = root / "custom_theme.json"
        root.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            json.dumps(dict(THEMES["custom"]), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        print(f"[Theme] Thème Personnalisée sauvegardé → {dest}")
        return True
    except Exception as e:
        print(f"[Theme] Erreur sauvegarde custom_theme.json : {e}")
        return False


def get_os() -> str:
    """Retourne l'OS détecté : 'windows', 'mac' ou 'linux'."""
    return _OS


def current_theme_name() -> str:
    """Retourne le nom du thème actif."""
    return _active_theme_name
