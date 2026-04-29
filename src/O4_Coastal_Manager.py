#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
O4_Coastal_Manager.py — Ortho4XP V2  (Avril 2026)  v2.0
=========================================================
Module autonome de gestion des tuiles côtières.
Chargé par O4_Color_Normalize et O4_Color_Check.
NE MODIFIE AUCUN FICHIER EXISTANT.

PRINCIPE (idée Roland / méthode Jojo) :
  Ortho4XP génère déjà des masques PNG côtiers via blur_mask().
  Mais la transition est trop régulière (convolution chapeau mathématique)
  → bord rectiligne, pas d'effet vague/écume naturel.

  Ce module applique un POST-TRAITEMENT sur chaque PNG côtier
  APRÈS sa sauvegarde par build_masks(), sans toucher à blur_mask() :

  1. Détection du bord côtier (frontière terre/mer dans le PNG)
  2. Irrégularisation du bord par bruit fractal multi-octave
     → ondulations naturelles qui imitent les vagues et l'écume
  3. Gradient d'écume : bande semi-transparente sur le bord côté mer
     → transition douce et réaliste comme dans les masques Jojo
  4. Protection absolue : intérieur terre (255) et eau profonde (0)
     ne sont jamais touchés → seul le bord est modifié

INTÉGRATION (sans modifier aucun fichier existant) :
  Appelé depuis O4_Mask_Utils.build_mask() après mask_im.save() :
      try:
          import O4_Coastal_Manager as COAST
          COAST.post_process_coastal_mask(mask_path, tile)
      except ImportError:
          pass

  Appelé depuis O4_Color_Normalize.normalize_if_enabled() :
      try:
          import O4_Coastal_Manager as COAST
          result = COAST.coastal_post_normalize(result, img, sea_mask_path, zl)
      except ImportError:
          pass

  Panneau "Côtes & Îles" dans O4_Color_Check via build_coastal_info_panel().
"""

import os
import math
import numpy as np
from PIL import Image, ImageFilter
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# PARAMÈTRES DU POST-TRAITEMENT CÔTIER
# ─────────────────────────────────────────────────────────────────────────────

# Largeur de la bande d'écume en pixels (masque ZL15 ≈ 4m/px → 30px ≈ 120m)
ECUME_WIDTH_PX = 0

# Amplitude maximale du bruit en pixels (irrégularité du bord côtier)
NOISE_AMPLITUDE_PX = 0

# Octaves du bruit fractal : (fréquence_spatiale, poids_relatif)
NOISE_OCTAVES = [
    (1/180.0, 0.50),   # grandes ondulations (baies, anses)
    (1/60.0,  0.30),   # ondulations moyennes
    (1/20.0,  0.15),   # petites irrégularités
    (1/7.0,   0.05),   # micro-textures (écume)
]

# Seuil de détection côtière (ratio pixels eau dans le masque)
COASTAL_THRESHOLD = 0.04

# Caches
_coastal_cache   = {}
_mask_arr_cache  = {}

# ─────────────────────────────────────────────────────────────────────────────
# RÉPERTOIRE ORTHO4XP
# ─────────────────────────────────────────────────────────────────────────────

def _get_ortho4xp_dir():
    here = Path(__file__).resolve()
    return str(here.parent.parent if here.parent.name == "src" else here.parent)

_ORTHO4XP_DIR = _get_ortho4xp_dir()
_MASK_DIR     = os.path.join(_ORTHO4XP_DIR, "Masks")

# ─────────────────────────────────────────────────────────────────────────────
# BRUIT FRACTAL (sans dépendance externe)
# ─────────────────────────────────────────────────────────────────────────────

def _make_noise_layer(seed, H, W, freq, amp):
    rng = np.random.default_rng(seed)
    px, py, pd = (rng.uniform(0, 2*math.pi) for _ in range(3))
    Y = np.arange(H, dtype=np.float32)
    X = np.arange(W, dtype=np.float32)
    Xg, Yg = np.meshgrid(X, Y)
    n = (np.sin(2*math.pi*freq*Xg + px)
       + np.sin(2*math.pi*freq*Yg + py)
       + np.sin(2*math.pi*freq*(Xg+Yg)*0.707 + pd)) / 3.0
    return (n * amp).astype(np.float32)

def _fractal_noise(seed_base, H, W, octaves):
    out = np.zeros((H, W), dtype=np.float32)
    for i, (freq, w) in enumerate(octaves):
        out += _make_noise_layer(seed_base + i*1000, H, W, freq,
                                 NOISE_AMPLITUDE_PX * w)
    return out

# ─────────────────────────────────────────────────────────────────────────────
# POST-TRAITEMENT DU MASQUE PNG CÔTIER
# ─────────────────────────────────────────────────────────────────────────────

def post_process_coastal_mask(mask_path, tile=None):
    """
    Applique un bord naturel (vagues/écume) sur un masque PNG côtier
    généré par Ortho4XP.

    Le PNG original reste intact en cas d'erreur.
    Retourne True si le traitement a été appliqué, False sinon.

    Usage depuis O4_Mask_Utils après mask_im.save(mask_path) :
        try:
            import O4_Coastal_Manager as COAST
            COAST.post_process_coastal_mask(mask_path, tile)
        except ImportError:
            pass
    """
    if not mask_path or not os.path.isfile(mask_path):
        return False
    try:
        img = Image.open(mask_path).convert("L")
        arr = np.array(img, dtype=np.float32)
        H, W = arr.shape

        # Vérifier que c'est bien une tuile côtière (mixte eau/terre)
        sea_r  = float((arr < 64).sum())  / max(arr.size, 1)
        land_r = float((arr > 200).sum()) / max(arr.size, 1)
        if sea_r < COASTAL_THRESHOLD or land_r < COASTAL_THRESHOLD:
            return False

        # Seed reproductible (même résultat à chaque build)
        seed = abs(hash(mask_path)) % (2**30)

        # Distance signée depuis la frontière terre/mer
        from scipy import ndimage as _ndi
        land = (arr >= 128).astype(np.float32)
        dist_signed = (
            _ndi.distance_transform_edt(land)
          - _ndi.distance_transform_edt(1.0 - land)
        ).astype(np.float32)

        # Bruit fractal multi-octave
        noise = _fractal_noise(seed, H, W, NOISE_OCTAVES)

        # Zone d'influence du bruit (bande autour du bord)
        influence = float(NOISE_AMPLITUDE_PX + ECUME_WIDTH_PX + 20)
        attn = np.clip(1.0 - np.abs(dist_signed) / influence, 0.0, 1.0)
        dist_noisy = dist_signed + noise * attn

        # Niveau de transparence "eau peu profonde" (sea_level de Jojo)
        sea_level = 100
        if tile is not None:
            try:
                rw = float(getattr(tile, "ratio_water", 0.2))
                sea_level = int(127 * (1 - min(1, 0.1 + rw)))
            except Exception:
                pass

        # Profil sigmoïde : dist_noisy → valeur 0..255
        k = math.log(19.0) / max(ECUME_WIDTH_PX, 1)
        prob_land = (1.0 / (1.0 + np.exp(-k * dist_noisy))).astype(np.float32)
        new_val = (prob_land * 255).astype(np.float32)

        # Bande d'écume côté mer : valeur = sea_level (semi-transparent)
        ecume = (dist_noisy >= -ECUME_WIDTH_PX) & (dist_noisy < 0)
        if ecume.sum() > 10:
            ratio_e = np.clip((dist_noisy + ECUME_WIDTH_PX) / max(ECUME_WIDTH_PX, 1),
                              0.0, 1.0)
            new_val[ecume] = (ratio_e * sea_level).astype(np.float32)[ecume]

        # Appliquer uniquement dans la zone d'influence
        in_zone = np.abs(dist_signed) < influence
        new_arr = arr.copy()
        new_arr[in_zone] = new_val[in_zone]

        # Protection absolue : zones purement terre ou mer
        new_arr[dist_signed >  influence] = 255
        new_arr[dist_signed < -influence] = 0
        new_arr = np.clip(new_arr, 0, 255).astype(np.uint8)

        # Lissage final doux (élimine les artefacts pixel sans effacer les ondulations)
        mask_zl = int(getattr(tile, "mask_zl", 15)) if tile else 15
        sr = max(1, int(2 ** (mask_zl - 14)))
        final = np.array(
            Image.fromarray(new_arr, "L").filter(ImageFilter.GaussianBlur(sr)),
            dtype=np.uint8
        )

        # Sauvegarde (remplace le PNG original)
        Image.fromarray(final, "L").save(mask_path)

        try:
            import O4_UI_Utils as UI
            UI.vprint(1, f"   [Coastal] bord de côtes et d'iles : dégradé automatique.: {os.path.basename(mask_path)}")
        except Exception:
            pass
        return True

    except Exception as e:
        try:
            import O4_UI_Utils as UI
            UI.vprint(2, f"   [Coastal] post_process ignoré ({os.path.basename(mask_path)}): {e}")
        except Exception:
            pass
        return False


def post_process_all_masks_in_dir(mask_dir, tile=None):
    """Applique le post-traitement sur tous les PNG d'un dossier."""
    if not os.path.isdir(mask_dir):
        return 0
    count = sum(
        1 for f in os.listdir(mask_dir)
        if f.endswith(".png")
        and post_process_coastal_mask(os.path.join(mask_dir, f), tile)
    )
    return count


# ─────────────────────────────────────────────────────────────────────────────
# DÉTECTION CÔTIÈRE
# ─────────────────────────────────────────────────────────────────────────────

def _load_mask_arr(path, size=None):
    if not path or not os.path.isfile(path):
        return None
    try:
        img = Image.open(path).convert("L")
        if size:
            img = img.resize(size, Image.BOX)
        return np.array(img, dtype=np.float32) / 255.0
    except Exception:
        return None

def is_coastal_from_mask_path(sea_mask_path):
    arr = _load_mask_arr(sea_mask_path, size=(64, 64))
    if arr is None:
        return False, 0.0
    r = float((arr < 0.5).sum()) / max(arr.size, 1)
    return r >= COASTAL_THRESHOLD, r

def is_coastal_tile(lat, lon):
    key = (int(lat), int(lon))
    if key in _coastal_cache:
        return _coastal_cache[key]
    result = {"is_coastal": False, "has_islands": False, "sea_ratio": 0.0}
    rla = "{:+.0f}".format(math.floor(lat/10)*10).zfill(3)
    rlo = "{:+.0f}".format(math.floor(lon/10)*10).zfill(4)
    sla = "{:+.0f}".format(lat).zfill(3)
    slo = "{:+.0f}".format(lon).zfill(4)
    mdir = os.path.join(_MASK_DIR, rla+rlo, sla+slo)
    if not os.path.isdir(mdir):
        _coastal_cache[key] = result
        return result
    pngs = [f for f in os.listdir(mdir) if f.endswith(".png")]
    if not pngs:
        _coastal_cache[key] = result
        return result
    arr = _load_mask_arr(os.path.join(mdir, pngs[0]), size=(64, 64))
    if arr is None:
        _coastal_cache[key] = result
        return result
    sr = float((arr < 0.5).sum()) / max(arr.size, 1)
    result["sea_ratio"] = sr
    if sr >= COASTAL_THRESHOLD:
        result["is_coastal"] = True
        if sr > 0.4 and float((arr >= 0.5).sum()) / max(arr.size, 1) > 0.05:
            result["has_islands"] = True
    _coastal_cache[key] = result
    return result

def clear_coastal_cache():
    _coastal_cache.clear()
    _mask_arr_cache.clear()

# ─────────────────────────────────────────────────────────────────────────────
# GÉNÉRATION AUTOMATIQUE DE MASQUE DEPUIS LE MESH
# ─────────────────────────────────────────────────────────────────────────────

def generate_coastal_mask_from_mesh(tile, til_x, til_y, zoomlevel, dico_sea):
    """
    Génère automatiquement un masque alpha côtier pour une tuile DDS,
    depuis les triangles mer du mesh Ortho4XP (dico_sea).

    Fonctionne pour n'importe quelle zone du monde — île, côte, fjord —
    sans fichier manuel. Équivalent automatique des masques Gimp.

    Algorithme :
    1. Dessiner les triangles mer en noir sur fond blanc (terre=255, mer=0)
    2. Calculer la distance signée depuis la frontière terre/mer
    3. Appliquer un profil sigmoïde pour un dégradé progressif
    4. Sauvegarder dans Masks/ au format legacy_mask

    Retourne le chemin du PNG généré, ou None si échec/pas de mer.
    """
    try:
        import O4_Geo_Utils as GEO
        import O4_File_Names as FNAMES
        from PIL import Image as _PIL, ImageDraw as _Draw
        from scipy import ndimage as _ndi

        # Coordonnées pixel de la tuile en ZL texture
        SIZE = 4096
        PAD  = 1024  # marge pour le flou débordant

        (latm0, lonm0) = GEO.gtile_to_wgs84(til_x, til_y, zoomlevel)
        (px0, py0) = GEO.wgs84_to_pix(latm0, lonm0, zoomlevel)
        px0 -= PAD
        py0 -= PAD

        # Créer image fond blanc (terre) avec marge
        mask_im  = _PIL.new("L", (SIZE + 2*PAD, SIZE + 2*PAD), 255)
        mask_drw = _Draw.Draw(mask_im)

        # Dessiner les triangles mer en noir
        # Chercher dans la clé exacte ET les 8 voisines (±16)
        # Nécessaire pour tuiles entièrement en mer dont les triangles
        # côtiers sont dans les clés adjacentes
        tris = []
        for dx in [-16, 0, 16]:
            for dy in [-16, 0, 16]:
                tris += dico_sea.get((til_x + dx, til_y + dy), [])
        if not tris:
            return None  # aucun triangle mer voisin → tuile terrestre pure

        for (lat1, lon1, lat2, lon2, lat3, lon3) in tris:
            (px1, py1) = GEO.wgs84_to_pix(lat1, lon1, zoomlevel)
            (px2, py2) = GEO.wgs84_to_pix(lat2, lon2, zoomlevel)
            (px3, py3) = GEO.wgs84_to_pix(lat3, lon3, zoomlevel)
            px1-=px0; px2-=px0; px3-=px0
            py1-=py0; py2-=py0; py3-=py0
            mask_drw.polygon([(px1,py1),(px2,py2),(px3,py3)], fill=0)
        del mask_drw

        arr = np.array(mask_im, dtype=np.float32)

        # Vérifier qu'il y a bien de la mer
        sea_r  = float((arr < 64).sum())  / max(arr.size, 1)
        if sea_r == 0.0:
            return None

        from PIL import ImageFilter as _IF
        pxscal = 4.0 * (2 ** (15 - zoomlevel))
        _mw = getattr(tile, 'masks_width', 8000)
        masks_width = float(_mw[0] if isinstance(_mw, (list, tuple)) else _mw)
        blur_r = max(2, int(masks_width / pxscal / 8))
        result = np.array(_PIL.fromarray(arr.astype(np.uint8), 'L').filter(_IF.GaussianBlur(blur_r)), dtype=np.uint8)
        final = result[PAD:PAD+SIZE, PAD:PAD+SIZE]

        # Sauvegarder dans Masks/
        dest_dir = FNAMES.mask_dir(tile.lat, tile.lon)
        if not os.path.isdir(dest_dir):
            os.makedirs(dest_dir)
        mask_path = os.path.join(dest_dir, FNAMES.legacy_mask(til_x, til_y))
        _PIL.fromarray(final, "L").save(mask_path)

        try:
            import O4_UI_Utils as UI
            UI.vprint(1, f"   [Coastal] Masque auto généré depuis mesh : {os.path.basename(mask_path)}")
        except Exception:
            pass

        return mask_path

    except Exception as e:
        try:
            import O4_UI_Utils as UI
            UI.vprint(2, f"   [Coastal] generate_coastal_mask_from_mesh erreur : {e}")
        except Exception:
            pass
        return None

# ─────────────────────────────────────────────────────────────────────────────
# PROTECTION EAU POUR COLOR NORMALIZE
# ─────────────────────────────────────────────────────────────────────────────

def apply_coastal_sea_protection(img_corrected, img_original,
                                  sea_mask_path, zl=None, lat=None, lon=None):
    if not sea_mask_path or not os.path.isfile(sea_mask_path):
        return img_corrected
    w, h = img_corrected.size
    raw = _load_mask_arr(sea_mask_path, size=(w, h))
    if raw is None:
        return img_corrected
    if float((raw < 0.5).sum()) / max(raw.size, 1) < COASTAL_THRESHOLD:
        return img_corrected
    zl_int = int(zl) if zl else 16
    pxscal_c = 4.0 * (2 ** (15 - zl_int))
    gr = max(1, min(w // 8, int(200.0 / pxscal_c)))
    land = (raw >= 0.5).astype(np.uint8) * 255
    gradient = np.array(
        Image.fromarray(land, "L").filter(ImageFilter.GaussianBlur(gr)),
        dtype=np.float32
    ) / 255.0
    ac = np.array(img_corrected.convert("RGB"), dtype=np.float32)
    ao = np.array(img_original.convert("RGB"),  dtype=np.float32)
    res = np.empty_like(ac)
    for ch in range(3):
        res[:,:,ch] = gradient*ac[:,:,ch] + (1.0-gradient)*ao[:,:,ch]
    out = Image.fromarray(np.clip(res, 0, 255).astype(np.uint8), "RGB")
    if img_corrected.mode == "RGBA":
        out = out.convert("RGBA")
        out.putalpha(img_corrected.split()[3])
    elif img_corrected.mode != "RGB":
        out = out.convert(img_corrected.mode)
    return out

def coastal_post_normalize(img_corrected, img_original,
                            sea_mask_path=None, zl=None, lat=None, lon=None):
    """Point d'entrée pour O4_Color_Normalize.normalize_if_enabled()."""
    if not sea_mask_path:
        return img_corrected
    is_c, _ = is_coastal_from_mask_path(sea_mask_path)
    if not is_c:
        return img_corrected
    return apply_coastal_sea_protection(
        img_corrected, img_original, sea_mask_path, zl=zl)

# ─────────────────────────────────────────────────────────────────────────────
# PANNEAU COLOR CHECK
# ─────────────────────────────────────────────────────────────────────────────

def build_coastal_info_panel(parent_frame):
    """Panneau 'Côtes & Îles' pour O4_Color_Check._build_ui()."""
    try:
        import tkinter as tk
        import threading

        fr = tk.LabelFrame(parent_frame,
            text="🌊 Zone maritime : bord de côtes et d'iles : dégradé automatique.",
             bg="#3b5b49",
            fg="#4488ff", font=("Arial", 10, "bold"), padx=4, pady=4)
        fr.pack(fill="x", padx=6, pady=(4, 0))

        lbl = tk.Label(fr, text="Analyse…", font=("Arial", 9), fg="#aaaaaa")
        lbl.pack(anchor="w")
        lb = tk.Listbox(fr, height=4, font=("Courier", 9),
                        bg="#1a1a2e", fg="#88ccff",
                        selectbackground="#334466", exportselection=False)
        lb.pack(fill="x", padx=2, pady=(2, 0))
        lbl2 = tk.Label(fr, text="", font=("Arial", 9), fg="#ffdd88",
                        wraplength=340, justify="left")
        lbl2.pack(anchor="w", pady=(2, 0))

        _tiles = []
        def _sel(e):
            s = lb.curselection()
            if s and s[0] < len(_tiles):
                t = _tiles[s[0]]
                lbl2.config(text=(
                    f"  {t['label']}  mer={t['sea_ratio']*100:.0f}%"
                    + (" + ÎLES" if t["has_islands"] else "")
                    + f"\n  Bruit: {NOISE_AMPLITUDE_PX}px | Écume: {ECUME_WIDTH_PX}px"
                ))
        lb.bind("<<ListboxSelect>>", _sel)

        def _scan():
            if not os.path.isdir(_MASK_DIR):
                lb.insert("end", "  Dossier Masks/ absent")
                return
            found = []
            for reg in os.listdir(_MASK_DIR):
                rp = os.path.join(_MASK_DIR, reg)
                if not os.path.isdir(rp):
                    continue
                for td in os.listdir(rp):
                    try:
                        lat, lon = int(td[:3]), int(td[3:7])
                    except Exception:
                        continue
                    info = is_coastal_tile(lat, lon)
                    if info["is_coastal"]:
                        found.append(dict(info, label=td))
            _tiles.clear(); _tiles.extend(found)
            lb.delete(0, "end")
            if not found:
                lb.insert("end", "  Aucune tuile côtière détectée")
                lbl.config(text="Aucune tuile côtière dans Masks/")
            else:
                for t in found:
                    icon = "🏝" if t["has_islands"] else "🌊"
                    lb.insert("end",
                        f"  {icon} {t['label']}  mer={t['sea_ratio']*100:.0f}%")
                lbl.config(text=f"{len(found)} tuile(s) — bord de mer auto")
        threading.Thread(target=_scan, daemon=True).start()
        return fr
    except Exception:
        return None

# ─────────────────────────────────────────────────────────────────────────────
# PARAMÈTRES CFG (pour O4_Mask_Utils)
# ─────────────────────────────────────────────────────────────────────────────

def get_coastal_params_for_tile(lat, lon):
    """Retourne les paramètres Jojo si la tuile est côtière, sinon None."""
    if is_coastal_tile(lat, lon)["is_coastal"]:
        return {
            "masks_width": 8000, "masking_mode": "sand",
            "mask_zl": 15, "ratio_water": 0.2,
            "use_masks_for_inland": False, "imprint_masks_to_dds": False,
            "distance_masks_too": False, "masks_use_DEM_too": False,
            "ratio_bathy": 0.0, "cover_zl": 18,
            "water_tech": "XP12", "mesh_zl": 19, "sea_texture_blur": 0.0,
        }
    return None
