"""
O4_Sea_Texture.py — Fallback maritime via EOX Sentinel-2
=========================================================
Ortho4XP V3.2 — Mai 2026
Auteur : Roland (Ypsos) — Codage : Claude (Anthropic AI)

PRINCIPE :
  Quand un JPG source est absent ou blanc (zone mer sans données),
  télécharger un JPG EOX Sentinel-2 (CC BY 4.0 — libre de droit)
  UNIQUEMENT sur les triangles identifiés comme MER dans le mesh (dico_sea).
  Jamais sur la terre → pas de remplacement nordel.

PIPELINE (ordre Roland) :
  1. JPG multi-source téléchargés
  2. Mesh → dico_sea → zones mer blanches détectées
  3. Téléchargement JPG EOX sur zones mer blanches uniquement
  4. Color Normalize sur chaque JPG séparément (IGN + EOX)
  5. Assemblage JPG corrigés → PNG complet
  6. PNG → DDS

ZL EOX : max ZL16 sur serveur public EOX.
  Si ZL demandé > 16 → téléchargement ZL16 + resize à taille cible (4096×4096).
  Color Normalize corrige la dominante colorimétrique Sentinel.

Licence EOX Sentinel-2 : CC BY 4.0
  https://s2maps.eu — usage libre, diffusion autorisée avec attribution.

Dossier sortie : Orthophotos/SEA/ZL{zl}/
  Format : {til_y_top}_{til_x_left}_SEA_ZL{zl}.jpg
  Cache brut EOX : Orthophotos/SEA/SEA_{zl_eox}/
"""

import os
import math
import urllib.request
from io import BytesIO
from PIL import Image
import numpy

import O4_UI_Utils as UI
import O4_File_Names as FNAMES

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────────────────────

EOX_MAX_ZL = 16

EOX_URL = (
    "https://a.tiles.maps.eox.at/wmts/?"
    "layer=s2cloudless-2023_3857&style=default"
    "&tilematrixset=GoogleMapsCompatible&Service=WMTS"
    "&Request=GetTile&Version=1.0.0&Format=image%2Fjpeg"
    "&TileMatrix={zoom}&TileCol={x}&TileRow={y}"
)

# Seuil blanc standard Ortho4XP : somme RGB >= 735 = pixel sans données
WHITE_SUM_THRESHOLD = 735

# Ratio minimum pixels blancs pour déclencher EOX (évite téléchargement pour 2-3 pixels)
WHITE_RATIO_MIN = 0.01


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSION COORDONNÉES
# ─────────────────────────────────────────────────────────────────────────────

def _ortho_tile_to_eox_tile(til_x_left, til_y_top, zl_ortho, zl_eox):
    """Convertit coordonnées tuile Ortho4XP vers coordonnées tuile EOX."""
    factor = 2 ** (zl_eox - zl_ortho)
    tx_eox = int(til_x_left * factor / 16)
    ty_eox = int(til_y_top  * factor / 16)
    return (tx_eox, ty_eox)


# ─────────────────────────────────────────────────────────────────────────────
# DÉTECTION ZONES BLANCHES MER
# ─────────────────────────────────────────────────────────────────────────────

def _is_sea_tile(til_x_left, til_y_top, dico_sea):
    """Vérifie si la tuile contient des triangles mer dans dico_sea."""
    return (til_x_left, til_y_top) in dico_sea and \
           len(dico_sea[(til_x_left, til_y_top)]) > 0


def needs_sea_fill(jpg_path, til_x_left, til_y_top, dico_sea):
    """
    Retourne True si EOX doit être téléchargé pour cette tuile.
    Conditions : tuile mer (dico_sea) ET (JPG absent OU blancs >= 1%)
    """
    if not _is_sea_tile(til_x_left, til_y_top, dico_sea):
        return False

    if not os.path.isfile(jpg_path):
        UI.vprint(2, f"   [SeaTex] JPG absent sur tuile mer : {os.path.basename(jpg_path)}")
        return True

    try:
        img  = Image.open(jpg_path).convert("RGB")
        arr  = numpy.array(img, dtype=numpy.uint16)
        som  = arr[:,:,0] + arr[:,:,1] + arr[:,:,2]
        ratio = (som >= WHITE_SUM_THRESHOLD).sum() / (arr.shape[0] * arr.shape[1])
        if ratio >= WHITE_RATIO_MIN:
            UI.vprint(2,
                f"   [SeaTex] {os.path.basename(jpg_path)} : "
                f"{ratio*100:.1f}% blanc mer → EOX requis")
            return True
    except Exception as e:
        UI.vprint(2, f"   [SeaTex] Erreur lecture {jpg_path} : {e}")
        return True

    return False


# ─────────────────────────────────────────────────────────────────────────────
# TÉLÉCHARGEMENT EOX
# ─────────────────────────────────────────────────────────────────────────────

def _get_eox_tile(tx_eox, ty_eox, zl_eox):
    """Télécharge ou récupère depuis cache la tuile EOX brute."""
    cache_dir  = os.path.join(FNAMES.Imagery_dir, "SEA", f"SEA_{zl_eox}")
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"{ty_eox}_{tx_eox}_SEA{zl_eox}.jpg")

    if os.path.isfile(cache_file):
        try:
            return Image.open(cache_file).convert("RGB")
        except Exception:
            pass

    url = EOX_URL.format(zoom=zl_eox, x=tx_eox, y=ty_eox)
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Ortho4XP/3.0 (s2maps.eu CC-BY-4.0)"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        if data[:2] != b"\xff\xd8":
            UI.vprint(2, f"   [SeaTex] Réponse non-JPEG EOX ZL{zl_eox}")
            return None
        with open(cache_file, "wb") as f:
            f.write(data)
        return Image.open(BytesIO(data)).convert("RGB")
    except Exception as e:
        UI.vprint(2, f"   [SeaTex] Téléchargement EOX ZL{zl_eox} échoué : {e}")
        return None


def download_sea_jpeg(tile, til_x_left, til_y_top, zoomlevel,
                      provider_code, dico_sea=None):
    """
    Télécharge JPG EOX pour une tuile mer blanche.
    Retourne chemin JPG sauvegardé ou None.
    """
    try:
        if dico_sea is None:
            try:
                import O4_Mask_Utils as MASK
                (dico_sea, _) = MASK.record_water_tris(tile)
            except Exception as e:
                UI.vprint(2, f"   [SeaTex] Impossible lire dico_sea : {e}")
                return None

        # Chemin JPG source
        jpg_path = ""
        try:
            import O4_Imagery_Utils as _IMG
            if provider_code in _IMG.providers_dict:
                jpg_name = FNAMES.jpeg_file_name_from_attributes(
                    til_x_left, til_y_top, zoomlevel, provider_code)
                jpg_dir  = FNAMES.jpeg_file_dir_from_attributes(
                    tile.lat, tile.lon, zoomlevel,
                    _IMG.providers_dict[provider_code])
                jpg_path = os.path.join(jpg_dir, jpg_name)
        except Exception:
            pass

        if not needs_sea_fill(jpg_path, til_x_left, til_y_top, dico_sea):
            return None

        zl_eox = min(int(zoomlevel), EOX_MAX_ZL)
        (tx_eox, ty_eox) = _ortho_tile_to_eox_tile(
            til_x_left, til_y_top, int(zoomlevel), zl_eox)

        sea_img = _get_eox_tile(tx_eox, ty_eox, zl_eox)
        if sea_img is None:
            return None

        if sea_img.size != (4096, 4096):
            sea_img = sea_img.resize((4096, 4096), Image.LANCZOS)

        out_dir  = os.path.join(FNAMES.Imagery_dir, "SEA", f"ZL{zoomlevel}")
        os.makedirs(out_dir, exist_ok=True)
        out_name = f"{til_y_top}_{til_x_left}_SEA_ZL{zoomlevel}.jpg"
        out_path = os.path.join(out_dir, out_name)
        sea_img.convert("RGB").save(out_path, quality=90)

        UI.vprint(1,
            f"   [SeaTex] EOX ZL{zl_eox}→ZL{zoomlevel} sauvegardé : {out_name}")
        return out_path

    except Exception as e:
        UI.vprint(2, f"   [SeaTex] download_sea_jpeg erreur : {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# ASSEMBLAGE — FUSION JPG SOURCE + EOX
# ─────────────────────────────────────────────────────────────────────────────

def _build_sea_fade_alpha(is_blanc, fade_px=128):
    """
    Construit un canal alpha (0-255) avec fondu progressif sur les bords
    extérieurs mer (là où le JPG touche le vide).

    Principe :
      - Pixels avec données (is_blanc=False) → alpha=255 (opaque)
      - Pixels blancs mer (is_blanc=True)    → alpha=0   (transparent)
      - Bord de transition                   → fondu exponentiel 255→0
        sur fade_px pixels depuis la frontière données/vide

    XP12 voit la transparence et affiche sa propre eau en dessous →
    jointure invisible quelle que soit la couleur XP12 (générique mondial).
    """
    from PIL import ImageFilter
    # Masque binaire : 255 = données, 0 = vide mer
    has_data = (~is_blanc).astype(numpy.uint8) * 255
    mask_img = Image.fromarray(has_data, "L")
    # Fondu gaussien sur fade_px pixels depuis le bord données/vide
    # GaussianBlur(r) ≈ transition sur ~3×r pixels
    blur_r = max(4, fade_px // 3)
    faded  = mask_img.filter(ImageFilter.GaussianBlur(blur_r))
    alpha  = numpy.array(faded, dtype=numpy.uint8)
    # Protection : intérieur données reste 255 (opaque total)
    alpha[~is_blanc] = 255
    return alpha


def fill_sea_blanks(jpg_path, sea_jpg_path, fade_px=128):
    """
    Fusionne JPG source avec JPG EOX : remplace pixels blancs par EOX.
    Applique un fondu alpha progressif sur les bords extérieurs mer.

    Règles :
      - Pixel blanc (somme >= 735) → EOX
      - Pixel avec données         → conservé
      - Bord données/vide          → fondu alpha 255→0 sur fade_px pixels
        → XP12 affiche sa propre eau en transparence → jointure invisible

    Retourne Image PIL RGBA (canal alpha = fondu mer).
    """
    try:
        src = numpy.array(Image.open(jpg_path).convert("RGB"),     dtype=numpy.uint16)
        eox = numpy.array(Image.open(sea_jpg_path).convert("RGB"), dtype=numpy.uint16)

        som      = src[:,:,0] + src[:,:,1] + src[:,:,2]
        is_blanc = (som >= WHITE_SUM_THRESHOLD)

        # Fusion RGB : blancs → EOX, données → source
        result = src.copy()
        for ch in range(3):
            result[:,:,ch] = numpy.where(is_blanc, eox[:,:,ch], src[:,:,ch])

        # Canal alpha : fondu progressif sur bords extérieurs mer
        alpha = _build_sea_fade_alpha(is_blanc, fade_px=fade_px)

        n = int(is_blanc.sum())
        UI.vprint(2,
            f"   [SeaTex] {n:,} pixels mer bouchés "
            f"({100*n/(src.shape[0]*src.shape[1]):.1f}%) "
            f"+ fondu alpha {fade_px}px")

        # Retourner RGBA avec canal alpha fondu
        rgb_img   = Image.fromarray(result.astype(numpy.uint8), "RGB")
        alpha_img = Image.fromarray(alpha, "L")
        rgba      = rgb_img.convert("RGBA")
        rgba.putalpha(alpha_img)
        return rgba

    except Exception as e:
        UI.vprint(2, f"   [SeaTex] fill_sea_blanks erreur : {e}")
        try:
            return Image.open(jpg_path).convert("RGB")
        except Exception:
            return None


def get_sea_jpeg_path(til_x_left, til_y_top, zoomlevel):
    """Retourne chemin JPG EOX en cache ou None."""
    out_dir  = os.path.join(FNAMES.Imagery_dir, "SEA", f"ZL{zoomlevel}")
    out_name = f"{til_y_top}_{til_x_left}_SEA_ZL{zoomlevel}.jpg"
    path     = os.path.join(out_dir, out_name)
    return path if os.path.isfile(path) else None


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def process_sea_fill(tile, til_x_left, til_y_top, zoomlevel,
                     provider_code, jpg_path, dico_sea=None):
    """
    Point d'entrée principal — appelé AVANT Color Normalize dans le pipeline.

    Étape 2 : détection zones mer blanches via dico_sea
    Étape 3 : téléchargement EOX si nécessaire
    → Retourne Image PIL fusionnée, ou None si pas de traitement.

    Si None → pipeline continue normalement (pas de modification).
    Si Image → utiliser cette image à la place du JPG source pour Color Normalize.
    """
    try:
        if dico_sea is None:
            try:
                import O4_Mask_Utils as MASK
                (dico_sea, _) = MASK.record_water_tris(tile)
            except Exception:
                return None

        if not needs_sea_fill(jpg_path, til_x_left, til_y_top, dico_sea):
            return None

        # Cache EOX existant ?
        sea_path = get_sea_jpeg_path(til_x_left, til_y_top, zoomlevel)
        if sea_path is None:
            sea_path = download_sea_jpeg(
                tile, til_x_left, til_y_top, zoomlevel,
                provider_code, dico_sea)

        if sea_path is None:
            UI.vprint(2, "   [SeaTex] EOX non disponible — tuile conservée")
            return None

        if os.path.isfile(jpg_path):
            return fill_sea_blanks(jpg_path, sea_path)
        else:
            return Image.open(sea_path).convert("RGB")

    except Exception as e:
        UI.vprint(2, f"   [SeaTex] process_sea_fill erreur : {e}")
        return None
