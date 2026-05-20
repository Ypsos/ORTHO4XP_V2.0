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
from PIL import Image, ImageDraw
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
# MASQUE MER DEPUIS MESH (dico_sea projeté sur ZL texture)
# ─────────────────────────────────────────────────────────────────────────────

def _sea_mask_from_dico(til_x_left, til_y_top, zoomlevel, dico_sea):
    """
    Projette les triangles mer du mesh (dico_sea) sur une image 4096x4096.
    Retourne numpy bool array : True = pixel mer, False = pixel données.
    Utilise la géographie réelle du mesh — indépendant de la couleur des pixels.
    """
    try:
        import O4_Geo_Utils as GEO
        size = 4096
        mask_img = Image.new("L", (size, size), 0)
        draw = ImageDraw.Draw(mask_img)

        key = (til_x_left, til_y_top)
        if key not in dico_sea or not dico_sea[key]:
            # Pas de triangles mer → toute la tuile est terre
            return numpy.zeros((size, size), dtype=bool)

        # Origine pixel de la tuile en coordonnées absolues ZL
        (lat0, lon0) = GEO.gtile_to_wgs84(til_x_left, til_y_top, int(zoomlevel))
        (px0, py0)   = GEO.wgs84_to_pix(lat0, lon0, int(zoomlevel))

        for (lat1, lon1, lat2, lon2, lat3, lon3) in dico_sea[key]:
            (px1, py1) = GEO.wgs84_to_pix(lat1, lon1, int(zoomlevel))
            (px2, py2) = GEO.wgs84_to_pix(lat2, lon2, int(zoomlevel))
            (px3, py3) = GEO.wgs84_to_pix(lat3, lon3, int(zoomlevel))
            # Coordonnées relatives à la tuile
            pts = [
                (px1 - px0, py1 - py0),
                (px2 - px0, py2 - py0),
                (px3 - px0, py3 - py0),
            ]
            draw.polygon(pts, fill=255)

        del draw
        return numpy.array(mask_img, dtype=numpy.uint8) > 128

    except Exception as e:
        UI.vprint(2, f"   [SeaTex] _sea_mask_from_dico erreur : {e}")
        # Fallback : aucun pixel mer détecté → pipeline continue sans modification
        return numpy.zeros((4096, 4096), dtype=bool)


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

def _build_sea_fade_alpha(is_blanc, zoomlevel=17, lat=46.0):
    """
    Construit un canal alpha (0-255) :
      - Zone données (is_blanc=False)        → alpha=255 (opaque)
      - Bande EOX 1km depuis le bord données → alpha=255 (EOX opaque)
      - Dégradé 1km au-delà de la bande      → alpha 255→0 linéaire
      - Au-delà du dégradé (large)           → alpha=0 (eau XP12 native)

    XP12 voit la transparence progressive → jointure invisible.
    """
    import math
    from scipy import ndimage as _ndi

    # Taille bande et dégradé en pixels selon ZL et latitude
    tile_m   = 40075000 / (2 ** int(zoomlevel)) * math.cos(math.radians(lat))
    px_per_m = is_blanc.shape[1] / (tile_m * 16)
    bande_px = int(1000 * px_per_m)   # 1km = bande EOX opaque
    fade_px  = int(1000 * px_per_m)   # 1km = dégradé vers transparent

    # Distance depuis le bord données/mer (en pixels)
    dist = _ndi.distance_transform_edt(is_blanc).astype(numpy.float32)

    # Alpha selon distance
    alpha = numpy.zeros(is_blanc.shape, dtype=numpy.float32)
    alpha[dist <= bande_px] = 255.0
    in_fade = (dist > bande_px) & (dist <= bande_px + fade_px)
    alpha[in_fade] = 255.0 * (1.0 - (dist[in_fade] - bande_px) / fade_px)

    # Zones données : toujours opaque
    alpha[~is_blanc] = 255.0

    return numpy.clip(alpha, 0, 255).astype(numpy.uint8)


def fill_sea_blanks(jpg_path, sea_jpg_path, zoomlevel=17, lat=46.0,
                    til_x_left=None, til_y_top=None, dico_sea=None):
    """
    Fusionne JPG source avec JPG EOX en utilisant le masque mer du mesh.
    Le masque mer est projeté depuis dico_sea (triangles réels) sur la tuile.

    Règles :
      - Pixel mer (triangle mesh)  → EOX RGB
      - Pixel avec données         → IGN conservé
      - Bande 1km depuis données   → EOX opaque (alpha=255)
      - Dégradé 1km au-delà        → alpha 255→0
      - Au large                   → alpha=0 (eau XP12 native)

    Retourne Image PIL RGBA.
    """
    try:
        src = numpy.array(Image.open(jpg_path).convert("RGB"),     dtype=numpy.uint16)
        eox = numpy.array(Image.open(sea_jpg_path).convert("RGB"), dtype=numpy.uint16)

        # Masque mer depuis le mesh (géographie réelle)
        if til_x_left is not None and til_y_top is not None and dico_sea is not None:
            is_mer = _sea_mask_from_dico(til_x_left, til_y_top, zoomlevel, dico_sea)
            if is_mer.shape != (src.shape[0], src.shape[1]):
                is_mer = numpy.array(
                    Image.fromarray(is_mer.astype(numpy.uint8)*255, "L").resize(
                        (src.shape[1], src.shape[0]), Image.NEAREST),
                    dtype=numpy.uint8) > 128
        else:
            # Fallback : détection par couleur si dico_sea absent
            som    = src[:,:,0] + src[:,:,1] + src[:,:,2]
            is_mer = (som >= WHITE_SUM_THRESHOLD)

        # Fusion RGB : mer → EOX, données → IGN
        result = src.copy()
        for ch in range(3):
            result[:,:,ch] = numpy.where(is_mer, eox[:,:,ch], src[:,:,ch])

        # Canal alpha : bande 1km opaque + dégradé 1km
        alpha = _build_sea_fade_alpha(is_mer, zoomlevel=zoomlevel, lat=lat)

        n = int(is_mer.sum())
        UI.vprint(2,
            f"   [SeaTex] {n:,} pixels mer (mesh) "
            f"({100*n/(src.shape[0]*src.shape[1]):.1f}%) "
            f"+ bande+dégradé 1km")

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
            _lat = float(getattr(tile, "lat", 46.0))
            return fill_sea_blanks(jpg_path, sea_path,
                                   zoomlevel=int(zoomlevel), lat=_lat,
                                   til_x_left=til_x_left, til_y_top=til_y_top,
                                   dico_sea=dico_sea)
        else:
            # JPG absent = tuile 100% mer sans données IGN
            # → EOX RGBA avec alpha=0 : XP12 affiche sa propre eau (pas de damier)
            eox = Image.open(sea_path).convert("RGBA")
            eox.putalpha(Image.new("L", eox.size, 0))
            UI.vprint(2, "   [SeaTex] Tuile 100% mer → alpha=0 (eau XP12 native)")
            return eox

    except Exception as e:
        UI.vprint(2, f"   [SeaTex] process_sea_fill erreur : {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# JPG-PATCH — Génération locale fond marin (pas de téléchargement)
# Appelé par O4_Tile_Utils.build_tile() AVANT les threads download/convert
# ─────────────────────────────────────────────────────────────────────────────

def _tile_folder(tile):
    """Retourne le nom de dossier standard Ortho4XP : ex. +46-003 ou +46+002"""
    sign_lat = "+" if tile.lat >= 0 else "-"
    sign_lon = "+" if tile.lon >= 0 else "-"
    return f"{sign_lat}{abs(int(tile.lat)):02d}{sign_lon}{abs(int(tile.lon)):03d}"


def generate_sea_jpg(tile, til_x_left, til_y_top, zoomlevel, provider_code,
                     neighbor_colors=None, jpeg_dir=None, dico_customzl=None):
    """
    Génère un JPG fond marin 4096×4096 dans :
      Orthophotos/JPG-Patch/+46-003/PATCH_{zoomlevel}/

    Couleur :
      - Moyenne RGB des JPG voisins si fournie (neighbor_colors = liste de tuples RGB)
      - Sinon : bleu maritime XP12 par défaut (42, 68, 95)
    Dégradé côte→large + grain subtil pour éviter le damier uniforme.

    Retourne le chemin JPG créé, ou None si erreur.
    Appelé par build_tile() dans O4_Tile_Utils.py.
    """
    try:
        # jpeg_file_dir_from_attributes construit Imagery_dir/imagery_dir/ZL{zl}
        # donc on génère dans PATCH_{zl}/ZL{zl}/ pour cohérence
        patch_dir = os.path.join(
            FNAMES.Imagery_dir,
            "JPG-Patch",
            _tile_folder(tile),
            f"JPG-Patch_{int(zoomlevel)}"
        )
        os.makedirs(patch_dir, exist_ok=True)

        # Format Ortho4XP standard : {tx}_{ty}_{provider}{zl}.jpg
        jpg_name = f"{int(til_x_left)}_{int(til_y_top)}_JPG-Patch{int(zoomlevel)}.jpg"
        jpg_path = os.path.join(patch_dir, jpg_name)

        if os.path.isfile(jpg_path):
            UI.vprint(1, f"   [SeaTex] JPG-Patch cache : {jpg_name}")
            return jpg_path

        # ── Couleur voisins depuis dico_customzl (provider mesh) ─────────────
        if not neighbor_colors and dico_customzl:
            neighbor_colors = []
            try:
                import O4_Imagery_Utils as _IMG
                for (dx, dy) in [(-16,0),(16,0),(0,-16),(0,16)]:
                    vx = int(til_x_left) + dx
                    vy = int(til_y_top)  + dy
                    # Trouver la clé mesh_zl correspondante
                    for key, val in dico_customzl.items():
                        (vtx, vty, vzl, vprov) = val
                        if vtx == vx and vty == vy and vzl == int(zoomlevel):
                            # Chercher le JPG dans le dossier du bon provider
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

        # ── Image 4096×4096 avec dégradé côte→large ──────────────────────────
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

        # ── Grain subtil (±4 niveaux) — seed déterministe par tuile ──────────
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
    Appelé par combine_textures() dans O4_Imagery_Utils.py
    pour pré-remplir le fond marin avant assemblage multi-source.
    """
    patch_dir = os.path.join(
        FNAMES.Imagery_dir,
        "JPG-Patch",
        _tile_folder(tile),
        f"JPG-Patch_{int(zoomlevel)}"
    )
    jpg_name = f"{int(til_x_left)}_{int(til_y_top)}_JPG-Patch{int(zoomlevel)}.jpg"
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
    """
    try:
        base_dir = os.path.join(FNAMES.Imagery_dir, "JPG-Patch")
    except Exception:
        return None
    if not os.path.isdir(base_dir):
        return None
    jpg_name = f"{int(til_x_left)}_{int(til_y_top)}_JPG-Patch{int(zoomlevel)}.jpg"
    for tile_folder in sorted(os.listdir(base_dir)):
        if not os.path.isdir(os.path.join(base_dir, tile_folder)):
            continue
        patch_dir = os.path.join(base_dir, tile_folder, f"JPG-Patch_{int(zoomlevel)}")
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
    Les tuiles voisines sont gérées par generate_sea_jpg au moment
    du build — pas de téléchargement réseau nécessaire.
    """
    pass
