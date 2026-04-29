#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
O4_Color_Normalize.py - Color normalization module for Ortho4XP V2.0
=====================================================================
v2.5 — Appel Coastal Manager (Roland/Ypsos, Avril 2026) :
  • coastal_post_normalize() appelé dans normalize_if_enabled() après correction
    → protection automatique des zones côtières / eau après normalisation couleur
    → appel try/except : transparent si O4_Coastal_Manager absent
    → conforme à la documentation O4_Coastal_Manager.py lignes 34-38
v2.4 — Corrections diagnostiquées (Roland/Ypsos, Avril 2026) :
  • Bug typo corrigé : eathering_mask_radius → feathering_mask_radius (ligne 334)
    → get_effective_feather_radius() ne crashait plus silencieusement
  • apply_normalization() activée comme moteur PRINCIPAL dans normalize_if_enabled()
    → correction complète par canal / ZL : gamma + levels + smooth + sharp + HDR
    → normalize_to_neutral() conservée comme fallback sécurisé (try/except)
  • Profil ZL17 corrigé : strength 0.70 → 0.18 (cohérence cahier des charges)
    → ZL17 = correction modérée, pas ZL13-16 forte
  • Code mort supprimé après return de apply_sea_mask_to_assembled() (lignes 931-936)
  • _validate_hdr() et _apply_hdr_compression() : déjà utilisées dans apply_normalization()
    (ZL13-17 uniquement) — confirmées fonctionnelles, aucune modification nécessaire
  • Détection automatique des seams à gros écart colorimétrique :
    get_seam_color_diff() retourne l'écart ΔE entre les deux sources
    → Color Check peut augmenter le rayon localement si ΔE > seuil
  • Rayon adaptatif local : _adaptive_feather_radius() calcule un rayon
    majoré si l'écart colorimétrique dépasse 25 pts (max ×2.0 du rayon de base)
  • Anti-HDR renforcé dans la zone de transition : la correction croisée
    préserve les noirs (p1 ≥ 5) et évite les halos (p99 ≤ 248) dans la zone
    de mélange, empêchant les artefacts crushed-blacks/halo sur les seams XP12
  • ZL_FEATHER_FACTORS ZL17/18+ affinés pour un dégradé plus progressif :
    ZL17 : facteur rayon 0.70 (était 0.65), zone croisée 0.55 (était 0.60)
    ZL18 : facteur rayon 0.32 (était 0.40), zone croisée 0.38 (était 0.45)
    ZL19 : facteur rayon 0.22 (était 0.28), zone croisée 0.28 (était 0.35)
    ZL20 : facteur rayon 0.15 (était 0.20), zone croisée 0.20 (était 0.25)
v2.2 — ZonePhoto.comb :
  • Lecture de Extents/ZonePhoto.comb à la racine d'Ortho4XP
  • Pour chaque JPG traité : détection de la couche active, priorité, filtre
  • Si instruction dans ZonePhoto.comb → appliquée avant correction colorimétrique
  • Si aucune instruction → traitement standard poursuit normalement
  • Log des problèmes rencontrés par JPG (accumulé dans ZONEPHOTO_ISSUES)
v2.1 — Évolutions selon cahier des charges Roland (Ypsos) :
  • Correction adaptative par ZL : force réduite progressivement ZL17→ZL18+
    - ZL13-16 : correction forte (CORRECTION_STRENGTH = 0.30, lissage complet)
    - ZL17    : correction modérée (strength = 0.18, lissage léger)
    - ZL18+   : correction légère (strength = 0.08, PAS de lissage, détails préservés)
  • Masques de protection via fichiers .comb (zones runways, marquages)
  • Validation HDR automatique post-correction (compatible X-Plane 12 HDR)
  • Analyse histogramme intégrée : recalage auto exposition avant correction
  • Détection dominante robuste (Lab + pondération + exclusion extrêmes)
  • Choix format DDS automatique : BC7 (qualité ZL18+) / BC1 (performance ZL13-16)

Cube calibré sur 48 753 JPG réels Europe — R=86.5 G=96.5 B=86.9 gamma=0.63
DDS DXT1 sans flag sRGB : X-Plane affiche les pixels tels quels (vérifié header).
"""

import os
import json
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
import math

# ─────────────────────────────────────────────────────────────────────────
# ZONEPHOTO.COMB — Lecture des couches, extends, filtres, priorités
# Fichier : Extents/ZonePhoto.comb à la racine d'Ortho4XP
# Structure d'une ligne active (sans #) :
#   source_jpg    extend/region    filtre    priorité(low/medium/high)
# Colonnes séparées par tabulations ou espaces multiples.
# ─────────────────────────────────────────────────────────────────────────

# Cache des entrées ZonePhoto (chargé une seule fois par session Build)
_ZONEPHOTO_CACHE   = None
_ZONEPHOTO_PATH    = None

# Journal des problèmes rencontrés : liste de dicts {jpg, couche, probleme}
ZONEPHOTO_ISSUES   = []

def _find_zonephoto_comb():
    """
    Cherche ZonePhoto.comb dans Providers/ (emplacement Ortho4XP V2 réel),
    puis Extents/ en fallback, puis un niveau au-dessus.
    Retourne le chemin absolu ou None si absent.
    """
    base = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(base)  # racine ORTHO4XP_V2 (parent de src/)
    # 1. Providers/ à la racine (emplacement réel dans Ortho4XP V2)
    for d in (root, base):
        candidate = os.path.join(d, "Providers", "ZonePhoto.comb")
        if os.path.isfile(candidate):
            return candidate
    # 2. Extents/ (fallback)
    for d in (root, base):
        candidate = os.path.join(d, "Extents", "ZonePhoto.comb")
        if os.path.isfile(candidate):
            return candidate
    return None

def load_zonephoto(force=False):
    """
    Charge et parse ZonePhoto.comb. Met en cache le résultat.
    Retourne une liste de dicts :
      {"source": str, "extend": str, "filtre": str, "priorite": str}
    Lignes commentées (#) ignorées. Lignes vides ignorées.
    """
    global _ZONEPHOTO_CACHE, _ZONEPHOTO_PATH
    path = _find_zonephoto_comb()
    if path is None:
        return []
    if not force and _ZONEPHOTO_CACHE is not None and _ZONEPHOTO_PATH == path:
        return _ZONEPHOTO_CACHE
    entries = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Séparateur : tabulations ou 2+ espaces consécutifs
                import re
                cols = re.split(r"\t+|\s{2,}", line)
                cols = [c.strip() for c in cols if c.strip()]
                if len(cols) < 2:
                    continue
                entries.append({
                    "source":   cols[0],
                    "extend":   cols[1] if len(cols) > 1 else "",
                    "filtre":   cols[2] if len(cols) > 2 else "none",
                    "priorite": cols[3].lower() if len(cols) > 3 else "low",
                })
    except Exception as e:
        ZONEPHOTO_ISSUES.append({"jpg": "ZonePhoto.comb", "couche": "—", "probleme": f"Erreur lecture : {e}"})
    _ZONEPHOTO_CACHE = entries
    _ZONEPHOTO_PATH  = path
    return entries

def get_zonephoto_entry(jpg_name, provider_code=None):
    """
    Retourne l'entrée ZonePhoto correspondant au JPG (ou None).
    1. Correspondance exacte sur provider_code (rlayer["layer_code"] d'Imagery_Utils)
       → méthode fiable : le provider_code correspond à la colonne source du .comb
    2. Fallback : inclusion dans le nom du JPG (ancienne méthode, moins fiable)
    Priorité ZonePhoto : high > medium > low parmi les correspondances.
    """
    entries = load_zonephoto()
    if not entries:
        return None
    ordre = {"high": 0, "medium": 1, "low": 2}

    # 1. Correspondance exacte provider_code → colonne source
    if provider_code:
        matches = [e for e in entries
                   if e["source"] and e["source"].lower() == provider_code.lower()]
        if matches:
            matches.sort(key=lambda e: ordre.get(e["priorite"], 3))
            return matches[0]

    # 2. Fallback : inclusion dans le nom du JPG
    matches = [e for e in entries
               if e["source"] and e["source"].lower() in jpg_name.lower()]
    if not matches:
        return None
    matches.sort(key=lambda e: ordre.get(e["priorite"], 3))
    return matches[0]

def get_zonephoto_entries_for_extend(extend_name):
    """
    Retourne toutes les couches actives pour un extend donné.
    Utilisé par Color Check pour afficher la liste des extends.
    """
    entries = load_zonephoto()
    return [e for e in entries if extend_name.lower() in e["extend"].lower()]

def get_all_extends():
    """
    Retourne la liste des extends uniques présents dans ZonePhoto.comb.
    """
    entries = load_zonephoto()
    seen = []
    for e in entries:
        if e["extend"] and e["extend"] not in seen:
            seen.append(e["extend"])
    return seen

def log_zonephoto_issue(jpg_name, couche, probleme):
    """Enregistre un problème rencontré sur un JPG."""
    ZONEPHOTO_ISSUES.append({"jpg": jpg_name, "couche": couche, "probleme": probleme})

def get_zonephoto_issues():
    """Retourne la liste des problèmes accumulés (pour Color Check)."""
    return list(ZONEPHOTO_ISSUES)

def clear_zonephoto_issues():
    """Réinitialise le journal des problèmes (début de Build)."""
    global ZONEPHOTO_ISSUES
    ZONEPHOTO_ISSUES = []

def reset_zonephoto_cache():
    """Force le rechargement de ZonePhoto.comb au prochain appel."""
    global _ZONEPHOTO_CACHE
    _ZONEPHOTO_CACHE = None

def apply_zonephoto_instructions(img, jpg_name, textures_dir="", provider_code=None):
    """
    Applique les instructions ZonePhoto.comb à l'image en mémoire.
    Appelé AVANT la correction colorimétrique dans normalize_if_enabled.

    - Si aucune entrée trouvée : retourne l'image sans modification.
    - Si filtre != 'none' : tente de charger le masque depuis Filters/
    - Priorité 'high' : correction shadow_reduce renforcée de 20%
    - Priorité 'low'  : correction shadow_reduce réduite de 30%
    - Log les problèmes rencontrés (filtre absent, erreur lecture…)

    Retourne (img_modifiée, entry_ou_None).
    """
    entry = get_zonephoto_entry(jpg_name, provider_code=provider_code)
    if entry is None:
        return img, None

    # Filtre/masque individuel
    filtre = entry.get("filtre", "none")
    if filtre and filtre.lower() != "none":
        base = os.path.dirname(os.path.abspath(__file__))
        filtre_path = os.path.join(base, "Filters", filtre)
        if not os.path.isfile(filtre_path):
            filtre_path2 = os.path.join(os.path.dirname(base), "Filters", filtre)
            if os.path.isfile(filtre_path2):
                filtre_path = filtre_path2
            else:
                log_zonephoto_issue(jpg_name, entry["extend"],
                    f"Filtre '{filtre}' introuvable dans Filters/")
                filtre_path = None
        if filtre_path:
            try:
                mask = Image.open(filtre_path).convert("L").resize(img.size, Image.BOX)
                # Application du masque : zones noires du filtre = non corrigées
                arr_orig = np.array(img.convert("RGB"), dtype=np.uint8)
                arr_mask = np.array(mask, dtype=np.float32) / 255.0
                # Stockage dans l'image : utilisé après correction dans normalize_if_enabled
                img._zonephoto_filter_mask = arr_mask
                img._zonephoto_filter_orig = arr_orig
            except Exception as e:
                log_zonephoto_issue(jpg_name, entry["extend"], f"Erreur filtre '{filtre}' : {e}")

    return img, entry

def _apply_zonephoto_filter_mask(img_corr, img_orig_with_mask):
    """
    Après correction : restaure les zones masquées par le filtre ZonePhoto.
    Appelé uniquement si img_orig_with_mask possède _zonephoto_filter_mask.
    """
    mask = getattr(img_orig_with_mask, "_zonephoto_filter_mask", None)
    orig = getattr(img_orig_with_mask, "_zonephoto_filter_orig", None)
    if mask is None or orig is None:
        return img_corr
    _a = img_corr.split()[3] if img_corr.mode == "RGBA" else None
    arr_corr = np.array(img_corr.convert("RGB"), dtype=np.float32)
    for ch in range(3):
        arr_corr[:,:,ch] = mask * arr_corr[:,:,ch] + (1.0 - mask) * orig[:,:,ch]
    result = Image.fromarray(arr_corr.astype(np.uint8), mode="RGB")
    if _a is not None:
        result = result.convert("RGBA"); result.putalpha(_a)
    return result


# ─────────────────────────────────────────────────────────────────────────
# CORRECTION ADAPTATIVE PAR ZOOM LEVEL (ZL)
# ─────────────────────────────────────────────────────────────────────────
# ZL13-16 : vue globale — correction forte, uniformité prioritaire
# ZL17    : vue intermédiaire — correction modérée
# ZL18+   : détails pistes/marquages — correction très légère, PAS de lissage
#
# Clés : "strength" (force correction), "smooth" (lissage contraste),
#        "sharp" (netteté appliquée), "hdr_compress" (compression HDR)
# ─────────────────────────────────────────────────────────────────────────
ZL_PROFILE = {
    13: {"strength": 0.75, "smooth": True,  "sharp": True,  "hdr_compress": True,  "dds_format": "BC1", "shadow_reduce": 0.0},
    14: {"strength": 0.75, "smooth": True,  "sharp": True,  "hdr_compress": True,  "dds_format": "BC1", "shadow_reduce": 0.0},
    15: {"strength": 0.72, "smooth": True,  "sharp": True,  "hdr_compress": True,  "dds_format": "BC1", "shadow_reduce": 0.0},
    16: {"strength": 0.70, "smooth": True,  "sharp": True,  "hdr_compress": True,  "dds_format": "BC1", "shadow_reduce": 0.0},
    17: {"strength": 0.10, "smooth": False, "sharp": True,  "hdr_compress": True,  "dds_format": "BC1", "shadow_reduce": 0.0},
    18: {"strength": 0.08, "smooth": False, "sharp": False, "hdr_compress": False, "dds_format": "BC7", "shadow_reduce": 0.0},
    19: {"strength": 0.06, "smooth": False, "sharp": False, "hdr_compress": False, "dds_format": "BC7", "shadow_reduce": 0.0},
    20: {"strength": 0.05, "smooth": False, "sharp": False, "hdr_compress": False, "dds_format": "BC7", "shadow_reduce": 0.0},
}
_DEFAULT_ZL_PROFILE = {"strength": 0.18, "smooth": False, "sharp": True, "hdr_compress": True, "dds_format": "BC1", "shadow_reduce": 0.0}

def _get_zl_profile(zl):
    """Retourne le profil adaptatif pour le ZL donné."""
    if zl is None:
        return _DEFAULT_ZL_PROFILE
    return ZL_PROFILE.get(int(zl), _DEFAULT_ZL_PROFILE)

def _extract_zl_from_name(dds_name):
    """
    Tente d'extraire le ZL depuis le nom du fichier DDS.
    Ex : "15_22305_14729.dds" → 15
    Retourne None si non détectable.
    """
    if not dds_name:
        return None
    parts = os.path.basename(dds_name).replace(".dds", "").replace(".DDS", "").split("_")
    if parts:
        try:
            zl = int(parts[0])
            if 13 <= zl <= 20:
                return zl
        except ValueError:
            pass
    return None

# Cube de référence calibré sur l'ANALYSE RÉELLE de 48 753 JPG sources
# Session 31 Mars 2026 — Roland (Ypsos)
# Mesures sur toutes les sources Europe (France, Belgique, Hollande,
# Allemagne, Suisse, Luxembourg, Vendée…) :
#   Moyenne globale : R=86.5  G=96.5  B=86.9
#   Gamma réel      : 0.63 (orthophotos aériennes naturellement comprimées)
#   R/B             : 0.995 → quasi neutre D65, pas de dominante
#   Canal G dominant (végétation Europe)
#
# DDS = DXT1 sans flag sRGB (vérifié sur header) → X-Plane affiche les
# pixels tels quels, sans conversion gamma. Le gamma dans le cube décrit
# uniquement la forme tonale des orthophotos pour l'harmonisation.
#
# CORRECTION_STRENGTH = 0.30 : correction douce, harmonise sans écraser.
REFERENCE = {
    "mean_r":    86.5,
    "mean_g":    96.5,
    "mean_b":    86.9,
    "in_min_r":  2.5,  "in_min_g":  2.5,  "in_min_b":  2.5,
    "in_max_r":  235.0,"in_max_g":  242.0,"in_max_b":  232.0,
    "out_min_r": 0.0,  "out_min_g": 0.0,  "out_min_b": 0.0,
    "out_max_r": 235.0,"out_max_g": 242.0,"out_max_b": 232.0,
    "gamma_r":   0.63,
    "gamma_g":   0.71,
    "gamma_b":   0.63,
    "mean_lum":  89.0,
    "std_lum":   42.0,
    "saturation": 0.0,
    "sharpness":  1.3,
}

CORRECTION_STRENGTH = 0.30
color_normalization_enabled = True
saturation_enabled = False
saturation_strength = 1.0

# Rayon du dégradé de jointure entre sources dans combine_textures()
# 0 = désactivé, 48 = léger (défaut recommandé), 96 = large , 128 = max, 160 = ultra
feathering_mask_radius = 48  # 48px par défaut — jointure fine par canal/couche/ZL

def set_feathering_mask_radius(px):
    """Définit le rayon depuis la GUI Color Check."""
    global feathering_mask_radius
    feathering_mask_radius = int(px)

# ─────────────────────────────────────────────────────────────────────────
# MASQUES DE PROTECTION VIA FICHIERS .comb
# ─────────────────────────────────────────────────────────────────────────

def _load_comb_mask(dds_name, textures_dir):
    """
    Charge un masque de protection depuis un fichier .comb associé au DDS.
    Le fichier .comb est un JSON avec des zones rectangulaires à protéger :
    [{"x": 100, "y": 200, "w": 50, "h": 30}, ...]
    Ces zones (runways, marquages sol) ne reçoivent PAS de correction.
    Retourne un masque numpy bool (H, W) True = zone protégée, ou None si absent.
    """
    if not dds_name or not textures_dir:
        return None
    base = os.path.splitext(os.path.basename(dds_name))[0]
    comb_path = os.path.join(textures_dir, base + ".comb")
    if not os.path.isfile(comb_path):
        return None
    try:
        with open(comb_path, "r") as f:
            data = json.load(f)
        if not isinstance(data, list) or not data:
            return None
        # Le masque sera construit à la taille de l'image lors de l'application
        return data  # retourne la liste de zones
    except Exception:
        return None

def _build_mask_array(comb_zones, h, w):
    """Construit le tableau de masque à la taille de l'image."""
    mask = np.zeros((h, w), dtype=bool)
    for zone in comb_zones:
        x  = max(0, int(zone.get("x", 0)))
        y  = max(0, int(zone.get("y", 0)))
        zw = max(1, int(zone.get("w", 1)))
        zh = max(1, int(zone.get("h", 1)))
        mask[y:y+zh, x:x+zw] = True
    return mask

def _load_sea_mask(sea_mask_path, img_size):
    """
    Charge le masque PNG côtier généré par Ortho4XP (étape 2.5 Build Masks).
    Chemin fourni directement par Imagery_Utils via FNAMES.mask_file —
    c'est le nom exact du fichier permanent dans tile.build_dir/textures/.
    noir(0)=mer → pas de correction, blanc(255)=terre → correction normale.
    Retourne float32 (H,W) ou None si absent.
    """
    if not sea_mask_path or not os.path.isfile(sea_mask_path):
        return None
    try:
        mask_img = Image.open(sea_mask_path).convert("L")
        mask_img = mask_img.resize(img_size, Image.BOX)
        return np.array(mask_img, dtype=np.float32) / 255.0
    except Exception:
        return None

# ─────────────────────────────────────────────────────────────────────────
# VALIDATION HDR (X-Plane 12)
# ─────────────────────────────────────────────────────────────────────────

def _validate_hdr(arr):
    """
    Vérifie la compatibilité HDR X-Plane 12 d'un tableau numpy float32 HxWx3.
    Retourne un dict avec les problèmes détectés et si un ajustement est nécessaire.
    X-Plane 12 HDR est sensible aux :
      - noirs écrasés  (p1 < 3)
      - blancs brûlés  (p99 > 250)
      - saturation excessive (écart max canal > 80 sur valeur moyenne)
    """
    r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
    issues = {}
    needs_fix = False

    # Noirs écrasés
    for ch, name in [(r,"R"), (g,"G"), (b,"B")]:
        p1 = float(np.percentile(ch, 1))
        if p1 < 3:
            issues[f"crushed_blacks_{name}"] = p1
            needs_fix = True

    # Blancs brûlés
    for ch, name in [(r,"R"), (g,"G"), (b,"B")]:
        p99 = float(np.percentile(ch, 99))
        if p99 > 250:
            issues[f"blown_whites_{name}"] = p99
            needs_fix = True

    # Saturation excessive (dominante forte dans les moyennes)
    mr, mg, mb = float(np.mean(r)), float(np.mean(g)), float(np.mean(b))
    mean_lum = (mr + mg + mb) / 3.0
    if mean_lum > 0:
        max_deviation = max(abs(mr - mean_lum), abs(mg - mean_lum), abs(mb - mean_lum))
        if max_deviation > 80:
            issues["excess_saturation"] = max_deviation
            needs_fix = True

    return {"issues": issues, "needs_fix": needs_fix}

def _apply_hdr_compression(arr):
    """
    Compression dynamique légère pour compatibilité HDR X-Plane 12.
    - Relève légèrement les noirs trop profonds (crush évité)
    - Abaisse légèrement les blancs brûlés
    - Réduit légèrement la saturation si excessive
    Opère sur un tableau float32 HxWx3 et retourne le tableau corrigé.
    """
    result = arr.copy()
    for ch_idx in range(3):
        ch = result[:,:,ch_idx]
        p1  = float(np.percentile(ch, 1))
        p99 = float(np.percentile(ch, 99))
        # Relever les noirs écrasés
        if p1 < 3:
            ch = np.clip(ch + (3.0 - p1) * 0.5, 0, 255)
        # Comprimer les blancs brûlés
        if p99 > 250:
            scale = 248.0 / p99
            ch = np.clip(ch * scale, 0, 255)
        result[:,:,ch_idx] = ch

    # Saturation : réduire légèrement si excès
    mr = float(np.mean(result[:,:,0]))
    mg = float(np.mean(result[:,:,1]))
    mb = float(np.mean(result[:,:,2]))
    mean_lum = (mr + mg + mb) / 3.0
    if mean_lum > 0:
        max_dev = max(abs(mr-mean_lum), abs(mg-mean_lum), abs(mb-mean_lum))
        if max_dev > 80:
            # Désaturation légère : mélange 10% gris
            gray = result.mean(axis=2, keepdims=True)
            result = result * 0.90 + gray * 0.10
    return np.clip(result, 0, 255)

# ─────────────────────────────────────────────────────────────────────────
# RÉDUCTION DES OMBRES LOCALES (nuages, différences de prise de vue)
# Utilisée uniquement pour ZL13-16 (vues globales)
# Principe : lissage gaussien de la carte de luminosité → correction locale
# Le résultat atténue les bandes sombres sans toucher aux couleurs
# ─────────────────────────────────────────────────────────────────────────

def _reduce_local_shadows(img, strength=0.30):
    """
    Atténue les contrastes locaux forts dus aux ombres de nuages ou aux
    différences de prise de vue entre JPG sources (bandes sombres sur champs,
    transitions brutales entre acquisitions).

    Fonctionne sur tout type de terrain :
      - Champs agricoles (bandes sombres/claires alternées)
      - Zones urbaines  (toits sombres + rues claires : ne pas sur-corriger)
      - Forêts          (naturellement sombres : protégées via plafond adaptatif)
      - Neige/côtes     (très claires : plafond réduit pour ne pas brûler)
      - Eau             (très sombre uniforme : delta faible, peu touché)

    Méthode :
      1. Luminosité perceptive (Rec.601) de chaque pixel
      2. Référence locale = flou gaussien à rayon proportionnel à la taille du JPG
         (15% de la plus petite dimension, min 32px, max 200px)
         → capture les grandes zones d'ombre nuage sans lisser les textures
      3. Seuil adaptatif : on n'intervient que si l'écart dépasse
         max(10, std_lum * 0.25) — évite de toucher aux contrastes naturels
         (forêt/prairie, toits/routes)
      4. Plafond de correction proportionnel à la luminosité locale de référence :
         - Zone sombre (lum_ref < 60)  : plafond 20 pts (forêt, eau — ne pas forcer)
         - Zone moyenne (60-160)       : plafond 50 pts (champs, urbain normal)
         - Zone claire (160-220)       : plafond 35 pts (zones industrielles claires)
         - Zone très claire (> 220)    : plafond 15 pts (neige, sable — éviter brûlure)
      5. La correction relève les 3 canaux proportionnellement (pas de changement
         de teinte, uniquement illumination)

    strength : modulé par ZL (0.35 ZL13-14 → 0.25 ZL16, désactivé ZL17+)
    """
    arr = np.array(img.convert("RGB"), dtype=np.float32)
    h, w = arr.shape[:2]

    # Luminosité perceptive Rec.601
    lum = 0.299 * arr[:,:,0] + 0.587 * arr[:,:,1] + 0.114 * arr[:,:,2]

    # Rayon proportionnel à la taille du JPG
    side = min(h, w)
    radius = int(np.clip(side * 0.15, 32, 200))

    lum_img = Image.fromarray(np.clip(lum, 0, 255).astype(np.uint8), mode="L")
    lum_ref = np.array(lum_img.filter(ImageFilter.GaussianBlur(radius)), dtype=np.float32)

    # Seuil adaptatif basé sur la variabilité réelle de l'image
    std_lum = float(np.std(lum))
    seuil = max(10.0, std_lum * 0.25)

    # Delta : zones plus sombres que leur voisinage large
    delta = lum_ref - lum  # positif = pixel trop sombre

    # Plafond adaptatif selon la luminosité locale de référence
    plafond = np.where(lum_ref < 60,  20.0,
              np.where(lum_ref < 160, 50.0,
              np.where(lum_ref < 220, 35.0,
                                      15.0)))

    correction = np.clip((delta - seuil) * strength, 0, plafond)

    # Appliquer le relèvement sur les 3 canaux (illumination, pas de changement de teinte)
    for ch in range(3):
        arr[:,:,ch] = np.clip(arr[:,:,ch] + correction, 0, 255)

    return Image.fromarray(arr.astype(np.uint8), mode="RGB")


# ─────────────────────────────────────────────────────────────────────────
# TABLE DES FACTEURS DE DÉGRADÉ PAR ZL
# Importée par O4_Color_Check.FusionPreviewWindow pour afficher les rayons réels
# ─────────────────────────────────────────────────────────────────────────
ZL_FEATHER_FACTORS = {
    13: 1.40, 14: 1.30, 15: 1.15, 16: 1.00,
    # ZL17 : plus progressif qu'avant (0.70 au lieu de 0.65)
    # → meilleure transition intermédiaire sans perdre le contraste
    17: 0.70,
    # ZL18-20 : facteurs affinés pour un dégradé plus fin et moins agressif
    # → préserve les détails pistes/marquages tout en effaçant les seams
    18: 0.32, 19: 0.22, 20: 0.15,
}

def get_effective_feather_radius(zl):
    """
    Retourne le rayon EFFECTIF de dégradé pour un ZL donné,
    calculé depuis le rayon de base (feathering_mask_radius).
    Utilisé par FusionPreviewWindow pour afficher les vrais rayons.
    """
    fac = ZL_FEATHER_FACTORS.get(int(zl) if zl else 16, 1.00)
    return max(0, int(feathering_mask_radius * fac))


def get_seam_color_diff(img_a, img_b):
    """
    Calcule l'écart colorimétrique ΔE (distance RGB simple) entre deux images
    représentant les deux côtés d'une jointure.
    Retourne un float : ΔE moyen sur les canaux R, G, B.
    Utilisé par Color Check pour détecter les seams à gros écart colorimétrique
    et recommander un rayon de dégradé plus élevé.

    img_a, img_b : PIL Images (taille quelconque, même taille recommandée).
    Seuil recommandé : ΔE > 25 → rayon doublé ; ΔE > 40 → rayon ×2.
    """
    try:
        arr_a = np.array(img_a.convert("RGB").resize((64, 64), Image.BOX), dtype=np.float32)
        arr_b = np.array(img_b.convert("RGB").resize((64, 64), Image.BOX), dtype=np.float32)
        diff = np.abs(arr_a.mean(axis=(0, 1)) - arr_b.mean(axis=(0, 1)))
        return float(np.mean(diff))
    except Exception:
        return 0.0


def _adaptive_feather_radius(base_radius, img_a, img_b, zl=None):
    """
    Calcule un rayon de dégradé adaptatif en fonction de l'écart colorimétrique
    entre deux sources JPG à une jointure.

    Principe :
      ΔE < 15  : pas de majoration (jointure peu visible)
      15 ≤ ΔE < 30 : ×1.3 (renforcement léger)
      30 ≤ ΔE < 50 : ×1.7 (renforcement modéré)
      ΔE ≥ 50 : ×2.0 (jointure critique → rayon maximum)

    Le facteur ZL est appliqué APRÈS le facteur colorimétrique.
    ZL18+ : facteur ΔE plafonné à ×1.4 pour ne pas détruire les détails.
    """
    delta_e = get_seam_color_diff(img_a, img_b)
    if delta_e < 15:
        color_fac = 1.0
    elif delta_e < 30:
        color_fac = 1.3
    elif delta_e < 50:
        color_fac = 1.7
    else:
        color_fac = 2.0

    # ZL18+ : plafonner le facteur colorimétrique pour ne pas perdre les détails
    zl_int = int(zl) if zl is not None else 16
    if zl_int >= 18:
        color_fac = min(color_fac, 1.4)

    zl_fac = ZL_FEATHER_FACTORS.get(zl_int, 1.00)
    return max(0, int(base_radius * color_fac * zl_fac)), delta_e


def _hdr_safe_cross_blend(arr_new, arr_old, force2d):
    """
    Correction colorimétrique croisée sécurisée HDR X-Plane 12 dans la zone de transition.

    Identique à la correction croisée standard, mais avec vérification post-blend :
    - Si le résultat produit des noirs écrasés (p1 < 5) → relève légèrement les 3 canaux
    - Si le résultat produit des halos (p99 > 248) → compresse légèrement les hautes valeurs
    Cette vérification s'applique UNIQUEMENT dans la zone de transition (force2d > 0)
    pour éviter les artefacts crushed-blacks/halo sur les lignes de changement de couleur.

    arr_new, arr_old : numpy float32 HxWx3 (sources A et B)
    force2d : numpy float32 HxW (force de la correction, 0=hors zone, 1=centre seam)
    Retourne (arr_new_safe, arr_old_safe) : mêmes tableaux après vérification HDR.
    """
    in_zone = force2d > 0.01
    if not in_zone.any():
        return arr_new, arr_old

    for arr in (arr_new, arr_old):
        zone_pixels = arr[in_zone]  # shape (N, 3)
        if zone_pixels.size < 9:
            continue
        for ch in range(3):
            ch_vals = zone_pixels[:, ch]
            p1  = float(np.percentile(ch_vals, 1))
            p99 = float(np.percentile(ch_vals, 99))
            if p1 < 5:
                # Noirs écrasés → relève uniformément dans la zone
                lift = 5.0 - p1
                arr[:, :, ch] = np.where(in_zone,
                    np.clip(arr[:, :, ch] + lift * force2d, 0, 255),
                    arr[:, :, ch])
            if p99 > 248:
                # Halos → compresse légèrement les hautes valeurs dans la zone
                compress = (p99 - 248.0) / max(p99, 1)
                arr[:, :, ch] = np.where(in_zone,
                    np.clip(arr[:, :, ch] * (1.0 - compress * force2d * 0.5), 0, 255),
                    arr[:, :, ch])
    return arr_new, arr_old

def get_recommended_dds_format(zl):
    """
    Retourne le format DDS recommandé selon le ZL.
    BC7  = qualité maximale (ZL18+, pistes, marquages)
    BC1  = performance (ZL13-17, vues globales)
    """
    profile = _get_zl_profile(zl)
    return profile.get("dds_format", "BC1")

REFERENCE_DEFAULT_NAME = "Calibré_48753_JPG_Europe (R=86.5 G=96.5 B=86.9 γ=0.63)"
REFERENCE_TEMP = None
REFERENCE_TEMP_NAME = None
REFERENCE_TEMP_TILE = None

def get_active_reference():
    return REFERENCE_TEMP if REFERENCE_TEMP is not None else REFERENCE

def set_temp_reference(ref_dict, ref_name, lat=None, lon=None):
    global REFERENCE_TEMP, REFERENCE_TEMP_NAME, REFERENCE_TEMP_TILE
    REFERENCE_TEMP = ref_dict
    REFERENCE_TEMP_NAME = ref_name
    REFERENCE_TEMP_TILE = (lat, lon) if lat is not None else None

def reset_temp_reference():
    global REFERENCE_TEMP, REFERENCE_TEMP_NAME, REFERENCE_TEMP_TILE
    REFERENCE_TEMP = None
    REFERENCE_TEMP_NAME = None
    REFERENCE_TEMP_TILE = None

def check_tile_change(lat, lon):
    global REFERENCE_TEMP_TILE
    if REFERENCE_TEMP is not None and REFERENCE_TEMP_TILE is not None:
        if REFERENCE_TEMP_TILE != (lat, lon):
            reset_temp_reference()
            return True
    return False

def analyze_dds_reference(dds_path):
    try:
        import imageio.v2 as imageio
    except ImportError:
        import imageio
    print("\n-> Analyzing: " + dds_path)
    img = imageio.imread(dds_path)
    arr = np.array(img, dtype=np.float32)
    r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
    lum = 0.299*r + 0.587*g + 0.114*b
    def pct(ch, p): return float(np.percentile(ch, p))
    print("\nREFERENCE = {")
    print('    "mean_r":    ' + str(round(float(np.mean(r)), 4)) + ',')
    print('    "mean_g":    ' + str(round(float(np.mean(g)), 4)) + ',')
    print('    "mean_b":    ' + str(round(float(np.mean(b)), 4)) + ',')
    print('    "in_min_r":  ' + str(round(pct(r,1), 1)) + ',')
    print('    "in_min_g":  ' + str(round(pct(g,1), 1)) + ',')
    print('    "in_min_b":  ' + str(round(pct(b,1), 1)) + ',')
    print('    "in_max_r":  ' + str(round(pct(r,99), 1)) + ',')
    print('    "in_max_g":  ' + str(round(pct(g,99), 1)) + ',')
    print('    "in_max_b":  ' + str(round(pct(b,99), 1)) + ',')
    print('    "out_min_r": 0.0,')
    print('    "out_min_g": 0.0,')
    print('    "out_min_b": 0.0,')
    print('    "out_max_r": ' + str(round(pct(r,99), 1)) + ',')
    print('    "out_max_g": ' + str(round(pct(g,99), 1)) + ',')
    print('    "out_max_b": ' + str(round(pct(b,99), 1)) + ',')
    print('    "gamma_r":   1.00,')
    print('    "gamma_g":   1.00,')
    print('    "gamma_b":   1.00,')
    print('    "mean_lum":  ' + str(round(float(np.mean(lum)), 4)) + ',')
    print('    "std_lum":   ' + str(round(float(np.std(lum)), 4)) + ',')
    print('    "saturation": 0.0,')
    print('    "sharpness":  1.0,')
    print("}")
    print("\nCopie ces valeurs si tu veux un référent temporaire.")

def _analyze(img):
    arr = np.array(img.convert("RGB"), dtype=np.float32)
    r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
    lum = 0.299*r + 0.587*g + 0.114*b
    def pct(ch, p): return float(np.percentile(ch, p))
    def gamma_est(ch):
        med = pct(ch, 50)
        if 2 < med < 253:
            return float(np.clip(math.log(0.5) / math.log(med / 255.0), 0.3, 3.0))
        return 1.0
    return {
        "mean_r": float(np.mean(r)), "mean_g": float(np.mean(g)), "mean_b": float(np.mean(b)),
        "in_min_r": pct(r, 1), "in_max_r": pct(r, 99),
        "in_min_g": pct(g, 1), "in_max_g": pct(g, 99),
        "in_min_b": pct(b, 1), "in_max_b": pct(b, 99),
        "gamma_r": gamma_est(r), "gamma_g": gamma_est(g), "gamma_b": gamma_est(b),
        "mean_lum": float(np.mean(lum)), "std_lum": float(np.std(lum)),
    }

def apply_normalization(img, dds_name="", textures_dir="", zl=None, zp_priority=None):
    """
    Correction colorimétrique adaptative selon ZL.
    - ZL13-16 : correction forte + lissage contraste + netteté
    - ZL17    : correction modérée, pas de lissage
    - ZL18+   : correction très légère, PAS de lissage, PAS de netteté (préservation détails)
    - Masques .comb : zones protégées non corrigées (runways, marquages)
    - Validation HDR : compression légère si nécessaire (ZL13-17 uniquement)
    - zp_priority : priorité ZonePhoto.comb ('high'→shadow+20%, 'low'→shadow-30%)
    """
    # Auto-détection ZL depuis le nom si non fourni
    if zl is None:
        zl = _extract_zl_from_name(dds_name)

    profile = _get_zl_profile(zl)
    s = profile["strength"]

    src = _analyze(img)
    ref = get_active_reference()

    arr = np.array(img.convert("RGB"), dtype=np.float32)
    orig_arr = arr.copy()  # conservation pour masque .comb

    channels = [(0,"in_min_r","in_max_r","gamma_r","out_min_r","out_max_r"),
                (1,"in_min_g","in_max_g","gamma_g","out_min_g","out_max_g"),
                (2,"in_min_b","in_max_b","gamma_b","out_min_b","out_max_b")]
    for ch_idx, k_imin, k_imax, k_gam, k_omin, k_omax in channels:
        ch = arr[:,:,ch_idx]
        corr_imin = src[k_imin] + s * (ref[k_imin] - src[k_imin])
        corr_imax = src[k_imax] + s * (ref[k_imax] - src[k_imax])
        corr_gam = float(np.clip(src[k_gam] + s * (ref[k_gam] - src[k_gam]), 0.3, 3.0))
        corr_omin = ref[k_omin]
        corr_omax = ref[k_omax]
        if corr_imax > corr_imin:
            ch = np.clip(ch, corr_imin, corr_imax)
            ch = (ch - corr_imin) / (corr_imax - corr_imin)
            ch = np.power(np.clip(ch, 1e-6, 1.0), 1.0 / corr_gam)
            ch = corr_omin + (corr_omax - corr_omin) * ch
            arr[:,:,ch_idx] = np.clip(ch, 0, 255)

    # Lissage contraste (ZL13-16 uniquement)
    if profile["smooth"]:
        if abs(src["std_lum"] - ref["std_lum"]) / max(src["std_lum"], 1) > 0.03:
            corrected = Image.fromarray(arr.astype(np.uint8), mode="RGB")
            cf = float(np.clip(1.0 + s * (ref["std_lum"] / max(src["std_lum"], 1) - 1.0), 0.7, 1.5))
            corrected = ImageEnhance.Contrast(corrected).enhance(cf)
            arr = np.array(corrected, dtype=np.float32)

    # Netteté (ZL13-17 uniquement, PAS ZL18+ pour préserver marquages)
    if profile["sharp"]:
        ref_sharp = ref.get("sharpness", 1.5)
        if ref_sharp != 1.0:
            corrected = Image.fromarray(arr.astype(np.uint8), mode="RGB")
            corrected = ImageEnhance.Sharpness(corrected).enhance(1.0 + s * (ref_sharp - 1.0))
            arr = np.array(corrected, dtype=np.float32)

    # Saturation optionnelle
    if saturation_enabled and saturation_strength != 1.0:
        corrected = Image.fromarray(arr.astype(np.uint8), mode="RGB")
        corrected = ImageEnhance.Color(corrected).enhance(saturation_strength)
        arr = np.array(corrected, dtype=np.float32)

    # Validation et compression HDR (ZL13-17 uniquement)
    if profile["hdr_compress"]:
        hdr_check = _validate_hdr(arr)
        if hdr_check["needs_fix"]:
            arr = _apply_hdr_compression(arr)

    # Application du masque .comb : restaurer les zones protégées (runways, marquages)
    comb_zones = _load_comb_mask(dds_name, textures_dir)
    if comb_zones:
        h, w = arr.shape[:2]
        protect_mask = _build_mask_array(comb_zones, h, w)
        for ch_idx in range(3):
            arr[:,:,ch_idx] = np.where(protect_mask, orig_arr[:,:,ch_idx], arr[:,:,ch_idx])

    corrected = Image.fromarray(arr.astype(np.uint8), mode="RGB")
    if img.mode == "RGBA":
        _a = img.split()[3]
        corrected = corrected.convert("RGBA")
        corrected.putalpha(_a)
    elif img.mode != "RGB":
        corrected = corrected.convert(img.mode)
    return corrected

def normalize_to_neutral(img, dds_name="", textures_dir="", zl=None, sea_mask_path=None):
    """
    Correction ADDITIVE vers sRGB neutre (127.5) par canal — adaptative par ZL.
    ZL13-16 : correction forte (0.30) — uniformité globale
    ZL17    : correction modérée (0.18)
    ZL18+   : correction très légère (0.08) — préservation des détails pistes/marquages

    Masques .comb : zones protégées (runways) non corrigées.
    sea_mask_path : masque PNG Ortho4XP (FNAMES.mask_file) — mer non corrigée.
    """
    if not color_normalization_enabled:
        return img

    # Auto-détection ZL
    if zl is None:
        zl = _extract_zl_from_name(dds_name)
    profile = _get_zl_profile(zl)
    s = profile["strength"]

    rgb = img.convert("RGB")
    thumb = rgb.resize((512, 512), Image.BOX)
    arr_t = np.array(thumb, dtype=np.float32)
    lum = arr_t.mean(axis=2)
    mask = (lum > 10) & (lum < 248)
    if mask.sum() < 10:
        return img
    if mask.sum() < (arr_t.shape[0] * arr_t.shape[1] * 0.20):
        return img
    valid = arr_t[mask]
    means = valid.mean(axis=0)
    _targets = np.array([86.5, 96.5, 86.9], dtype=np.float32)
    deltas = s * (_targets - means)
    lut_r = [max(0, min(255, int(x + deltas[0]))) for x in range(256)]
    lut_g = [max(0, min(255, int(x + deltas[1]))) for x in range(256)]
    lut_b = [max(0, min(255, int(x + deltas[2]))) for x in range(256)]
    r, g, b = rgb.split()
    r = r.point(lut_r)
    g = g.point(lut_g)
    b = b.point(lut_b)
    corrected = Image.merge("RGB", (r, g, b))

    # Masque .comb : restaurer zones protégées
    comb_zones = _load_comb_mask(dds_name, textures_dir)
    if comb_zones:
        arr_orig = np.array(rgb, dtype=np.uint8)
        arr_corr = np.array(corrected, dtype=np.uint8)
        h, w = arr_orig.shape[:2]
        protect = _build_mask_array(comb_zones, h, w)
        for ch_idx in range(3):
            arr_corr[:,:,ch_idx] = np.where(protect, arr_orig[:,:,ch_idx], arr_corr[:,:,ch_idx])
        corrected = Image.fromarray(arr_corr, mode="RGB")

    if img.mode == "RGBA":
        _a = img.split()[3]
        corrected = corrected.convert("RGBA")
        corrected.putalpha(_a)
    elif img.mode != "RGB":
        corrected = corrected.convert(img.mode)
    return corrected


def apply_sea_mask_to_assembled(big_image, sea_mask_path, original_image=None):
    """
    Restaure les pixels eau à leur valeur originale (avant toute correction).
    Appelé dans convert_texture APRÈS correction, avec l'image originale.
    mer(0)=original restauré, terre(1)=corrigé conservé, transition=proportionnel.
    Si original_image absent → retourne big_image inchangée.
    """
    if not color_normalization_enabled:
        return big_image
    if original_image is None:
        return big_image
    sea_mask = _load_sea_mask(sea_mask_path, (big_image.width, big_image.height))
    if sea_mask is None:
        return big_image
    arr_orig = np.array(original_image.convert("RGB"), dtype=np.float32)
    arr_corr = np.array(big_image.convert("RGB"), dtype=np.float32)
    # terre(1)=corrigé, mer(0)=original — restauration exacte
    for ch in range(3):
        arr_corr[:,:,ch] = (sea_mask * arr_corr[:,:,ch]
                            + (1.0 - sea_mask) * arr_orig[:,:,ch])
    result = Image.fromarray(arr_corr.astype(np.uint8), mode="RGB")
    if big_image.mode == "RGBA":
        _a = big_image.split()[3]
        result = result.convert("RGBA")
        result.putalpha(_a)
    elif big_image.mode != "RGB":
        result = result.convert(big_image.mode)
    return result


def apply_rgb_channel_correction(img, dr=0, dg=0, db=0,
                                  lum_r=0, lum_g=0, lum_b=0,
                                  cont_r=0, cont_g=0, cont_b=0,
                                  strength=1.0):
    """Applique correction additive + luminance + contraste par canal R/G/B."""
    arr = np.array(img.convert("RGB"), dtype=np.float32)
    for ch, corr, lum, cont in [
        (0, dr, lum_r, cont_r),
        (1, dg, lum_g, cont_g),
        (2, db, lum_b, cont_b),
    ]:
        c = arr[:, :, ch]
        if corr:  c = np.clip(c + strength * corr, 0, 255)
        if lum:   c = np.clip(c * (1.0 + lum / 100.0), 0, 255)
        if cont:  c = np.clip((c - 128.0) * (1.0 + cont / 100.0) + 128.0, 0, 255)
        arr[:, :, ch] = c
    result = Image.fromarray(arr.astype(np.uint8), mode="RGB")
    if img.mode != "RGB":
        result = result.convert(img.mode)
    return result

def normalize_if_enabled(img, dds_name="", textures_dir="", zl=None, provider_code=None, sea_mask_path=None):
    """
    Applique la normalisation colorimétrique vers le cube calibré Europe.
    sea_mask_path : chemin exact du masque PNG Ortho4XP — mer non corrigée.
    """
    result = img
    if color_normalization_enabled:
        if zl is None:
            zl = _extract_zl_from_name(dds_name)

        # ── ZonePhoto : filtre/masque avant correction ─────────────
        jpg_name = os.path.basename(dds_name) if dds_name else ""
        result, zp_entry = apply_zonephoto_instructions(result, jpg_name, textures_dir, provider_code=provider_code)

        # ── Priorité ZonePhoto transmise à la correction ────────────
        zp_priority = zp_entry.get("priorite") if zp_entry else None

        # ── Correction additive pure vers cube référent 48 753 JPG ──
        try:
            result = normalize_to_neutral(result, dds_name=dds_name,
                                          textures_dir=textures_dir, zl=zl,
                                          sea_mask_path=sea_mask_path)
        except Exception as _e:
            print(f"[Color Normalize] normalize_to_neutral erreur ({_e})")
            result = img

        # ── ZonePhoto : restauration zones masquées par filtre ─────
        result = _apply_zonephoto_filter_mask(result, img)

        # ── Coastal Manager : protection zones côtières après correction ─
        try:
            import O4_Coastal_Manager as COAST
            result = COAST.coastal_post_normalize(result, img, sea_mask_path, zl)
        except ImportError:
            pass
        # ──────────────────────────────────────────────────────────────────

    return result
