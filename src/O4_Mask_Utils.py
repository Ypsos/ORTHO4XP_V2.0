# Version validée 30 avril 2026 — V2 XP12 (modification 8 mai 2026)
# MODIFICATION : build_mask() — en water_tech XP12, les tuiles purement
# maritimes (dico_sea sans dico_inland) ne génèrent plus de masque PNG.
# La mer XP12 est gérée nativement via WATER_COLOR_MASK dans le .ter.
# Seules les tuiles avec eau intérieure (lacs, rivières) produisent un masque.
import os
import sys
import time
import queue
from math import atan, ceil, floor
import numpy
from PIL import Image, ImageDraw, ImageFilter, ImageOps
import skfmm
import O4_DEM_Utils as DEM
import O4_File_Names as FNAMES
import O4_UI_Utils as UI
import O4_Geo_Utils as GEO
import O4_Imagery_Utils as IMG
import O4_OSM_Utils as OSM
import O4_Vector_Utils as VECT
import O4_Mesh_Utils as MESH
from O4_Parallel_Utils import parallel_execute

mask_altitude_above = 0.5
masks_build_slots = 4

################################################################################
def mask_name_for_texture(tile, til_x_left, til_y_top, zl, *args):
    if int(zl) < tile.mask_zl:
        return ""
    factor = 2 ** (zl - tile.mask_zl)
    m_til_x = (int(til_x_left / factor) // 16) * 16
    m_til_y = (int(til_y_top / factor) // 16) * 16
    rx = int((til_x_left - factor * m_til_x) / 16)
    ry = int((til_y_top - factor * m_til_y) / 16)
    return os.path.join(
        FNAMES.mask_dir(tile.lat, tile.lon),
        FNAMES.legacy_mask(m_til_x, m_til_y)
        )
################################################################################

################################################################################
def needs_mask(tile, til_x_left, til_y_top, zl, *args):
    if int(zl) < tile.mask_zl:
        return False
    factor = 2 ** (zl - tile.mask_zl)
    m_til_x = (int(til_x_left / factor) // 16) * 16
    m_til_y = (int(til_y_top / factor) // 16) * 16
    rx = int((til_x_left - factor * m_til_x) / 16)
    ry = int((til_y_top - factor * m_til_y) / 16)
    mask_file = os.path.join(
        FNAMES.mask_dir(tile.lat, tile.lon),
        FNAMES.legacy_mask(m_til_x, m_til_y)
        )
    if not os.path.isfile(mask_file):
        return False
    big_img = Image.open(mask_file)
    x0 = int(rx * 4096 / factor)
    y0 = int(ry * 4096 / factor)
    small_img = big_img.crop((x0, y0, x0 + 4096 // factor, y0 + 4096 // factor))
    small_array = numpy.array(small_img, dtype=numpy.uint8)
    if small_array.max() == 0:
        return False
    else:
        return small_img
################################################################################

################################################################################
def build_masks(tile, for_imagery=False):

    if UI.is_working:
        return 0
    UI.is_working = 1

    # Which grey level for inland water equivalent ?
    im = Image.open(os.path.join(FNAMES.Utils_dir, "water_transition.png"))
    sea_level = im.getpixel((0, 127 * (1 - min(1, 0.1 + tile.ratio_water))))
    del im

    UI.red_flag = False
    UI.logprint(
        "Step 2.5 for tile lat=", tile.lat, ", lon=", tile.lon, ": starting."
    )
    UI.vprint(
        0,
        "\nStep 2.5 : Building masks for tile "
        + FNAMES.short_latlon(tile.lat, tile.lon)
        + " : \n--------\n",
    )

    timer = time.time()

    # Check we have a mesh for this tile
    if not os.path.exists(FNAMES.mesh_file(tile.build_dir, tile.lat, tile.lon)):
        UI.lvprint(
            0,
            "ERROR: Mesh file ",
            FNAMES.mesh_file(tile.build_dir, tile.lat, tile.lon),
            "absent.",
        )
        UI.exit_message_and_bottom_line("")
        return 0

    # Check or create dest dir
    dest_dir = (
        FNAMES.mask_dir(tile.lat, tile.lon)
        if not for_imagery
        else os.path.join(
            FNAMES.mask_dir(tile.lat, tile.lon), "Combined_imagery"
        )
    )
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)

    # Select nearby meshes
    mesh_list = select_neighbor_meshes(tile)

    # Delete old masks
    UI.vprint(1, "-> Deleting existing masks")
    delete_old_masks_in_tile(tile, dest_dir)

    # Record water tris form mesh (and portions of nearby meshes)
    UI.vprint(1, "-> Reading mesh data")
    (dico_sea, dico_inland) = record_water_tris(tile, )

    UI.vprint(1, "-> Construction of the masks")

    if tile.masks_use_DEM_too:
        try:
            fill_nodata = tile.fill_nodata or "to zero"
            source = (
                (";" in tile.custom_dem) and tile.custom_dem.split(";")[0]
            ) or tile.custom_dem
            tile.dem = DEM.DEM(
                tile.lat, tile.lon, source, fill_nodata, info_only=False
            )
        except:
            UI.exit_message_and_bottom_line(
                "\nERROR: Could not determine the appropriate elevation source.",
                " Please check your custom_dem entry."
            )
            return 0

    #################################
    def build_mask(til_x, til_y):

        (til_x_min, til_y_min) = GEO.wgs84_to_orthogrid(
            tile.lat + 1, tile.lon, tile.mask_zl)
        (til_x_max, til_y_max) = GEO.wgs84_to_orthogrid(
            tile.lat, tile.lon + 1, tile.mask_zl)
        if (til_x < til_x_min or til_x > til_x_max or til_y < til_y_min or
            til_y > til_y_max):
            return 1

        pre_mask = build_water_pre_mask(til_x, til_y, mesh_list, dico_sea,
                                         dico_inland, sea_level, tile)
        if tile.masks_use_DEM_too:
            dem_array = build_dem_pre_mask(til_x, til_y, tile)
            pre_mask = numpy.maximum(pre_mask, dem_array)
            del(dem_array)

        if tile.masks_custom_extent:
            custom_array = build_custom_pre_mask(til_x, til_y, sea_level, tile)

        if (pre_mask.max() == 0) and (
                not tile.masks_custom_extent or custom_array.max() == 0):
            return 1


        blured_mask = blur_mask(pre_mask, tile, sea_level)

        # Terre forcée à 255, transition côtière conservée naturellement
        blured_mask = numpy.maximum(
            (pre_mask > 0).astype(numpy.uint8) * 255,
            blured_mask
        )
        blured_mask = blured_mask[1024 : 4096 + 1024, 1024 : 4096 + 1024]

        if tile.masks_custom_extent:
            blured_mask = numpy.maximum(blured_mask, custom_mask)

        if not (blured_mask.max() == 0 or blured_mask.min() >= 250):
            mask_im = Image.fromarray(blured_mask)
            _mask_png_path = os.path.join(dest_dir, FNAMES.legacy_mask(til_x, til_y))
            mask_im.save(_mask_png_path)
            del blured_mask

            # Distance masks for bathymetry cut-off
            if (tile.distance_masks_too):
                pre_mask = (pre_mask > 0).astype(float) * 2 - 1
                band = 255 / 2**(16 - tile.mask_zl)
                dist_array = skfmm.distance(pre_mask, narrow = band)
                if (isinstance(dist_array, numpy.ma.core.MaskedArray)):
                    dist_array = dist_array.filled(-99999)
                dist_array[pre_mask > 0] = 0
                del(pre_mask)
                dist_array = dist_array[1024 : 4096 + 1024, 1024 : 4096 + 1024]
                dist_array = dist_array * (2**(16 - tile.mask_zl))
                dist_array = numpy.minimum(-numpy.minimum(dist_array, 0), 255)
                dist_array = dist_array.astype(numpy.uint8)
                masks_im = Image.fromarray(dist_array)
                masks_im.save(os.path.join(
                    dest_dir, FNAMES.distance_mask(til_x, til_y)))
                UI.vprint(1, "   Created", FNAMES.legacy_mask(til_x, til_y),
                "and", FNAMES.distance_mask(til_x, til_y))
            else:
                UI.vprint(1, "   Created", FNAMES.legacy_mask(til_x, til_y))
        return 1
    #################################

    masks_queue = queue.Queue()
    for key in dico_sea:
        masks_queue.put(key)
    dico_progress = {"done": 0, "bar": 1}

    parallel_execute(build_mask, masks_queue, masks_build_slots,
                     progress=dico_progress)

    UI.progress_bar(1, 100)

    UI.timings_and_bottom_line(timer)
    UI.logprint(
        "Step 2.5 for tile lat=", tile.lat, ", lon=", tile.lon, ": normal exit."
    )
    UI.exit_message_and_bottom_line()
    return 1
################################################################################

################################################################################
def select_neighbor_meshes(tile):
    mesh_list = []
    for close_lat in range(tile.lat - 1, tile.lat + 2):
        for close_lon in range(tile.lon - 1, tile.lon + 2):
            close_build_dir = (tile.build_dir if tile.grouped
                else tile.build_dir.replace(
                    FNAMES.tile_dir(tile.lat, tile.lon),
                    FNAMES.tile_dir(close_lat, close_lon),
                )
            )
            close_mesh_file_name = FNAMES.mesh_file(
                close_build_dir, close_lat, close_lon
            )
            if os.path.isfile(close_mesh_file_name):
                mesh_list.append(close_mesh_file_name)
    return mesh_list

################################################################################
def delete_old_masks_in_tile(tile, dest_dir):

    (til_x_min, til_y_min) = GEO.wgs84_to_orthogrid(
        tile.lat + 1, tile.lon, tile.mask_zl)
    (til_x_max, til_y_max) = GEO.wgs84_to_orthogrid(
        tile.lat, tile.lon + 1, tile.mask_zl)

    for til_x in range(til_x_min, til_x_max + 1, 16):
        for til_y in range(til_y_min, til_y_max + 1, 16):
            # Supprimer mask PNG classique
            try:
                os.remove(
                    os.path.join(dest_dir, FNAMES.legacy_mask(til_x, til_y))
                )
            except:
                pass
            # Supprimer mask distance _dist.png
            try:
                dist_name = FNAMES.legacy_mask(til_x, til_y).replace('.png', '_dist.png')
                os.remove(os.path.join(dest_dir, dist_name))
            except:
                pass
            # Supprimer masks synthétiques temporaires _synth_*.png
            try:
                synth_name = f"_synth_{til_x}_{til_y}.png"
                os.remove(os.path.join(dest_dir, synth_name))
            except:
                pass

################################################################################
def build_water_pre_mask(til_x, til_y, mesh_list, dico_sea, dico_inland,
                         sea_level, tile):
    (latm0, lonm0) = GEO.gtile_to_wgs84(til_x, til_y, tile.mask_zl)
    (px0, py0) = GEO.wgs84_to_pix(latm0, lonm0, tile.mask_zl)
    px0 -= 1024
    py0 -= 1024

    mask_im = Image.new("L", (4096 + 2 * 1024, 4096 + 2 * 1024), "black")
    mask_draw = ImageDraw.Draw(mask_im)

    for mesh_file_name in mesh_list:
        latlonstr = mesh_file_name.split(".mes")[-2][-7:]
        lathere = int(latlonstr[0:3])
        lonhere = int(latlonstr[3:7])
        (px1, py1) = GEO.wgs84_to_pix(lathere, lonhere, tile.mask_zl)
        (px2, py2) = GEO.wgs84_to_pix(lathere, lonhere + 1, tile.mask_zl)
        (px3, py3) = GEO.wgs84_to_pix(lathere + 1, lonhere + 1, tile.mask_zl)
        (px4, py4) = GEO.wgs84_to_pix(lathere + 1, lonhere, tile.mask_zl)
        px1 -= px0; px2 -= px0; px3 -= px0; px4 -= px0
        py1 -= py0; py2 -= py0; py3 -= py0; py4 -= py0
        mask_draw.polygon([(px1, py1), (px2, py2), (px3, py3), (px4, py4)], fill="white")

    if (til_x, til_y) in dico_inland:
        for (lat1, lon1, lat2, lon2, lat3, lon3) in dico_inland[(til_x, til_y)]:
            (px1, py1) = GEO.wgs84_to_pix(lat1, lon1, tile.mask_zl)
            (px2, py2) = GEO.wgs84_to_pix(lat2, lon2, tile.mask_zl)
            (px3, py3) = GEO.wgs84_to_pix(lat3, lon3, tile.mask_zl)
            px1 -= px0; px2 -= px0; px3 -= px0
            py1 -= py0; py2 -= py0; py3 -= py0
            mask_draw.polygon([(px1, py1), (px2, py2), (px3, py3)], fill=sea_level)

    if (til_x, til_y) in dico_sea:
        for (lat1, lon1, lat2, lon2, lat3, lon3) in dico_sea[(til_x, til_y)]:
            (px1, py1) = GEO.wgs84_to_pix(lat1, lon1, tile.mask_zl)
            (px2, py2) = GEO.wgs84_to_pix(lat2, lon2, tile.mask_zl)
            (px3, py3) = GEO.wgs84_to_pix(lat3, lon3, tile.mask_zl)
            px1 -= px0; px2 -= px0; px3 -= px0
            py1 -= py0; py2 -= py0; py3 -= py0
            mask_draw.polygon([(px1, py1), (px2, py2), (px3, py3)], fill="black")

    del mask_draw
    img_array = numpy.array(mask_im, dtype=numpy.uint8)

    # Correction du bug : si c'est presque tout de la mer, on force tout en noir
    if (img_array < 50).sum() > 0.85 * img_array.size:
        img_array[:] = 0

    return img_array

#####################

################################################################################
def build_dem_pre_mask(til_x, til_y, tile):
    (latm0, lonm0) = GEO.gtile_to_wgs84(til_x, til_y, tile.mask_zl)
    (px0, py0) = GEO.wgs84_to_pix(latm0, lonm0, tile.mask_zl)
    px0 -= 1024
    py0 -= 1024
    # computing the part of the mask coming from the DEM:
    (latmax, lonmin) = GEO.pix_to_wgs84(px0, py0, tile.mask_zl)
    (latmin, lonmax) = GEO.pix_to_wgs84(px0 + 6144, py0 + 6144, tile.mask_zl)
    (x03857, y03857) = GEO.geo_to_webm(lonmin, latmax)
    (x13857, y13857) = GEO.geo_to_webm(lonmax, latmin)
    (
        (lonmin, lonmax, latmin, latmax),
        demarr4326,
    ) = tile.dem.super_level_set(
        mask_altitude_above, (lonmin, lonmax, latmin, latmax)
    )
    if demarr4326.any():
        demim4326 = Image.fromarray(
            demarr4326.astype(numpy.uint8) * 255
        )
        del demarr4326
        s_bbox = (lonmin, latmax, lonmax, latmin)
        t_bbox = (x03857, y03857, x13857, y13857)
        demim3857 = IMG.gdalwarp_alternative(
            s_bbox, "4326", demim4326, t_bbox, "3857", (6144, 6144)
        )
        demim3857 = demim3857.filter(
            ImageFilter.GaussianBlur(0.3 * 2 ** (tile.mask_zl - 14))
        )  # slight increase of area
        dem_array = (
            numpy.array(demim3857, dtype=numpy.uint8) > 0
        ).astype(numpy.uint8) * 255
        del demim3857
        del demim4326
    else:
        dem_array = numpy.zeros((6144, 6144), dtype=numpy.uint8)
    return dem_array
################################################################################

################################################################################
def build_custom_pre_mask(til_x, til_y, sea_level, tile):
    custom_mask_array = numpy.zeros((4096, 4096), dtype=numpy.uint8)
    (latm0, lonm0) = GEO.gtile_to_wgs84(til_x, til_y, tile.mask_zl)
    (latm1, lonm1) = GEO.gtile_to_wgs84(til_x + 16, til_y + 16, tile.mask_zl)
    bbox_4326 = (lonm0, latm0, lonm1, latm1)
    masks_im = IMG.has_data(
        bbox_4326,
        tile.masks_custom_extent,
        True,
        mask_size=(4096, 4096),
        is_sharp_resize=False,
        is_mask_layer=False,
    )
    if masks_im:
        custom_mask_array = (
            numpy.array(masks_im, dtype=numpy.uint8) * (sea_level / 255)
        ).astype(numpy.uint8)

    return custom_mask_array
################################################################################

################################################################################
def record_water_tris(tile):
    mesh_list = []
    for close_lat in range(tile.lat - 1, tile.lat + 2):
        for close_lon in range(tile.lon - 1, tile.lon + 2):
            close_build_dir = (
                tile.build_dir
                if tile.grouped
                else tile.build_dir.replace(
                    FNAMES.tile_dir(tile.lat, tile.lon),
                    FNAMES.tile_dir(close_lat, close_lon),
                )
            )
            close_mesh_file_name = FNAMES.mesh_file(
                close_build_dir, close_lat, close_lon
            )
            if os.path.isfile(close_mesh_file_name):
                mesh_list.append(close_mesh_file_name)
    ####################
    dico_sea = {}
    dico_inland = {}
    ####################
    [til_x_min, til_y_min] = GEO.wgs84_to_orthogrid(
        tile.lat + 1, tile.lon, tile.mask_zl
    )
    [til_x_max, til_y_max] = GEO.wgs84_to_orthogrid(
        tile.lat, tile.lon + 1, tile.mask_zl
    )
    UI.vprint(1, "-> Reading mesh data")
    for mesh_file_name in mesh_list:
        try:
            f_mesh = open(mesh_file_name, "r")
            UI.vprint(1, "   * ", mesh_file_name)
        except:
            UI.lvprint(
                1, "Mesh file ", mesh_file_name, " could not be read. Skipped."
            )
            continue
        mesh_version = float(f_mesh.readline().strip().split()[-1])
        has_water = 7 if mesh_version >= 1.3 else 3
        for i in range(3):
            f_mesh.readline()
        nbr_pt_in = int(f_mesh.readline())
        pt_in = numpy.zeros(5 * nbr_pt_in, "float")
        for i in range(0, nbr_pt_in):
            pt_in[5 * i : 5 * i + 3] = [
                float(x) for x in f_mesh.readline().split()[:3]
            ]
        for i in range(0, 3):
            f_mesh.readline()
        for i in range(0, nbr_pt_in):
            pt_in[5 * i + 3 : 5 * i + 5] = [
                float(x) for x in f_mesh.readline().split()[:2]
            ]
        for i in range(0, 2):  # skip 2 lines
            f_mesh.readline()
        nbr_tri_in = int(f_mesh.readline())  # read nbr of tris
        step_stones = nbr_tri_in // 100
        percent = -1
        UI.vprint(
            2,
            " Attribution process of masks buffers to water triangles for "
            + str(mesh_file_name)
            + ".",
        )
        for i in range(0, nbr_tri_in):
            if i % step_stones == 0:
                percent += 1
                UI.progress_bar(1, int(percent * 5 / 10))
                if UI.red_flag:
                    UI.exit_message_and_bottom_line()
                    return 0
            (n1, n2, n3, tri_type) = [
                int(x) - 1 for x in f_mesh.readline().split()[:4]
            ]
            tri_type += 1
            if (
                (not tri_type)
                or (not (tri_type & has_water))
                or (
                    (tri_type & has_water) < 2 and not tile.use_masks_for_inland
                )
            ):
                continue
            (lon1, lat1) = pt_in[5 * n1 : 5 * n1 + 2]
            (lon2, lat2) = pt_in[5 * n2 : 5 * n2 + 2]
            (lon3, lat3) = pt_in[5 * n3 : 5 * n3 + 2]
            bary_lat = (lat1 + lat2 + lat3) / 3
            bary_lon = (lon1 + lon2 + lon3) / 3
            (til_x, til_y) = GEO.wgs84_to_orthogrid(
                bary_lat, bary_lon, tile.mask_zl
            )
            if (
                til_x < til_x_min - 16
                or til_x > til_x_max + 16
                or til_y < til_y_min - 16
                or til_y > til_y_max + 16
            ):
                continue
            (til_x2, til_y2) = GEO.wgs84_to_orthogrid(
                bary_lat, bary_lon, tile.mask_zl + 2
            )
            a = (til_x2 // 16) % 4
            b = (til_y2 // 16) % 4
            if (til_x, til_y) in dico_sea:
                dico_sea[(til_x, til_y)].append(
                    (lat1, lon1, lat2, lon2, lat3, lon3)
                )
            else:
                dico_sea[(til_x, til_y)] = [
                    (lat1, lon1, lat2, lon2, lat3, lon3)
                ]
            if a == 0:
                if (til_x - 16, til_y) in dico_sea:
                    dico_sea[(til_x - 16, til_y)].append(
                        (lat1, lon1, lat2, lon2, lat3, lon3)
                    )
                else:
                    dico_sea[(til_x - 16, til_y)] = [
                        (lat1, lon1, lat2, lon2, lat3, lon3)
                    ]
                if b == 0:
                    if (til_x - 16, til_y - 16) in dico_sea:
                        dico_sea[(til_x - 16, til_y - 16)].append(
                            (lat1, lon1, lat2, lon2, lat3, lon3)
                        )
                    else:
                        dico_sea[(til_x - 16, til_y - 16)] = [
                            (lat1, lon1, lat2, lon2, lat3, lon3)
                        ]
                if b == 3:
                    if (til_x - 16, til_y + 16) in dico_sea:
                        dico_sea[(til_x - 16, til_y + 16)].append(
                            (lat1, lon1, lat2, lon2, lat3, lon3)
                        )
                    else:
                        dico_sea[(til_x - 16, til_y + 16)] = [
                            (lat1, lon1, lat2, lon2, lat3, lon3)
                        ]
            if a == 3:
                if (til_x + 16, til_y) in dico_sea:
                    dico_sea[(til_x + 16, til_y)].append(
                        (lat1, lon1, lat2, lon2, lat3, lon3)
                    )
                else:
                    dico_sea[(til_x + 16, til_y)] = [
                        (lat1, lon1, lat2, lon2, lat3, lon3)
                    ]
                if b == 0:
                    if (til_x + 16, til_y - 16) in dico_sea:
                        dico_sea[(til_x + 16, til_y - 16)].append(
                            (lat1, lon1, lat2, lon2, lat3, lon3)
                        )
                    else:
                        dico_sea[(til_x + 16, til_y - 16)] = [
                            (lat1, lon1, lat2, lon2, lat3, lon3)
                        ]
                if b == 3:
                    if (til_x + 16, til_y + 16) in dico_sea:
                        dico_sea[(til_x + 16, til_y + 16)].append(
                            (lat1, lon1, lat2, lon2, lat3, lon3)
                        )
                    else:
                        dico_sea[(til_x + 16, til_y + 16)] = [
                            (lat1, lon1, lat2, lon2, lat3, lon3)
                        ]
            if b == 0:
                if (til_x, til_y - 16) in dico_sea:
                    dico_sea[(til_x, til_y - 16)].append(
                        (lat1, lon1, lat2, lon2, lat3, lon3)
                    )
                else:
                    dico_sea[(til_x, til_y - 16)] = [
                        (lat1, lon1, lat2, lon2, lat3, lon3)
                    ]
            if b == 3:
                if (til_x, til_y + 16) in dico_sea:
                    dico_sea[(til_x, til_y + 16)].append(
                        (lat1, lon1, lat2, lon2, lat3, lon3)
                    )
                else:
                    dico_sea[(til_x, til_y + 16)] = [
                        (lat1, lon1, lat2, lon2, lat3, lon3)
                    ]
        f_mesh.close()
        if not tile.use_masks_for_inland:
            UI.vprint(2, "   Taking care of inland water near shoreline")
            f_mesh = open(mesh_file_name, "r")
            for i in range(0, 4):
                f_mesh.readline()
            nbr_pt_in = int(f_mesh.readline())
            for i in range(0, 2 * nbr_pt_in + 5):
                f_mesh.readline()
            nbr_tri_in = int(f_mesh.readline())  # read nbr of tris
            step_stones = nbr_tri_in // 100
            percent = -1
            for i in range(0, nbr_tri_in):
                if i % step_stones == 0:
                    percent += 1
                    UI.progress_bar(1, int(percent * 5 / 10))
                    if UI.red_flag:
                        UI.exit_message_and_bottom_line()
                        return 0
                (n1, n2, n3, tri_type) = [
                    int(x) - 1 for x in f_mesh.readline().split()[:4]
                ]
                tri_type += 1
                if not (tri_type & has_water) == 1:
                    continue
                (lon1, lat1) = pt_in[5 * n1 : 5 * n1 + 2]
                (lon2, lat2) = pt_in[5 * n2 : 5 * n2 + 2]
                (lon3, lat3) = pt_in[5 * n3 : 5 * n3 + 2]
                bary_lat = (lat1 + lat2 + lat3) / 3
                bary_lon = (lon1 + lon2 + lon3) / 3
                (til_x, til_y) = GEO.wgs84_to_orthogrid(
                    bary_lat, bary_lon, tile.mask_zl
                )
                if (
                    til_x < til_x_min - 16
                    or til_x > til_x_max + 16
                    or til_y < til_y_min - 16
                    or til_y > til_y_max + 16
                ):
                    continue
                (til_x2, til_y2) = GEO.wgs84_to_orthogrid(
                    bary_lat, bary_lon, tile.mask_zl + 2
                )
                a = (til_x2 // 16) % 4
                b = (til_y2 // 16) % 4
                # Here an inland water tri is added ONLY if sea water tri were
                # already added for this mask extent
                if (til_x, til_y) in dico_sea:
                    if (til_x, til_y) in dico_inland:
                        dico_inland[(til_x, til_y)].append(
                            (lat1, lon1, lat2, lon2, lat3, lon3)
                        )
                    else:
                        dico_inland[(til_x, til_y)] = [
                            (lat1, lon1, lat2, lon2, lat3, lon3)
                        ]
            f_mesh.close()

    return (dico_sea, dico_inland)
################################################################################

################################################################################
def blur_mask(img_array, tile, sea_level):
    ##########################################
    def transition_profile(ratio, ttype):
        if ttype == "spline":
            return 3 * ratio ** 2 - 2 * ratio ** 3
        elif ttype == "linear":
            return ratio
        elif ttype == "parabolic":
            return 2 * ratio - ratio ** 2
    ##########################################
    pxscal = GEO.webmercator_pixel_size(tile.lat + 0.5, tile.mask_zl)
    if tile.masking_mode == "sand":
        blur_width = int(tile.masks_width / pxscal)
    elif tile.masking_mode == "rocks":
        blur_width = int(tile.masks_width / (2 * pxscal))
    elif tile.masking_mode == "3steps":
        blur_width = [int(L / pxscal) for L in tile.masks_width]
    # Sand mode — GaussianBlur PIL (rapide à tout ZL)
    if tile.masking_mode == "sand" and blur_width:
        b_img_array = numpy.array(
            Image.fromarray(img_array)
            .convert("L")
            .filter(ImageFilter.GaussianBlur(radius=blur_width)),
            dtype=numpy.uint8,
        )
    # Rocks mode
    elif tile.masking_mode == "rocks" and blur_width:
        # slight increase of the mask, then gaussian blur, nonlinear map and
        # a tiny bit of smoothing again on a short scale along the shore
        b_img_array = (
            numpy.array(
                Image.fromarray(img_array)
                .convert("L")
                .filter(ImageFilter.GaussianBlur(blur_width / 3)),
                dtype=numpy.uint8,
            )
            > 0
        ).astype(numpy.uint8) * 255
        b_img_array = numpy.array(
            Image.fromarray(b_img_array)
            .convert("L")
            .filter(ImageFilter.GaussianBlur(blur_width)),
            dtype=numpy.uint8,
        )
        # nonlinear map
        b_img_array = numpy.array(
            255
            * numpy.sin(
                numpy.minimum(b_img_array, 127) / 127 * numpy.pi / 2
            )
            ** 2,
            dtype=numpy.uint8,
        )
        b_img_array = numpy.array(
            Image.fromarray(b_img_array)
            .convert("L")
            .filter(ImageFilter.GaussianBlur(blur_width / 3)),
            dtype=numpy.uint8,
        )
    # 3steps mode
    elif tile.masking_mode == "3steps" and blur_width:
        transin = blur_width[0]
        midzone = blur_width[1]
        transout = blur_width[2]
        # We first build the "sea_level" zone
        sea_b_radius = midzone / 3
        b_mask_array = (
            numpy.array(
                Image.fromarray(img_array)
                .convert("L")
                .filter(ImageFilter.GaussianBlur(sea_b_radius)),
                dtype=numpy.uint8,
            )
            > 0
        ).astype(numpy.uint8) * 255
        b_mask_array = (
            numpy.array(
                Image.fromarray(b_mask_array)
                .convert("L")
                .filter(ImageFilter.GaussianBlur(sea_b_radius)),
                dtype=numpy.uint8,
            )
            == 255
        ).astype(numpy.uint8) * 255
        # Transition from 255 to sea_level in transin meters
        stepsin = int(transin / 3)
        b_img_array = numpy.array(img_array)
        for i in range(stepsin):
            value = 255 - (255 - sea_level) * transition_profile(
                (i + 1) / stepsin, "spline"
            )
            b_mask_array = (
                numpy.array(
                    Image.fromarray(b_mask_array)
                    .convert("L")
                    .filter(ImageFilter.GaussianBlur(1)),
                    dtype=numpy.uint8,
                )
                > 0
            ).astype(numpy.uint8) * 255
            b_img_array[b_img_array == 0] = (
                b_mask_array[b_img_array == 0] > 0
            ) * value
        sea_b_radius_buffered = (midzone + transout) / 3
        b_mask_array = (
            numpy.array(
                Image.fromarray(b_mask_array)
                .convert("L")
                .filter(ImageFilter.GaussianBlur(sea_b_radius_buffered)),
                dtype=numpy.uint8,
            )
            > 0
        ).astype(numpy.uint8) * 255
        b_mask_array = (
            numpy.array(
                Image.fromarray(b_mask_array)
                .convert("L")
                .filter(
                    ImageFilter.GaussianBlur(
                        sea_b_radius_buffered - sea_b_radius
                    )
                ),
                dtype=numpy.uint8,
            )
            == 255
        ).astype(numpy.uint8) * 255
        b_img_array[(b_img_array == 0) * (b_mask_array != 0)] = sea_level
        # Finally the transition to the X-Plane sea
        # We go from sea_level to 0 in transout meters
        stepsout = int(transout / 3)
        for i in range(stepsout):
            value = sea_level * (
                1 - transition_profile((i + 1) / stepsout, "linear")
            )
            b_mask_array = (
                numpy.array(
                    Image.fromarray(b_mask_array)
                    .convert("L")
                    .filter(ImageFilter.GaussianBlur(1)),
                    dtype=numpy.uint8,
                )
                > 0
            ).astype(numpy.uint8) * 255
            b_img_array[(b_img_array == 0) * (b_mask_array != 0)] = value
            UI.vprint(2, value)
        # To smoothen the thresolding introduced above we do a global short
        # extent gaussian blur
        b_img_array = numpy.array(
            Image.fromarray(b_img_array)
            .convert("L")
            .filter(ImageFilter.GaussianBlur(2)),
            dtype=numpy.uint8,
        )
    else:
        # Just a (futile) copy
        b_img_array = numpy.array(img_array)

    return b_img_array
################################################################################

################################################################################
def triangulation_to_image(name, pixel_size, grid_size_or_bbox):
    f_node = open(name + ".1.node", "r")
    nbr_pt = int(f_node.readline().split()[0])
    vertices = numpy.zeros(2 * nbr_pt)
    for i in range(0, nbr_pt):
        # Triangle .node files have the node index starting from 1
        data = f_node.readline().split()
        vertices[2 * i] = float(data[1])
        vertices[2 * i + 1] = float(data[2])
    f_node.close()
    f_ele = open(name + ".1.ele", "r")
    nbr_tri = int(f_ele.readline().split()[0])
    if isinstance(grid_size_or_bbox, tuple):
        (xmin, ymin, xmax, ymax) = grid_size_or_bbox
        grid_size = (
            round((xmax - xmin) / pixel_size),
            round((ymax - ymin) / pixel_size),
        )
    else:
        grid_size = grid_size_or_bbox
        xmin = vertices[0::2].min()
        xmax = vertices[0::2].max()
        ymin = vertices[1::2].min()
        ymax = vertices[1::2].max()
    mask_im = Image.new("L", grid_size, "black")
    mask_draw = ImageDraw.Draw(mask_im)
    for i in range(0, nbr_tri):
        data = f_ele.readline().split()
        n1 = int(data[1]) - 1
        n2 = int(data[2]) - 1
        n3 = int(data[3]) - 1
        px1 = round((vertices[2 * n1] - xmin) / pixel_size)
        py1 = round((ymax - vertices[2 * n1 + 1]) / pixel_size)
        px2 = round((vertices[2 * n2] - xmin) / pixel_size)
        py2 = round((ymax - vertices[2 * n2 + 1]) / pixel_size)
        px3 = round((vertices[2 * n3] - xmin) / pixel_size)
        py3 = round((ymax - vertices[2 * n3 + 1]) / pixel_size)
        mask_draw.polygon([(px1, py1), (px2, py2), (px3, py3)], fill="white")
    f_ele.close()
    del mask_draw
    return mask_im
################################################################################

################################################################################
def build_mask_from_triangulation(
    name,
    pixel_size,
    grid_size_or_bbox,
    mask_width,
    buffer_width,
    query=False,
):
    mask_im = triangulation_to_image(name, pixel_size, grid_size_or_bbox)
    img_array = numpy.array(mask_im, dtype=numpy.uint8)
    (xmin, ymin) = (img_array.nonzero()[1].min(), img_array.nonzero()[0].min())
    (xmax, ymax) = (img_array.nonzero()[1].max(), img_array.nonzero()[0].max())
    buffer = ""
    try:
        f = open(name + ".ext", "r")
        for line in f.readlines():
            if ("#" not in line) or query:
                continue
            if "Initially" not in line:
                buffer += "# Initially c" + line[3:]
            else:
                buffer += line
        f.close()
    except:
        pass
    buffer += "# Created with : " + " ".join(sys.argv) + "\n"
    buffer += (
        "mask_bounds="
        + str(xmin)
        + ","
        + str(ymin)
        + ","
        + str(xmax)
        + ","
        + str(ymax)
        + "\n"
    )
    f = open(name + ".ext", "w")
    f.write(buffer)
    f.close()
    if buffer_width:
        UI.vprint(1, "Buffer of the mask...")
        mask_im = mask_im.filter(ImageFilter.GaussianBlur(buffer_width / 4))
        if buffer_width > 0:
            mask_im = Image.fromarray(
                (numpy.array(mask_im, dtype=numpy.uint8) > 0).astype(
                    numpy.uint8
                )
                * 255
            )
        else:  # buffer width can be negative
            mask_im = Image.fromarray(
                (numpy.array(mask_im, dtype=numpy.uint8) == 255).astype(
                    numpy.uint8
                )
                * 255
            )
    if mask_width:
        mask_width += 1
        UI.vprint(1, "Blur of the mask...")
        img_array = numpy.array(mask_im, dtype=numpy.uint8)
        kernel = numpy.ones(int(mask_width)) / int(mask_width)
        kernel = numpy.array(range(1, 2 * mask_width))
        kernel[mask_width:] = range(mask_width - 1, 0, -1)
        kernel = kernel / mask_width ** 2
        for i in range(0, len(img_array)):
            img_array[i] = numpy.convolve(img_array[i], kernel, "same")
        img_array = img_array.transpose()
        for i in range(0, len(img_array)):
            img_array[i] = numpy.convolve(img_array[i], kernel, "same")
        img_array = img_array.transpose()
        # --- NETTOYAGE ANTI-TRIANGLES ---
        img_array[img_array < 15] = 0    # Force le noir pur en mer (indispensable)
        img_array[img_array > 240] = 255 # Force le blanc pur sur terre
        img_array = numpy.array(img_array, dtype=numpy.uint8)
        mask_im = Image.fromarray(img_array)
    mask_im.save(name + ".png")
    for f in [
        name + ".poly",
        name + ".node",
        name + ".1.node",
        name + ".1.ele",
    ]:
        try:
            os.remove(f)
        except:
            pass
    print("Done!")
################################################################################
