"""
O4_Backup_Manager.py
Ortho4XP V3 — Lot A / Livrable A1
Auteur : Roland (Ypsos) — Codage : Claude (Anthropic AI)
Version : 1.0 — Mai 2026

Rôle :
    - Créer des sauvegardes horodatées automatiques avant toute modification
    - Permettre un rollback 1-clic vers la dernière sauvegarde
    - Protéger les fichiers .py / .comb / .ccorr / .dds / .cfg
    - Zéro cassure V2 : module autonome, rien n'est modifié dans les fichiers existants

Utilisation depuis un autre module :
    from O4_Backup_Manager import backup_file, rollback_last, list_backups
"""

import os
import shutil
import json
import time
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Import du système de logs Ortho4XP existant (O4_UI_Utils)
# Si indisponible (tests standalone), on bascule sur print simple
# ---------------------------------------------------------------------------
try:
    import O4_UI_Utils as UI
    def _log(msg):
        UI.lvprint(1, "[BACKUP] " + msg)
    def _logwarn(msg):
        UI.lvprint(1, "[BACKUP] ATTENTION : " + msg)
except ImportError:
    def _log(msg):
        print(time.strftime("%Y-%m-%d %H:%M:%S") + " [BACKUP] " + msg)
    def _logwarn(msg):
        print(time.strftime("%Y-%m-%d %H:%M:%S") + " [BACKUP] ATTENTION : " + msg)

# ---------------------------------------------------------------------------
# Configuration — modifiable sans toucher au reste du code
# ---------------------------------------------------------------------------

# Dossier de sauvegarde : créé automatiquement à côté des sources
_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
BACKUP_ROOT  = os.path.join(_SCRIPT_DIR, "_backups_O4")

# Nombre max de sauvegardes conservées PAR fichier (les plus anciennes sont purgées)
MAX_BACKUPS_PER_FILE = 10

# Extensions qui déclenchent TOUJOURS une sauvegarde automatique
PROTECTED_EXTENSIONS = {".py", ".comb", ".ccorr", ".dds", ".cfg", ".json"}

# Fichier d'index (trace horodatée de toutes les sauvegardes)
_INDEX_FILE = os.path.join(BACKUP_ROOT, "_index.json")


# ---------------------------------------------------------------------------
# Fonctions internes
# ---------------------------------------------------------------------------

def _ensure_dir():
    """Crée le dossier de sauvegarde s'il n'existe pas."""
    os.makedirs(BACKUP_ROOT, exist_ok=True)


def _timestamp():
    """Horodatage compact sans caractères interdits sur tous les OS."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _load_index():
    """Charge l'index JSON. Retourne dict vide si absent ou corrompu."""
    if os.path.isfile(_INDEX_FILE):
        try:
            with open(_INDEX_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            _logwarn("Index corrompu — réinitialisation propre.")
    return {}


def _save_index(index):
    """Écrit l'index JSON sur disque."""
    try:
        with open(_INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
    except Exception as e:
        _logwarn(f"Impossible d'écrire l'index : {e}")


def _file_key(filepath):
    """Clé unique dans l'index pour un fichier (chemin absolu normalisé)."""
    return os.path.normpath(os.path.abspath(filepath))


def _backup_filename(original_path, ts):
    """
    Construit le nom du fichier de sauvegarde.
    Exemple : O4_DSF_Utils.py → O4_DSF_Utils__20260518_143022.py.bak
    """
    p = Path(original_path)
    return f"{p.stem}__{ts}{p.suffix}.bak"


def _prune_old_backups(key, index):
    """
    Supprime les sauvegardes les plus anciennes si on dépasse MAX_BACKUPS_PER_FILE.
    Modifie l'index en place.
    """
    entries = index.get(key, [])
    while len(entries) > MAX_BACKUPS_PER_FILE:
        oldest   = entries.pop(0)
        old_path = oldest.get("backup_path", "")
        if old_path and os.path.isfile(old_path):
            try:
                os.remove(old_path)
                _log(f"Ancienne sauvegarde purgée : {os.path.basename(old_path)}")
            except Exception as e:
                _logwarn(f"Impossible de supprimer {old_path} : {e}")
    index[key] = entries


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------

def backup_file(filepath, reason="auto"):
    """
    Crée une sauvegarde horodatée du fichier donné AVANT toute modification.

    Paramètres :
        filepath : chemin absolu ou relatif du fichier à sauvegarder
        reason   : motif affiché dans les logs (ex: "avant modification DSF")

    Retourne :
        Le chemin de la sauvegarde créée, ou None en cas d'erreur.
    """
    filepath = os.path.abspath(filepath)

    if not os.path.isfile(filepath):
        _logwarn(f"Fichier introuvable, sauvegarde impossible : {filepath}")
        return None

    ext = Path(filepath).suffix.lower()
    if ext not in PROTECTED_EXTENSIONS:
        _logwarn(f"Extension '{ext}' non listée — sauvegarde créée par précaution.")

    _ensure_dir()

    ts       = _timestamp()
    bak_name = _backup_filename(filepath, ts)
    bak_path = os.path.join(BACKUP_ROOT, bak_name)

    try:
        shutil.copy2(filepath, bak_path)
    except Exception as e:
        _logwarn(f"Échec copie de {os.path.basename(filepath)} : {e}")
        return None

    # Mise à jour de l'index
    index = _load_index()
    key   = _file_key(filepath)
    if key not in index:
        index[key] = []

    index[key].append({
        "timestamp"   : ts,
        "reason"      : reason,
        "original"    : filepath,
        "backup_path" : bak_path,
        "size_bytes"  : os.path.getsize(bak_path),
    })

    _prune_old_backups(key, index)
    _save_index(index)

    _log(f"Sauvegarde OK : {os.path.basename(filepath)} → {bak_name}  [{reason}]")
    return bak_path


def rollback_last(filepath):
    """
    Restaure la DERNIÈRE sauvegarde connue du fichier (rollback 1-clic).

    Paramètres :
        filepath : chemin du fichier original à restaurer

    Retourne :
        True si restauration réussie, False sinon.
    """
    filepath = os.path.abspath(filepath)
    key      = _file_key(filepath)
    index    = _load_index()
    entries  = index.get(key, [])

    if not entries:
        _logwarn(f"Aucune sauvegarde trouvée pour : {os.path.basename(filepath)}")
        return False

    last     = entries[-1]
    bak_path = last.get("backup_path", "")

    if not os.path.isfile(bak_path):
        _logwarn(f"Fichier de sauvegarde introuvable sur disque : {bak_path}")
        return False

    try:
        shutil.copy2(bak_path, filepath)
        _log(f"Rollback OK : {os.path.basename(filepath)} "
             f"← {os.path.basename(bak_path)}  [timestamp: {last.get('timestamp')}]")
        return True
    except Exception as e:
        _logwarn(f"Rollback échoué pour {os.path.basename(filepath)} : {e}")
        return False


def rollback_to(filepath, timestamp):
    """
    Restaure une sauvegarde spécifique identifiée par son horodatage.

    Paramètres :
        filepath  : chemin du fichier original
        timestamp : horodatage au format YYYYMMDD_HHMMSS

    Retourne :
        True si restauration réussie, False sinon.
    """
    filepath = os.path.abspath(filepath)
    key      = _file_key(filepath)
    index    = _load_index()
    entries  = index.get(key, [])

    target = next((e for e in entries if e.get("timestamp") == timestamp), None)
    if not target:
        _logwarn(f"Aucune sauvegarde avec timestamp={timestamp} "
                 f"pour {os.path.basename(filepath)}")
        return False

    bak_path = target.get("backup_path", "")
    if not os.path.isfile(bak_path):
        _logwarn(f"Fichier de sauvegarde introuvable : {bak_path}")
        return False

    try:
        shutil.copy2(bak_path, filepath)
        _log(f"Rollback ciblé OK : {os.path.basename(filepath)} "
             f"← {os.path.basename(bak_path)}")
        return True
    except Exception as e:
        _logwarn(f"Rollback ciblé échoué : {e}")
        return False


def list_backups(filepath=None):
    """
    Liste les sauvegardes disponibles.

    Paramètres :
        filepath : si fourni, liste uniquement les sauvegardes de ce fichier
                   si None, liste toutes les sauvegardes connues

    Retourne :
        Liste de dicts triée du plus récent au plus ancien.
        Champs : original, timestamp, backup_path, reason, size_bytes
    """
    index  = _load_index()
    result = []

    if filepath:
        key    = _file_key(filepath)
        result = list(index.get(key, []))
    else:
        for entries in index.values():
            result.extend(entries)

    result.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return result


def backup_multiple(filepaths, reason="auto"):
    """
    Sauvegarde plusieurs fichiers en une seule opération.

    Paramètres :
        filepaths : liste de chemins à sauvegarder
        reason    : motif commun affiché dans les logs

    Retourne :
        Dict {filepath: backup_path ou None}
    """
    results = {}
    for fp in filepaths:
        results[fp] = backup_file(fp, reason=reason)
    return results


# ---------------------------------------------------------------------------
# Test standalone (python O4_Backup_Manager.py)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import tempfile

    print("=== Test O4_Backup_Manager ===\n")

    # Créer un fichier temporaire .py de test
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as tmp:
        tmp.write("# fichier test\nprint('version 1')\n")
        test_file = tmp.name

    print(f"Fichier test : {test_file}")

    # Test 1 : backup
    bak = backup_file(test_file, reason="test unitaire v1")
    assert bak and os.path.isfile(bak), "ERREUR : sauvegarde non créée"
    print(f"[OK] Sauvegarde créée : {os.path.basename(bak)}")

    # Modifier le fichier
    with open(test_file, "w") as f:
        f.write("# fichier test\nprint('version 2 — modifiée')\n")

    # Test 2 : rollback_last
    ok = rollback_last(test_file)
    assert ok, "ERREUR : rollback échoué"
    content = open(test_file).read()
    assert "version 1" in content, "ERREUR : rollback n'a pas restauré la bonne version"
    print("[OK] Rollback 1-clic réussi")

    # Test 3 : list_backups
    backups = list_backups(test_file)
    assert len(backups) >= 1
    print(f"[OK] list_backups : {len(backups)} entrée(s)")

    # Test 4 : backup_multiple
    res = backup_multiple([test_file], reason="test multiple")
    assert res[test_file] is not None
    print("[OK] backup_multiple réussi")

    # Nettoyage
    os.remove(test_file)
    print("\n✅ Tous les tests O4_Backup_Manager passés.")
