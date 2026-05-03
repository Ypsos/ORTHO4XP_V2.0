"""
O4_Sea_Texture.py — Fallback maritime pour zones côtières sans données
=======================================================================
Télécharge les tuiles EOX Sentinel-2 (libre de droits, couverture mondiale)
pour les zones côtières en mer où le provider principal n'a pas de données.

Appelé depuis O4_Tile_Utils.download_textures quand build_jpeg_ortho retourne False.
Le JPG SEA est téléchargé dans le même dossier que les autres JPG du provider
afin d'être assemblé normalement dans le pipeline existant.

Zéro lecture mesh — zéro interaction avec build_dsf.
Cache permanent dans Orthophotos/SEA/SEA_12/.

Auteur : Ortho4XP V2
"""

import os, urllib.request
from io import BytesIO
from PIL import Image

import O4_UI_Utils as UI
import O4_File_Names as FNAMES
import O4_Geo_Utils as GEO

# ─── Constantes ────────────────────────────────────────────────────────────────
SEA_ZL  = 12
SEA_URL = (
    "https://a.tiles.maps.eox.at/wmts/?"
    "layer=s2cloudless-2023_3857&style=default"
    "&tilematrixset=GoogleMapsCompatible&Service=WMTS"
    "&Request=GetTile&Version=1.0.0&Format=image%2Fjpeg"
    "&TileMatrix={zoom}&TileCol={x}&TileRow={y}"
)

# dico_sea chargé par O4_Tile_Utils dans IMG._dico_sea_global avant les threads
# Zéro relecture mesh dans les threads — zéro deadlock


def download_sea_jpeg(tile, til_x_left, til_y_top, zoomlevel, provider_code,
                      *args):
    """
    Télécharge un JPG EOX Sentinel-2 pour une tuile côtière sans données.
    Retourne True si le JPG a été téléchargé et sauvegardé, False sinon.
    """
    try:
        # 1. Vérifier que c'est une zone mer côtière
        # Lire depuis IMG._dico_sea_global — chargé dans thread principal, zéro deadlock
        import O4_Imagery_Utils as _IMG
        dico_sea = getattr(_IMG, '_dico_sea_global', {})
        if not dico_sea:
            return False

        mask_zl = int(getattr(tile, 'mask_zl', 17))
        factor = max(1, 2**(int(zoomlevel) - int(mask_zl)))
        mx = (int(til_x_left / factor) // 16) * 16
        my = (int(til_y_top  / factor) // 16) * 16

        is_sea = False
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                if ((mx + dx*16), (my + dy*16)) in dico_sea:
                    is_sea = True
                    break

        if not is_sea:
            return False

        # 2. Télécharger tuile EOX ZL12 correspondante
        sea_img = _get_sea_tile(til_x_left, til_y_top, zoomlevel)
        if sea_img is None:
            return False

        # 3. Sauvegarder dans le dossier du provider principal
        import O4_Imagery_Utils as IMG
        layers = IMG.local_combined_providers_dict.get(provider_code, [])
        if not layers:
            return False

        layer_code = layers[0]["layer_code"]
        if layer_code not in IMG.providers_dict:
            return False

        out_dir = FNAMES.jpeg_file_dir_from_attributes(
            tile.lat, tile.lon, zoomlevel,
            IMG.providers_dict[layer_code]
        )
        out_name = FNAMES.jpeg_file_name_from_attributes(
            til_x_left, til_y_top, zoomlevel, provider_code
        )

        if not os.path.exists(out_dir):
            os.makedirs(out_dir)

        # Redimensionner à 4096x4096
        sea_img = sea_img.resize((4096, 4096), Image.LANCZOS)
        sea_img.convert("RGB").save(os.path.join(out_dir, out_name), quality=85)

        UI.vprint(1, f"   [SeaTex] JPG maritime EOX : {out_name}")
        return True

    except Exception as e:
        UI.vprint(2, f"   [SeaTex] erreur : {e}")
        return False


def _get_sea_tile(til_x, til_y, zl_ortho):
    """Télécharge ou récupère en cache la tuile EOX ZL12."""
    # Convertir coordonnées Ortho4XP → TMS webmercator ZL12
    n_ortho = 2**zl_ortho
    lon_w = til_x / n_ortho * 360.0 - 180.0
    lat_n_rad = (1 - 2 * til_y / n_ortho) * 3.14159265
    import math
    lat_n = math.degrees(math.atan(math.sinh(lat_n_rad)))

    n_sea = 2**SEA_ZL
    tx = int((lon_w + 180.0) / 360.0 * n_sea)
    ty = int((1 - math.log(math.tan(math.radians(lat_n)) +
              1/math.cos(math.radians(lat_n))) / math.pi) / 2 * n_sea)

    # Cache
    cache_dir = os.path.join(FNAMES.Imagery_dir, "SEA", f"SEA_{SEA_ZL}")
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"{ty}_{tx}_SEA{SEA_ZL}.jpg")

    if os.path.isfile(cache_file):
        try:
            return Image.open(cache_file).convert("RGB")
        except Exception:
            pass

    # Téléchargement
    url = SEA_URL.format(zoom=SEA_ZL, x=tx, y=ty)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Ortho4XP/2.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        if data[:2] == b'\xff\xd8':
            with open(cache_file, 'wb') as f:
                f.write(data)
            return Image.open(BytesIO(data)).convert("RGB")
        else:
            UI.vprint(2, f"   [SeaTex] réponse non-JPEG depuis EOX")
    except Exception as e:
        UI.vprint(2, f"   [SeaTex] téléchargement EOX échoué : {e}")

    return None


def patch_sea_black_zones(tile, til_x_left, til_y_top, zoomlevel, provider_code,
                          *args):
    """
    Après build_jpeg_ortho réussi, vérifie si le JPG contient des zones noires
    en mer et les remplace par la tuile EOX correspondante.
    Le JPG est sauvegardé à la même place — l'assemblage PNG lira la version corrigée.
    Retourne True si le JPG a été modifié.
    """
    try:
        import O4_Imagery_Utils as _IMG
        dico_sea = getattr(_IMG, '_dico_sea_global', {})
        if not dico_sea:
            return False

        # Vérifier zone mer
        mask_zl = int(getattr(tile, 'mask_zl', 17))
        factor = max(1, 2**(int(zoomlevel) - int(mask_zl)))
        mx = (int(til_x_left / factor) // 16) * 16
        my = (int(til_y_top  / factor) // 16) * 16

        is_sea = False
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                if ((mx + dx*16), (my + dy*16)) in dico_sea:
                    is_sea = True
                    break
        if not is_sea:
            return False

        # Trouver le JPG source
        layers = _IMG.local_combined_providers_dict.get(provider_code, [])
        if not layers:
            return False

        jpg_path = None
        for rlayer in layers:
            layer_code = rlayer["layer_code"]
            if layer_code not in _IMG.providers_dict:
                continue
            fname = FNAMES.jpeg_file_name_from_attributes(
                til_x_left, til_y_top, zoomlevel, layer_code)
            fdir = FNAMES.jpeg_file_dir_from_attributes(
                tile.lat, tile.lon, zoomlevel, _IMG.providers_dict[layer_code])
            fpath = os.path.join(fdir, fname)
            if os.path.isfile(fpath):
                jpg_path = fpath
                break

        if not jpg_path:
            return False

        # Charger et vérifier zones noires
        import numpy as np
        from PIL import Image as _PIL
        img = _PIL.open(jpg_path).convert("RGB")
        arr = np.array(img, dtype=np.uint8)
        is_black = ((arr[:,:,0] < 30) & (arr[:,:,1] < 30) & (arr[:,:,2] < 30))

        if not is_black.any():
            return False

        # Télécharger EOX et remplacer zones noires
        sea_img = _get_sea_tile(til_x_left, til_y_top, zoomlevel)
        if sea_img is None:
            return False

        sea_arr = np.array(sea_img.resize(img.size, _PIL.LANCZOS), dtype=np.uint8)

        # Dégradé flou pour jointure invisible
        from PIL import ImageFilter
        mask_blur = np.array(
            _PIL.fromarray(is_black.astype(np.uint8)*255, 'L')
               .filter(ImageFilter.GaussianBlur(16)),
            dtype=np.float32) / 255.0

        result = arr.copy().astype(np.float32)
        for ch in range(3):
            result[:,:,ch] = mask_blur*sea_arr[:,:,ch] + (1-mask_blur)*arr[:,:,ch]

        _PIL.fromarray(result.astype(np.uint8)).save(jpg_path, quality=85)
        UI.vprint(1, f"   [SeaTex] Zones noires remplacées par EOX : {os.path.basename(jpg_path)}")
        return True

    except Exception as e:
        UI.vprint(2, f"   [SeaTex] patch erreur : {e}")
        return False
