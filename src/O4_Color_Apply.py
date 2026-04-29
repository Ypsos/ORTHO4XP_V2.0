#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
O4_Color_Apply.py  —  ORTHO4XP V2  (Avril 2026)
================================================
v1.1 — Correction apply_ccorr_jpg() (Roland/Ypsos, Avril 2026) :
  • apply_ccorr_jpg() cherchait le .ccorr dans jpg_dir (dossier source JPG)
    alors qu'il est sauvegardé dans textures_dir de la tuile.
    → Recherche multi-dossiers : jpg_dir, puis ../textures/, puis fallback.
    → La fonction est maintenant réellement active dans le flux
      combine_textures() via O4_Imagery_Utils.py.

Deux fonctions principales appelées depuis O4_Imagery_Utils.convert_texture() :

  1. apply_ccorr()      — Applique les corrections Color Check (.ccorr) sur le
                          PNG assemblé, APRÈS combine_textures() et Color Normalize.

  2. apply_ccorr_jpg()  — Applique les corrections Color Check sur chaque JPG source
                          AVANT assemblage, dans combine_textures().

  3. apply_feathering() — Détecte les bords nets (jointures entre sources JPG
                          différentes) dans l'image assemblée et applique un
                          fondu progressif (feathering) sur une largeur variable.
                          Fonction en réserve — le grain de sable d'Imagery_Utils
                          est le système principal de feathering.

Ordre d'appel dans combine_textures() (par JPG source) :
    normalize_if_enabled(jpg)
    → apply_ccorr_jpg(jpg)
    → composite + grain de sable
    → apply_ccorr(assembled)
    → DDS

Le JPG source n'est JAMAIS modifié.
"""

import os
import json
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

# ═══════════════════════════════════════════════════════════════════
#  CONFIGURATION GLOBALE
#  Toutes les valeurs ajustables sont ici, en un seul endroit.
# ═══════════════════════════════════════════════════════════════════

# ── Corrections Color Check ────────────────────────────────────────
CORRECTIONS_FILE          = "color_corrections.ccorr"
color_check_apply_enabled = True   # False = désactive sans toucher au code

# ── Fondu de bords (feathering) ────────────────────────────────────
feathering_enabled        = True   # False = désactive le fondu

# Largeur du fondu de chaque côté de la jointure, en pixels (sur 4096x4096).
# Valeurs typiques : 48 (fin), 96 (moyen), 128 (large), 256 (très large).
# Peut être surchargé par la GUI Color Check via feathering_width_override.
FEATHERING_WIDTH_DEFAULT  = 140
feathering_width_override = None
FEATHERING_EDGE_THRESHOLD = 20

# Mode de fondu :
#   "linear"   — transition linéaire simple (rapide)
#   "cosine"   — transition en cosinus (plus douce, recommandée)
#   "gaussian" — flou gaussien progressif (le plus naturel)
FEATHERING_MODE           = "cosine"

# Adaptation automatique de la largeur selon l'écart colorimétrique détecté.
# Si l'écart dépasse AUTO_SCALE_THRESHOLD, la largeur est élargie
# jusqu'à AUTO_SCALE_MAX pixels.
FEATHERING_AUTO_SCALE     = True
AUTO_SCALE_THRESHOLD      = 40    # écart moyen RGB (0-255) pour déclencher
AUTO_SCALE_FACTOR         = 1.5   # multiplicateur si grand écart
AUTO_SCALE_MAX            = 256   # largeur maximale absolue (px)


# ═══════════════════════════════════════════════════════════════════
#  PARTIE I — CORRECTIONS COLOR CHECK
# ═══════════════════════════════════════════════════════════════════

def _load_corrections(textures_dir):
    """Charge le fichier .ccorr depuis le dossier textures de la tuile."""
    path = os.path.join(textures_dir, CORRECTIONS_FILE)
    if os.path.isfile(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"[O4_Color_Apply] Impossible de lire {path} : {e}")
    return {}


def _apply_corrections_to_array(arr, corr):
    """
    Applique un dict de corrections sur un tableau HxWx3 float32.
    Retourne un tableau HxWx3 uint8.
    """
    arr = arr.copy()

    # Décalage / luminosité / contraste par canal
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
        gray   = (r_orig + g_orig + b_orig) / 3.0
        if sr != 0.0:
            arr[:, :, 0] = np.clip(gray + (r_orig - gray) * (1.0 + sr), 0, 255)
        if sg != 0.0:
            arr[:, :, 1] = np.clip(gray + (g_orig - gray) * (1.0 + sg), 0, 255)
        if sb != 0.0:
            arr[:, :, 2] = np.clip(gray + (b_orig - gray) * (1.0 + sb), 0, 255)

    return np.clip(arr, 0, 255).astype(np.uint8)


def apply_ccorr(big_image, dds_name, textures_dir, sea_mask_path=None):
    """
    Applique les corrections Color Check sur big_image (PIL RGB/RGBA).

    Paramètres
    ----------
    big_image    : PIL.Image  — image assemblée (RGB ou RGBA)
    dds_name     : str        — nom du fichier DDS (ex: "46624_67024_BI17.dds")
    textures_dir : str        — chemin du dossier textures de la tuile
    sea_mask_path: str|None   — chemin masque PNG Ortho4XP — pixels mer non corrigés

    Retourne PIL.Image corrigée, ou big_image inchangée si pas de correction.
    """
    if not color_check_apply_enabled:
        return big_image

    corrections = _load_corrections(textures_dir)
    if not corrections:
        return big_image

    basename = os.path.basename(dds_name)
    corr = corrections.get(basename)
    if not corr:
        return big_image

    has_alpha = big_image.mode == "RGBA"
    rgb_img   = big_image.convert("RGB") if has_alpha else big_image
    arr_orig  = np.array(rgb_img, dtype=np.float32)

    arr           = arr_orig.copy()
    corrected_arr = _apply_corrections_to_array(arr, corr)
    corrected     = Image.fromarray(corrected_arr, mode="RGB")

    sharp = corr.get("sharp", 0)
    if sharp > 0:
        corrected = ImageEnhance.Sharpness(corrected).enhance(1.0 + sharp / 100.0)

    # Masque mer : restaurer pixels eau à l'original — protège OrthoLitto/zones côtières
    if sea_mask_path and os.path.isfile(sea_mask_path):
        try:
            _mask_img = Image.open(sea_mask_path).convert("L").resize(
                corrected.size, Image.BOX)
            _sea = np.array(_mask_img, dtype=np.float32) / 255.0  # 0=mer 1=terre
            _arr_c = np.array(corrected, dtype=np.float32)
            for _ch in range(3):
                _arr_c[:, :, _ch] = (_sea * _arr_c[:, :, _ch]
                                     + (1.0 - _sea) * arr_orig[:, :, _ch])
            corrected = Image.fromarray(_arr_c.astype(np.uint8), mode="RGB")
        except Exception:
            pass

    if has_alpha:
        corrected = corrected.convert("RGBA")
        _, _, _, a_orig = big_image.split()
        corrected.putalpha(a_orig)

    print(f"[O4_Color_Apply] ccorr → {basename}  "
          f"dr={corr.get('dr',0):+d} dg={corr.get('dg',0):+d} "
          f"db={corr.get('db',0):+d}  "
          f"sat_r={corr.get('sat_r',0):+d} sat_g={corr.get('sat_g',0):+d} "
          f"sat_b={corr.get('sat_b',0):+d}  sharp={corr.get('sharp',0)}")
    return corrected


def apply_ccorr_jpg(img, jpg_name, jpg_dir, zl=None):
    """
    Applique les corrections Color Check sur un JPG individuel AVANT assemblage.
    Appelé depuis combine_textures() après normalize_if_enabled(), sur chaque
    JPG source — même point d'interception que Color Normalize.

    jpg_name : str   — nom du fichier JPG (ex: "15_22305_14729.jpg")
    jpg_dir  : str   — dossier contenant le JPG source
    zl       : int   — zoom level (pour force adaptative par ZL)

    Force : ZL13-16 pleine (×1.0), ZL17 modérée (×0.70), ZL18+ légère (×0.15).
    La clé JPG dans le .ccorr est sauvegardée par Color Check dans textures_dir.

    Recherche du .ccorr :
      1. jpg_dir (dossier du JPG source) — correction locale
      2. Dossier parent de jpg_dir + "textures/" — emplacement standard tuile
      3. jpg_dir/../textures/ — fallback si structure non standard
    """
    if not color_check_apply_enabled:
        return img

    # Recherche du .ccorr : le fichier est sauvegardé dans textures_dir de la tuile,
    # pas dans jpg_dir (dossier source des JPG). On essaie plusieurs emplacements.
    corrections = {}
    for candidate_dir in [
        jpg_dir,
        os.path.join(os.path.dirname(jpg_dir), "textures"),
        os.path.join(jpg_dir, "..", "textures"),
    ]:
        candidate_dir = os.path.normpath(candidate_dir)
        corrections = _load_corrections(candidate_dir)
        if corrections:
            break

    if not corrections:
        return img

    basename = os.path.basename(jpg_name)
    corr = corrections.get(basename)
    if not corr:
        return img

    # Force adaptative par ZL
    zl_int = int(zl) if zl else 16
    if zl_int >= 18:
        zl_strength = 0.15
    elif zl_int == 17:
        zl_strength = 0.70
    else:
        zl_strength = 1.0

    corr_scaled = {}
    for k, v in corr.items():
        if k == "sharp":
            corr_scaled[k] = v if zl_int < 18 else 0
        elif isinstance(v, (int, float)):
            corr_scaled[k] = v * zl_strength
        else:
            corr_scaled[k] = v

    has_alpha = img.mode == "RGBA"
    rgb_img   = img.convert("RGB") if has_alpha else img
    arr           = np.array(rgb_img, dtype=np.float32)
    corrected_arr = _apply_corrections_to_array(arr, corr_scaled)
    corrected     = Image.fromarray(corrected_arr, mode="RGB")

    sharp = corr.get("sharp", 0)
    if sharp > 0 and zl_int < 18:
        corrected = ImageEnhance.Sharpness(corrected).enhance(1.0 + sharp / 100.0)

    if has_alpha:
        corrected = corrected.convert("RGBA")
        _, _, _, a_orig = img.split()
        corrected.putalpha(a_orig)

    print(f"[O4_Color_Apply] ccorr_jpg ZL{zl_int} (×{zl_strength:.2f}) → {basename}  "
          f"dr={corr.get('dr',0):+d} dg={corr.get('dg',0):+d} db={corr.get('db',0):+d}")
    return corrected

def _get_feathering_width():
    """Retourne la largeur effective du fondu."""
    if feathering_width_override is not None:
        return int(feathering_width_override)
    return int(FEATHERING_WIDTH_DEFAULT)


def _build_transition_ramp(n, mode):
    """
    Construit un vecteur 1D de poids [0.0 … 1.0] de longueur n.
    0.0 = bord de jointure, 1.0 = zone stable.
    """
    t = np.linspace(0.0, 1.0, n, dtype=np.float32)
    if mode == "linear":
        return t
    elif mode == "cosine":
        return ((1.0 - np.cos(np.pi * t)) / 2.0).astype(np.float32)
    else:  # gaussian
        sigma = n / 3.0
        g = np.exp(-0.5 * ((np.arange(n, dtype=np.float32) - n) / sigma) ** 2)
        return (g / g.max()).astype(np.float32)


def _detect_seam_mask(arr_f, threshold):
    """
    Détecte les bords nets (jointures entre sources) dans l'image.
    Calcule le gradient de la luminance — les zones de fort gradient
    correspondent aux jointures entre sources différentes.

    Retourne un masque booléen (H, W) : True = jointure.
    """
    lum = (0.299 * arr_f[:, :, 0] +
           0.587 * arr_f[:, :, 1] +
           0.114 * arr_f[:, :, 2])

    grad_h = np.abs(np.diff(lum, axis=1))
    grad_v = np.abs(np.diff(lum, axis=0))

    edge_h = np.zeros(lum.shape, dtype=np.float32)
    edge_v = np.zeros(lum.shape, dtype=np.float32)
    edge_h[:, 1:]  = grad_h
    edge_h[:, :-1] = np.maximum(edge_h[:, :-1], grad_h)
    edge_v[1:, :]  = grad_v
    edge_v[:-1, :] = np.maximum(edge_v[:-1, :], grad_v)

    return np.maximum(edge_h, edge_v) > threshold


def _measure_color_gap(arr_f, seam_mask, sample_width=8):
    """
    Mesure l'écart colorimétrique moyen de part et d'autre des jointures.
    Utilisé pour l'adaptation automatique de la largeur du fondu.
    """
    rows, cols = np.where(seam_mask)
    if len(rows) == 0:
        return 0.0

    step = max(1, len(rows) // 500)
    rows = rows[::step]
    cols = cols[::step]
    H, W = arr_f.shape[:2]

    diffs = []
    for r, c in zip(rows, cols):
        c0 = max(0, c - sample_width)
        c1 = min(W - 1, c + sample_width)
        if c0 == c1:
            continue
        diffs.append(np.mean(np.abs(arr_f[r, c0, :3] - arr_f[r, c1, :3])))

    return float(np.mean(diffs)) if diffs else 0.0


def _build_feather_weight_map(seam_mask, width, mode):
    """
    Construit une carte de poids (H, W) ∈ [0, 1] :
      - 0.0 sur les jointures exactes  → fondu maximal
      - 1.0 loin des jointures          → pixel inchangé

    Méthode : on diffuse le masque de jointure par flou gaussien,
    puis on applique la rampe de transition choisie.
    """
    seam_u8  = (seam_mask.astype(np.float32) * 255).astype(np.uint8)
    seam_pil = Image.fromarray(seam_u8, mode="L")

    blur_r   = max(4, int(width * 0.65))
    blurred  = np.array(
        seam_pil.filter(ImageFilter.GaussianBlur(radius=blur_r)),
        dtype=np.float32
    ) / 255.0   # 0 = loin, 1 = jointure

    # Construction de la rampe indexée par distance normalisée
    ramp = _build_transition_ramp(256, mode)
    idx  = np.clip((blurred * 255).astype(np.int32), 0, 255)

    # weight = 1 - influence : proche jointure → faible poids (fondu fort)
    weight_map = ramp[idx].astype(np.float32)
    return weight_map


def _apply_feather_blend(arr_f, weight_map, width):
    """
    Mélange chaque pixel avec la version floutée de son voisinage.
    weight_map = 1 → pixel inchangé
    weight_map = 0 → pixel remplacé par la valeur moyennée locale
    """
    pil_img  = Image.fromarray(np.clip(arr_f, 0, 255).astype(np.uint8), mode="RGB")
    blur_r   = max(4, width // 2)
    blurred  = np.array(
        pil_img.filter(ImageFilter.GaussianBlur(radius=blur_r)),
        dtype=np.float32
    )
    w       = weight_map[:, :, np.newaxis]   # broadcast sur les 3 canaux
    blended = w * arr_f + (1.0 - w) * blurred
    return np.clip(blended, 0, 255).astype(np.uint8)


def apply_feathering(big_image):
    """
    Détecte les jointures nettes entre sources dans big_image et applique
    un fondu progressif (feathering) de largeur variable.

    Largeur pilotable :
      • FEATHERING_WIDTH_DEFAULT  (valeur dans ce fichier)
      • feathering_width_override (surchargé depuis la GUI Color Check)
      • adapté automatiquement si FEATHERING_AUTO_SCALE = True

    Modes de transition : "linear", "cosine" (défaut), "gaussian"

    Paramètres
    ----------
    big_image : PIL.Image  — image assemblée RGB ou RGBA

    Retourne PIL.Image avec jointures adoucies, ou big_image inchangée
    si fondu désactivé ou aucune jointure détectée.
    """
    if not feathering_enabled:
        return big_image

    has_alpha = big_image.mode == "RGBA"
    rgb_img   = big_image.convert("RGB") if has_alpha else big_image
    arr_f     = np.array(rgb_img, dtype=np.float32)

    # ── 1. Détection des jointures ───────────────────────────────
    seam_mask = _detect_seam_mask(arr_f, FEATHERING_EDGE_THRESHOLD)
    n_seam    = int(seam_mask.sum())

    if n_seam < 10:
        # Aucune jointure significative — image d'une seule source
        return big_image

    # ── 2. Adaptation automatique de la largeur ──────────────────
    width = _get_feathering_width()
    if FEATHERING_AUTO_SCALE:
        gap = _measure_color_gap(arr_f, seam_mask)
        if gap > AUTO_SCALE_THRESHOLD:
            scale = min(
                AUTO_SCALE_FACTOR * (gap / AUTO_SCALE_THRESHOLD),
                AUTO_SCALE_MAX / max(width, 1)
            )
            width = int(min(width * scale, AUTO_SCALE_MAX))
        print(f"[O4_Color_Apply] feathering — {n_seam} px de jointure  "
              f"écart moy={gap:.1f}  largeur fondu={width} px  mode={FEATHERING_MODE}")
    else:
        print(f"[O4_Color_Apply] feathering — {n_seam} px de jointure  "
              f"largeur={width} px  mode={FEATHERING_MODE}")

    # ── 3. Carte de poids ────────────────────────────────────────
    weight_map = _build_feather_weight_map(seam_mask, width, FEATHERING_MODE)

    # ── 4. Application du fondu ──────────────────────────────────
    result_arr = _apply_feather_blend(arr_f, weight_map, width)
    result     = Image.fromarray(result_arr, mode="RGB")

    if has_alpha:
        result = result.convert("RGBA")
        _, _, _, a_orig = big_image.split()
        result.putalpha(a_orig)

    return result


# ═══════════════════════════════════════════════════════════════════
#  API publique — pilotage depuis la GUI Color Check
# ═══════════════════════════════════════════════════════════════════

def set_feathering_width(px):
    """
    Surcharge la largeur du fondu depuis la GUI Color Check.
    Valeurs utiles : 48, 96, 128, 256.
    Passer None pour revenir à FEATHERING_WIDTH_DEFAULT.
    """
    global feathering_width_override
    feathering_width_override = int(px) if px is not None else None


def set_feathering_enabled(state):
    """Active (True) ou désactive (False) le fondu depuis la GUI."""
    global feathering_enabled
    feathering_enabled = bool(state)


def set_color_check_enabled(state):
    """Active (True) ou désactive (False) les corrections .ccorr."""
    global color_check_apply_enabled
    color_check_apply_enabled = bool(state)
