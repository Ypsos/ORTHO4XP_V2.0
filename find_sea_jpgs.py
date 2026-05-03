import sys, os
sys.path.insert(0, './src')
sys.path.insert(0, './Providers')

import O4_File_Names as FNAMES
import O4_UI_Utils as UI
import O4_Overlay_Utils as OVL

cfg = {}
with open(os.path.join(FNAMES.Ortho4XP_dir, "Ortho4XP.cfg")) as f:
    for line in f:
        if '=' in line and not line.startswith('#'):
            k, v = line.strip().split('=', 1)
            cfg[k.strip()] = v.strip()

OVL.custom_overlay_src = cfg.get('custom_overlay_src', '')

import O4_Imagery_Utils as IMG
IMG.initialize_providers_dict()
IMG.initialize_extents_dict()
IMG.initialize_color_filters_dict()
IMG.initialize_combined_providers_dict()

class FakeTile:
    lat=46; lon=-3; grouped=False
    build_dir='/Users/rolandlehmann/Applications/ORTHO4XP_V2/Tiles/zOrtho4XP_+46-003'
    water_tech=cfg.get('water_tech','XP12')
    imprint_masks_to_dds=True
    mask_zl=int(cfg.get('mask_zl',17))
    default_website='ZonePhoto'; zone_list=[]
    iterate=0; mesh_zl=int(cfg.get('mesh_zl',19))

tile = FakeTile()
IMG.initialize_local_combined_providers_dict(tile)

# Trouver le dossier JPG
layers = IMG.local_combined_providers_dict.get('ZonePhoto', [])
print(f"Layers ZonePhoto : {len(layers)}")
for rlayer in layers[:3]:
    layer_code = rlayer['layer_code']
    if layer_code in IMG.providers_dict:
        d = FNAMES.jpeg_file_dir_from_attributes(46, -3, 17, IMG.providers_dict[layer_code])
        print(f"  Layer {layer_code} → {d}")
        if os.path.isdir(d):
            jpgs = os.listdir(d)
            print(f"    JPG présents : {len(jpgs)}")
            print(f"    Exemples : {jpgs[:3]}")
        break
