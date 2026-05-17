import os
import time
import shutil
import queue
import threading
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



################################################################################
################################################################################
def download_textures(tile, download_queue, convert_queue):
    UI.vprint(1, "-> Opening download queue.")
    done = 0
    while True:
        texture_attributes = download_queue.get()
        if isinstance(texture_attributes, str) and texture_attributes == "quit":
            UI.progress_bar(2, 100)
            break
        if IMG.build_jpeg_ortho(tile, *texture_attributes):
            done += 1
            UI.progress_bar(
                2, int(100 * done / (done + download_queue.qsize()))
            )
            try:
                import O4_Sea_Texture as _SEA
                import O4_Imagery_Utils as _IMG
                import O4_File_Names as _FN
                import numpy as _np
                from PIL import Image as _PILc

                # Trouver le JPG source
                def _get_jpg_path():
                    layers = _IMG.local_combined_providers_dict.get(
                        texture_attributes[3] if len(texture_attributes) > 3 else "", []
                    )
                    for rlayer in layers:
                        lc = rlayer.get("layer_code", "")
                        if lc not in _IMG.providers_dict:
                            continue
                        fname = _FN.jpeg_file_name_from_attributes(
                            texture_attributes[0], texture_attributes[1],
                            texture_attributes[2], lc)
                        fdir = _FN.jpeg_file_dir_from_attributes(
                            tile.lat, tile.lon, texture_attributes[2],
                            _IMG.providers_dict[lc])
                        fpath = os.path.join(fdir, fname)
                        if os.path.isfile(fpath):
                            return fpath
                    return None

                # Étape 1 : bouche zones noires/uniformes avec EOX
                _SEA.patch_sea_black_zones(tile, *texture_attributes)

                # Étape 2 : JPG bleu XP12 UNIQUEMENT sur tuiles uniformes
                # (pleine mer sans fond marin réel)
                jpg_path = _get_jpg_path()
                if jpg_path:
                    try:
                        arr_c = _np.array(
                            _PILc.open(jpg_path).convert("RGB"), dtype=_np.uint8
                        )
                        is_uniform = arr_c.astype('float32').std() < _SEA.UNIFORM_STD_THRESHOLD
                        if is_uniform:
                            _SEA.apply_sea_join_dissolve(
                                tile, *texture_attributes, jpg_path)
                    except Exception:
                        pass
            except Exception as _se:
                UI.vprint(2, f"   [SeaTex] patch : {_se}")
            convert_queue.put((tile, *texture_attributes))
        else:
            # Fallback maritime : EOX Sentinel-2 pour zones sans JPG en mer
            try:
                import O4_Sea_Texture as _SEA
                if _SEA.download_sea_jpeg(tile, *texture_attributes):
                    done += 1
                    UI.progress_bar(
                        2, int(100 * done / (done + download_queue.qsize()))
                    )
                    # Étape 3 : grain de sable sur le JPG EOX téléchargé
                    import O4_Imagery_Utils as _IMG
                    import O4_File_Names as _FN
                    layers = _IMG.local_combined_providers_dict.get(
                        texture_attributes[3] if len(texture_attributes) > 3 else "", []
                    )
                    for rlayer in layers:
                        lc = rlayer.get("layer_code", "")
                        if lc not in _IMG.providers_dict:
                            continue
                        fname = _FN.jpeg_file_name_from_attributes(
                            texture_attributes[0], texture_attributes[1],
                            texture_attributes[2], lc)
                        fdir = _FN.jpeg_file_dir_from_attributes(
                            tile.lat, tile.lon, texture_attributes[2],
                            _IMG.providers_dict[lc])
                        fpath = os.path.join(fdir, fname)
                        if os.path.isfile(fpath):
                            _SEA.build_sea_buffer_jpeg(
                                tile, *texture_attributes, fpath)
                            break
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

    download_queue = queue.Queue()
    convert_queue = queue.Queue()

    download_launched = False
    convert_launched = False

    build_dsf_thread = threading.Thread(
        target=DSF.build_dsf, args=[tile, download_queue]
    )
    download_thread = threading.Thread(
        target=download_textures, args=[tile, download_queue, convert_queue]
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
