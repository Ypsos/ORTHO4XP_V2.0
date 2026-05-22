"""
O4_Sea_Texture.py — Fond marin local via JPG-Patch
===================================================
Ortho4XP V3.2 — Mai 2026
Auteur : Roland (Ypsos) — Codage : Claude (Anthropic AI)

PRINCIPE :
  Générer localement des JPG fond marin (bleu dégradé ou fill_sea_nodata)
  dans Orthophotos/JPG-Patch/+46-003/PATCH_{zl}/
  Le provider PATCH injecté par O4_Imagery_Utils les récupère comme source.
  Zéro téléchargement réseau — zéro dossier SEA.

PIPELINE :
  1. build_tile() → generate_sea_jpg() pour chaque tuile mer
  2. JPG-Patch sauvegardé dans JPG-Patch/+46-003/PATCH_17/
  3. Provider PATCH lu par combine_textures() via _get_sea_tile()
  4. PNG → DDS normalement

Supprimé (tests terminés) :
  - Toutes les fonctions EOX Sentinel-2 (téléchargement réseau)
  - Dossier SEA/ — jamais créé
"""

import os
import math
from PIL import Image
import numpy
from scipy.ndimage import distance_transform_edt as _dte

import O4_UI_Utils as UI
import O4_File_Names as FNAMES


# ─────────────────────────────────────────────────────────────────────────────
# UTILITAIRE DOSSIER TUILE
# ─────────────────────────────────────────────────────────────────────────────

def _tile_folder(tile):
    """Retourne le nom de dossier standard Ortho4XP : ex. +46-003 ou +46+002"""
    sign_lat = "+" if tile.lat >= 0 else "-"
    sign_lon = "+" if tile.lon >= 0 else "-"
    return f"{sign_lat}{abs(int(tile.lat)):02d}{sign_lon}{abs(int(tile.lon)):03d}"


# ─────────────────────────────────────────────────────────────────────────────
# FILL SEA NODATA — Correction zones noires des JPG marin (v42)
# Algorithme : inpainting pixels mer clairs + HDR cross blend jointure
# ─────────────────────────────────────────────────────────────────────────────

def _hdr_safe_cross_blend_local(arr_new, arr_old, force2d):
    """Cross blend HDR sécurisé — évite noirs écrasés et halos."""
    in_zone = force2d > 0.01
    if not in_zone.any():
        return arr_new, arr_old
    for arr in (arr_new, arr_old):
        zone_pixels = arr[in_zone]
        if zone_pixels.size < 9:
            continue
        for ch in range(3):
            ch_vals = zone_pixels[:, ch]
            p1  = float(numpy.percentile(ch_vals, 1))
            p99 = float(numpy.percentile(ch_vals, 99))
            if p1 < 5:
                lift = 5.0 - p1
                arr[:,:,ch] = numpy.where(
                    in_zone, numpy.clip(arr[:,:,ch] + lift * force2d, 0, 255), arr[:,:,ch])
            if p99 > 248:
                compress = (p99 - 248.0) / max(p99, 1)
                arr[:,:,ch] = numpy.where(
                    in_zone, numpy.clip(arr[:,:,ch] * (1.0 - compress * force2d * 0.5), 0, 255), arr[:,:,ch])
    return arr_new, arr_old


def fill_sea_nodata(jpg_path):
    """
    Remplit les zones sans données (noires) d'un JPG marin.
    Algorithme :
      1. Détecter zone noire (R<25, G<60, B<70)
      2. Source = pixels mer clairs (B>=R, luminosité >= percentile 40)
      3. Inpainting : chaque pixel noir → pixel source le plus proche
      4. HDR cross blend sur bande 15px à cheval sur la jointure
    Retourne Image PIL 4096x4096 corrigée, ou None si pas de zone noire.
    """
    try:
        img = Image.open(jpg_path).convert('RGB')
        img_small = img.resize((512, 512), Image.LANCZOS)
        arr = numpy.array(img_small, dtype=numpy.float32)

        no_data = (arr[:,:,0] < 25) & (arr[:,:,1] < 60) & (arr[:,:,2] < 70)
        if no_data.sum() == 0:
            return None  # pas de zone noire → pas de traitement

        valid = ~no_data
        is_sea = (arr[:,:,2].astype(int) >= arr[:,:,0].astype(int) - 5)
        lum = arr[:,:,1]
        sea_valid = valid & is_sea
        thresh = float(numpy.percentile(lum[sea_valid], 40)) if sea_valid.sum() > 100 else 60.0
        bright_sea = sea_valid & (lum >= thresh)
        if bright_sea.sum() < 100:
            bright_sea = valid

        # Inpainting : pixel noir → pixel source clair le plus proche
        _, idx = _dte(~bright_sea, return_indices=True)
        rows_nd, cols_nd = numpy.where(no_data)
        filled = arr.copy()
        for ch in range(3):
            filled[rows_nd, cols_nd, ch] = arr[
                idx[0][rows_nd, cols_nd],
                idx[1][rows_nd, cols_nd], ch]

        # HDR cross blend sur bande jointure (15px des 2 côtés)
        dist_out = _dte(~no_data).astype(numpy.float32)
        dist_in  = _dte(no_data).astype(numpy.float32)
        half = 15
        dist_seam = numpy.minimum(dist_out, dist_in)
        force2d = numpy.clip(1.0 - dist_seam / half, 0.0, 1.0).astype(numpy.float32)

        arr_a = filled.copy()
        arr_b = arr.copy()
        arr_b[no_data] = filled[no_data]
        arr_a, arr_b = _hdr_safe_cross_blend_local(arr_a, arr_b, force2d)

        final = arr.copy()
        final[no_data] = filled[no_data]
        m = force2d > 0
        for ch in range(3):
            final[:,:,ch][m] = (
                (1 - force2d[m]) * final[:,:,ch][m] +
                force2d[m] * arr_a[:,:,ch][m]
            ).clip(0, 255)

        # Upscale à 4096x4096
        return Image.fromarray(final.astype(numpy.uint8)).resize(
            (4096, 4096), Image.LANCZOS)

    except Exception as e:
        UI.vprint(2, f"   [SeaTex] fill_sea_nodata erreur : {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# JPG-PATCH — Génération locale fond marin (zéro réseau)
# Appelé par build_tile() dans O4_Tile_Utils.py AVANT les threads
# ─────────────────────────────────────────────────────────────────────────────

def generate_sea_jpg(tile, til_x_left, til_y_top, zoomlevel, provider_code,
                     neighbor_colors=None, jpeg_dir=None, dico_customzl=None):
    """
    Génère un JPG fond marin 4096×4096 dans :
      Orthophotos/JPG-Patch/+46-003/PATCH_{zoomlevel}/

    Nom fichier : {ty}_{tx}_PATCH{zl}.jpg  (format Ortho4XP standard)

    Couleur :
      - Moyenne RGB des JPG voisins si disponible
      - Sinon : bleu maritime XP12 par défaut (42, 68, 95)
    Dégradé côte→large + grain subtil pour éviter le damier uniforme.

    Retourne le chemin JPG créé, ou None si erreur.
    """
    try:
        patch_dir = os.path.join(
            FNAMES.Imagery_dir,
            "JPG-Patch",
            _tile_folder(tile),
            f"PATCH_{int(zoomlevel)}"
        )
        os.makedirs(patch_dir, exist_ok=True)

        # Format Ortho4XP standard : {ty}_{tx}_{provider}{zl}.jpg
        jpg_name = f"{int(til_x_left)}_{int(til_y_top)}_PATCH{int(zoomlevel)}.jpg"
        jpg_path = os.path.join(patch_dir, jpg_name)

        if os.path.isfile(jpg_path):
            UI.vprint(1, f"   [SeaTex] JPG-Patch cache : {jpg_name}")
            return jpg_path

        # ── Couleur voisins depuis dico_customzl ─────────────────────────────
        if not neighbor_colors and dico_customzl:
            neighbor_colors = []
            try:
                import O4_Imagery_Utils as _IMG
                for (dx, dy) in [(-16,0),(16,0),(0,-16),(0,16)]:
                    vx = int(til_x_left) + dx
                    vy = int(til_y_top)  + dy
                    for key, val in dico_customzl.items():
                        (vtx, vty, vzl, vprov) = val
                        if vtx == vx and vty == vy and vzl == int(zoomlevel):
                            if vprov in _IMG.providers_dict:
                                _vdir = FNAMES.jpeg_file_dir_from_attributes(
                                    tile.lat, tile.lon, vzl,
                                    _IMG.providers_dict[vprov])
                                _vname = FNAMES.jpeg_file_name_from_attributes(
                                    vtx, vty, vzl, vprov)
                                _vpath = os.path.join(_vdir, _vname)
                                if os.path.isfile(_vpath):
                                    try:
                                        va = numpy.array(
                                            Image.open(_vpath).convert("RGB"))
                                        neighbor_colors.append(
                                            tuple(int(x) for x in va.mean(axis=(0,1))))
                                    except Exception:
                                        pass
                            break
            except Exception:
                pass

        if neighbor_colors:
            r = int(numpy.mean([c[0] for c in neighbor_colors]))
            g = int(numpy.mean([c[1] for c in neighbor_colors]))
            b = int(numpy.mean([c[2] for c in neighbor_colors]))
            UI.vprint(2, f"   [SeaTex] Couleur voisins RGB({r},{g},{b})"
                         f" — {len(neighbor_colors)} source(s)")
        else:
            r, g, b = 42, 68, 95  # bleu maritime XP12 par défaut

        # ── Chercher JPG voisin pour fill_sea_nodata ─────────────────────────
        neighbor_jpg = None
        if dico_customzl:
            try:
                import O4_Imagery_Utils as _IMG2
                for (dx, dy) in [(-16,0),(16,0),(0,-16),(0,16),
                                  (-16,-16),(16,-16),(-16,16),(16,16)]:
                    vx = int(til_x_left) + dx
                    vy = int(til_y_top)  + dy
                    for key, val in dico_customzl.items():
                        (vtx, vty, vzl, vprov) = val
                        if vtx == vx and vty == vy and vzl == int(zoomlevel):
                            if vprov in _IMG2.providers_dict:
                                _vdir = FNAMES.jpeg_file_dir_from_attributes(
                                    tile.lat, tile.lon, vzl,
                                    _IMG2.providers_dict[vprov])
                                _vname = FNAMES.jpeg_file_name_from_attributes(
                                    vtx, vty, vzl, vprov)
                                _vpath = os.path.join(_vdir, _vname)
                                if os.path.isfile(_vpath):
                                    neighbor_jpg = _vpath
                                    break
                    if neighbor_jpg:
                        break
            except Exception:
                pass

        # Tenter fill_sea_nodata sur le JPG voisin
        filled_img = None
        if neighbor_jpg:
            filled_img = fill_sea_nodata(neighbor_jpg)
            if filled_img is not None:
                UI.vprint(2, f"   [SeaTex] fill_sea_nodata appliqué depuis voisin")

        if filled_img is not None:
            filled_img.save(jpg_path, quality=85)
        else:
            # ── Fallback : fond bleu avec dégradé côte→large ─────────────────
            size = 4096
            arr  = numpy.zeros((size, size, 3), dtype=numpy.uint8)
            for row in range(size):
                t  = row / (size - 1)
                rr = max(0, int(r * (1.0 - 0.30 * t)))
                gg = max(0, int(g * (1.0 - 0.25 * t)))
                bb = max(0, int(b * (1.0 - 0.10 * t)))
                arr[row, :, 0] = rr
                arr[row, :, 1] = gg
                arr[row, :, 2] = bb
            rng   = numpy.random.default_rng(seed=int(til_x_left) ^ int(til_y_top))
            noise = rng.integers(-4, 5, size=(size, size, 3), dtype=numpy.int16)
            arr   = numpy.clip(arr.astype(numpy.int16) + noise, 0, 255).astype(numpy.uint8)
            Image.fromarray(arr, "RGB").save(jpg_path, quality=85)

        UI.vprint(1, f"   [SeaTex] JPG-Patch généré : {jpg_name}")
        return jpg_path

    except Exception as e:
        import traceback
        UI.vprint(0, f"   [SeaTex] generate_sea_jpg ERREUR : {e} | {traceback.format_exc()}")
        return None


def _get_sea_tile_for_tile(tile, til_x_left, til_y_top, zoomlevel):
    """
    Retourne Image PIL depuis JPG-Patch si disponible.
    Appelé par combine_textures() dans O4_Imagery_Utils.py.
    Nom fichier : {ty}_{tx}_PATCH{zl}.jpg
    """
    patch_dir = os.path.join(
        FNAMES.Imagery_dir,
        "JPG-Patch",
        _tile_folder(tile),
        f"PATCH_{int(zoomlevel)}"
    )
    jpg_name = f"{int(til_x_left)}_{int(til_y_top)}_PATCH{int(zoomlevel)}.jpg"
    jpg_path = os.path.join(patch_dir, jpg_name)
    if os.path.isfile(jpg_path):
        try:
            return Image.open(jpg_path).convert("RGB")
        except Exception:
            return None
    return None


def _get_sea_tile(til_x_left, til_y_top, zoomlevel):
    """
    Version sans tile — parcourt les dossiers JPG-Patch existants.
    Compatibilité avec les appels existants dans O4_Imagery_Utils.py.
    Nom fichier : {ty}_{tx}_PATCH{zl}.jpg
    """
    try:
        base_dir = os.path.join(FNAMES.Imagery_dir, "JPG-Patch")
    except Exception:
        return None
    if not os.path.isdir(base_dir):
        return None
    jpg_name = f"{int(til_x_left)}_{int(til_y_top)}_PATCH{int(zoomlevel)}.jpg"
    for tile_folder in sorted(os.listdir(base_dir)):
        if not os.path.isdir(os.path.join(base_dir, tile_folder)):
            continue
        patch_dir = os.path.join(base_dir, tile_folder, f"PATCH_{int(zoomlevel)}")
        jpg_path  = os.path.join(patch_dir, jpg_name)
        if os.path.isfile(jpg_path):
            try:
                return Image.open(jpg_path).convert("RGB")
            except Exception:
                return None
    return None


def download_sea_neighbor_row(tile, til_x_left, til_y_top, zoomlevel,
                               provider_code):
    """
    Stub compatible avec l'appel existant dans combine_textures().
    Les tuiles voisines sont gérées par generate_sea_jpg — zéro réseau.
    """
    pass
