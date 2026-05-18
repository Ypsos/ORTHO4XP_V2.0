import os
import time
import shutil
import queue
import threading
import math
from PIL import Image
import O4_UI_Utils as UI
import O4_File_Names as FNAMES
import O4_Imagery_Utils as IMG
import O4_Vector_Map as VMAP
import O4_Mesh_Utils as MESH
import O4_Mask_Utils as MASK
import O4_DSF_Utils as DSF
import O4_Overlay_Utils as OVL
from O4_Parallel_Utils import parallel_launch, parallel_join

max_convert_slots = 4
skip_downloads = False
skip_converts = False

# Largeur de la bande côtière vers le large pour EOX si JPG absent
# Fond marin visible satellite ≈ 2km depuis la côte
SEA_BAND_KM = 2.0


################################################################################
def build_sea_texture_set(tile, dico_customzl):
    """
    Lit le mesh et retourne un set de texture_attributes correspondant à des
    triangles tri_type=2 (mer) situés dans la bande SEA_BAND_KM depuis le bord
    des JPG source existants, ET sans JPG source disponible.
    Appelé dans build_tile() avant les threads — zéro deadlock.
    """
    sea_set = set()
    try:
        import O4_Geo_Utils as GEO
        mesh_file = FNAMES.mesh_file(tile.build_dir, tile.lat, tile.lon)
        if not os.path.isfile(mesh_file):
            return sea_set

        (mesh_version, nbr_nodes, node_coords, nbr_tris,
         tri_idx, tri_types) = MESH.read_mesh_file(mesh_file)

        has_water = 7 if (mesh_version >= 1.3) else 3

        band_deg_lat = SEA_BAND_KM / 111.12
        band_deg_lon = SEA_BAND_KM / (
            111.12 * math.cos(math.radians(tile.lat + 0.5))
        )

        # Collecter les positions lon/lat approximatives des JPG existants
        existing_jpg_pos = []
        for key, tex_attr in dico_customzl.items():
            (til_x, til_y, zl, provider_code) = tex_attr
            layers = IMG.local_combined_providers_dict.get(provider_code, [])
            for rlayer in layers:
                lc = rlayer.get("layer_code", "")
                if lc not in IMG.providers_dict:
                    continue
                fname = FNAMES.jpeg_file_name_from_attributes(
                    til_x, til_y, zl, lc)
                fdir = FNAMES.jpeg_file_dir_from_attributes(
                    tile.lat, tile.lon, zl, IMG.providers_dict[lc])
                if os.path.isfile(os.path.join(fdir, fname)):
                    n = 2 ** zl
                    lon_approx = til_x / n * 360.0 - 180.0
                    lat_approx = math.degrees(
                        math.atan(math.sinh(math.pi * (1 - 2 * til_y / n)))
                    )
                    existing_jpg_pos.append((lat_approx, lon_approx))
                break

        if not existing_jpg_pos:
            return sea_set

        # Pour chaque triangle mer sans JPG dans la bande
        for i in range(nbr_tris):
            t = tri_types[i] & has_water
            t = t and (2 * (t > 1 or tile.use_masks_for_inland) or 1)
            if t != 2:
                continue

            (n1, n2, n3) = tri_idx[3 * i: 3 * i + 3]
            bary_lon = (
                node_coords[5*n1] + node_coords[5*n2] + node_coords[5*n3]
            ) / 3
            bary_lat = (
                node_coords[5*n1+1] + node_coords[5*n2+1] + node_coords[5*n3+1]
            ) / 3

            key = GEO.wgs84_to_orthogrid(bary_lat, bary_lon, tile.mesh_zl)
            if key not in dico_customzl:
                continue

            tex_attr = dico_customzl[key]
            (til_x, til_y, zl, provider_code) = tex_attr

            # Vérifier que le JPG est absent
            jpg_exists = False
            layers = IMG.local_combined_providers_dict.get(provider_code, [])
            for rlayer in layers:
                lc = rlayer.get("layer_code", "")
                if lc not in IMG.providers_dict:
                    continue
                fname = FNAMES.jpeg_file_name_from_attributes(
                    til_x, til_y, zl, lc)
                fdir = FNAMES.jpeg_file_dir_from_attributes(
                    tile.lat, tile.lon, zl, IMG.providers_dict[lc])
                if os.path.isfile(os.path.join(fdir, fname)):
                    jpg_exists = True
                break

            if jpg_exists:
                continue

            # Vérifier que le barycentre est dans la bande 2km
            in_band = any(
                abs(bary_lat - lat_j) <= band_deg_lat and
                abs(bary_lon - lon_j) <= band_deg_lon
                for (lat_j, lon_j) in existing_jpg_pos
            )

            if in_band:
                sea_set.add(tex_attr)

        UI.vprint(
            1, f"   [SeaTex] {len(sea_set)} tuile(s) mer dans bande "
               f"{SEA_BAND_KM}km identifiée(s) via mesh."
        )
    except Exception as e:
        UI.vprint(2, f"   [SeaTex] build_sea_texture_set erreur : {e}")
    return sea_set


################################################################################
################################################################################
def download_textures(tile, download_queue, convert_queue, sea_texture_set=None):
    UI.vprint(1, "-> Opening download queue.")
    done = 0
    while True:
        texture_attributes = download_queue.get()
        if isinstance(texture_attributes, str) and texture_attributes == "quit":
            UI.progress_bar(2, 100)
            break
        if IMG.build_jpeg_ortho(tile, *texture_attributes):
            # JPG source présent — pipeline original inchangé
            done += 1
            UI.progress_bar(
                2, int(100 * done / (done + download_queue.qsize()))
            )
            convert_queue.put((tile, *texture_attributes))
        else:
            # JPG absent — EOX uniquement si triangle mer dans bande 2km
            is_sea_tile = (sea_texture_set is not None and
                           texture_attributes in sea_texture_set)
            if is_sea_tile:
                try:
                    import O4_Sea_Texture as _SEA
                    if _SEA.download_sea_jpeg(tile, *texture_attributes):
                        done += 1
                        UI.progress_bar(
                            2, int(100 * done / (done + download_queue.qsize()))
                        )
                        convert_queue.put((tile, *texture_attributes))
                except Exception as _se:
                    UI.vprint(2, f"   [SeaTex] fallback : {_se}")

        if UI.red_flag:
            UI.vprint(1, "Download process interrupted.")
            return 0
    if done:
        UI.vprint(1, " *Download of textures completed.")
    return 1

################################################################################
def build_tile(tile):
    if UI.is_working:
        return 0
    UI.is_working = 1
    UI.red_flag = False
    UI.logprint(
        "Step 3 for tile lat=", tile.lat, ", lon=", tile.lon, ": starting."
    )
    UI.vprint(
        0,
        "\nStep 3 : Building DSF/Imagery for tile "
        + FNAMES.short_latlon(tile.lat, tile.lon)
        + " : \n--------\n",
    )

    if not os.path.isfile(FNAMES.mesh_file(tile.build_dir, tile.lat, tile.lon)):
        UI.lvprint(
            0, "ERROR: A mesh file must first be constructed for the tile!"
        )
        UI.exit_message_and_bottom_line("")
        return 0

    timer = time.time()

    tile.write_to_config()

    if not IMG.initialize_local_combined_providers_dict(tile):
        UI.exit_message_and_bottom_line("")
        return 0

    try:
        if not os.path.exists(
            os.path.join(
                tile.build_dir,
                "Earth nav data",
                FNAMES.round_latlon(tile.lat, tile.lon),
            )
        ):
            os.makedirs(
                os.path.join(
                    tile.build_dir,
                    "Earth nav data",
                    FNAMES.round_latlon(tile.lat, tile.lon),
                )
            )
        if not os.path.isdir(os.path.join(tile.build_dir, "textures")):
            os.makedirs(os.path.join(tile.build_dir, "textures"))
        if UI.cleaning_level > 1 and not tile.grouped:
            for f in os.listdir(os.path.join(tile.build_dir, "textures")):
                if f[-4:] != ".png":
                    continue
                try:
                    os.remove(os.path.join(tile.build_dir, "textures", f))
                except:
                    pass
        if not tile.grouped:
            try:
                shutil.rmtree(os.path.join(tile.build_dir, "terrain"))
            except:
                pass
        if not os.path.isdir(os.path.join(tile.build_dir, "terrain")):
            os.makedirs(os.path.join(tile.build_dir, "terrain"))
    except Exception as e:
        UI.lvprint(0, "ERROR: Cannot create tile subdirectories.")
        UI.vprint(3, e)
        UI.exit_message_and_bottom_line("")
        return 0

    # Construire le set des tuiles mer dans bande 2km — thread principal
    try:
        dico_customzl = DSF.zone_list_to_ortho_dico(tile)
        sea_texture_set = build_sea_texture_set(tile, dico_customzl)
    except Exception as _ste:
        UI.vprint(2, f"   [SeaTex] sea_texture_set non construit : {_ste}")
        sea_texture_set = None

    download_queue = queue.Queue()
    convert_queue = queue.Queue()

    download_launched = False
    convert_launched = False

    build_dsf_thread = threading.Thread(
        target=DSF.build_dsf, args=[tile, download_queue]
    )
    download_thread = threading.Thread(
        target=download_textures,
        args=[tile, download_queue, convert_queue, sea_texture_set]
    )
    build_dsf_thread.start()
    if not skip_downloads:
        download_thread.start()
        download_launched = True
        if not skip_converts:
            UI.vprint(
                1,
                "-> Opening convert queue and",
                max_convert_slots,
                "conversion workers.",
            )
            dico_conv_progress = {"done": 0, "bar": 3}
            convert_workers = parallel_launch(
                IMG.convert_texture,
                convert_queue,
                max_convert_slots,
                progress=dico_conv_progress,
            )
            convert_launched = True
    build_dsf_thread.join()
    if download_launched:
        download_queue.put("quit")
        download_thread.join()
        if convert_launched:
            for _ in range(max_convert_slots):
                convert_queue.put("quit")
            parallel_join(convert_workers)
            if UI.red_flag:
                UI.vprint(1, "DDS conversion process interrupted.")
            elif dico_conv_progress["done"] >= 1:
                UI.vprint(1, " *DDS conversion of textures completed.")
    UI.vprint(1, " *Activating DSF file.")
    # Supprimer les PNG masques côtiers après DSF et DDS terminés
    for _f in os.listdir(os.path.join(tile.build_dir, "textures")):
        if _f.endswith(".png") and _f != "water_transition.png" and "_ZL" not in _f:
            try:
                os.remove(os.path.join(tile.build_dir, "textures", _f))
            except:
                pass
    dsf_file_name = os.path.join(
        tile.build_dir,
        "Earth nav data",
        FNAMES.long_latlon(tile.lat, tile.lon) + ".dsf",
    )
    try:
        os.replace(dsf_file_name + ".tmp", dsf_file_name)
    except:
        UI.vprint(0, "ERROR : could not rename DSF file, tile is not actived.")
    if UI.red_flag:
        UI.exit_message_and_bottom_line()
        return 0
    if UI.cleaning_level > 1:
        try:
            os.remove(FNAMES.alt_file(tile))
        except:
            pass
        try:
            os.remove(FNAMES.input_node_file(tile))
        except:
            pass
        try:
            os.remove(FNAMES.input_poly_file(tile))
        except:
            pass
    if UI.cleaning_level > 2:
        try:
            os.remove(FNAMES.mesh_file(tile.build_dir, tile.lat, tile.lon))
        except:
            pass
        try:
            os.remove(FNAMES.apt_file(tile))
        except:
            pass
    if UI.cleaning_level > 1 and not tile.grouped:
        remove_unwanted_textures(tile)
    UI.timings_and_bottom_line(timer)
    UI.logprint(
        "Step 3 for tile lat=", tile.lat, ", lon=", tile.lon, ": normal exit."
    )
    return 1

################################################################################
def build_all(tile):
    VMAP.build_poly_file(tile)
    if UI.red_flag:
        UI.exit_message_and_bottom_line("")
        return 0
    MESH.build_mesh(tile)
    if UI.red_flag:
        UI.exit_message_and_bottom_line("")
        return 0
    MASK.build_masks(tile)
    if UI.red_flag:
        UI.exit_message_and_bottom_line("")
        return 0
    build_tile(tile)
    if UI.red_flag:
        UI.exit_message_and_bottom_line("")
        return 0
    UI.is_working = 0
    return 1

################################################################################
def build_tile_list(
    tile, list_lat_lon, do_osm, do_mesh, do_mask, do_dsf, do_ovl, do_ptc
):
    if UI.is_working:
        return 0
    UI.red_flag = 0
    timer = time.time()
    UI.lvprint(
        0, "Batch build launched for a number of", len(list_lat_lon), "tiles."
    )
    k = 0
    for (lat, lon) in list_lat_lon:
        k += 1
        UI.vprint(
            1,
            "Dealing with tile ",
            k,
            "/",
            len(list_lat_lon),
            ":",
            FNAMES.short_latlon(lat, lon),
        )
        (tile.lat, tile.lon) = (lat, lon)
        tile.build_dir = FNAMES.build_dir(
            tile.lat, tile.lon, tile.custom_build_dir
        )
        tile.dem = None
        if do_ptc:
            tile.read_from_config()
        if do_osm or do_mesh or do_dsf:
            tile.make_dirs()
        if do_osm:
            VMAP.build_poly_file(tile)
            if UI.red_flag:
                UI.exit_message_and_bottom_line()
                return 0
        if do_mesh:
            MESH.build_mesh(tile)
            if UI.red_flag:
                UI.exit_message_and_bottom_line()
                return 0
        if do_mask:
            MASK.build_masks(tile)
            if UI.red_flag:
                UI.exit_message_and_bottom_line()
                return 0
        if do_dsf:
            build_tile(tile)
            if UI.red_flag:
                UI.exit_message_and_bottom_line()
                return 0
        if do_ovl:
            OVL.build_overlay(lat, lon)
            if UI.red_flag:
                UI.exit_message_and_bottom_line()
                return 0
        try:
            UI.gui.earth_window.canvas.delete(
                UI.gui.earth_window.dico_tiles_todo[(lat, lon)]
            )
            UI.gui.earth_window.dico_tiles_todo.pop((lat, lon), None)
        except:
            pass
    UI.lvprint(
        0, "Batch process completed in", UI.nicer_timer(time.time() - timer)
    )
    return 1

################################################################################
def remove_unwanted_textures(tile):
    texture_list = []
    for f in os.listdir(os.path.join(tile.build_dir, "terrain")):
        if f[-4:] != ".ter":
            continue
        if f[-5] != "y":  # overlay
            texture_list.append(f.replace(".ter", ".dds"))
        else:
            texture_list.append("_".join(f[:-4].split("_")[:-2]) + ".dds")
    for f in os.listdir(os.path.join(tile.build_dir, "textures")):
        if f[-4:] != ".dds":
            continue
        if f not in texture_list:
            print("Removing obsolete texture", f)
            try:
                os.remove(os.path.join(tile.build_dir, "textures", f))
            except:
                pass
