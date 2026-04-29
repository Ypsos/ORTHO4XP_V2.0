import os, sys
import numpy as np
from PIL import Image, ImageFilter

BASE = "/Users/rolandlehmann/Applications/ORTHO4XP_V2"
MASKS = f"{BASE}/Masks/+40-010/+46-003"
TEXTURES = f"{BASE}/Tiles/zOrtho4XP_+46-003/textures"

print("="*60)
print("SIMULATION Draw Water Masks + Coastal Manager + Build")
print("="*60)

# Lire les PNG existants dans Masks/
pngs = [f for f in os.listdir(MASKS) if f.endswith('.png')]
print(f"\nPNG dans Masks/ : {len(pngs)}")

# Analyser chaque PNG
noirs = []
gris = []
blancs = []

for png in sorted(pngs):
    path = os.path.join(MASKS, png)
    img = Image.open(path)
    hist = img.histogram()
    total = sum(hist)
    vmax = 255 - next(i for i,v in enumerate(reversed(hist)) if v>0)
    vmin = next(i for i,v in enumerate(hist) if v>0)
    noir_pct = round(100*sum(hist[:10])/total)
    
    if vmax < 30:
        noirs.append((png, vmax))
    elif vmax < 150:
        gris.append((png, vmax))
    else:
        blancs.append((png, vmax))

print(f"\nPNG 100% noirs (max<30) : {len(noirs)}")
for p,v in noirs[:5]:
    print(f"  {p} max={v}")
if len(noirs)>5: print(f"  ... et {len(noirs)-5} autres")

print(f"\nPNG gris (30<max<150) : {len(gris)}")
for p,v in gris[:5]:
    print(f"  {p} max={v}")

print(f"\nPNG corrects (max>150) : {len(blancs)}")

# Vérifier DDS existants
dds_files = [f for f in os.listdir(TEXTURES) if f.endswith('.dds')]
print(f"\nDDS dans textures/ : {len(dds_files)}")

# Tuiles problématiques
print("\n--- TUILES CRITIQUES ---")
for key in ["46096_64704","46112_64704","46128_64704","46256_64704"]:
    parts = key.split("_")
    png = f"{parts[1]}_{parts[0]}.png"
    dds = f"{key}_ZonePhoto17.dds"
    png_ok = os.path.isfile(os.path.join(MASKS, png))
    dds_ok = os.path.isfile(os.path.join(TEXTURES, dds))
    
    if png_ok:
        img = Image.open(os.path.join(MASKS, png))
        hist = img.histogram()
        vmax = 255 - next(i for i,v in enumerate(reversed(hist)) if v>0)
        png_info = f"max={vmax}"
    else:
        png_info = "ABSENT"
    
    print(f"  {key}: DDS={'OK' if dds_ok else 'ABSENT'} PNG={png_info}")

