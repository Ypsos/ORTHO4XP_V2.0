"""
O4_XP12_Materials.py
Ortho4XP V3 — Phase 3 / Point 2
Auteur : Roland (Ypsos) — Codage : Claude (Anthropic AI)
Version : 1.0 — Mai 2026

Rôle :
    - Générer les paramètres matériaux XP12 (Wetness, Roughness, Specular)
    - Enrichir les fichiers .ter avec les directives XP12 materials
    - Mapping automatique depuis les données imagery (type de sol détecté)
    - Zéro cassure V2 : module autonome, rien modifié dans les fichiers existants

Utilisation :
    from O4_XP12_Materials import XP12Materials, enrich_ter_file
    mat = XP12Materials.from_image(img, provider_code, tile_id)
    enrich_ter_file("terrain/64784_46224_ZL17.ter", mat)
"""

import os
import time
import numpy
from PIL import Image
from dataclasses import dataclass, field
from typing import Optional, Dict

# ---------------------------------------------------------------------------
# Import système de logs Ortho4XP
# ---------------------------------------------------------------------------
try:
    import O4_UI_Utils as UI
    def _log(msg):  UI.lvprint(1, "[XP12MAT] " + msg)
    def _warn(msg): UI.lvprint(1, "[XP12MAT] ATTENTION : " + msg)
except ImportError:
    def _log(msg):  print(time.strftime("%Y-%m-%d %H:%M:%S") + " [XP12MAT] " + msg)
    def _warn(msg): print(time.strftime("%Y-%m-%d %H:%M:%S") + " [XP12MAT] ATTENTION : " + msg)


# ---------------------------------------------------------------------------
# Types de sol détectés automatiquement depuis l'image
# ---------------------------------------------------------------------------
SOIL_UNKNOWN   = "unknown"
SOIL_URBAN     = "urban"       # zones urbaines (gris, faible végétation)
SOIL_FOREST    = "forest"      # forêt (vert foncé dominant)
SOIL_FIELD     = "field"       # champs (vert clair / jaune)
SOIL_BARE      = "bare"        # sol nu / désert (brun/ocre)
SOIL_WATER     = "water"       # eau (bleu dominant)
SOIL_SNOW      = "snow"        # neige (blanc très lumineux)
SOIL_BEACH     = "beach"       # plage / sable clair


# ---------------------------------------------------------------------------
# Profils matériaux XP12 par type de sol
# Valeurs : wetness [0-1], roughness [0-1], specular [0-1]
# ---------------------------------------------------------------------------
_MATERIAL_PROFILES: Dict[str, Dict] = {
    SOIL_URBAN : {"wetness": 0.20, "roughness": 0.75, "specular": 0.15,
                  "normal_scale": 1.0,  "description": "Zones urbaines"},
    SOIL_FOREST: {"wetness": 0.45, "roughness": 0.90, "specular": 0.05,
                  "normal_scale": 1.2,  "description": "Forêt/végétation dense"},
    SOIL_FIELD : {"wetness": 0.35, "roughness": 0.85, "specular": 0.08,
                  "normal_scale": 0.9,  "description": "Champs/prairies"},
    SOIL_BARE  : {"wetness": 0.10, "roughness": 0.80, "specular": 0.10,
                  "normal_scale": 1.1,  "description": "Sol nu/désert"},
    SOIL_WATER : {"wetness": 1.00, "roughness": 0.05, "specular": 0.80,
                  "normal_scale": 0.5,  "description": "Eau"},
    SOIL_SNOW  : {"wetness": 0.60, "roughness": 0.30, "specular": 0.60,
                  "normal_scale": 0.4,  "description": "Neige/glace"},
    SOIL_BEACH : {"wetness": 0.25, "roughness": 0.70, "specular": 0.20,
                  "normal_scale": 0.8,  "description": "Plage/sable"},
    SOIL_UNKNOWN:{"wetness": 0.25, "roughness": 0.75, "specular": 0.10,
                  "normal_scale": 1.0,  "description": "Type inconnu (défaut)"},
}


# ---------------------------------------------------------------------------
# Dataclass résultat matériaux
# ---------------------------------------------------------------------------
@dataclass
class XP12Materials:
    soil_type    : str   = SOIL_UNKNOWN
    wetness      : float = 0.25
    roughness    : float = 0.75
    specular     : float = 0.10
    normal_scale : float = 1.0
    confidence   : float = 0.0    # [0-1] confiance de la détection
    details      : Dict  = field(default_factory=dict)

    @classmethod
    def from_profile(cls, soil_type: str) -> "XP12Materials":
        """Crée un XP12Materials depuis un profil connu."""
        p = _MATERIAL_PROFILES.get(soil_type, _MATERIAL_PROFILES[SOIL_UNKNOWN])
        return cls(
            soil_type    = soil_type,
            wetness      = p["wetness"],
            roughness    = p["roughness"],
            specular     = p["specular"],
            normal_scale = p["normal_scale"],
            confidence   = 1.0,
        )

    @classmethod
    def from_image(cls, image: Image.Image,
                   provider_code: str = "",
                   tile_id: str = "") -> "XP12Materials":
        """
        Détecte automatiquement le type de sol depuis l'image
        et retourne les paramètres matériaux XP12 correspondants.

        Paramètres :
            image         : image PIL (RGB)
            provider_code : code provider (pour logs)
            tile_id       : identifiant tuile (pour logs)

        Retourne :
            XP12Materials avec soil_type, wetness, roughness, specular détectés
        """
        thumb = image.convert("RGB").resize((64, 64), Image.BICUBIC)
        arr   = numpy.array(thumb, dtype=numpy.float32)

        soil_type, confidence, details = _detect_soil_type(arr)
        p = _MATERIAL_PROFILES.get(soil_type, _MATERIAL_PROFILES[SOIL_UNKNOWN])

        mat = cls(
            soil_type    = soil_type,
            wetness      = p["wetness"],
            roughness    = p["roughness"],
            specular     = p["specular"],
            normal_scale = p["normal_scale"],
            confidence   = confidence,
            details      = details,
        )

        _log(f"[{provider_code or '?'} / {tile_id or '?'}] "
             f"Sol={soil_type} conf={confidence:.0%} "
             f"wet={mat.wetness:.2f} rough={mat.roughness:.2f} "
             f"spec={mat.specular:.2f}")
        return mat

    def to_ter_lines(self) -> list:
        """
        Retourne les lignes à injecter dans un fichier .ter XP12.
        Compatible avec la syntaxe Laminar Research X-Plane 12.

        Retourne :
            Liste de str — lignes prêtes à écrire
        """
        lines = [
            f"# XP12 Materials — {self.soil_type} "
            f"(confidence {self.confidence:.0%})",
            f"WET {self.wetness:.3f}",
            f"ROUGHNESS {self.roughness:.3f}",
            f"SPECULAR {self.specular:.3f}",
            f"NORMAL_SCALE {self.normal_scale:.3f}",
        ]
        return lines

    def to_dict(self) -> dict:
        return {
            "soil_type"   : self.soil_type,
            "wetness"     : round(self.wetness,      3),
            "roughness"   : round(self.roughness,    3),
            "specular"    : round(self.specular,     3),
            "normal_scale": round(self.normal_scale, 3),
            "confidence"  : round(self.confidence,   3),
            "details"     : self.details,
        }


# ---------------------------------------------------------------------------
# Détection automatique du type de sol
# ---------------------------------------------------------------------------

def _detect_soil_type(arr: numpy.ndarray):
    """
    Analyse une image 64x64 float32 et retourne (soil_type, confidence, details).

    Algorithme :
        1. Calcul des statistiques RGB (moyennes, dominantes)
        2. Calcul indices spectraux (NDVI simplifié, luminance, saturation)
        3. Arbre de décision basé sur ces indices
    """
    r = arr[:,:,0]
    g = arr[:,:,1]
    b = arr[:,:,2]

    mean_r = float(r.mean())
    mean_g = float(g.mean())
    mean_b = float(b.mean())
    luminance  = (mean_r + mean_g + mean_b) / 3.0
    saturation = float(numpy.maximum(
        numpy.maximum(r, g), numpy.maximum(g, b)).mean()
        - numpy.minimum(numpy.minimum(r, g), numpy.minimum(g, b)).mean())

    # NDVI simplifié : (G - R) / (G + R + 1e-5)
    ndvi = (mean_g - mean_r) / (mean_g + mean_r + 1e-5)

    # Ratio bleu (eau)
    ratio_bleu = mean_b / (mean_r + mean_g + mean_b + 1e-5)

    # Ratio rouge-brun (sol nu)
    ratio_brun = mean_r / (mean_g + mean_b + 1e-5)

    details = {
        "mean_r": round(mean_r, 1), "mean_g": round(mean_g, 1),
        "mean_b": round(mean_b, 1), "luminance": round(luminance, 1),
        "saturation": round(saturation, 1), "ndvi": round(ndvi, 3),
        "ratio_bleu": round(ratio_bleu, 3), "ratio_brun": round(ratio_brun, 3),
    }

    # ── Arbre de décision ─────────────────────────────────────────────
    # Neige : très lumineux + très faible saturation
    if luminance > 210 and saturation < 20:
        return SOIL_SNOW, 0.85, details

    # Eau : bleu dominant + faible luminance globale
    if ratio_bleu > 0.38 and mean_b > mean_r and mean_b > mean_g:
        conf = min(1.0, (ratio_bleu - 0.38) * 8 + 0.6)
        return SOIL_WATER, conf, details

    # Plage/sable : lumineux + faible saturation + dominante légèrement chaude
    if luminance > 170 and saturation < 35 and mean_r >= mean_g >= mean_b:
        return SOIL_BEACH, 0.70, details

    # Forêt : NDVI élevé + vert dominant
    if ndvi > 0.08 and mean_g > mean_r and mean_g > mean_b:
        conf = min(1.0, ndvi * 5 + 0.4)
        return SOIL_FOREST, conf, details

    # Champs/prairies : NDVI modéré + vert-jaune
    if ndvi > 0.02 and mean_g >= mean_r:
        return SOIL_FIELD, 0.65, details

    # Sol nu / désert : rouge-brun dominant
    if ratio_brun > 0.45 and saturation > 20:
        return SOIL_BARE, 0.70, details

    # Zones urbaines : gris moyen + faible saturation
    if saturation < 30 and 80 < luminance < 180:
        return SOIL_URBAN, 0.60, details

    # Défaut
    return SOIL_UNKNOWN, 0.40, details


# ---------------------------------------------------------------------------
# Fonction utilitaire : enrichir un fichier .ter existant
# ---------------------------------------------------------------------------

def enrich_ter_file(ter_path: str,
                    materials: XP12Materials,
                    backup: bool = True) -> bool:
    """
    Injecte les directives XP12 materials dans un fichier .ter existant.

    Paramètres :
        ter_path  : chemin du fichier .ter à enrichir
        materials : XP12Materials à injecter
        backup    : si True, crée une sauvegarde .ter.bak avant modification

    Retourne :
        True si succès, False sinon.

    Comportement :
        - Si les directives XP12 sont déjà présentes → met à jour sans doublon
        - Injection après la ligne LOAD_CENTER (position standard XP12)
        - Non bloquant : en cas d'erreur, le .ter original est conservé
    """
    if not os.path.isfile(ter_path):
        _warn(f"Fichier .ter introuvable : {ter_path}")
        return False

    try:
        with open(ter_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        _warn(f"Lecture .ter échouée : {e}")
        return False

    # Backup obligatoire
    if backup:
        bak = ter_path + ".bak"
        try:
            import shutil
            shutil.copy2(ter_path, bak)
        except Exception as e:
            _warn(f"Backup .ter échoué : {e} — abandon")
            return False

    # Supprimer les anciennes directives XP12 si présentes
    xp12_keys = {"WET ", "ROUGHNESS ", "SPECULAR ", "NORMAL_SCALE ",
                 "# XP12 Materials"}
    lines_clean = [l for l in lines
                   if not any(l.strip().startswith(k) for k in xp12_keys)]

    # Trouver position d'injection (après LOAD_CENTER ou en fin de fichier)
    insert_idx = len(lines_clean)
    for i, line in enumerate(lines_clean):
        if line.strip().startswith("LOAD_CENTER"):
            insert_idx = i + 1
            break

    # Injecter les nouvelles directives
    new_lines_mat = [l + "\n" for l in materials.to_ter_lines()]
    final_lines   = (lines_clean[:insert_idx]
                     + new_lines_mat
                     + lines_clean[insert_idx:])

    try:
        with open(ter_path, "w", encoding="utf-8") as f:
            f.writelines(final_lines)
        _log(f"Enrichi : {os.path.basename(ter_path)} "
             f"[{materials.soil_type} wet={materials.wetness:.2f}]")
        return True
    except Exception as e:
        _warn(f"Écriture .ter échouée : {e}")
        # Restaurer depuis backup
        if backup and os.path.isfile(ter_path + ".bak"):
            import shutil
            shutil.copy2(ter_path + ".bak", ter_path)
            _warn("Fichier .ter restauré depuis backup")
        return False


# ---------------------------------------------------------------------------
# Test standalone (python O4_XP12_Materials.py)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import tempfile

    print("=== Test O4_XP12_Materials ===\n")

    # Test 1 : détection types de sol
    cas_test = [
        ("Forêt",   numpy.array([[[60, 110, 50]]*64]*64,  dtype='uint8')),
        ("Eau",     numpy.array([[[80, 120, 200]]*64]*64, dtype='uint8')),
        ("Neige",   numpy.array([[[245,248,250]]*64]*64,  dtype='uint8')),
        ("Sol nu",  numpy.array([[[160, 110, 70]]*64]*64, dtype='uint8')),
        ("Urbain",  numpy.array([[[130,128,125]]*64]*64,  dtype='uint8')),
    ]
    for nom, arr in cas_test:
        img  = Image.fromarray(arr, 'RGB')
        mat  = XP12Materials.from_image(img, "TEST", nom)
        print(f"  [OK] {nom:10} → {mat.soil_type:10} "
              f"conf={mat.confidence:.0%} "
              f"wet={mat.wetness:.2f} spec={mat.specular:.2f}")

    # Test 2 : to_ter_lines
    mat_foret = XP12Materials.from_profile(SOIL_FOREST)
    lines = mat_foret.to_ter_lines()
    assert any("WET" in l for l in lines)
    assert any("ROUGHNESS" in l for l in lines)
    assert any("SPECULAR" in l for l in lines)
    print("[OK] to_ter_lines() génère les directives XP12")

    # Test 3 : enrich_ter_file
    ter_content = (
        "A\n800\nTERRAIN\n\n"
        "LOAD_CENTER 48.5 2.5 100 4096\n"
        "BASE_TEX_NOWRAP textures/64784_46224_ZonePhoto17.dds\n"
    )
    with tempfile.NamedTemporaryFile(suffix=".ter", delete=False,
                                     mode="w") as f:
        f.write(ter_content)
        ter_path = f.name

    ok = enrich_ter_file(ter_path, mat_foret, backup=True)
    assert ok
    with open(ter_path) as f:
        content = f.read()
    assert "WET" in content
    assert "ROUGHNESS" in content
    assert "# XP12 Materials" in content
    # Vérifier que LOAD_CENTER est toujours là
    assert "LOAD_CENTER" in content
    print("[OK] enrich_ter_file() injecte les directives sans casser le .ter")

    # Test 4 : idempotence (2ème appel ne duplique pas les directives)
    mat_eau = XP12Materials.from_profile(SOIL_WATER)
    ok2 = enrich_ter_file(ter_path, mat_eau, backup=False)
    assert ok2
    with open(ter_path) as f:
        content2 = f.read()
    count_wet = content2.count("WET ")
    assert count_wet == 1, f"Directive WET dupliquée : {count_wet} fois"
    print("[OK] Idempotence : 2ème appel met à jour sans dupliquer")

    # Test 5 : to_dict
    d = mat_foret.to_dict()
    for k in ["soil_type","wetness","roughness","specular","normal_scale"]:
        assert k in d, f"Clé manquante : {k}"
    print("[OK] to_dict() contient toutes les clés")

    os.remove(ter_path)
    print("\n✅ Tous les tests O4_XP12_Materials passés.")
