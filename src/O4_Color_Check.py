#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
O4_Color_Check.py - Version ORTHO4XP V2.0 (Avril 2026) - REFONTE v2.9
Corrections v2.9 (Roland/Ypsos, Avril 2026) :
  • FusionPreviewWindow — déplacement fluide :
    pendant le drag → rendu rapide (NEAREST, sans overlay orange, délai 8ms)
    à l'arrêt de la souris → rendu complet (BILINEAR + overlay orange, délai 25ms)
  • BatchPreviewWindow — résumé des corrections actives affiché sous le titre
  • BatchPreviewWindow — points jaunes parasites supprimés (nettoyage morphologique)
  • BatchPreviewWindow — trait séparateur orig/corrigé réduit à 1px centré
Corrections v2.8 (Roland/Ypsos, Avril 2026) :
  • BatchPreviewWindow : self.textures_dir manquant ajouté → crash masque mer corrigé
  • _apply_group_correction : rescan après sauvegarde → indicateur ✏ mis à jour en temps réel
  • Double-clic groupe ZL dans liste gauche → ouvre Batch Preview directement
  • _filter_left : recherche connectée aux labels de zones .comb (pas seulement le nom DDS)
  • analyze_dds renforcé : dérive vs cube de référence calibré (R=86.5 G=96.5 B=86.9)
    → pixels eau/nuage exclus de la moyenne, drift_r/g/b/max calculés et affichés
  • Liste gauche : colonne Δ (dérive vs référence) affichée si > 5 pts
Corrections v2.7 (Roland/Ypsos, Avril 2026) :
  • DPI Aware réel : détection winfo_fpixels("1i") au lieu de s=1.3 fixe
    → adaptatif Windows/macOS/Linux, plafond ×2.0 pour écrans 4K
    → fallback s=1.3 si détection impossible
  • FusionPreviewWindow — points jaunes parasites supprimés :
    nettoyage morphologique du masque seam (composantes < 1% de la principale
    supprimées) → seule la vraie ligne de jointure reste visible
  • FusionPreviewWindow — vue initiale = tuile ENTIÈRE dans le canvas :
    zoom calculé automatiquement pour fit-to-canvas au premier rendu
    (plus de tuile coupée au démarrage)
  • Commentaire dupliqué "Sélection dans les listes" supprimé (lignes 1110-1112)
  • Fonctions get_zl_factor() et find_by_dds_id() dupliquées supprimées
    (seconde définition redondante en fin de fichier)
Nouveautés v2.6 :
  - Rayon de dégradé par défaut porté à 96px (était 24px) : jointures invisibles
  - Facteurs ZL bas (ZL13-16) renforcés : transitions très larges vue globale
  - Réduction ombres locales (shadow_reduce) activée ZL13-16 : vagues/bandes éliminées
  - Correction strength ZL13-16 renforcée : uniformité globale accrue
Nouveautés v2.5 :
  - Dégradé de jointure (seams) amélioré :
    * Affichage du rayon effectif par ZL dans la section dégradé (table ZL13→ZL20)
    * Conseils intégrés : seam persistante → augmenter rayon ou générer .comb seam
    * Nouveau bouton "Générer .comb seam" : détecte automatiquement la jointure
      dans le DDS sélectionné et génère un masque de protection (.comb) sur la zone
    * FusionPreviewWindow : affichage ΔE colorimétrique entre les deux sources
      + conseils adaptatifs (faible/modéré/fort/critique) + table rayons ZL
    * Rayon adaptatif automatique selon ΔE : si l'écart est fort, le rayon est
      majoré localement au Build (×1.3 à ×2.0 selon ΔE, plafonné ZL18+)
Nouveautés v2.4 :
  - Listes gauche/droite entièrement refondues : organisées par couche ZL / extend
  - Chaque entrée affiche : numéro JPG, couche ZL, couleur dominante, valeur, masques .comb
  - Champ de recherche par numéro JPG ou DDS dans chaque liste
  - Fenêtre "Couleur Cible" affiche les extends et JPG regroupés sans dominante
  - Génération de fichiers .comb par Color Check (numéro JPG, couche, corrections)
  - Mode batch preview : évalue l'impact des corrections sur une couche entière avant application
  - Suppression définitive de la détection des dominantes > 8 pts et liste "DDS à dominante colorée"
Corrections v2.3 :
  - Section ① "Identifier dominantes" : scan + correction colorimétrique
  - Section ② "Dégradé de jointure sources" : OFF / 24 / 48 / 64 / 128 px
Corrections v2.2 :
  - Sélection conservée visuellement (exportselection=0)
Corrections v2.1 :
  - Curseurs Saturation R/G/B corrigés
  - Build relance : supprime DDS du groupe sélectionné
  - Taille minimale de fenêtre bloquée (minsize)
"""

import os
import json
import threading
import tkinter as tk
from tkinter import RIDGE, LEFT, RIGHT, HORIZONTAL, END, messagebox
import tkinter.ttk as ttk
import numpy as np
from PIL import Image, ImageTk, ImageEnhance, ImageFilter

CORRECTIONS_FILE = "color_corrections.ccorr"
COMB_EXT         = ".comb"   # extension des fichiers générés par Color Check

# Dossier archive global : Color_check/ à la racine d'Ortho4XP
import pathlib as _pl
COLOR_CHECK_ARCHIVE_DIR = str(
    _pl.Path(__file__).resolve().parent.parent / "Color_check"
)

# ─────────────────────────────────────────────────────────────────
# Utilitaires fichiers
# ─────────────────────────────────────────────────────────────────

def load_corrections(textures_dir):
    path = os.path.join(textures_dir, CORRECTIONS_FILE)
    if os.path.isfile(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_corrections(textures_dir, corrections):
    path = os.path.join(textures_dir, CORRECTIONS_FILE)
    try:
        with open(path, "w") as f:
            json.dump(corrections, f, indent=2)
    except Exception:
        pass


def save_comb(textures_dir, jpg_name, zl, corrections, protect_zones=None):
    """
    Génère un fichier .comb associé à un JPG (ex: 15_22305_14729.comb).
    Contient : numéro JPG, couche ZL, corrections appliquées,
               zones de protection géométriques (rectangles — pistes, marquages).
    protect_zones : liste de dicts {"x", "y", "w", "h", "label"} en pixels relatifs (0-4096).
    """
    base      = os.path.splitext(jpg_name)[0]
    comb_path = os.path.join(textures_dir, base + COMB_EXT)
    data = {
        "jpg":           jpg_name,
        "zl":            zl,
        "corrections":   corrections,
        "protect_zones": protect_zones or [],
    }
    try:
        with open(comb_path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def load_comb_for_jpg(textures_dir, jpg_name):
    """Charge le .comb d'un JPG s'il existe, sinon None."""
    base = os.path.splitext(jpg_name)[0]
    path = os.path.join(textures_dir, base + COMB_EXT)
    if os.path.isfile(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return None


# ─────────────────────────────────────────────────────────────────
# Analyse DDS — par couche ZL / extend (sans détection dominante)
# ─────────────────────────────────────────────────────────────────

def _extract_zl_from_name(name):
    """Extrait le ZL depuis le nom DDS/JPG. Ex: '15_22305_14729.dds' → 15"""
    parts = os.path.basename(name).replace(".dds","").replace(".DDS","").replace(".jpg","").split("_")
    if parts:
        try:
            zl = int(parts[0])
            if 13 <= zl <= 20:
                return zl
        except ValueError:
            pass
    return None


def _extract_extend_from_name(name):
    """Extrait l'extend depuis le nom. Format attendu: ZL_X_Y → 'ZL_X'"""
    parts = os.path.basename(name).replace(".dds","").replace(".DDS","").replace(".jpg","").split("_")
    if len(parts) >= 2:
        return f"{parts[0]}_{parts[1]}"
    return "inconnu"


def analyze_dds(dds_path):
    """
    Analyse un DDS : couleur moyenne R/G/B, ZL, extend, infos .comb.
    Dominante : détection simple + dérive vs cube de référence calibré
    (R=86.5 G=96.5 B=86.9 — 48 753 JPG Europe).
    Pas de seuil filtrant — toutes les tuiles sont listées.
    """
    textures_dir = os.path.dirname(dds_path)
    fname = os.path.basename(dds_path)
    zl     = _extract_zl_from_name(fname)
    extend = _extract_extend_from_name(fname)

    # Cherche un .comb associé (même base que le DDS)
    base     = os.path.splitext(fname)[0]
    comb_path = os.path.join(textures_dir, base + COMB_EXT)
    has_comb  = os.path.isfile(comb_path)
    comb_info = None
    if has_comb:
        try:
            with open(comb_path) as f:
                comb_info = json.load(f)
        except Exception:
            pass

    # Cube de référence calibré 48 753 JPG Europe
    _REF_R, _REF_G, _REF_B = 86.5, 96.5, 86.9

    try:
        img  = Image.open(dds_path).convert("RGB")
        arr  = np.array(img.resize((64, 64), Image.BOX), dtype=np.float32)
        # Exclure les pixels très sombres (< 10) et très clairs (> 248) — eau/nuage
        lum  = 0.299 * arr[:,:,0] + 0.587 * arr[:,:,1] + 0.114 * arr[:,:,2]
        mask = (lum > 10) & (lum < 248)
        if mask.sum() > 10:
            valid = arr[mask]
            mr = float(valid[:, 0].mean())
            mg = float(valid[:, 1].mean())
            mb = float(valid[:, 2].mean())
        else:
            mr = float(np.mean(arr[:, :, 0]))
            mg = float(np.mean(arr[:, :, 1]))
            mb = float(np.mean(arr[:, :, 2]))

        # Dominante simple (écart inter-canaux)
        dr   = mr - (mg + mb) / 2
        dg   = mg - (mr + mb) / 2
        db   = mb - (mr + mg) / 2
        delta    = max(dr, dg, db)
        if   delta == dr and delta > 3: dominant = "R"
        elif delta == dg and delta > 3: dominant = "G"
        elif delta == db and delta > 3: dominant = "B"
        else:                           dominant = None

        # Dérive vs cube de référence calibré (pour affichage niveau de dérive)
        drift_r = mr - _REF_R
        drift_g = mg - _REF_G
        drift_b = mb - _REF_B
        drift_max = max(abs(drift_r), abs(drift_g), abs(drift_b))

        return {
            "path": dds_path, "name": fname,
            "mean_r": mr, "mean_g": mg, "mean_b": mb,
            "dominant": dominant, "delta": delta,
            "drift_r": round(drift_r, 1),
            "drift_g": round(drift_g, 1),
            "drift_b": round(drift_b, 1),
            "drift_max": round(drift_max, 1),
            "zl": zl, "extend": extend,
            "has_comb": has_comb, "comb_info": comb_info,
        }
    except Exception as e:
        return {
            "path": dds_path, "name": fname,
            "dominant": None, "delta": 0,
            "zl": zl, "extend": extend,
            "has_comb": has_comb, "comb_info": comb_info,
            "error": str(e),
        }


def load_dds_preview(dds_path, max_size=512):
    try:
        img = Image.open(dds_path).convert("RGB")
        if max(img.width, img.height) > max_size:
            img = img.resize((max_size, max_size), Image.BOX)
        return img
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────
# Application des corrections sur un tableau numpy float32
# (utilisé à la fois pour la preview et pour le build)
# ─────────────────────────────────────────────────────────────────

def apply_corrections_to_array(arr, corr, sea_mask=None):
    """
    Applique un dictionnaire de corrections à un tableau numpy HxWx3 float32.
    Retourne un tableau HxWx3 uint8.

    sea_mask : tableau float32 (H,W) optionnel — 0.0=mer, 1.0=terre.
    Si fourni, la correction est proportionnelle : mer=original, terre=corrigé.
    Chargé depuis le PNG Ortho4XP via CNORM._load_sea_mask() par l'appelant.
    """
    arr_orig = arr.copy()
    arr = arr.copy()

    # Corrections canal par canal : décalage / luminosité / contraste
    for ch, key_corr, key_lum, key_cont in [
        (0, "dr",    "lum_r", "cont_r"),
        (1, "dg",    "lum_g", "cont_g"),
        (2, "db",    "lum_b", "cont_b"),
    ]:
        c     = arr[:, :, ch].copy()
        delta = corr.get(key_corr, 0)
        lum   = corr.get(key_lum,  0)
        cont  = corr.get(key_cont, 0)
        if delta: c = np.clip(c + delta, 0, 255)
        if lum:   c = np.clip(c * (1.0 + lum  / 100.0), 0, 255)
        if cont:  c = np.clip((c - 128.0) * (1.0 + cont / 100.0) + 128.0, 0, 255)
        arr[:, :, ch] = c

    # Saturation par canal
    sr = corr.get("sat_r", 0) / 100.0
    sg = corr.get("sat_g", 0) / 100.0
    sb = corr.get("sat_b", 0) / 100.0
    if sr != 0.0 or sg != 0.0 or sb != 0.0:
        r_orig = arr[:, :, 0].copy()
        g_orig = arr[:, :, 1].copy()
        b_orig = arr[:, :, 2].copy()
        gray = (r_orig + g_orig + b_orig) / 3.0
        if sr != 0.0:
            arr[:, :, 0] = np.clip(gray + (r_orig - gray) * (1.0 + sr), 0, 255)
        if sg != 0.0:
            arr[:, :, 1] = np.clip(gray + (g_orig - gray) * (1.0 + sg), 0, 255)
        if sb != 0.0:
            arr[:, :, 2] = np.clip(gray + (b_orig - gray) * (1.0 + sb), 0, 255)

    result = np.clip(arr, 0, 255)

    # ── Protection eau via masque PNG Ortho4XP ─────────────────────────────
    # mer (0.0) = original conservé, terre (1.0) = corrigé, côte = proportionnel
    if sea_mask is not None:
        h, w = result.shape[:2]
        sm = sea_mask
        if sm.shape != (h, w):
            from PIL import Image as _PIL
            sm = np.array(
                _PIL.fromarray((sm * 255).astype(np.uint8), mode="L").resize(
                    (w, h), _PIL.BOX), dtype=np.float32) / 255.0
        for ch in range(3):
            result[:,:,ch] = sm * result[:,:,ch] + (1.0 - sm) * arr_orig[:,:,ch]
    # ───────────────────────────────────────────────────────────────────────

    return np.clip(result, 0, 255).astype(np.uint8)


# ─────────────────────────────────────────────────────────────────
# Fenêtre principale Color Check
# ─────────────────────────────────────────────────────────────────

class ColorCheckWindow(tk.Toplevel):

    def __init__(self, parent, textures_dir, tile_info=None):
        super().__init__(parent)
        self.title("Color Check")
        self.configure(bg="#3b5b49")
        self.resizable(True, True)

        # ── DPI Aware réel — adaptatif venv multi-OS (Windows/macOS/Linux) ──
        # Détecte le scaling système réel plutôt qu'un facteur fixe 1.3.
        # Plafond 2.0 pour les écrans 4K (évite les fenêtres hors écran).
        try:
            _dpi = self.winfo_fpixels("1i")  # pixels par pouce réels sur l'écran courant
            if _dpi < 72:
                _dpi = 96.0  # valeur aberrante → fallback 96 dpi
            s = max(1.0, min(_dpi / 96.0, 2.0))  # 96 dpi=1.0, 120=1.25, 192=2.0 (4K)
        except Exception:
            s = 1.3  # fallback si détection impossible
        self._s  = s
        self._fs = lambda x: int(x * s)
        self._thumb = int(255 * s)

        self.textures_dir = self._resolve_textures_dir(textures_dir)
        self.tile_info    = tile_info

        # Données refondues : organisées par ZL/extend
        self.layer_groups      = {}   # {zl: [info, ...]}
        self.extend_groups     = {}   # {extend: [info, ...]}
        self.all_dds_list      = []   # liste plate de tous les DDS analysés
        self.selected_group    = None
        self.selected_dds_info = None
        self.target_idx        = None

        self.preview_orig   = None
        self.preview_target = None

        self.var_r     = tk.IntVar(value=0)
        self.var_g     = tk.IntVar(value=0)
        self.var_b     = tk.IntVar(value=0)
        self.var_lr    = tk.IntVar(value=0)
        self.var_lg    = tk.IntVar(value=0)
        self.var_lb    = tk.IntVar(value=0)
        self.var_cr    = tk.IntVar(value=0)
        self.var_cg    = tk.IntVar(value=0)
        self.var_cb    = tk.IntVar(value=0)
        self.var_sr    = tk.IntVar(value=0)
        self.var_sg    = tk.IntVar(value=0)
        self.var_sb    = tk.IntVar(value=0)
        self.var_sharp = tk.IntVar(value=0)

        self._photo_source = None
        self._photo_corr   = None
        self._photo_target = None

        # Données internes pour les listes refondues
        self._left_items  = []   # [(display_str, info_or_None, is_header), ...]
        self._right_items = []   # [(display_str, info_or_None, is_header), ...]

        self._disable_cnorm()
        self._build_ui()

        self.update_idletasks()
        min_w = self.winfo_reqwidth()
        min_h = self.winfo_reqheight()
        self.minsize(min_w, min_h)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(200, self._scan)


    # ─────────────────────────────────────────────────────────────
    # Résolution dossier textures
    # ─────────────────────────────────────────────────────────────

    def _resolve_textures_dir(self, textures_dir):
        if os.path.isdir(textures_dir):
            return textures_dir
        alt = os.path.join(os.getcwd(), textures_dir)
        if os.path.isdir(alt):
            return alt
        parent = os.path.dirname(textures_dir)
        if os.path.isdir(parent):
            candidate = os.path.join(parent, "textures")
            if os.path.isdir(candidate):
                return candidate
        return textures_dir

    # ─────────────────────────────────────────────────────────────
    # Color Normalize
    # ─────────────────────────────────────────────────────────────

    def _disable_cnorm(self):
        try:
            self.master.cnorm_checkbox.config(state="disabled")
            import O4_Color_Normalize as CNORM
            CNORM.color_normalization_enabled = False
        except Exception:
            pass

    def _enable_cnorm(self):
        try:
            self.master.cnorm_checkbox.config(state="normal")
            if getattr(self.master, "cnorm_enabled", None) and self.master.cnorm_enabled.get():
                import O4_Color_Normalize as CNORM
                CNORM.color_normalization_enabled = True
        except Exception:
            pass

    def _open_fusion_preview(self):
        """
        Ouvre une fenêtre de preview du feathering sur le DDS sélectionné.
        Simule les 5 valeurs de rayon côte à côte pour choisir avant Build.
        Fonctionne sur le DDS actif : détecte toutes les jointures internes
        (même celles entre plusieurs sources dans un seul PNG/DDS).
        """
        if not self.selected_dds_info:
            # Si aucun DDS sélectionné, prendre le premier disponible
            if self.all_dds_list:
                info = self.all_dds_list[0]
            else:
                self.status.config(text="⚠ Aucun DDS disponible pour le preview.")
                return
        else:
            info = self.selected_dds_info

        dds_path = info["path"]
        if not os.path.isfile(dds_path):
            self.status.config(text=f"⚠ Fichier introuvable : {dds_path}")
            return

        self.status.config(text=f"Ouverture preview fusion sur {info['name']}…")
        FusionPreviewWindow(self, dds_path)

    def _set_feathering(self, radius):
        """Mémorise le rayon de fusion dans Color Normalize pour le prochain Build."""
        try:
            import O4_Color_Normalize as CNORM
            CNORM.set_feathering_mask_radius(radius)
        except Exception:
            pass
        if radius == 0:
            self.lbl_feather.config(text="Dégradé : OFF", fg="#aaaaaa")
            self.status.config(text="Dégradé de jointure : désactivé (jointure nette)")
        else:
            self.lbl_feather.config(
                text=f"Dégradé : {radius} px — prochain Build",
                fg="#ffdd88")
            self.status.config(
                text=f"Dégradé damier : {radius} px — s'applique à tous les DDS au prochain Build")
        self._update_zl_radii_display()

    def _update_zl_radii_display(self):
        """
        Met à jour l'affichage des rayons effectifs par ZL dans la section dégradé.
        Affiche uniquement les ZL présents dans la tuile courante si connus,
        sinon affiche la table ZL13→ZL20.
        Conseille les rayons critiques pour les seams persistantes.
        """
        try:
            import O4_Color_Normalize as CNORM
            base = CNORM.feathering_mask_radius
            if base == 0:
                self._lbl_zl_radii.config(text="  Rayons effectifs : dégradé OFF")
                return
            lines = [f"  Rayons effectifs (base {base}px) :"]
            for zl in (13, 14, 15, 16, 17, 18, 19, 20):
                r = CNORM.get_effective_feather_radius(zl)
                note = ""
                if zl <= 16 and r < 24:
                    note = " ⚠ trop faible"
                elif zl >= 18 and r > 40:
                    note = " ⚠ risque détails"
                lines.append(f"    ZL{zl} → {r} px{note}")
            self._lbl_zl_radii.config(text="\n".join(lines))
        except Exception:
            self._lbl_zl_radii.config(text="")

    def _generate_seam_comb(self):
        """
        Génère un fichier .comb de protection sur la zone de jointure (seam)
        du DDS sélectionné, pour éviter que la correction colorimétrique
        n'altère la zone précisément où deux sources se rejoignent.

        Fonctionnement :
          1. Détecte automatiquement la jointure dans le DDS sélectionné
          2. Calcule un rectangle de protection autour de la seam (largeur = rayon courant)
          3. Sauvegarde le .comb avec ce rectangle + corrections curseurs actuels
          4. La seam protégée ne recevra PAS de correction Color Normalize
             → Color Check peut alors appliquer manuellement la bonne correction
        """
        if not self.selected_dds_info:
            if self.all_dds_list:
                info = self.all_dds_list[0]
            else:
                self.status.config(text="⚠ Aucun DDS sélectionné pour générer le .comb seam.")
                return
        else:
            info = self.selected_dds_info

        dds_path = info["path"]
        if not os.path.isfile(dds_path):
            self.status.config(text=f"⚠ Fichier introuvable : {dds_path}")
            return

        try:
            import O4_Color_Normalize as CNORM
            base_radius = CNORM.feathering_mask_radius
        except Exception:
            base_radius = 48

        protection_half = max(12, base_radius)

        self.status.config(text=f"Analyse jointure pour {info['name']}…")

        def _do_seam_comb():
            try:
                src = Image.open(dds_path).convert("RGB")
                arr = np.array(src, dtype=np.float32)
                H, W = arr.shape[:2]

                seams = _detect_seams(arr)
                n = int(seams.sum())

                if n < 3:
                    self.after(0, lambda: self.status.config(
                        text=f"⚠ Aucune jointure détectée dans {info['name']}"))
                    return

                ys, xs = np.where(seams)
                seam_cx = float(xs.mean())
                seam_cy = float(ys.mean())
                span_x = float(xs.max() - xs.min())
                span_y = float(ys.max() - ys.min())
                is_horiz = span_y < span_x

                # Rectangle de protection autour de la seam
                if is_horiz:
                    # Jointure horizontale → rectangle sur toute la largeur
                    y0p = max(0, int(seam_cy) - protection_half)
                    y1p = min(H, int(seam_cy) + protection_half)
                    protect_zones = [{"x": 0, "y": y0p, "w": W, "h": y1p - y0p,
                                      "label": "seam_horizontal"}]
                else:
                    # Jointure verticale → rectangle sur toute la hauteur
                    x0p = max(0, int(seam_cx) - protection_half)
                    x1p = min(W, int(seam_cx) + protection_half)
                    protect_zones = [{"x": x0p, "y": 0, "w": x1p - x0p, "h": H,
                                      "label": "seam_vertical"}]

                # Calcul ΔE entre les deux côtés de la jointure
                try:
                    _arr_a = arr[:, :int(seam_cx)] if not is_horiz else arr[:int(seam_cy), :]
                    _arr_b = arr[:, int(seam_cx):] if not is_horiz else arr[int(seam_cy):, :]
                    _img_a = Image.fromarray(_arr_a.clip(0, 255).astype(np.uint8))
                    _img_b = Image.fromarray(_arr_b.clip(0, 255).astype(np.uint8))
                    import O4_Color_Normalize as CNORM
                    de = CNORM.get_seam_color_diff(_img_a, _img_b)
                except Exception:
                    de = 0.0

                entry = {
                    "dr":     self.var_r.get(),   "dg":     self.var_g.get(),   "db":     self.var_b.get(),
                    "lum_r":  self.var_lr.get(),  "lum_g":  self.var_lg.get(),  "lum_b":  self.var_lb.get(),
                    "cont_r": self.var_cr.get(),  "cont_g": self.var_cg.get(),  "cont_b": self.var_cb.get(),
                    "sat_r":  self.var_sr.get(),  "sat_g":  self.var_sg.get(),  "sat_b":  self.var_sb.get(),
                    "sharp":  self.var_sharp.get(),
                    "seam_delta_e": round(de, 1),
                    "seam_protection_px": protection_half,
                }

                zl = info.get("zl", 0)
                jpg_name = os.path.splitext(info["name"])[0] + ".jpg"
                save_comb(self.textures_dir, jpg_name, zl, entry, protect_zones)

                orient = "horizontale" if is_horiz else "verticale"
                self.after(0, lambda: self.status.config(
                    text=f"✅ .comb seam généré : {jpg_name.replace('.jpg','.comb')} "
                         f"— jointure {orient} ±{protection_half}px — ΔE={de:.0f}"))
                self.after(0, self._scan)
            except Exception as e:
                self.after(0, lambda: self.status.config(text=f"⚠ Erreur génération .comb seam : {e}"))

        threading.Thread(target=_do_seam_comb, daemon=True).start()

    def _launch_build_with_fusion(self):
        """
        Lance le Build complet de la tuile avec le masque de fusion actif.
        S'applique à TOUS les DDS (pas seulement les dominantes).
        Si OFF : Build sans dégradé (0px) — ne cumule PAS avec le 24px interne.
        Après le Build, remet feathering à 24px (défaut Build).
        """
        try:
            import O4_Color_Normalize as CNORM
            radius = CNORM.feathering_mask_radius
        except Exception:
            radius = 0

        if radius == 0:
            if not messagebox.askyesno(
                "Dégradé sur OFF",
                "Le dégradé est sur OFF.\n"
                "Le Build utilisera 0 px (jointure nette).\n\n"
                "Continuer quand même ?"
            ):
                return

        # Supprime TOUS les DDS de la tuile pour forcer la régénération
        textures_dir = self.textures_dir
        deleted = []
        try:
            for f in os.listdir(textures_dir):
                if f.lower().endswith(".dds"):
                    try:
                        os.remove(os.path.join(textures_dir, f))
                        deleted.append(f)
                    except Exception:
                        pass
        except Exception as e:
            self.status.config(text=f"⚠ Erreur nettoyage DDS : {e}")
            return

        msg_radius = f"{radius} px" if radius > 0 else "OFF"
        self.status.config(
            text=f"🔨 Build dégradé ({msg_radius}) — {len(deleted)} DDS supprimés, régénération…")

        try:
            self.master.build_tile()
        except Exception as e:
            self.status.config(text=f"⚠ Erreur Build fusion : {e}")
            return

        self.status.config(
            text=f"✅ Build dégradé lancé — dégradé {msg_radius} — {len(deleted)} DDS régénérés")
        # Remet le dégradé à 24 px (défaut Build) après lancement
        try:
            import O4_Color_Normalize as CNORM
            CNORM.set_feathering_mask_radius(24)
        except Exception:
            pass
        self._scan()

    def _on_close(self):
        try:
            self.master.cnorm_enabled.set(1)
            self.master.cnorm_checkbox.config(state="normal")
            import O4_Color_Normalize as CNORM
            CNORM.color_normalization_enabled = True
            # Remet le dégradé à 24 px (défaut Build) à la fermeture
            CNORM.set_feathering_mask_radius(24)
        except Exception:
            pass
        self.destroy()

    # ─────────────────────────────────────────────────────────────
    # Construction de l'interface
    # ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        s  = self._s
        fs = self._fs
        T  = self._thumb
        sl = int(210 * s)

        tk.Label(self, text="Corrections R.G.B., Netteté, saturation, Zone de fusion",
                 bg="#3b5b49", fg="light green",
                 font=("TkFixedFont", fs(13), "bold")).pack(fill=tk.X, padx=10, pady=(8, 2))

        self.lbl_path = tk.Label(self, text=f"📁 {self.textures_dir}",
                                 bg="#3b5b49", fg="#aaffaa",
                                 font=("TkFixedFont", fs(11)), anchor="w")
        self.lbl_path.pack(fill=tk.X, padx=10, pady=(0, 4))

        mid = tk.Frame(self, bg="#3b5b49")
        mid.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # ── GAUCHE : liste par couche ZL / extend ──────────────────────
        left = tk.Frame(mid, bg="#3b5b49", relief=RIDGE, bd=2)
        left.pack(side=LEFT, fill=tk.Y, padx=(0, 8))

        tk.Label(left, text="Couches ZL / Tuiles (toutes)", bg="#3b5b49", fg="light green",
                 font=("TkFixedFont", fs(10), "bold")).pack(pady=(6, 2))

        # Champ de recherche gauche
        sf_l = tk.Frame(left, bg="#3b5b49")
        sf_l.pack(fill=tk.X, padx=4, pady=(2, 2))
        tk.Label(sf_l, text="🔍", bg="#3b5b49", fg="white",
                 font=("TkFixedFont", fs(10))).pack(side=LEFT)
        self._search_left_var = tk.StringVar()
        self._search_left_var.trace_add("write", lambda *a: self._filter_left())
        tk.Entry(sf_l, textvariable=self._search_left_var, bg="#1a3a20", fg="white",
                 font=("TkFixedFont", fs(9)), insertbackground="white", width=18).pack(side=LEFT, padx=2)

        lb_wrap = tk.Frame(left, bg="#3b5b49")
        lb_wrap.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)
        sb1 = tk.Scrollbar(lb_wrap, orient=tk.VERTICAL)
        self.listbox_layers = tk.Listbox(
            lb_wrap, bg="black", fg="yellow",
            font=("TkFixedFont", fs(9)), width=34, height=13,
            selectbackground="#004400", yscrollcommand=sb1.set,
            exportselection=0)
        sb1.config(command=self.listbox_layers.yview)
        self.listbox_layers.pack(side=LEFT, fill=tk.BOTH, expand=True)
        sb1.pack(side=RIGHT, fill=tk.Y)
        self.listbox_layers.bind("<<ListboxSelect>>", self._on_select_layer)
        self.listbox_layers.bind("<Double-Button-1>",  self._on_dbl_click_layer)

        # Boutons section gauche
        tk.Label(left, text="① Couches / Corrections",
                 bg="#3b5b49", fg="light green",
                 font=("TkFixedFont", fs(9), "bold")).pack(pady=(6, 1))

        for text, cmd in [
            ("🔍 Scanner couches",        self._scan),
            ("📋 Exporter liste",          self._export_list),
            ("🎨 Appliquer au groupe",     self._apply_group_correction),
            ("💾 Générer .comb",           self._save_comb_for_group),
            ("👁 Batch Preview couche",    self._batch_preview),
            ("🗑 Supprimer DDS sélect.",   self._delete_one),
            ("🗑 Supprimer TOUS DDS ZL",   self._delete_all),
        ]:
            ttk.Button(left, text=text, command=cmd).pack(fill=tk.X, padx=6, pady=2)

        self.btn_build = ttk.Button(left, text="🔨 Lancer Build (groupe)",
                                    command=self._launch_build, state="disabled")
        self.btn_build.pack(fill=tk.X, padx=6, pady=2)

        # Archive .ccorr
        tk.Frame(left, bg="#555555", height=1).pack(fill=tk.X, padx=6, pady=(10, 2))
        tk.Label(left, text="Archive corrections (Color_check/)",
                 bg="#3b5b49", fg="#aaaaaa",
                 font=("TkFixedFont", fs(8))).pack()
        _bf = tk.Frame(left, bg="#3b5b49")
        _bf.pack(fill=tk.X, padx=6, pady=(2, 4))
        ttk.Button(_bf, text="💾 Archiver",
                   command=self._archive_corrections).pack(
                   side=LEFT, fill=tk.X, expand=True, padx=(0, 2))
        ttk.Button(_bf, text="📂 Restaurer",
                   command=self._restore_corrections).pack(
                   side=LEFT, fill=tk.X, expand=True, padx=(2, 0))

        # Section dégradé
        tk.Frame(left, bg="#555555", height=2).pack(fill=tk.X, padx=6, pady=(6, 4))
        tk.Label(left, text="② Dégradé de jointure sources",
                 bg="#3b5b49", fg="#ffdd88",
                 font=("TkFixedFont", fs(9), "bold")).pack(pady=(0, 2))
        tk.Label(left, text="(damier progressif — toute la tuile)",
                 bg="#3b5b49", fg="#888888",
                 font=("TkFixedFont", fs(7))).pack()

        self._feather_var = tk.StringVar(value="0")

        self.lbl_feather = tk.Label(left, text="Dégradé : OFF",
                                    bg="#3b5b49", fg="#aaaaaa",
                                    font=("TkFixedFont", fs(8)))
        self.lbl_feather.pack(pady=(3, 2))
        self.after(100, lambda: self._set_feathering(48))

        # Affichage des rayons effectifs par ZL (mis à jour quand le rayon change)
        self._lbl_zl_radii = tk.Label(
            left, text="", bg="#3b5b49", fg="#888888",
            font=("TkFixedFont", fs(7)), justify="left", anchor="w")
        self._lbl_zl_radii.pack(fill=tk.X, padx=8, pady=(0, 4))
        self.after(200, self._update_zl_radii_display)

        # Conseils seam persistante
        tk.Label(left, text="💡 Seam persistante : augmentez le rayon\n"
                             "   ou générez un masque .comb sur la zone.",
                 bg="#3b5b49", fg="#aaaaaa",
                 font=("TkFixedFont", fs(7)), justify="left").pack(
                 fill=tk.X, padx=8, pady=(0, 4))

        ttk.Button(
            left, text="👁 Preview dégradé (avant Build)",
            command=self._open_fusion_preview,
        ).pack(fill=tk.X, padx=6, pady=(0, 2))

        ttk.Button(
            left, text="🛡 Générer .comb seam (zone protégée)",
            command=self._generate_seam_comb,
        ).pack(fill=tk.X, padx=6, pady=(0, 8))

        # ── CENTRE : prévisualisations + curseurs ──────────────────
        center = tk.Frame(mid, bg="#3b5b49")
        center.pack(side=LEFT, fill=tk.BOTH, expand=True, padx=8)

        hdr = tk.Frame(center, bg="#3b5b49")
        hdr.pack(fill=tk.X, pady=(0, 2))
        hdr.columnconfigure(0, weight=1)
        hdr.columnconfigure(1, weight=1)
        hdr.columnconfigure(2, weight=1)
        for col, txt in enumerate(["Image Source", "Correction", "Couleur Cible"]):
            tk.Label(hdr, text=txt, bg="#3b5b49", fg="white",
                     font=("TkFixedFont", fs(11), "bold"),
                     anchor="center").grid(row=0, column=col, sticky="ew")

        cv_frame = tk.Frame(center, bg="#3b5b49")
        cv_frame.pack(fill=tk.BOTH, expand=True, pady=6)
        cv_frame.columnconfigure(0, weight=1)
        cv_frame.columnconfigure(1, weight=1)
        cv_frame.columnconfigure(2, weight=1)
        cv_frame.rowconfigure(0, weight=1)

        self.canvas_source = tk.Canvas(cv_frame, width=T, height=T,
                                       bg="#111111", highlightthickness=1,
                                       highlightbackground="gray40")
        self.canvas_corr   = tk.Canvas(cv_frame, width=T, height=T,
                                       bg="#111111", highlightthickness=1,
                                       highlightbackground="gray40")
        self.canvas_target = tk.Canvas(cv_frame, width=T, height=T,
                                       bg="#111111", highlightthickness=1,
                                       highlightbackground="gray40")

        self.canvas_source.grid(row=0, column=0, padx=6, sticky="nsew")
        self.canvas_corr  .grid(row=0, column=1, padx=6, sticky="nsew")
        self.canvas_target.grid(row=0, column=2, padx=6, sticky="nsew")

        self.canvas_source.bind("<Configure>", self._on_canvas_resize)
        self.canvas_corr  .bind("<Configure>", self._on_canvas_resize)
        self.canvas_target.bind("<Configure>", self._on_canvas_resize)

        # ── DROITE : liste Couleur Cible par extend/ZL sans dominante ──
        right = tk.Frame(mid, bg="#3b5b49", relief=RIDGE, bd=2)
        right.pack(side=LEFT, fill=tk.Y, padx=(8, 0))

        tk.Label(right, text="Couleur Cible — extends / ZL",
                 bg="#3b5b49", fg="light blue",
                 font=("TkFixedFont", fs(10), "bold")).pack(pady=(6, 2))

        # Champ de recherche droite
        sf_r = tk.Frame(right, bg="#3b5b49")
        sf_r.pack(fill=tk.X, padx=4, pady=(2, 2))
        tk.Label(sf_r, text="🔍", bg="#3b5b49", fg="white",
                 font=("TkFixedFont", fs(10))).pack(side=LEFT)
        self._search_right_var = tk.StringVar()
        self._search_right_var.trace_add("write", lambda *a: self._filter_right())
        tk.Entry(sf_r, textvariable=self._search_right_var, bg="#1a2a40", fg="white",
                 font=("TkFixedFont", fs(9)), insertbackground="white", width=18).pack(side=LEFT, padx=2)

        lb_wrap2 = tk.Frame(right, bg="#3b5b49")
        lb_wrap2.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)
        sb2 = tk.Scrollbar(lb_wrap2, orient=tk.VERTICAL)
        self.listbox_target = tk.Listbox(
            lb_wrap2, bg="black", fg="#88ccff",
            font=("TkFixedFont", fs(9)), width=34, height=12,
            selectbackground="#002244", yscrollcommand=sb2.set,
            exportselection=0)
        sb2.config(command=self.listbox_target.yview)
        self.listbox_target.pack(side=LEFT, fill=tk.BOTH, expand=True)
        sb2.pack(side=RIGHT, fill=tk.Y)
        self.listbox_target.bind("<<ListboxSelect>>", self._on_select_target)

        # Curseurs
        sf = tk.LabelFrame(center, text="Correction sRGB par canal + Saturation",
                           bg="#3b5b49", fg="yellow",
                           font=("TkFixedFont", fs(10), "bold"))
        sf.pack(fill=tk.X, padx=6, pady=8)

        cursors = [
            ("R  corr",  self.var_r,  "#ff6666", -60, 60),
            ("G  corr",  self.var_g,  "#66ff66", -60, 60),
            ("B  corr",  self.var_b,  "#6699ff", -60, 60),
            ("R  Lum",   self.var_lr, "#ffaaaa", -50, 50),
            ("G  Lum",   self.var_lg, "#aaffaa", -50, 50),
            ("B  Lum",   self.var_lb, "#aaaaff", -50, 50),
            ("R  Cont",  self.var_cr, "#ff6666", -50, 50),
            ("G  Cont",  self.var_cg, "#66ff66", -50, 50),
            ("B  Cont",  self.var_cb, "#6699ff", -50, 50),
            ("Sat R",    self.var_sr, "#ff8888", -50, 50),
            ("Sat G",    self.var_sg, "#88ff88", -50, 50),
            ("Sat B",    self.var_sb, "#8888ff", -50, 50),
        ]

        for row, (label, var, color, frm, to) in enumerate(cursors):
            fc = tk.Frame(sf, bg="#3b5b49")
            fc.grid(row=row // 3, column=row % 3, padx=8, pady=4, sticky="w")
            tk.Label(fc, text=label, bg="#3b5b49", fg=color,
                     font=("TkFixedFont", fs(10)), width=8, anchor="e").pack(side=LEFT)
            tk.Scale(fc, from_=frm, to=to, orient=HORIZONTAL, variable=var,
                     bg="#3b5b49", fg=color, troughcolor="#003300", length=sl,
                     font=("TkFixedFont", fs(11)),
                     command=self._on_slider_change).pack(side=LEFT)

        # Netteté
        nf = tk.LabelFrame(center, text="Netteté", bg="#3b5b49", fg="yellow",
                           font=("TkFixedFont", fs(10), "bold"))
        nf.pack(fill=tk.X, padx=6, pady=4)
        fn = tk.Frame(nf, bg="#3b5b49")
        fn.pack(padx=8, pady=3, anchor="w")
        tk.Label(fn, text="Netteté", bg="#3b5b49", fg="white",
                 font=("TkFixedFont", fs(10)), width=8, anchor="e").pack(side=LEFT)
        tk.Scale(fn, from_=0, to=300, orient=HORIZONTAL, variable=self.var_sharp,
                 bg="#3b5b49", fg="white", troughcolor="#003300", length=sl,
                 font=("TkFixedFont", fs(11)),
                 command=self._on_slider_change).pack(side=LEFT)

        # Boutons d'action
        cb = tk.Frame(center, bg="#3b5b49")
        cb.pack(fill=tk.X, padx=6, pady=6)
        ttk.Button(cb, text="🎯 Auto-détecter",    command=self._auto_detect).pack(side=LEFT, padx=4)
        ttk.Button(cb, text="↺ Reset curseurs",    command=self._reset_sliders).pack(side=LEFT, padx=4)
        ttk.Button(cb, text="🔬 Auto depuis Cible", command=self._auto_from_target).pack(side=LEFT, padx=4)

        # ── Panneau Côtes & Îles (O4_Coastal_Manager) ─────────────────────
        try:
            import O4_Coastal_Manager as COAST
            COAST.build_coastal_info_panel(self)
        except ImportError:
            pass
        # ──────────────────────────────────────────────────────────────────

        self.status = tk.Label(self, text="En attente…",
                               bg="black", fg="light green",
                               font=("TkFixedFont", fs(10)), anchor="w")
        self.status.pack(fill=tk.X, padx=6, pady=(4, 8))


    # ─────────────────────────────────────────────────────────────
    # Redimensionnement dynamique des canvases
    # ─────────────────────────────────────────────────────────────

    def _on_canvas_resize(self, event=None):
        """Redessine les images dans les canvases quand la fenêtre change de taille."""
        self._redraw_canvas(self.canvas_source, self._photo_source, self.preview_orig)
        # Pour la correction, on la recalcule à partir de l'original
        if self.preview_orig:
            self._update_preview()
        self._redraw_canvas(self.canvas_target, self._photo_target, self.preview_target)

    def _redraw_canvas(self, canvas, photo_ref, pil_img):
        """Redimensionne et affiche une image PIL dans un canvas."""
        if pil_img is None:
            return
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w < 2 or h < 2:
            return
        resized = pil_img.resize((w, h), Image.LANCZOS)
        photo   = ImageTk.PhotoImage(resized)
        # On met à jour la référence selon le canvas
        if canvas is self.canvas_source:
            self._photo_source = photo
        elif canvas is self.canvas_target:
            self._photo_target = photo
        canvas.delete("all")
        canvas.create_image(0, 0, anchor=tk.NW, image=photo)

    # ─────────────────────────────────────────────────────────────
    # Slider → preview
    # ─────────────────────────────────────────────────────────────

    def _on_slider_change(self, *args):
        self._update_preview()

    # ─────────────────────────────────────────────────────────────
    # Scan dossier textures
    # ─────────────────────────────────────────────────────────────

    def _scan(self):
        if not os.path.isdir(self.textures_dir):
            self.status.config(text=f"⚠ Dossier textures introuvable : {self.textures_dir}")
            self.lbl_path.config(fg="#ff6666")
            return

        self.lbl_path.config(fg="#aaffaa")
        self.status.config(text="Scan en cours…")
        self.listbox_layers.delete(0, END)
        self.listbox_target.delete(0, END)
        self.layer_groups      = {}
        self.extend_groups     = {}
        self.all_dds_list      = []
        self._left_items       = []
        self._right_items      = []
        self.selected_group    = None
        self.selected_dds_info = None

        threading.Thread(target=self._scan_thread, daemon=True).start()

    def _scan_thread(self):
        try:
            all_files = os.listdir(self.textures_dir)
        except Exception as e:
            self.after(0, lambda: self.status.config(text=f"⚠ Erreur lecture dossier : {e}"))
            return

        files = sorted(f for f in all_files if f.lower().endswith(".dds"))
        if not files:
            self.after(0, lambda: self.status.config(
                text=f"Aucun DDS trouvé dans : {self.textures_dir}"))
            return

        all_dds = []
        for i, fname in enumerate(files):
            self.after(0, lambda i=i, t=len(files), f=fname:
                       self.status.config(text=f"Scan {i+1}/{t} — {f}…"))
            info = analyze_dds(os.path.join(self.textures_dir, fname))
            all_dds.append(info)

        self.after(0, lambda: self._scan_done(all_dds))

    def _scan_done(self, all_dds):
        self.all_dds_list = all_dds

        # ── Organiser par couche ZL ──────────────────────────────
        layer_groups = {}
        for info in all_dds:
            zl = info.get("zl") or 0
            layer_groups.setdefault(zl, []).append(info)

        # ── Organiser par extend (pour la liste droite / cible) ──
        extend_groups = {}
        for info in all_dds:
            ext = info.get("extend", "inconnu")
            extend_groups.setdefault(ext, []).append(info)

        self.layer_groups  = layer_groups
        self.extend_groups = extend_groups

        # ── Remplir liste GAUCHE : couche ZL → fichiers ──────────
        self.listbox_layers.delete(0, END)
        self._left_items = []
        corrections = load_corrections(self.textures_dir)

        for zl in sorted(layer_groups.keys()):
            files_in_zl = layer_groups[zl]
            zl_label    = f"ZL{zl}" if zl else "ZL?"
            header_txt  = f"═══ {zl_label}  ({len(files_in_zl)} tuiles) ═══"
            self.listbox_layers.insert(END, header_txt)
            hi = self.listbox_layers.size() - 1
            self.listbox_layers.itemconfig(hi, fg="#aaffaa")
            self._left_items.append((header_txt, {"zl": zl, "files": files_in_zl}, True))

            for info in files_in_zl:
                fname     = info["name"]
                mr        = info.get("mean_r", 0)
                mg        = info.get("mean_g", 0)
                mb        = info.get("mean_b", 0)
                dom       = info.get("dominant")
                delta     = info.get("delta", 0)
                drift_max = info.get("drift_max", 0)
                # Dominante avec valeur chiffrée : [R+12] au lieu de [R]
                dom_s   = f"[{dom}{delta:+.0f}]" if dom else "      "
                # Dérive vs cube de référence calibré (affichée si > 5 pts)
                drift_s = f"Δ{drift_max:+.0f}" if drift_max > 5 else "   "
                # Icône .comb avec nombre de zones si connu
                comb_info = info.get("comb_info")
                if info.get("has_comb"):
                    if isinstance(comb_info, dict):
                        nz = len(comb_info.get("protect_zones", []) or [])
                        comb = f"📎{nz}" if nz else "📎"
                    elif isinstance(comb_info, list):
                        comb = f"📎{len(comb_info)}"
                    else:
                        comb = "📎"
                else:
                    comb = "  "
                corr  = "✏" if fname in corrections else " "
                # Format : comb corr dom dérive R/G/B  nom
                line  = f"  {comb}{corr} {dom_s} {drift_s} R{mr:3.0f} G{mg:3.0f} B{mb:3.0f}  {fname}"
                self.listbox_layers.insert(END, line)
                li = self.listbox_layers.size() - 1
                # Couleur selon dominante
                if dom == "R":
                    self.listbox_layers.itemconfig(li, fg="#ff9999")
                elif dom == "G":
                    self.listbox_layers.itemconfig(li, fg="#99ff99")
                elif dom == "B":
                    self.listbox_layers.itemconfig(li, fg="#9999ff")
                else:
                    self.listbox_layers.itemconfig(li, fg="#dddddd")
                self._left_items.append((line, info, False))

        # ── Remplir liste DROITE : extends regroupés → Couleur Cible ──
        self.listbox_target.delete(0, END)
        self._right_items = []
        corrections = load_corrections(self.textures_dir)

        for ext in sorted(extend_groups.keys()):
            files_in_ext = extend_groups[ext]
            hdr = f"── {ext}  ({len(files_in_ext)} JPG) ──"
            self.listbox_target.insert(END, hdr)
            hi2 = self.listbox_target.size() - 1
            self.listbox_target.itemconfig(hi2, fg="#aaddff")
            self._right_items.append((hdr, {"extend": ext, "files": files_in_ext}, True))

            for info in files_in_ext:
                fname = info["name"]
                mr    = info.get("mean_r", 0)
                mg    = info.get("mean_g", 0)
                mb    = info.get("mean_b", 0)
                zl    = info.get("zl", "?")
                line  = f"  ZL{zl}  R{mr:3.0f} G{mg:3.0f} B{mb:3.0f}  {fname}"
                self.listbox_target.insert(END, line)
                li2 = self.listbox_target.size() - 1
                self.listbox_target.itemconfig(li2, fg="#88ccff")
                self._right_items.append((line, info, False))

        total = len(all_dds)
        self.status.config(
            text=f"{total} DDS scannés — {len(layer_groups)} couches ZL — {len(extend_groups)} extends")

        self.btn_build.config(state="normal" if all_dds else "disabled")

    # ─────────────────────────────────────────────────────────────
    # Filtres de recherche
    # ─────────────────────────────────────────────────────────────

    def _filter_left(self):
        """Filtre la liste gauche selon le texte de recherche.
        Cherche dans : nom DDS, ZL, dominante, et labels de zones .comb."""
        q = self._search_left_var.get().strip().lower()
        self.listbox_layers.delete(0, END)
        for txt, data, is_header in self._left_items:
            # Recherche dans le texte affiché
            match = not q or q in txt.lower()
            # Recherche complémentaire dans les données .comb si fichier individuel
            if not match and q and isinstance(data, dict) and "has_comb" in data:
                comb_info = data.get("comb_info") or {}
                if isinstance(comb_info, dict):
                    zones = comb_info.get("protect_zones", [])
                    comb_str = " ".join(
                        str(z.get("label", "")) for z in (zones or [])
                        if isinstance(z, dict)
                    ).lower()
                    if q in comb_str:
                        match = True
            if match:
                self.listbox_layers.insert(END, txt)
                i = self.listbox_layers.size() - 1
                if is_header:
                    self.listbox_layers.itemconfig(i, fg="#aaffaa")
                else:
                    dom = data.get("dominant") if isinstance(data, dict) and "mean_r" in data else None
                    if dom == "R":   self.listbox_layers.itemconfig(i, fg="#ff9999")
                    elif dom == "G": self.listbox_layers.itemconfig(i, fg="#99ff99")
                    elif dom == "B": self.listbox_layers.itemconfig(i, fg="#9999ff")
                    else:            self.listbox_layers.itemconfig(i, fg="#dddddd")

    def _filter_right(self):
        """Filtre la liste droite selon le texte de recherche."""
        q = self._search_right_var.get().strip().lower()
        self.listbox_target.delete(0, END)
        for txt, data, is_header in self._right_items:
            if not q or q in txt.lower():
                self.listbox_target.insert(END, txt)
                i = self.listbox_target.size() - 1
                if is_header:
                    self.listbox_target.itemconfig(i, fg="#aaddff")
                else:
                    self.listbox_target.itemconfig(i, fg="#88ccff")


    # ─────────────────────────────────────────────────────────────
    # Sélection dans les listes
    # ─────────────────────────────────────────────────────────────

    def _on_select_layer(self, event):
        """
        Clic dans la liste gauche (couches ZL).
        Header ZL → sélectionne le groupe ZL entier.
        Fichier individuel → sélectionne ce DDS.
        """
        sel = self.listbox_layers.curselection()
        if not sel:
            return
        # Retrouver l'item dans _left_items via le texte affiché
        # (la liste peut être filtrée, donc on cherche par texte)
        displayed_idx = sel[0]
        displayed_txt = self.listbox_layers.get(displayed_idx)

        # Chercher dans _left_items
        matched = None
        for txt, data, is_header in self._left_items:
            if txt == displayed_txt:
                matched = (txt, data, is_header)
                break

        if matched is None:
            return

        txt, data, is_header = matched

        if is_header:
            # Groupe ZL entier
            zl    = data["zl"]
            files = data["files"]
            self.selected_group    = {"zl": zl, "files": files, "key": f"ZL{zl}"}
            self.selected_dds_info = files[0] if files else None
            self._load_preview()
            n = len(files)
            self.status.config(
                text=f"ZL{zl} — {n} tuile{'s' if n>1 else ''} — clic sur un fichier pour prévisualiser")
        else:
            # Fichier individuel
            info = data
            self.selected_dds_info = info
            zl = info.get("zl", "?")
            self.selected_group = {
                "zl": zl,
                "files": self.layer_groups.get(zl, [info]),
                "key": f"ZL{zl}",
            }
            self._load_preview()
            fname = info["name"]
            mr    = info.get("mean_r", 0)
            mg    = info.get("mean_g", 0)
            mb    = info.get("mean_b", 0)
            dom   = info.get("dominant")
            dom_s = f"  [{dom}+{info.get('delta',0):.0f}pt]" if dom else ""
            # Détail .comb : nombre de zones + ΔE si enregistré
            comb_s = ""
            if info.get("has_comb"):
                comb_info = info.get("comb_info") or {}
                # comb_info peut être une liste (format protection seule) ou un dict
                if isinstance(comb_info, dict):
                    zones = comb_info.get("protect_zones", [])
                    n_zones = len(zones) if isinstance(zones, list) else 0
                    de_s = comb_info.get("seam_delta_e")
                    de_txt = f" ΔE={de_s:.0f}" if de_s else ""
                    comb_s = f"  [.comb ✓ {n_zones}z{de_txt}]"
                elif isinstance(comb_info, list):
                    comb_s = f"  [.comb ✓ {len(comb_info)}z]"
                else:
                    comb_s = "  [.comb ✓]"
            self.status.config(
                text=f"ZL{zl}  {fname}  R{mr:.0f} G{mg:.0f} B{mb:.0f}{dom_s}{comb_s}")


    def _on_dbl_click_layer(self, event):
        """
        Double-clic sur un groupe ZL dans la liste gauche → ouvre Batch Preview.
        Si un fichier individuel est double-cliqué → batch preview sur sa couche ZL.
        """
        if self.selected_group:
            files = self.selected_group.get("files", [])
            if files:
                self._batch_preview()

    # ─────────────────────────────────────────────────────────────
    # Chargement et mise à jour des previews
    # ─────────────────────────────────────────────────────────────

    def _load_preview(self):
        if not self.selected_dds_info:
            return
        img = load_dds_preview(self.selected_dds_info["path"])
        if img:
            self.preview_orig = img.resize((self._thumb, self._thumb), Image.LANCZOS)
        else:
            self.preview_orig = None

        # Reset curseurs seulement si on change de groupe
        if (not self.selected_group
                or self.selected_dds_info not in self.selected_group.get("files", [])):
            self._reset_sliders()

        self._update_preview()

    def _on_select_target(self, event):
        """Clic dans la liste droite (Couleur Cible par extend)."""
        sel = self.listbox_target.curselection()
        if not sel:
            return
        displayed_txt = self.listbox_target.get(sel[0])

        for txt, data, is_header in self._right_items:
            if txt == displayed_txt:
                if is_header:
                    # Groupe extend sélectionné → preview du premier fichier
                    files = data.get("files", [])
                    if files:
                        self.target_idx = 0
                        info = files[0]
                        img  = load_dds_preview(info["path"])
                        if img:
                            w = self.canvas_target.winfo_width()  or self._thumb
                            h = self.canvas_target.winfo_height() or self._thumb
                            self.preview_target = img.resize((max(w, 4), max(h, 4)), Image.LANCZOS)
                            self._photo_target  = ImageTk.PhotoImage(self.preview_target)
                            self.canvas_target.delete("all")
                            self.canvas_target.create_image(0, 0, anchor=tk.NW, image=self._photo_target)
                        self.status.config(
                            text=f"Cible : extend {data['extend']} — {len(files)} tuiles")
                else:
                    info = data
                    img  = load_dds_preview(info["path"])
                    if img:
                        w = self.canvas_target.winfo_width()  or self._thumb
                        h = self.canvas_target.winfo_height() or self._thumb
                        self.preview_target = img.resize((max(w, 4), max(h, 4)), Image.LANCZOS)
                        self._photo_target  = ImageTk.PhotoImage(self.preview_target)
                        self.canvas_target.delete("all")
                        self.canvas_target.create_image(0, 0, anchor=tk.NW, image=self._photo_target)
                    mr = info.get("mean_r", 0)
                    mg = info.get("mean_g", 0)
                    mb = info.get("mean_b", 0)
                    self.status.config(
                        text=f"Cible : {info['name']}  R{mr:.0f} G{mg:.0f} B{mb:.0f}")
                break


    def _update_preview(self):
        if not self.preview_orig:
            return

        # Construit le dict corrections depuis les curseurs
        corr = {
            "dr":     self.var_r.get(),  "dg":     self.var_g.get(),  "db":     self.var_b.get(),
            "lum_r":  self.var_lr.get(), "lum_g":  self.var_lg.get(), "lum_b":  self.var_lb.get(),
            "cont_r": self.var_cr.get(), "cont_g": self.var_cg.get(), "cont_b": self.var_cb.get(),
            "sat_r":  self.var_sr.get(), "sat_g":  self.var_sg.get(), "sat_b":  self.var_sb.get(),
            "sharp":  self.var_sharp.get(),
        }

        arr       = np.array(self.preview_orig, dtype=np.float32)
        # Charger masque PNG côtier si disponible
        _sea_mask = None
        if self.selected_dds_info:
            try:
                import O4_Color_Normalize as CNORM
                import O4_File_Names as FNAMES
                _info = self.selected_dds_info
                _zl   = _info.get("zl")
                _name = _info.get("name", "")
                # Construire le chemin exact via FNAMES.mask_file
                _parts = os.path.splitext(_name)[0].split("_")
                if len(_parts) >= 2:
                    try:
                        _tx = int(_parts[0]); _ty = int(_parts[1])
                        _sea_path = os.path.join(
                            self.textures_dir,
                            FNAMES.mask_file(_tx, _ty, _zl, ""))
                        _sea_mask = CNORM._load_sea_mask(
                            _sea_path,
                            (self.preview_orig.width, self.preview_orig.height))
                    except Exception:
                        pass
            except Exception:
                pass
        corrected = Image.fromarray(apply_corrections_to_array(arr, corr, sea_mask=_sea_mask))

        # Netteté
        if corr["sharp"] > 0:
            corrected = ImageEnhance.Sharpness(corrected).enhance(
                1.0 + corr["sharp"] / 100.0)

        # Adapte la taille aux canvases actuels
        sw = self.canvas_source.winfo_width()  or self._thumb
        sh = self.canvas_source.winfo_height() or self._thumb
        src_disp = self.preview_orig.resize((max(sw, 4), max(sh, 4)), Image.LANCZOS)
        cw = self.canvas_corr.winfo_width()   or self._thumb
        ch = self.canvas_corr.winfo_height()  or self._thumb
        cor_disp = corrected.resize((max(cw, 4), max(ch, 4)), Image.LANCZOS)

        self._photo_source = ImageTk.PhotoImage(src_disp)
        self._photo_corr   = ImageTk.PhotoImage(cor_disp)

        self.canvas_source.delete("all")
        self.canvas_corr.delete("all")
        self.canvas_source.create_image(0, 0, anchor=tk.NW, image=self._photo_source)
        self.canvas_corr  .create_image(0, 0, anchor=tk.NW, image=self._photo_corr)

    # ─────────────────────────────────────────────────────────────
    # Actions sur les boutons
    # ─────────────────────────────────────────────────────────────

    def _auto_detect(self):
        if not self.selected_dds_info:
            self.status.config(text="⚠ Sélectionnez d'abord un DDS.")
            return
        info   = self.selected_dds_info
        d, pt  = info["dominant"], round(info["delta"])
        self._reset_sliders()
        if   d == "R": self.var_r.set(-pt)
        elif d == "G": self.var_g.set(-pt)
        elif d == "B": self.var_b.set(-pt)
        self._update_preview()
        self.status.config(text=f"Auto : [{d} {-pt:+d}pt]")

    def _auto_from_target(self):
        if not self.selected_dds_info or self.target_idx is None:
            self.status.config(text="⚠ Sélectionnez un DDS à gauche ET une cible à droite.")
            return
        if not self.preview_orig or not self.preview_target:
            return

        arr_s  = np.array(self.preview_orig,   dtype=np.float32)
        arr_t  = np.array(self.preview_target, dtype=np.float32)

        # Redimension si les tailles diffèrent
        if arr_s.shape != arr_t.shape:
            arr_t = np.array(
                self.preview_target.resize(
                    (arr_s.shape[1], arr_s.shape[0]), Image.LANCZOS),
                dtype=np.float32)

        corr_r = int(round(np.mean(arr_t[:, :, 0]) - np.mean(arr_s[:, :, 0])))
        corr_g = int(round(np.mean(arr_t[:, :, 1]) - np.mean(arr_s[:, :, 1])))
        corr_b = int(round(np.mean(arr_t[:, :, 2]) - np.mean(arr_s[:, :, 2])))

        self.var_r.set(corr_r)
        self.var_g.set(corr_g)
        self.var_b.set(corr_b)
        self._update_preview()
        self.status.config(text=f"Auto depuis cible : R{corr_r:+d} G{corr_g:+d} B{corr_b:+d}")

    def _reset_sliders(self):
        for v in (self.var_r, self.var_g, self.var_b,
                  self.var_lr, self.var_lg, self.var_lb,
                  self.var_cr, self.var_cg, self.var_cb,
                  self.var_sr, self.var_sg, self.var_sb):
            v.set(0)
        self.var_sharp.set(0)
        self._update_preview()

    def _apply_group_correction(self):
        """
        Applique les corrections des curseurs au groupe sélectionné (ZL entier ou fichier).
        Sauvegarde dans .ccorr pour chaque fichier du groupe.
        """
        if not self.selected_group:
            self.status.config(text="⚠ Sélectionnez d'abord une couche ZL ou un fichier.")
            return

        entry = {
            "dr":     self.var_r.get(),   "dg":     self.var_g.get(),   "db":     self.var_b.get(),
            "lum_r":  self.var_lr.get(),  "lum_g":  self.var_lg.get(),  "lum_b":  self.var_lb.get(),
            "cont_r": self.var_cr.get(),  "cont_g": self.var_cg.get(),  "cont_b": self.var_cb.get(),
            "sat_r":  self.var_sr.get(),  "sat_g":  self.var_sg.get(),  "sat_b":  self.var_sb.get(),
            "sharp":  self.var_sharp.get(),
            "strength": 1.0,
        }

        vals = [entry[k] for k in entry if k != "strength"]
        if all(v == 0 for v in vals):
            self.status.config(
                text="⚠ Tous les curseurs sont à 0 — ajustez au moins un curseur.")
            return

        corrections = load_corrections(self.textures_dir)
        files = self.selected_group.get("files", [])
        if self.selected_dds_info and self.selected_dds_info not in files:
            files = [self.selected_dds_info]

        for info in files:
            # Clé DDS (existant — pour apply_ccorr post-assemblage)
            corrections[info["name"]] = entry.copy()
            # Clé JPG (nouveau — pour apply_ccorr_jpg sur chaque JPG avant assemblage)
            jpg_key = os.path.splitext(info["name"])[0] + ".jpg"
            corrections[jpg_key] = entry.copy()
        save_corrections(self.textures_dir, corrections)

        parts = []
        if entry["dr"] or entry["dg"] or entry["db"]:
            parts.append(f"R{entry['dr']:+d} G{entry['dg']:+d} B{entry['db']:+d}")
        if entry["lum_r"] or entry["lum_g"] or entry["lum_b"]:
            parts.append(f"Lum R{entry['lum_r']:+d} G{entry['lum_g']:+d} B{entry['lum_b']:+d}")
        if entry["sharp"]:
            parts.append(f"Sharp+{entry['sharp']}")

        n   = len(files)
        key = self.selected_group.get("key", "?")
        self.status.config(
            text=f"✅ {key} — {n} fichier{'s' if n>1 else ''} mis à jour : " + "  ".join(parts))
        self.btn_build.config(state="normal")
        # Rescan léger pour mettre à jour l'indicateur ✏ dans la liste
        self.after(100, self._scan)

    def _save_comb_for_group(self):
        """
        Ouvre l'éditeur de zones de protection pour le DDS sélectionné.
        L'utilisateur dessine des rectangles sur l'image (pistes, marquages).
        Le .comb généré contient : nom JPG, couche ZL, corrections, zones de protection.
        Si plusieurs fichiers dans le groupe → applique les mêmes zones à tous.
        """
        if not self.selected_group:
            self.status.config(text="⚠ Sélectionnez d'abord une couche ZL ou un fichier.")
            return

        # DDS de référence pour l'éditeur visuel
        info = self.selected_dds_info
        if not info:
            files = self.selected_group.get("files", [])
            info  = files[0] if files else None
        if not info:
            self.status.config(text="⚠ Aucun DDS disponible.")
            return

        entry = {
            "dr":     self.var_r.get(),   "dg":     self.var_g.get(),   "db":     self.var_b.get(),
            "lum_r":  self.var_lr.get(),  "lum_g":  self.var_lg.get(),  "lum_b":  self.var_lb.get(),
            "cont_r": self.var_cr.get(),  "cont_g": self.var_cg.get(),  "cont_b": self.var_cb.get(),
            "sat_r":  self.var_sr.get(),  "sat_g":  self.var_sg.get(),  "sat_b":  self.var_sb.get(),
            "sharp":  self.var_sharp.get(),
        }

        files_group = self.selected_group.get("files", [])
        if self.selected_dds_info and self.selected_dds_info not in files_group:
            files_group = [self.selected_dds_info]

        def _on_zones_confirmed(zones):
            count = 0
            for fi in files_group:
                zl       = fi.get("zl", 0)
                jpg_name = os.path.splitext(fi["name"])[0] + ".jpg"
                save_comb(self.textures_dir, jpg_name, zl, entry, zones)
                count += 1
            key = self.selected_group.get("key", "?")
            self.status.config(
                text=f"✅ {count} fichier(s) .comb générés pour {key}  ({len(zones)} zone(s) protégée(s))")
            self._scan()

        CombZoneEditor(self, info["path"], _on_zones_confirmed)

    def _batch_preview(self):
        """
        Mode batch preview : affiche une fenêtre montrant l'impact des corrections
        actuelles sur toutes les tuiles de la couche ZL sélectionnée (miniatures).
        """
        if not self.selected_group:
            self.status.config(text="⚠ Sélectionnez d'abord une couche ZL.")
            return

        files = self.selected_group.get("files", [])
        if not files:
            self.status.config(text="⚠ Aucun fichier dans ce groupe.")
            return

        entry = {
            "dr":     self.var_r.get(),   "dg":     self.var_g.get(),   "db":     self.var_b.get(),
            "lum_r":  self.var_lr.get(),  "lum_g":  self.var_lg.get(),  "lum_b":  self.var_lb.get(),
            "cont_r": self.var_cr.get(),  "cont_g": self.var_cg.get(),  "cont_b": self.var_cb.get(),
            "sat_r":  self.var_sr.get(),  "sat_g":  self.var_sg.get(),  "sat_b":  self.var_sb.get(),
            "sharp":  self.var_sharp.get(),
        }

        key = self.selected_group.get("key", "?")
        BatchPreviewWindow(self, files, entry, key)


    def _delete_one(self):
        if not self.selected_dds_info:
            self.status.config(text="⚠ Sélectionnez un DDS individuel.")
            return
        self._do_delete(self.selected_dds_info)
        self._scan()

    def _delete_all(self):
        """Supprime tous les DDS de la couche ZL sélectionnée."""
        if not self.selected_group:
            self.status.config(text="⚠ Sélectionnez d'abord une couche ZL.")
            return
        files = self.selected_group.get("files", [])
        if not files:
            return
        key = self.selected_group.get("key", "?")
        if not messagebox.askyesno(
                "Confirmation", f"Supprimer {len(files)} DDS de {key} ?"):
            return
        for info in files:
            self._do_delete(info)
        self._scan()


    def _do_delete(self, info):
        corrections = load_corrections(self.textures_dir)
        corrections[info["name"]] = {
            "dr":     self.var_r.get(),  "dg":     self.var_g.get(),  "db":     self.var_b.get(),
            "lum_r":  self.var_lr.get(), "lum_g":  self.var_lg.get(), "lum_b":  self.var_lb.get(),
            "cont_r": self.var_cr.get(), "cont_g": self.var_cg.get(), "cont_b": self.var_cb.get(),
            "sat_r":  self.var_sr.get(), "sat_g":  self.var_sg.get(), "sat_b":  self.var_sb.get(),
            "strength": 1.0,
        }
        save_corrections(self.textures_dir, corrections)
        try:
            os.remove(info["path"])
        except Exception:
            pass

    def _archive_corrections(self):
        """
        Copie le .ccorr de la tuile courante dans Color_check/
        Nom du fichier : <dossier_tuile>.ccorr  (ex: +46-002.ccorr)
        Aucun impact sur le Build — archive manuelle uniquement.
        """
        src_path = os.path.join(self.textures_dir, CORRECTIONS_FILE)
        if not os.path.isfile(src_path):
            self.status.config(
                text="⚠ Aucune correction à archiver — appliquez d'abord des corrections.")
            return
        try:
            os.makedirs(COLOR_CHECK_ARCHIVE_DIR, exist_ok=True)
            # Nom basé sur le dossier de la tuile (ex: +46-002)
            tile_name = os.path.basename(
                os.path.dirname(os.path.dirname(self.textures_dir)))
            if not tile_name or tile_name == ".":
                tile_name = os.path.basename(
                    os.path.dirname(self.textures_dir))
            dest_name = f"{tile_name}.ccorr"
            dest_path = os.path.join(COLOR_CHECK_ARCHIVE_DIR, dest_name)
            import shutil
            shutil.copy2(src_path, dest_path)
            self.status.config(
                text=f"✅ Corrections archivées → Color_check/{dest_name}")
        except Exception as e:
            self.status.config(text=f"⚠ Erreur archivage : {e}")

    def _restore_corrections(self):
        """
        Choisit un fichier .ccorr dans Color_check/ et le copie
        dans le dossier textures de la tuile courante.
        Remplace les corrections existantes (confirmation demandée).
        """
        if not os.path.isdir(COLOR_CHECK_ARCHIVE_DIR):
            self.status.config(
                text="⚠ Dossier Color_check/ introuvable — aucune archive disponible.")
            return
        archives = [
            f for f in os.listdir(COLOR_CHECK_ARCHIVE_DIR)
            if f.endswith(".ccorr")
        ]
        if not archives:
            self.status.config(
                text="⚠ Aucune archive dans Color_check/ — archivez d'abord des corrections.")
            return
        # Fenêtre de sélection
        sel_win = tk.Toplevel(self)
        sel_win.title("Restaurer corrections")
        sel_win.configure(bg="#3b5b49")
        sel_win.resizable(False, False)
        tk.Label(sel_win, text="Choisir une archive à restaurer :",
                 bg="#3b5b49", fg="light green",
                 font=("TkFixedFont", 11, "bold")).pack(padx=12, pady=(10, 4))
        lb = tk.Listbox(sel_win, bg="black", fg="#88ccff",
                        font=("TkFixedFont", 10), width=36, height=min(len(archives), 10),
                        selectbackground="#002244", exportselection=0)
        lb.pack(padx=12, pady=4)
        for a in sorted(archives):
            lb.insert(END, a)
        lb.selection_set(0)
        def _do_restore():
            sel = lb.curselection()
            if not sel:
                return
            chosen = archives[sel[0]]
            src_arch = os.path.join(COLOR_CHECK_ARCHIVE_DIR, chosen)
            dest = os.path.join(self.textures_dir, CORRECTIONS_FILE)
            existing = os.path.isfile(dest)
            if existing:
                if not messagebox.askyesno(
                    "Confirmation",
                    f"Remplacer les corrections actuelles\npar {chosen} ?",
                    parent=sel_win):
                    return
            try:
                import shutil
                shutil.copy2(src_arch, dest)
                sel_win.destroy()
                self.status.config(
                    text=f"✅ Corrections restaurées depuis Color_check/{chosen}")
                self._scan()
            except Exception as e:
                self.status.config(text=f"⚠ Erreur restauration : {e}")
        btn_f = tk.Frame(sel_win, bg="#3b5b49")
        btn_f.pack(pady=(4, 10))
        ttk.Button(btn_f, text="✅ Restaurer",
                   command=_do_restore).pack(side=LEFT, padx=6)
        ttk.Button(btn_f, text="Annuler",
                   command=sel_win.destroy).pack(side=LEFT, padx=6)

    def _export_list(self):
        """Exporte la liste de toutes les tuiles, organisée par couche ZL."""
        if not self.all_dds_list:
            self.status.config(text="⚠ Aucun DDS scanné.")
            return
        out = os.path.join(self.textures_dir, "color_check_export.txt")
        try:
            with open(out, "w") as f:
                f.write(f"Color Check — Export couches ZL\n")
                f.write(f"Dossier : {self.textures_dir}\n")
                f.write(f"Total : {len(self.all_dds_list)} tuiles\n\n")
                for zl in sorted(self.layer_groups.keys()):
                    files = self.layer_groups[zl]
                    f.write(f"═══ ZL{zl} — {len(files)} tuiles ═══\n")
                    for info in files:
                        dom  = info.get("dominant")
                        dom_s = f"[{dom}]" if dom else "   "
                        comb = "[.comb]" if info.get("has_comb") else ""
                        f.write(f"  {dom_s} R{info.get('mean_r',0):3.0f} G{info.get('mean_g',0):3.0f} "
                                f"B{info.get('mean_b',0):3.0f}  {info['name']} {comb}\n")
                    f.write("\n")
            self.status.config(text=f"✅ Exporté : {out}")
        except Exception as e:
            self.status.config(text=f"Erreur export : {e}")


    def _launch_build(self):
        """
        Build pour le groupe sélectionné (couche ZL ou fichier individuel) :
          1. Supprime les DDS du groupe
          2. Applique les corrections uniquement à ces DDS
          3. Lance le build via le parent
        """
        if not self.selected_group:
            self.status.config(text="⚠ Sélectionnez d'abord une couche ZL dans la liste.")
            return

        group     = self.selected_group
        group_key = group.get("key", "?")
        files     = group.get("files", [])
        deleted   = []
        errors    = []

        for info in files:
            dds_path = info["path"]
            try:
                if os.path.isfile(dds_path):
                    os.remove(dds_path)
                    deleted.append(info["name"])
            except Exception as e:
                errors.append(f"{info['name']}: {e}")

        corrections = load_corrections(self.textures_dir)
        entry = {
            "dr":     self.var_r.get(),  "dg":     self.var_g.get(),  "db":     self.var_b.get(),
            "lum_r":  self.var_lr.get(), "lum_g":  self.var_lg.get(), "lum_b":  self.var_lb.get(),
            "cont_r": self.var_cr.get(), "cont_g": self.var_cg.get(), "cont_b": self.var_cb.get(),
            "sat_r":  self.var_sr.get(), "sat_g":  self.var_sg.get(), "sat_b":  self.var_sb.get(),
            "sharp":  self.var_sharp.get(),
            "strength": 1.0,
        }
        for info in files:
            corrections[info["name"]] = entry.copy()
        save_corrections(self.textures_dir, corrections)

        try:
            self.master.build_tile()
        except Exception as e:
            self.status.config(
                text=f"⚠ Erreur Build : {e}  ({len(deleted)} DDS supprimés du groupe {group_key})")
            return

        self.btn_build.config(state="disabled")
        msg = (f"✅ Build lancé — {group_key} : {len(deleted)} DDS supprimés"
               + (f" — ⚠ erreurs : {'; '.join(errors)}" if errors else ""))
        self.status.config(text=msg)
        self._scan()


# ─────────────────────────────────────────────────────────────────
# Éditeur de zones de protection pour .comb
# ─────────────────────────────────────────────────────────────────

class CombZoneEditor(tk.Toplevel):
    """
    Éditeur visuel de zones de protection géométriques pour .comb.
    Affiche le DDS, l'utilisateur dessine des rectangles à la souris
    sur les zones à protéger (pistes, marquages, textures fines).
    Chaque rectangle est converti en coordonnées 0-4096 (espace DDS).
    Validation → callback(zones) avec la liste des rectangles.
    """
    CANVAS_SIZE = 700   # px affichage

    def __init__(self, parent, dds_path, on_confirm):
        super().__init__(parent)
        self.title(f"Zones de protection .comb — {os.path.basename(dds_path)}")
        self.configure(bg="#1a1a2a")
        self.resizable(True, True)

        self._dds_path  = dds_path
        self._on_confirm = on_confirm
        self._zones      = []      # [{x, y, w, h, label}, ...] coords 0-4096
        self._img_pil    = None    # image originale pleine résolution
        self._img_w      = 4096
        self._img_h      = 4096
        self._photos     = []

        # État dessin
        self._draw_start = None    # (cx, cy) début rectangle en cours
        self._rect_id    = None    # id rectangle tkinter en cours
        self._selected   = None    # index zone sélectionnée

        # ── Titre ──
        tk.Label(self, text="Dessinez des rectangles sur les zones à protéger (pistes, marquages)",
                 bg="#1a1a2a", fg="#aaddff",
                 font=("TkFixedFont", 10, "bold")).pack(pady=(8, 2))
        tk.Label(self, text="Clic+glisser = nouveau rectangle  |  Clic sur zone = sélectionner  |  Suppr = effacer",
                 bg="#1a1a2a", fg="#888888",
                 font=("TkFixedFont", 8)).pack()

        # ── Canvas image ──
        cv_frm = tk.Frame(self, bg="#1a1a2a")
        cv_frm.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        self._canvas = tk.Canvas(cv_frm,
                                 width=self.CANVAS_SIZE, height=self.CANVAS_SIZE,
                                 bg="#111111", cursor="crosshair",
                                 highlightthickness=1, highlightbackground="#555555")
        self._canvas.pack(side=LEFT, fill=tk.BOTH, expand=True)

        # Panneau droite : liste zones + label
        right = tk.Frame(cv_frm, bg="#1a1a2a", width=200)
        right.pack(side=LEFT, fill=tk.Y, padx=(8, 0))
        right.pack_propagate(False)

        tk.Label(right, text="Zones protégées", bg="#1a1a2a", fg="#aaddff",
                 font=("TkFixedFont", 10, "bold")).pack(pady=(4, 2))

        lb_frm = tk.Frame(right, bg="#1a1a2a")
        lb_frm.pack(fill=tk.BOTH, expand=True)
        vsb = tk.Scrollbar(lb_frm, orient=tk.VERTICAL)
        vsb.pack(side=RIGHT, fill=tk.Y)
        self._lb_zones = tk.Listbox(lb_frm, bg="black", fg="#88ddff",
                                    font=("TkFixedFont", 8), width=22,
                                    selectbackground="#003366",
                                    yscrollcommand=vsb.set, exportselection=0)
        vsb.config(command=self._lb_zones.yview)
        self._lb_zones.pack(side=LEFT, fill=tk.BOTH, expand=True)
        self._lb_zones.bind("<<ListboxSelect>>", self._on_lb_select)

        # Label de la zone sélectionnée
        tk.Label(right, text="Étiquette :", bg="#1a1a2a", fg="#aaaaaa",
                 font=("TkFixedFont", 8)).pack(pady=(6, 0))
        self._label_var = tk.StringVar(value="piste")
        tk.Entry(right, textvariable=self._label_var, bg="#223322", fg="white",
                 font=("TkFixedFont", 9), insertbackground="white").pack(fill=tk.X, padx=4)
        ttk.Button(right, text="✏ Renommer sélect.",
                   command=self._rename_zone).pack(fill=tk.X, padx=4, pady=2)
        ttk.Button(right, text="🗑 Supprimer sélect.",
                   command=self._delete_selected).pack(fill=tk.X, padx=4, pady=2)
        ttk.Button(right, text="🗑 Tout effacer",
                   command=self._clear_all).pack(fill=tk.X, padx=4, pady=(8, 2))

        # ── Statut + boutons bas ──
        self._lbl_status = tk.Label(self, text="Chargement image…",
                                    bg="#1a1a2a", fg="#aaffaa",
                                    font=("TkFixedFont", 9))
        self._lbl_status.pack(fill=tk.X, padx=8, pady=(2, 4))

        bf = tk.Frame(self, bg="#1a1a2a")
        bf.pack(pady=(0, 10))
        ttk.Button(bf, text="✅ Valider et générer .comb",
                   command=self._confirm).pack(side=LEFT, padx=8)
        ttk.Button(bf, text="Annuler",
                   command=self.destroy).pack(side=LEFT, padx=8)

        # Bindings dessin
        self._canvas.bind("<ButtonPress-1>",   self._on_press)
        self._canvas.bind("<B1-Motion>",        self._on_drag)
        self._canvas.bind("<ButtonRelease-1>",  self._on_release)
        self._canvas.bind("<Configure>",        lambda e: self._redraw())
        self.bind("<Delete>",                   lambda e: self._delete_selected())
        self.bind("<BackSpace>",                lambda e: self._delete_selected())

        threading.Thread(target=self._load_image, daemon=True).start()

    # ── Chargement image ────────────────────────────────────────────

    def _load_image(self):
        try:
            img = Image.open(self._dds_path).convert("RGB")
            self._img_pil = img
            self._img_w, self._img_h = img.size
            self.after(0, self._redraw)
            self.after(0, lambda: self._lbl_status.config(
                text="Dessinez des rectangles sur les zones à protéger.",
                fg="#aaffaa"))
        except Exception as e:
            self.after(0, lambda: self._lbl_status.config(
                text=f"⚠ Erreur chargement : {e}", fg="#ff6666"))

    # ── Dessin canvas ───────────────────────────────────────────────

    def _canvas_size(self):
        cw = self._canvas.winfo_width()  or self.CANVAS_SIZE
        ch = self._canvas.winfo_height() or self.CANVAS_SIZE
        return cw, ch

    def _img_to_canvas(self, ix, iy):
        """Convertit coordonnées image (0-img_w/h) → canvas."""
        cw, ch = self._canvas_size()
        return ix * cw / self._img_w, iy * ch / self._img_h

    def _canvas_to_img(self, cx, cy):
        """Convertit coordonnées canvas → image (0-img_w/h)."""
        cw, ch = self._canvas_size()
        return cx * self._img_w / cw, cy * self._img_h / ch

    def _redraw(self):
        self._canvas.delete("all")
        if self._img_pil is None:
            return
        cw, ch = self._canvas_size()
        if cw < 2 or ch < 2:
            return
        thumb = self._img_pil.resize((cw, ch), Image.BOX)
        photo = ImageTk.PhotoImage(thumb)
        self._photos.append(photo)
        if len(self._photos) > 4:
            self._photos = self._photos[-4:]
        self._canvas.create_image(0, 0, anchor=tk.NW, image=photo)
        self._canvas.photo = photo

        # Dessiner les zones existantes
        for i, z in enumerate(self._zones):
            x1c, y1c = self._img_to_canvas(z["x"], z["y"])
            x2c, y2c = self._img_to_canvas(z["x"] + z["w"], z["y"] + z["h"])
            color = "#ff4444" if i == self._selected else "#ffaa00"
            self._canvas.create_rectangle(x1c, y1c, x2c, y2c,
                                          outline=color, width=2,
                                          fill=color, stipple="gray25")
            lbl = z.get("label", "")
            if lbl:
                self._canvas.create_text(
                    (x1c + x2c) / 2, (y1c + y2c) / 2,
                    text=lbl, fill="white",
                    font=("TkFixedFont", 8, "bold"))

    def _refresh_listbox(self):
        self._lb_zones.delete(0, END)
        for i, z in enumerate(self._zones):
            lbl = z.get("label", "zone")
            self._lb_zones.insert(END,
                f"#{i+1} {lbl}  {z['w']}×{z['h']}")
        if self._selected is not None and self._selected < len(self._zones):
            self._lb_zones.selection_set(self._selected)

    # ── Événements souris ───────────────────────────────────────────

    def _on_press(self, event):
        # Vérifie si clic sur une zone existante
        ix, iy = self._canvas_to_img(event.x, event.y)
        for i, z in enumerate(self._zones):
            if (z["x"] <= ix <= z["x"] + z["w"] and
                    z["y"] <= iy <= z["y"] + z["h"]):
                self._selected = i
                self._redraw()
                self._refresh_listbox()
                return
        # Sinon : début nouveau rectangle
        self._selected   = None
        self._draw_start = (event.x, event.y)
        self._rect_id    = None

    def _on_drag(self, event):
        if self._draw_start is None:
            return
        if self._rect_id:
            self._canvas.delete(self._rect_id)
        x0, y0 = self._draw_start
        self._rect_id = self._canvas.create_rectangle(
            x0, y0, event.x, event.y,
            outline="#00ff88", width=2, dash=(4, 2))

    def _on_release(self, event):
        if self._draw_start is None:
            return
        x0c, y0c = self._draw_start
        x1c, y1c = event.x, event.y
        self._draw_start = None
        if self._rect_id:
            self._canvas.delete(self._rect_id)
            self._rect_id = None

        # Ignorer les rectangles trop petits (< 5px)
        if abs(x1c - x0c) < 5 or abs(y1c - y0c) < 5:
            return

        # Convertir en coordonnées image
        ix0, iy0 = self._canvas_to_img(min(x0c, x1c), min(y0c, y1c))
        ix1, iy1 = self._canvas_to_img(max(x0c, x1c), max(y0c, y1c))
        ix0 = max(0, int(ix0));  iy0 = max(0, int(iy0))
        ix1 = min(self._img_w, int(ix1)); iy1 = min(self._img_h, int(iy1))

        zone = {
            "x": ix0, "y": iy0,
            "w": ix1 - ix0, "h": iy1 - iy0,
            "label": self._label_var.get().strip() or "zone",
        }
        self._zones.append(zone)
        self._selected = len(self._zones) - 1
        self._redraw()
        self._refresh_listbox()
        self._lbl_status.config(
            text=f"{len(self._zones)} zone(s) — {zone['label']}  "
                 f"x={zone['x']} y={zone['y']} w={zone['w']} h={zone['h']}",
            fg="#aaffaa")

    def _on_lb_select(self, event):
        sel = self._lb_zones.curselection()
        if sel:
            self._selected = sel[0]
            self._redraw()

    def _rename_zone(self):
        if self._selected is not None and self._selected < len(self._zones):
            self._zones[self._selected]["label"] = self._label_var.get().strip() or "zone"
            self._redraw()
            self._refresh_listbox()

    def _delete_selected(self):
        if self._selected is not None and self._selected < len(self._zones):
            self._zones.pop(self._selected)
            self._selected = None
            self._redraw()
            self._refresh_listbox()

    def _clear_all(self):
        self._zones    = []
        self._selected = None
        self._redraw()
        self._refresh_listbox()

    def _confirm(self):
        self._on_confirm(list(self._zones))
        self.destroy()


class BatchPreviewWindow(tk.Toplevel):
    """
    Affiche en miniatures côte à côte (avant / après correction)
    toutes les tuiles d'une couche ZL sélectionnée.
    Clic sur une miniature → agrandissement avec zoom/pan.
    v2.5 : affiche la zone de jointure (seam) surlignée en orange
    sur chaque miniature si un seam est détecté → aperçu de l'impact
    du dégradé avant Build.
    """
    THUMB_SIZE = 128
    COLS       = 6

    def __init__(self, parent, files, corrections, label):
        super().__init__(parent)
        self.title(f"Batch Preview — {label}")
        self.configure(bg="#1a2a18")
        self.resizable(True, True)

        self._files       = files
        self._corrections = corrections
        self._label       = label
        self._photos      = []
        # stocke (orig_PIL, corr_PIL, name) pour l'agrandissement
        self._tile_data   = {}

        # textures_dir : déduit depuis le chemin du premier fichier
        # (utilisé pour le masque mer PNG Ortho4XP dans _load_all)
        self.textures_dir = os.path.dirname(files[0]["path"]) if files else ""

        tk.Label(self, text=f"Batch Preview — {label}  ({len(files)} tuiles)",
                 bg="#1a2a18", fg="#aaffaa",
                 font=("TkFixedFont", 11, "bold")).pack(pady=(8, 4))
        tk.Label(self, text="Gauche = original  |  Droite = corrigé  — clic pour agrandir",
                 bg="#1a2a18", fg="#ffdd88",
                 font=("TkFixedFont", 9)).pack()

        # ── Résumé des corrections appliquées ─────────────────────────────
        # Construit une ligne lisible des valeurs non-nulles pour confirmer
        # que les curseurs étaient bien réglés au moment de l'ouverture.
        _parts = []
        _names = [
            ("dr","R"),("dg","G"),("db","B"),
            ("lum_r","LumR"),("lum_g","LumG"),("lum_b","LumB"),
            ("cont_r","CntR"),("cont_g","CntG"),("cont_b","CntB"),
            ("sat_r","SatR"),("sat_g","SatG"),("sat_b","SatB"),
            ("sharp","Sharp"),
        ]
        for key, lbl in _names:
            v = corrections.get(key, 0)
            if v:
                _parts.append(f"{lbl}:{v:+g}" if isinstance(v, float) else f"{lbl}:{v:+d}")
        _corr_txt  = "  ".join(_parts) if _parts else "⚠ Aucune correction active — les deux panneaux seront identiques"
        _corr_color = "#aaffaa" if _parts else "#ffaa44"
        tk.Label(self, text=_corr_txt, bg="#1a2a18", fg=_corr_color,
                 font=("TkFixedFont", 8)).pack(pady=(0, 4))

        frm_outer = tk.Frame(self, bg="#1a2a18")
        frm_outer.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        vsb = tk.Scrollbar(frm_outer, orient=tk.VERTICAL)
        vsb.pack(side=RIGHT, fill=tk.Y)
        self._canvas_scroll = tk.Canvas(frm_outer, bg="#111111",
                                        yscrollcommand=vsb.set,
                                        highlightthickness=0)
        self._canvas_scroll.pack(side=LEFT, fill=tk.BOTH, expand=True)
        vsb.config(command=self._canvas_scroll.yview)

        self._inner = tk.Frame(self._canvas_scroll, bg="#111111")
        canvas_win  = self._canvas_scroll.create_window((0, 0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>",
                         lambda e: self._canvas_scroll.configure(
                             scrollregion=self._canvas_scroll.bbox("all")))
        self._canvas_scroll.bind("<Configure>",
                                 lambda e: self._canvas_scroll.itemconfig(
                                     canvas_win, width=e.width))

        self._lbl_status = tk.Label(self, text="Chargement…",
                                    bg="#1a2a18", fg="#aaffaa",
                                    font=("TkFixedFont", 9))
        self._lbl_status.pack(fill=tk.X, padx=8, pady=(2, 6))

        ttk.Button(self, text="Fermer", command=self.destroy).pack(pady=(0, 8))

        threading.Thread(target=self._load_all, daemon=True).start()

    def _load_all(self):
        T    = self.THUMB_SIZE
        cols = self.COLS
        corr = self._corrections

        # Récupérer le rayon de feathering courant pour la preview seam
        try:
            import O4_Color_Normalize as CNORM
            feather_base = CNORM.feathering_mask_radius
        except Exception:
            feather_base = 0

        for i, info in enumerate(self._files):
            self.after(0, lambda i=i, t=len(self._files):
                       self._lbl_status.config(text=f"Chargement {i+1}/{t}…"))
            try:
                img = Image.open(info["path"]).convert("RGB")
            except Exception:
                continue

            orig = img.resize((T, T), Image.BOX)
            arr  = np.array(orig, dtype=np.float32)
            # Charger masque PNG côtier si disponible
            _sea_mask_b = None
            try:
                import O4_Color_Normalize as CNORM
                import O4_File_Names as FNAMES
                _zl_b  = info.get("zl")
                _parts_b = os.path.splitext(info["name"])[0].split("_")
                if len(_parts_b) >= 2:
                    _tx_b = int(_parts_b[0]); _ty_b = int(_parts_b[1])
                    _sea_path_b = os.path.join(
                        self.textures_dir,
                        FNAMES.mask_file(_tx_b, _ty_b, _zl_b, ""))
                    _sea_mask_b = CNORM._load_sea_mask(_sea_path_b, (T, T))
            except Exception:
                pass
            corr_arr = apply_corrections_to_array(arr, corr, sea_mask=_sea_mask_b)
            if corr.get("sharp", 0) > 0:
                corr_img = ImageEnhance.Sharpness(
                    Image.fromarray(corr_arr)
                ).enhance(1.0 + corr["sharp"] / 100.0)
                corr_arr = np.array(corr_img)
            corrected = Image.fromarray(corr_arr)

            # ── Détection seam sur miniature et surlignage orange ─────────
            # Si un seam est détecté ET que le feathering est actif :
            # → surligne la zone de dégradé en orange semi-transparent sur la miniature corrigée
            # → permet de visualiser l'impact du dégradé avant Build
            seam_info = ""
            if feather_base > 0:
                try:
                    arr_t = np.array(orig, dtype=np.float32)
                    seams_t = _detect_seams(arr_t)
                    # Nettoyage morphologique : supprimer composantes isolées < 1% de la principale
                    # (même méthode que FusionPreviewWindow v2.7 → élimine points jaunes parasites)
                    try:
                        from scipy import ndimage as _ndi_b
                        _lbl_b, _num_b = _ndi_b.label(seams_t)
                        if _num_b > 1:
                            _sizes_b = np.array([(_lbl_b == k).sum() for k in range(1, _num_b + 1)])
                            _main_b  = _sizes_b.max()
                            for k, s in enumerate(_sizes_b, 1):
                                if s < _main_b * 0.01:
                                    seams_t[_lbl_b == k] = False
                    except Exception:
                        pass
                    n_seam = int(seams_t.sum())
                    if n_seam >= 3:
                        ys_t, xs_t = np.where(seams_t)
                        cx_t = float(xs_t.mean())
                        cy_t = float(ys_t.mean())
                        horiz_t = (float(ys_t.max() - ys_t.min()) < float(xs_t.max() - xs_t.min()))
                        # Rayon adaptatif sur miniature (proportionnel)
                        r_thumb = max(2, int(feather_base * T / 4096))
                        corr_arr2 = np.array(corrected, dtype=np.float32)
                        if horiz_t:
                            dist = np.abs(np.arange(T, dtype=np.float32) - cy_t)
                            dist2d = dist[:, np.newaxis] * np.ones((1, T), dtype=np.float32)
                        else:
                            dist = np.abs(np.arange(T, dtype=np.float32) - cx_t)
                            dist2d = np.ones((T, 1), dtype=np.float32) * dist[np.newaxis, :]
                        alpha = np.clip(1.0 - dist2d / max(r_thumb, 1), 0.0, 1.0) * 0.45
                        ov = np.zeros_like(corr_arr2)
                        ov[:, :, 0] = 255; ov[:, :, 1] = 130
                        corr_arr2 = np.clip(corr_arr2 * (1 - alpha[:, :, np.newaxis])
                                            + ov * alpha[:, :, np.newaxis], 0, 255)
                        # Ligne jaune sur la seam exacte
                        seam_f = seams_t.astype(np.float32)[:, :, np.newaxis]
                        corr_arr2 = np.clip(
                            corr_arr2 * (1 - seam_f * 0.9)
                            + np.array([255, 255, 0], dtype=np.float32) * seam_f * 0.9, 0, 255)
                        corrected = Image.fromarray(corr_arr2.astype(np.uint8))
                        seam_info = "⚡"  # indicateur seam détectée
                except Exception:
                    pass

            # Combiné : orig gauche / corrigé droite
            combined = Image.new("RGB", (T * 2, T))
            combined.paste(orig,      (0, 0))
            combined.paste(corrected, (T, 0))
            arr_c = np.array(combined)
            arr_c[:, T:T+1, :] = [255, 255, 0]   # séparateur 1px centré
            combined = Image.fromarray(arr_c)

            row = i // cols
            col = i % cols
            name = info["name"]
            # Stocker orig/corr en taille intermédiaire pour le zoom (512px)
            orig_med = img.resize((512, 512), Image.LANCZOS)
            corr_med = Image.fromarray(apply_corrections_to_array(
                np.array(orig_med, dtype=np.float32), corr, sea_mask=_sea_mask_b))
            self._tile_data[name] = (orig_med, corr_med, name)

            self.after(0, lambda combined=combined, row=row, col=col,
                       name=name, si=seam_info: self._place_thumb(combined, row, col, name, si))

        self.after(0, lambda: self._lbl_status.config(
            text=f"✅ {len(self._files)} tuiles — ⚡ = seam détectée (zone orange = dégradé) — clic pour agrandir",
            fg="#aaffaa"))

    def _place_thumb(self, img, row, col, name, seam_info=""):
        frm = tk.Frame(self._inner, bg="#111111", bd=1, relief=RIDGE,
                       cursor="hand2")
        frm.grid(row=row * 2, column=col, padx=2, pady=(2, 0))
        photo = ImageTk.PhotoImage(img)
        self._photos.append(photo)
        lbl = tk.Label(frm, image=photo, bg="#111111", cursor="hand2")
        lbl.pack()
        # Clic → agrandissement
        lbl.bind("<Button-1>", lambda e, n=name: self._open_zoom(n))
        frm.bind("<Button-1>", lambda e, n=name: self._open_zoom(n))
        display_name = f"{seam_info}{name[:22]}" if seam_info else name[:22]
        tk.Label(self._inner, text=display_name, bg="#111111",
                 fg="#ffaa44" if seam_info else "#888888",
                 font=("TkFixedFont", 7),
                 cursor="hand2").grid(row=row * 2 + 1, column=col, padx=2, pady=(0, 4))

    def _open_zoom(self, name):
        """Ouvre une fenêtre agrandie avec zoom/pan pour la tuile cliquée."""
        data = self._tile_data.get(name)
        if not data:
            return
        orig_med, corr_med, fname = data
        BatchZoomWindow(self, orig_med, corr_med, fname)


class BatchZoomWindow(tk.Toplevel):
    """
    Fenêtre d'agrandissement d'une tuile depuis Batch Preview.
    Affiche original (gauche) et corrigé (droite) en grand.
    Zoom molette, pan clic+glisser sur chaque panneau.
    """
    PANEL_W = 600
    PANEL_H = 600

    def __init__(self, parent, orig, corrected, name):
        super().__init__(parent)
        self.title(f"Zoom — {name}")
        self.configure(bg="#0e1e0e")
        self.resizable(True, True)

        self._orig      = np.array(orig, dtype=np.float32)
        self._corr      = np.array(corrected, dtype=np.float32)
        self._zoom      = 1.0
        self._pan_x     = 0.0
        self._pan_y     = 0.0
        self._drag_start = None
        self._photos    = []
        self._pending   = None

        tk.Label(self, text=f"  {name}  —  molette zoom  |  clic+glisser pan",
                 bg="#0e1e0e", fg="#aaffaa",
                 font=("TkFixedFont", 10, "bold")).pack(fill=tk.X, pady=(6, 2))

        hdr = tk.Frame(self, bg="#0e1e0e")
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="ORIGINAL", bg="#0e1e0e", fg="#ffdd88",
                 font=("TkFixedFont", 11, "bold"), width=30).pack(side=LEFT, expand=True)
        tk.Label(hdr, text="CORRIGÉ",  bg="#0e1e0e", fg="#aaffff",
                 font=("TkFixedFont", 11, "bold"), width=30).pack(side=LEFT, expand=True)

        cv_frame = tk.Frame(self, bg="#0e1e0e")
        cv_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self._cv_orig = tk.Canvas(cv_frame, width=self.PANEL_W, height=self.PANEL_H,
                                  bg="#111111", highlightthickness=1,
                                  highlightbackground="#555555")
        self._cv_corr = tk.Canvas(cv_frame, width=self.PANEL_W, height=self.PANEL_H,
                                  bg="#111111", highlightthickness=1,
                                  highlightbackground="#555555")
        self._cv_orig.pack(side=LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))
        self._cv_corr.pack(side=LEFT, fill=tk.BOTH, expand=True)

        for cv in (self._cv_orig, self._cv_corr):
            cv.bind("<ButtonPress-1>",  self._drag_start_cb)
            cv.bind("<B1-Motion>",       self._drag_move_cb)
            cv.bind("<ButtonRelease-1>", self._drag_end_cb)
            cv.bind("<MouseWheel>",      self._wheel_cb)
            cv.bind("<Button-4>",        self._wheel_cb)
            cv.bind("<Button-5>",        self._wheel_cb)
            cv.bind("<Configure>",       lambda e: self._schedule())

        self._lbl_zoom = tk.Label(self, text="×1.0",
                                  bg="#0e1e0e", fg="#aaaaaa",
                                  font=("TkFixedFont", 9))
        self._lbl_zoom.pack(pady=(2, 2))

        bf = tk.Frame(self, bg="#0e1e0e")
        bf.pack(pady=(0, 8))
        ttk.Button(bf, text="↺ Reset zoom", command=self._reset_zoom).pack(side=LEFT, padx=6)
        ttk.Button(bf, text="Fermer",        command=self.destroy).pack(side=LEFT, padx=6)

        self.after(100, self._render)

    def _reset_zoom(self):
        self._zoom  = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._render()

    def _schedule(self):
        if self._pending:
            self.after_cancel(self._pending)
        self._pending = self.after(20, self._render)

    def _wheel_cb(self, event):
        f = 1.2 if (event.num == 4 or event.delta > 0) else 1.0 / 1.2
        self._zoom = max(0.2, min(self._zoom * f, 30.0))
        self._schedule()

    def _drag_start_cb(self, event):
        self._drag_start = (event.x, event.y, self._pan_x, self._pan_y)

    def _drag_move_cb(self, event):
        if not self._drag_start:
            return
        sx, sy, px0, py0 = self._drag_start
        self._pan_x = px0 - (event.x - sx) / self._zoom
        self._pan_y = py0 - (event.y - sy) / self._zoom
        self._schedule()

    def _drag_end_cb(self, event):
        self._drag_start = None

    def _render(self, *_):
        self._lbl_zoom.config(text=f"×{self._zoom:.1f}")
        self._render_panel(self._cv_orig, self._orig)
        self._render_panel(self._cv_corr, self._corr)

    def _render_panel(self, cv, arr):
        H, W = arr.shape[:2]
        cw = cv.winfo_width()  or self.PANEL_W
        ch = cv.winfo_height() or self.PANEL_H
        z  = self._zoom
        cx0 = int(self._pan_x + W / 2.0 - cw / (2.0 * z))
        cy0 = int(self._pan_y + H / 2.0 - ch / (2.0 * z))
        sw  = max(1, min(int(cw / z), W))
        sh  = max(1, min(int(ch / z), H))
        x0  = max(0, min(cx0, W - sw))
        y0  = max(0, min(cy0, H - sh))
        x1  = min(W, x0 + sw)
        y1  = min(H, y0 + sh)
        crop = arr[y0:y1, x0:x1].clip(0, 255).astype(np.uint8)
        pil  = Image.fromarray(crop, mode="RGB")
        out  = pil.resize((cw, ch),
                          Image.NEAREST if z > 4 else Image.BILINEAR)
        photo = ImageTk.PhotoImage(out)
        self._photos.append(photo)
        if len(self._photos) > 8:
            self._photos = self._photos[-8:]
        cv.delete("all")
        cv.create_image(0, 0, anchor=tk.NW, image=photo)
        cv.photo = photo


# ─────────────────────────────────────────────────────────────────
# Utilitaire feathering (preview)
# ─────────────────────────────────────────────────────────────────

def _detect_seams(arr_f, threshold=40):
    """
    Détecte les jointures FRANCHES entre sources dans un tableau HxWx3 float32.
    Retourne un masque booléen (H, W) : True = frontière inter-sources.

    Seuil 40 (vs 25 avant) : ignore les variations de texture normales,
    ne capture que les changements brusques réels entre deux sources.
    Filtre médian 3x3 sur la luminance pour éliminer le bruit pixel.
    """
    # Luminance lissée pour ignorer le bruit de texture
    lum_img = Image.fromarray(
        (0.299 * arr_f[:, :, 0] + 0.587 * arr_f[:, :, 1] + 0.114 * arr_f[:, :, 2]
        ).clip(0, 255).astype(np.uint8), mode="L"
    ).filter(ImageFilter.MedianFilter(3))
    lum = np.array(lum_img, dtype=np.float32)

    gh = np.abs(np.diff(lum, axis=1))
    gv = np.abs(np.diff(lum, axis=0))
    edge = np.zeros(lum.shape, dtype=np.float32)
    edge[:, 1:]  = np.maximum(edge[:, 1:],  gh)
    edge[:, :-1] = np.maximum(edge[:, :-1], gh)
    edge[1:, :]  = np.maximum(edge[1:, :],  gv)
    edge[:-1, :] = np.maximum(edge[:-1, :], gv)
    return edge > threshold


def _apply_feather_preview(pil_img, radius):
    """
    Preview "grains de sable" : montre la DENSITÉ RÉELLE de dispersion
    pixel par pixel sur l'image originale.

    - radius == 0  → image originale seule
    - radius > 0   → points rouges (source A) et bleus (source B) simulant
                     la dispersion exponentielle réelle du Build
                     + ligne blanche sur la jointure exacte

    Plus le radius est grand → plus les grains sont épars et loin de la frontière.
    L'image de fond reste visible → on voit exactement ce qui sera mélangé.
    """
    if radius == 0:
        return pil_img.copy()

    arr = np.array(pil_img.convert("RGB"), dtype=np.float32)
    seams = _detect_seams(arr)
    n = int(seams.sum())

    if n < 3:
        out = arr.copy().astype(np.uint8)
        t = 5
        out[:t, :]  = [220, 100, 0]
        out[-t:, :] = [220, 100, 0]
        out[:, :t]  = [220, 100, 0]
        out[:, -t:] = [220, 100, 0]
        return Image.fromarray(out, mode="RGB")

    # ── Distance signée depuis la jointure ───────────────────────────
    seam_u8   = seams.astype(np.uint8)
    from scipy import ndimage as _ndi
    # Masque binaire : 1 = côté A (pixels lumineux au-dessus de la jointure)
    # Approximation : on utilise la jointure pour séparer les deux régions
    lum = 0.299*arr[:,:,0] + 0.587*arr[:,:,1] + 0.114*arr[:,:,2]
    # Labelliser les deux régions de part et d'autre de la jointure
    seam_dil = _ndi.binary_dilation(seam_u8, iterations=2)
    mask_work = (~seam_dil).astype(np.uint8)
    labels, _ = _ndi.label(mask_work)
    # Région A = label du coin haut-gauche, région B = autre
    lab_A = labels[0, 0] if labels[0, 0] > 0 else 1
    region_A = (labels == lab_A).astype(np.float32)
    # Distance signée : >0 côté A, <0 côté B
    dist_A = _ndi.distance_transform_edt(region_A)
    dist_B = _ndi.distance_transform_edt(1.0 - region_A)
    dist_signed = (dist_A - dist_B).astype(np.float32)

    # ── Probabilité sigmoïde exponentielle (même algo que le Build) ──
    k = np.log(3.0) / max(radius, 1)
    prob_A = (1.0 / (1.0 + np.exp(-k * dist_signed))).astype(np.float32)

    # ── Tirage déterministe pour la preview ──────────────────────────
    rng = np.random.default_rng(42)
    threshold = rng.uniform(0.0, 1.0, arr.shape[:2]).astype(np.float32)
    use_A = threshold < prob_A  # True = grain source A, False = grain B

    # ── Visualisation : points colorés sur image originale ───────────
    # Montrer UNIQUEMENT les pixels de la zone de transition (prob entre 5% et 95%)
    in_transition = (prob_A > 0.05) & (prob_A < 0.95)
    # Sous-échantillonner pour ne pas surcharger (1 grain sur 4)
    show_mask = in_transition & (rng.uniform(0.0, 1.0, arr.shape[:2]) < 0.25)

    out = arr.copy()
    # Grains rouges = pixels qui seront source A dans cette zone
    out[show_mask & use_A]  = [220, 60,  60]   # rouge source A
    # Grains bleus = pixels qui seront source B dans cette zone
    out[show_mask & ~use_A] = [60,  100, 220]  # bleu source B

    # ── Ligne blanche sur la jointure exacte ─────────────────────────
    seam_f = seams.astype(np.float32)[:, :, np.newaxis]
    out = np.clip(
        out * (1.0 - seam_f * 0.7)
        + np.array([255, 255, 180], dtype=np.float32) * seam_f * 0.7,
        0, 255
    ).astype(np.uint8)

    return Image.fromarray(out, mode="RGB")


# ─────────────────────────────────────────────────────────────────
# Fenêtre de preview feathering — Jointure colorimétrique interactive
# ─────────────────────────────────────────────────────────────────

class FusionPreviewWindow(tk.Toplevel):
    """
    Fenêtre "Jointure colorimétrique — déplacez le curseur".

    Image interactive PIL : zoom molette + déplacement clic+glisser.
    Ligne jaune = jointure colorimétrique entre JPG sources (droite traversante).
    Zone orange = zone de dégradé, réactive au curseur 24-200 px.
    Boutons : Appliquer / Build toute la tuile / Fermer.
    """

    CANVAS_W = 880
    CANVAS_H = 620

    def __init__(self, parent, dds_path):
        super().__init__(parent)
        self.title(f"Jointure colorimétrique — {os.path.basename(dds_path)}")
        self.configure(bg="#1a2a20")
        self.resizable(True, True)

        self._parent   = parent
        self._dds_path = dds_path
        self._photos   = []

        # Image et données jointure
        self._arr_full    = None   # numpy float32 pleine résolution
        self._seam_mask   = None   # masque bool pleine résolution
        self._seam_cx     = None   # centre jointure X
        self._seam_cy     = None   # centre jointure Y
        self._seam_horiz  = False  # True = jointure horizontale
        self._mean_A      = None
        self._mean_B      = None

        # Navigation
        self._zoom       = 1.0
        self._pan_x      = 0.0    # décalage depuis centre image (pixels image)
        self._pan_y      = 0.0
        self._drag_start = None
        self._pending    = None
        self._fit_done   = False  # True après le premier fit-to-canvas réel

        self._current_radius = tk.IntVar(value=48)

        # ── UI ──────────────────────────────────────────────────────
        self._lbl_status = tk.Label(self, text="Chargement…",
                                    bg="#1a2a20", fg="#aaffaa",
                                    font=("TkFixedFont", 9))
        self._lbl_status.pack(fill=tk.X, padx=10, pady=(6, 2))

        tk.Label(self, text="Jointure colorimétrique — déplacez le curseur",
                 bg="#1a2a20", fg="#ffdd88",
                 font=("TkFixedFont", 11, "bold")).pack(pady=(0, 2))

        # Canvas image
        self._canvas = tk.Canvas(self,
                                 width=self.CANVAS_W, height=self.CANVAS_H,
                                 bg="#111111", highlightthickness=1,
                                 highlightbackground="#555555")
        self._canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # Bindings — sur canvas ET fenêtre pour Mac
        self._canvas.bind("<ButtonPress-1>",   self._drag_start_cb)
        self._canvas.bind("<B1-Motion>",        self._drag_move_cb)
        self._canvas.bind("<ButtonRelease-1>",  self._drag_end_cb)
        self._canvas.bind("<MouseWheel>",       self._wheel_cb)
        self._canvas.bind("<Button-4>",         self._wheel_cb)
        self._canvas.bind("<Button-5>",         self._wheel_cb)
        self._canvas.bind("<Configure>",        lambda e: self._schedule())
        self.bind("<MouseWheel>",               self._wheel_cb)

        # Colorimétrie
        colbar = tk.Frame(self, bg="#1a2a20")
        colbar.pack(fill=tk.X, padx=10, pady=(4, 0))
        self._lbl_col_A = tk.Label(colbar, text="Source A : —",
                                   bg="#1a2a20", fg="#ff9988",
                                   font=("TkFixedFont", 9), anchor="w")
        self._lbl_col_A.pack(side=tk.LEFT, padx=6)
        self._lbl_col_B = tk.Label(colbar, text="Source B : —",
                                   bg="#1a2a20", fg="#88aaff",
                                   font=("TkFixedFont", 9), anchor="e")
        self._lbl_col_B.pack(side=tk.RIGHT, padx=6)

        # Affichage ΔE et rayons effectifs par ZL
        self._lbl_de = tk.Label(self, text="",
                                bg="#1a2a20", fg="#ffdd88",
                                font=("TkFixedFont", 8), anchor="w")
        self._lbl_de.pack(fill=tk.X, padx=16, pady=(2, 0))
        self._lbl_zl_table = tk.Label(self, text="",
                                      bg="#1a2a20", fg="#888888",
                                      font=("TkFixedFont", 7), anchor="w",
                                      justify="left")
        self._lbl_zl_table.pack(fill=tk.X, padx=16, pady=(0, 2))

        # Curseur
        sf = tk.Frame(self, bg="#1a2a20")
        sf.pack(fill=tk.X, padx=10, pady=(8, 2))
        tk.Label(sf, text="Rayon dégradé :", bg="#1a2a20", fg="#ffdd88",
                 font=("TkFixedFont", 10, "bold")).pack(side=tk.LEFT)
        self._lbl_r = tk.Label(sf, text="48 px", width=10,
                               bg="#1a2a20", fg="#aaffaa",
                               font=("TkFixedFont", 10, "bold"))
        self._lbl_r.pack(side=tk.LEFT, padx=6)
        tk.Scale(sf, from_=24, to=200, orient=tk.HORIZONTAL,
                 variable=self._current_radius,
                 bg="#1a2a20", troughcolor="#003300", fg="#aaffaa",
                 highlightthickness=0, length=500,
                 command=self._on_slider).pack(side=tk.LEFT, fill=tk.X,
                                               expand=True, padx=6)

        # Boutons
        bf = tk.Frame(self, bg="#1a2a20")
        bf.pack(pady=(6, 10))
        ttk.Button(bf, text="✅ Appliquer ce rayon et fermer",
                   command=self._apply).pack(side=tk.LEFT, padx=8)
        ttk.Button(bf, text="🔨 Build avec dégradé (toute la tuile)",
                   command=self._build).pack(side=tk.LEFT, padx=8)
        ttk.Button(bf, text="↺ Vue entière",
                   command=self._reset_fit).pack(side=tk.LEFT, padx=8)
        ttk.Button(bf, text="✖ Fermer sans appliquer",
                   command=self.destroy).pack(side=tk.LEFT, padx=8)

        import threading
        threading.Thread(target=self._compute, daemon=True).start()

    # ── Calcul (thread) ──────────────────────────────────────────────

    def _reset_fit(self):
        """Remet la vue en fit-to-canvas (tuile entière visible)."""
        self._fit_done = False
        self._pan_x    = 0.0
        self._pan_y    = 0.0
        self._schedule()

    def _compute(self):
        try:
            src = Image.open(self._dds_path).convert("RGB")
        except Exception as e:
            self.after(0, lambda: self._lbl_status.config(
                text=f"⚠ {e}", fg="#ff6666"))
            return

        arr = np.array(src, dtype=np.float32)
        H, W = arr.shape[:2]

        # Réduction preview à 1024px max : suffisant pour voir les jointures,
        # beaucoup plus léger pour le zoom/pan interactif
        PREV_MAX = 1024
        if max(H, W) > PREV_MAX:
            scale_prev = PREV_MAX / max(H, W)
            pw, ph = max(1, int(W * scale_prev)), max(1, int(H * scale_prev))
            arr = np.array(src.resize((pw, ph), Image.BOX), dtype=np.float32)
            H, W = arr.shape[:2]

        self._arr_full = arr

        self.after(0, lambda: self._lbl_status.config(text="Détection jointure…"))

        # Détection sur thumbnail 512px max
        TMAX  = 512
        scale = min(1.0, TMAX / max(H, W))
        tw, th = max(1, int(W * scale)), max(1, int(H * scale))
        arr_t = np.array(src.resize((tw, th), Image.BOX), dtype=np.float32)
        seam_t = _detect_seams(arr_t)

        # Remonter à pleine résolution
        if scale < 1.0:
            si = Image.fromarray(seam_t.astype(np.uint8) * 255, mode="L")
            seam_full = np.array(si.resize((W, H), Image.NEAREST)) > 127
        else:
            seam_full = seam_t

        # ── Nettoyage morphologique du masque seam ────────────────────────
        # Le masque brut contient des milliers de points épars sur toute l'image
        # (bruit de texture). On ne conserve que la composante principale (la vraie
        # ligne de jointure) en supprimant toutes les composantes de moins de 50px.
        try:
            from scipy import ndimage as _ndi_clean
            labeled, n_comp = _ndi_clean.label(seam_full)
            if n_comp > 1:
                comp_sizes = _ndi_clean.sum(seam_full, labeled, range(1, n_comp + 1))
                # Garder uniquement les composantes ≥ 1% de la plus grande
                max_size = max(comp_sizes)
                min_keep = max(50, max_size * 0.01)
                keep_labels = [i + 1 for i, s in enumerate(comp_sizes) if s >= min_keep]
                seam_clean = np.zeros_like(seam_full, dtype=bool)
                for lbl in keep_labels:
                    seam_clean |= (labeled == lbl)
                seam_full = seam_clean
        except Exception:
            pass  # Si scipy absent, on garde le masque brut
        # ──────────────────────────────────────────────────────────────────

        self._seam_mask = seam_full

        # Ramener le masque seam à l'échelle de _arr_full (qui peut être réduit à 1024px)
        H_full, W_full = self._arr_full.shape[:2]
        if seam_full.shape != (H_full, W_full):
            si_resize = Image.fromarray(seam_full.astype(np.uint8) * 255, mode="L")
            seam_display = np.array(
                si_resize.resize((W_full, H_full), Image.NEAREST)) > 127
        else:
            seam_display = seam_full

        # Centre et orientation jointure — dans l'espace _arr_full (1024px)
        ys, xs = np.where(seam_display)
        n = int(seam_display.sum())
        if n > 0:
            self._seam_cx    = float(xs.mean())
            self._seam_cy    = float(ys.mean())
            span_x = float(xs.max() - xs.min())
            span_y = float(ys.max() - ys.min())
            self._seam_horiz = span_y < span_x

        # Vue initiale : tuile ENTIÈRE visible dans le canvas (zoom adapté)
        # Pan centré sur l'image, zoom calculé pour afficher toute la tuile
        self._pan_x = 0.0
        self._pan_y = 0.0
        # Le zoom initial sera recalculé au premier _render() selon la taille canvas réelle

        # Colorimétrie A/B — sur _arr_full (1024px) avec seam_display même échelle
        from scipy import ndimage as _ndi2
        dil = _ndi2.binary_dilation(seam_display, iterations=4)
        mw  = (~dil).astype(np.uint8)
        lab, _ = _ndi2.label(mw)
        la  = lab[0, 0] if lab[0, 0] > 0 else 1
        sA  = (lab == la)
        sB  = (lab > 0) & (~sA)
        self._mean_A = arr[sA].mean(axis=0) if sA.sum() > 10 else arr.mean(axis=(0,1))
        self._mean_B = arr[sB].mean(axis=0) if sB.sum() > 10 else arr.mean(axis=(0,1))

        mA, mB = self._mean_A, self._mean_B
        self.after(0, lambda: self._lbl_col_A.config(
            text=f"Source A : R={mA[0]:.0f}  G={mA[1]:.0f}  B={mA[2]:.0f}"))
        self.after(0, lambda: self._lbl_col_B.config(
            text=f"Source B : R={mB[0]:.0f}  G={mB[1]:.0f}  B={mB[2]:.0f}"))

        # ΔE colorimétrique entre les deux sources + conseils
        de = float(np.mean(np.abs(mA - mB)))
        if de < 10:
            de_conseil = "faible — dégradé standard suffisant"
            de_color = "#aaffaa"
        elif de < 25:
            de_conseil = "modéré — dégradé 64-96 px recommandé"
            de_color = "#ffdd88"
        elif de < 50:
            de_conseil = "fort — augmentez le rayon ou générez un .comb seam"
            de_color = "#ffaa44"
        else:
            de_conseil = "très fort — seam critique, .comb seam obligatoire"
            de_color = "#ff6666"
        self.after(0, lambda: self._lbl_de.config(
            text=f"ΔE colorimétrique : {de:.0f}  →  {de_conseil}",
            fg=de_color))

        # Table des rayons effectifs par ZL
        try:
            import O4_Color_Normalize as CNORM
            base = CNORM.feathering_mask_radius
            if base > 0:
                parts = [f"Rayons effectifs (base {base}px) :"]
                for zl in (13, 14, 15, 16, 17, 18, 19, 20):
                    r = CNORM.get_effective_feather_radius(zl)
                    # Estimation rayon avec boost ΔE
                    if de >= 50:
                        boost = 2.0 if zl < 18 else 1.4
                    elif de >= 30:
                        boost = 1.7 if zl < 18 else 1.3
                    elif de >= 15:
                        boost = 1.3 if zl < 18 else 1.15
                    else:
                        boost = 1.0
                    r_adapted = int(r * boost)
                    extra = f" → {r_adapted}px (avec ΔE boost)" if r_adapted != r else ""
                    parts.append(f"  ZL{zl} : {r}px{extra}")
                zl_txt = "  |  ".join(parts[:1]) + "\n" + "  ".join(parts[1:5]) + "\n" + "  ".join(parts[5:])
            else:
                zl_txt = "Dégradé OFF — activez un rayon pour voir la table ZL"
            self.after(0, lambda t=zl_txt: self._lbl_zl_table.config(text=t))
        except Exception:
            pass

        self.after(0, lambda: self._lbl_status.config(
            text=f"{n} px de jointure — glissez / zoomez l'image",
            fg="#aaffaa"))
        self.after(0, self._render)

    # ── Rendu PIL (pas de canvas natif pour le zoom) ─────────────────

    def _render(self, fast=False, *_):
        """Rendu canvas. fast=True pendant drag : pas d'overlay orange, NEAREST."""
        if self._arr_full is None:
            return

        arr  = self._arr_full
        H, W = arr.shape[:2]
        radius = int(self._current_radius.get())

        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()

        # ── Fit-to-canvas : une seule fois, quand le canvas a sa vraie taille ──
        # On attend que cw/ch soient réels (>100px) pour calculer le zoom initial.
        # Sans ce test, winfo_width() retourne 1 ou CANVAS_W fictif → zoom trop petit.
        if not self._fit_done:
            if cw > 100 and ch > 100:
                self._zoom     = max(0.05, min(cw / max(W, 1), ch / max(H, 1)))
                self._pan_x    = 0.0
                self._pan_y    = 0.0
                self._fit_done = True
            else:
                # Canvas pas encore rendu → replanifier dans 80ms
                self.after(80, self._render)
                return
        # ────────────────────────────────────────────────────────────────────────

        if cw < 2:
            cw = self.CANVAS_W
        if ch < 2:
            ch = self.CANVAS_H

        z   = self._zoom
        # Pan libre : pas de blocage aux bords — fond noir si hors image
        cx0 = int(self._pan_x + W / 2.0 - cw / (2.0 * z))
        cy0 = int(self._pan_y + H / 2.0 - ch / (2.0 * z))
        # Taille de la fenêtre en pixels-image (clampée pour éviter buffers immenses)
        sw  = max(1, min(int(cw / z) + 1, W + 2))
        sh  = max(1, min(int(ch / z) + 1, H + 2))

        # Région source dans l'image (clampée aux bords)
        sx0 = max(0, cx0);          sy0 = max(0, cy0)
        sx1 = min(W, cx0 + sw);     sy1 = min(H, cy0 + sh)
        # Offset de destination dans le canvas (où coller le crop)
        dx  = max(0, -cx0);         dy  = max(0, -cy0)

        # Canvas de sortie fond noir
        out_arr = np.zeros((sh, sw, 3), dtype=np.uint8)
        if sx1 > sx0 and sy1 > sy0:
            patch = arr[sy0:sy1, sx0:sx1].clip(0, 255).astype(np.uint8)
            out_arr[dy:dy + (sy1 - sy0), dx:dx + (sx1 - sx0)] = patch

        # Pour l'overlay orange on garde les vraies coordonnées image
        x0, y0, x1, y1 = sx0, sy0, sx1, sy1
        crop = out_arr

        # Zone orange : uniquement en rendu complet (pas pendant drag)
        if not fast and radius > 0 and self._seam_cx is not None:
            # Coordonnées jointure dans l'espace canvas (out_arr sw x sh)
            seam_cx_local = self._seam_cx - cx0
            seam_cy_local = self._seam_cy - cy0
            if self._seam_horiz:
                dist = np.abs(np.arange(sh, dtype=np.float32) - seam_cy_local)
                dist2d = dist[:, np.newaxis] * np.ones((1, sw), dtype=np.float32)
            else:
                dist = np.abs(np.arange(sw, dtype=np.float32) - seam_cx_local)
                dist2d = np.ones((sh, 1), dtype=np.float32) * dist[np.newaxis, :]
            alpha = np.clip(1.0 - dist2d / max(radius, 1), 0.0, 1.0)
            blend = alpha[:, :, np.newaxis] * 0.50
            ov = np.zeros_like(crop, dtype=np.float32)
            ov[:, :, 0] = 255
            ov[:, :, 1] = 130
            crop = np.clip(crop.astype(np.float32) * (1 - blend) + ov * blend, 0, 255).astype(np.uint8)

        # Resize : NEAREST pendant drag (rapide), BILINEAR sinon
        pil_crop = Image.fromarray(crop.astype(np.uint8), mode="RGB")
        interp   = Image.NEAREST if (fast or z > 4) else Image.BILINEAR
        out      = pil_crop.resize((cw, ch), interp)

        photo = ImageTk.PhotoImage(out)
        self._photos.append(photo)
        if len(self._photos) > 4:
            self._photos = self._photos[-4:]
        self._canvas.delete("all")
        self._canvas.create_image(0, 0, anchor=tk.NW, image=photo)
        self._canvas.photo = photo
        self._lbl_r.config(text=f"{radius} px  ×{z:.1f}")

    def _schedule(self, fast=False):
        """Planifie un rendu. fast=True pendant drag : délai 8ms sans overlay."""
        if self._pending:
            self.after_cancel(self._pending)
        delay = 8 if fast else 25
        self._pending = self.after(delay, lambda: self._render(fast=fast))

    # ── Interactions ─────────────────────────────────────────────────

    def _on_slider(self, val):
        self._lbl_r.config(text=f"{int(float(val))} px")
        self._schedule()

    def _wheel_cb(self, event):
        f = 1.15 if (event.num == 4 or event.delta > 0) else 1.0 / 1.15
        # Zoom minimum = fit-to-canvas (calculé dynamiquement) pour toujours
        # pouvoir revenir à la vue tuile entière par dézoom molette
        if self._arr_full is not None:
            H, W = self._arr_full.shape[:2]
            cw = self._canvas.winfo_width() or self.CANVAS_W
            ch = self._canvas.winfo_height() or self.CANVAS_H
            z_fit = max(0.01, min(cw / max(W, 1), ch / max(H, 1)))
        else:
            z_fit = 0.05
        self._zoom = max(z_fit, min(self._zoom * f, 20.0))
        self._schedule()

    def _drag_start_cb(self, event):
        self._canvas.focus_set()
        self._drag_start = (event.x, event.y, self._pan_x, self._pan_y)

    def _drag_move_cb(self, event):
        if not self._drag_start:
            return
        sx, sy, px0, py0 = self._drag_start
        self._pan_x = px0 - (event.x - sx) / self._zoom
        self._pan_y = py0 - (event.y - sy) / self._zoom
        self._schedule(fast=True)   # rendu rapide sans overlay pendant le drag

    def _drag_end_cb(self, event):
        self._drag_start = None
        self._schedule(fast=False)  # rendu complet avec overlay dès relâchement souris

    # ── Appliquer / Build ────────────────────────────────────────────

    def _apply(self):
        radius = int(self._current_radius.get())
        try:
            import O4_Color_Normalize as CNORM
            CNORM.set_feathering_mask_radius(radius)
        except Exception:
            pass
        self._parent._feather_var.set(str(radius))
        self._parent._set_feathering(radius)
        self._parent.status.config(
            text=f"✅ Rayon {radius} px sélectionné — prêt pour Build")
        self.destroy()

    def _build(self):
        radius = int(self._current_radius.get())
        try:
            import O4_Color_Normalize as CNORM
            CNORM.set_feathering_mask_radius(radius)
            if hasattr(CNORM, 'feather_tile_borders'):
                CNORM.feather_tile_borders = True
        except Exception:
            pass
        self._parent._feather_var.set(str(radius))
        self._parent._set_feathering(radius)

        textures_dir = self._parent.textures_dir
        deleted = []
        try:
            for f in os.listdir(textures_dir):
                if f.lower().endswith(".dds"):
                    try:
                        os.remove(os.path.join(textures_dir, f))
                        deleted.append(f)
                    except Exception:
                        pass
        except Exception as e:
            self._parent.status.config(text=f"⚠ Erreur : {e}")
            return

        self._parent.status.config(
            text=f"🔨 Build {radius} px — {len(deleted)} DDS supprimés…")
        try:
            self._parent.master.build_tile()
        except Exception as e:
            self._parent.status.config(text=f"⚠ Erreur Build : {e}")
            return
        try:
            import O4_Color_Normalize as CNORM
            CNORM.set_feathering_mask_radius(24)
        except Exception:
            pass
        self._parent._scan()
        self.destroy()
# ─────────────────────────────────────────────────────────────────
# Point d'entrée
# ─────────────────────────────────────────────────────────────────

def open_color_check(parent, textures_dir, tile_info=None):
    ColorCheckWindow(parent, textures_dir, tile_info)
