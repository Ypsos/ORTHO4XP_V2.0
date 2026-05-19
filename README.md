# ORTHO4XP V3.2

![ORTHO4XP V3 Banner](BanniereGithub.png)

**La version moderne d'Ortho4XP**  
Installation automatique • Sans terminal • Pour X-Plane 12

[![TÉLÉCHARGER LA DERNIÈRE VERSION](https://img.shields.io/badge/TÉLÉCHARGER%20LA%20DERNIÈRE%20VERSION-00C853?style=for-the-badge&logo=download&logoColor=white)](https://github.com/Ypsos/ORTHO4XP_V3/releases/latest)

---

## 🧭 Origine du projet

| | |
|---|---|
| **Logiciel original** | Créé par Oscar Pilote → [github.com/oscarpilote/Ortho4XP](https://github.com/oscarpilote/Ortho4XP) |
| **Version 1.40 maintenue** | Fork par Shred86 → [github.com/shred86/Ortho4XP](https://github.com/shred86/Ortho4XP) |
| **Cette V3** | Refonte complète par **Roland (Ypsos)** avec **Claude (Anthropic AI)** |

En mars 2026, j'ai contacté Oscar Pilote et la communauté (Issue GitHub #299, Topic X-Plane.org).  
Réponse : *« Tu fais ce que tu veux, tu es libre »*.  
Cet espace a été créé afin que la version V3 soit **claire, indépendante et accessible à tous**.

---

## ⚡ Tableau comparatif — V1.40 vs V2 vs V3.2

| Fonctionnalité | Ortho4XP 1.40 (Shred86) | Ortho4XP V2 (Roland) | **Ortho4XP V3.2 (Roland)** |
|---|---|---|---|
| Installation | Scripts bash/bat manuels | ✅ Launcher graphique 1 clic | ✅ Identique V2 |
| Python | Non géré | ✅ Python 3.12 auto | ✅ Identique V2 |
| Environnement | Système hôte | ✅ venv isolé | ✅ Identique V2 |
| Compatibilité | macOS Intel, Windows | ✅ M1–M4, Intel, Win, Linux | ✅ Identique V2 |
| Performance | Python 3.x standard | ✅ +15 à 20% calculs mesh | ✅ Identique V2 |
| Interface | Fenêtre standard | ✅ Adaptée 4K | ✅ Identique V2 |
| Eau transparente XP12 | Non géré | ✅ BC3 + canal alpha | ✅ Identique V2 |
| Masques côtiers | Manuel | ✅ Auto depuis mesh | ✅ Identique V2 |
| Color Normalize | Absent | ✅ sRGB — intensité 100% | ✅ Identique V2 |
| Color Check | Absent | ✅ Interface correction | ✅ Identique V2 |
| Validation XP12 | Non testée | ✅ Validée | ✅ Identique V2 |
| **Event Bus** | Absent | Absent | ✅ **V3** — Architecture event-driven |
| **Pipeline orchestré** | Absent | Absent | ✅ **V3** — Étapes nommées, statuts, durées |
| **Cache intelligent** | Absent | Absent | ✅ **V3** — Rebuild ignoré si tuile à jour |
| **Thèmes interface** | Absent | Absent | ✅ **V3** — 5 thèmes + personnalisation |
| **Scoring providers** | Absent | Absent | ✅ **V3** — Qualité image évaluée automatiquement |
| **GPU Backend** | Absent | Absent | ✅ **V3** — CUDA auto, CPU fallback silencieux |
| **Sauvegardes auto** | Absent | Absent | ✅ **V3.2** — Horodatées, rollback 1-clic |
| **Protection mémoire** | Absent | Absent | ✅ **V3.2** — Cache RAM surveillé en temps réel |
| **Provider failover** | Absent | Absent | ✅ **V3.2** — Bascule automatique si score bas |
| **Export scores CSV/JSON** | Absent | Absent | ✅ **V3.2** — Historique complet exportable |
| **IA détection nuages** | Absent | Absent | ✅ **V3.2** — Détection avancée 3 critères |
| **XP12 Materials** | Absent | Absent | ✅ **V3.2** — Wetness/Roughness/Specular auto |
| **Timeline build** | Absent | Absent | ✅ **V3.2** — Durées par étape dans la GUI |
| **RAM live GUI** | Absent | Absent | ✅ **V3.2** — Indicateur mémoire en temps réel |
| **Debug visualizations** | Absent | Absent | ✅ **V3.2** — Cartes seam/blur/color |

---

## 🆕 Nouveautés V3.2 — Mai 2026

### 🛡️ Sauvegardes automatiques + Rollback — `O4_Backup_Manager`
- Sauvegarde horodatée automatique avant toute modification de fichier critique
- Rollback 1-clic depuis le terminal : `python rollback.py O4_DSF_Utils.py`
- Index JSON de toutes les sauvegardes avec motif et timestamp
- Protège `.py`, `.comb`, `.ccorr`, `.dds`, `.cfg`
- Maximum 10 sauvegardes par fichier — purge automatique des plus anciennes

### 🧠 Protection Cache RAM — `O4_Memory_Manager`
- Surveillance RAM en temps réel via `psutil`
- Nettoyage automatique si seuil dépassé (défaut : 80% RAM système)
- Taille max du cache configurable (défaut : 8 Go)
- Mode dégradé silencieux si `psutil` absent
- `check_and_cleanup_memory()` disponible pour les boucles lourdes

### 🔄 Provider Abstraction + Failover — `O4_Provider_Abstraction`
- Couche d'abstraction entre le pipeline et les providers imagery
- Failover automatique si un provider est défaillant (blacklist 5 minutes)
- Blacklist après 3 échecs consécutifs — reset automatique
- Sélection du premier provider actif selon l'ordre de priorité
- Thread-safe — compatible builds en parallèle

### 📊 Score Logger — `O4_Score_Logger`
- Enregistrement de chaque score provider avec horodatage
- Export CSV et JSON à tout moment
- Statistiques agrégées par provider (moyenne, min, max, bruit, nuages, seam)
- Rapport console lisible en fin de build
- `auto_persist=True` : écriture sur disque à chaque tuile

### 🤖 IA Détection Nuages + Seams — `O4_Provider_Score` amélioré
- **Nuages** : 3 critères combinés — nuages denses, voile atmosphérique, exclusion ciel bleu
  - Tolérance jusqu'à 5% de couverture nuageuse (évite les faux positifs)
  - Détection du brouillard et voile via variance locale
  - Ciel bleu non pénalisé
- **Seam risk** : analyse sur 4 bords indépendants
  - Détection des jointures directionnelles (1 seul bord problématique)
  - Gradient abrupt sur ligne de bordure
  - Score détaillé par composante

### 🌧️ XP12 Materials — `O4_XP12_Materials`
- Détection automatique du type de sol depuis l'image : forêt, eau, neige, urbain, champ, sol nu, plage
- Paramètres XP12 générés automatiquement : `WET`, `ROUGHNESS`, `SPECULAR`, `NORMAL_SCALE`
- Injection directe dans les fichiers `.ter` (backup automatique avant modification)
- Idempotent : une 2ème application met à jour sans dupliquer les directives
- Profils calibrés par type de sol (ex. eau : wet=1.0, specular=0.80)

### ⏱️ Timeline + Benchmark + Debug — `O4_Benchmark`
- **Timeline** : suivi chronologique des 5 étapes du build, rapport en fin de session
- **Benchmark** : mesure CPU vs GPU pour histogramme, color transfer, feathering
- **Debug visualizations** : images PNG de diagnostic dans `_debug_viz/`
  - `seam_risk_map` : zones à risque surlignées en rouge
  - `color_transfer_compare` : avant/après côte à côte
  - `blur_map` : carte de netteté (vert=net, bleu=flou)

### 🖥️ GUI — Bouton ⏱ Timeline + RAM live
- **Bouton ⏱ Chronologie** dans la barre Color Normalize — popup avec durées de chaque étape
- **Indicateur RAM live** : rafraîchi toutes les 5 secondes, rouge si > 80%
- **Couleurs boutons Mac corrigées** : texte visible sur fond foncé (Apple Silicon + Intel)
- **9 nouvelles entrées** dans les fichiers de langue EN et FR

---

## 🆕 Nouveautés V3.0 — Architecture Moderne

### 🔄 Event Bus — `O4_EventBus`
- Architecture event-driven : les modules communiquent sans se connaître directement
- 6 événements : `TILE_START`, `TILE_PROGRESS`, `TILE_COMPLETE`, `TILE_ERROR`, `PIPELINE_STEP`, `CACHE_HIT`
- Singleton thread-safe

### 🔄 Pipeline Orchestrateur — `O4_Pipeline`
- Gestion propre des étapes de construction
- Chaque étape est nommée, chronométrée, et publie son statut en temps réel
- Arrêt propre si une étape échoue — sans corruption de fichiers

### 🛡️ Cache Intelligent — `O4_Dependency`
- Hash SHA256 des paramètres de chaque tuile
- Si la tuile est déjà construite avec les mêmes paramètres → rebuild ignoré
- Sauvegarde dans `tile_meta.json` après chaque build réussi

### 🎨 Gestionnaire de Thèmes — `O4_Theme_Manager`
- 5 thèmes : **Roland** (défaut), **Ardoise**, **Sable du désert**, **Océan profond**, **Personnalisé**
- Thème sauvegardé automatiquement entre les sessions
- Compatible Windows, macOS, Linux

### 📊 Scoring Providers — `O4_Provider_Score`
- Évaluation automatique de chaque image téléchargée
- 5 critères : bruit, compression JPEG, nuages, drift colorimétrique, risque seam
- Score global 0–100 avec label qualité

### ⚡ Backend GPU/CPU — `O4_GPU_Backend`
- Détection automatique GPU (NVIDIA CUDA via CuPy ou PyTorch)
- Repli silencieux sur CPU si pas de GPU

---

## 🚀 Pourquoi ORTHO4XP V3.2 ?

L'objectif est de transformer ORTHO4XP en un **vrai moteur de traitement photogrammétrique moderne** tout en conservant une **compatibilité totale avec la V2** — aucun workflow existant n'est cassé.

### ✨ Les points forts

- 📦 **Zéro Terminal** — Installation et lancement entièrement automatisés
- 🖱️ **Accessibilité** — Conçu pour les simmers sans manipulation de code
- 🛠️ **Fiabilité** — Sauvegardes automatiques + rollback + staging intégré
- 🌊 **Eau transparente XP12** — Masques côtiers automatiques depuis le mesh
- 🎨 **Colorimétrie avancée** — Normalisation sRGB et correction visuelle par tuile
- 📊 **Scoring automatique** — Qualité des images évaluée, exportée CSV/JSON
- 🤖 **IA intégrée** — Détection nuages, seams et type de sol automatique
- 🌧️ **XP12 Materials** — Wetness, Roughness, Specular générés automatiquement
- ⏱️ **Timeline** — Durées de chaque étape visibles dans la GUI
- 🧠 **RAM protégée** — Indicateur live + nettoyage automatique
- ⚡ **GPU si disponible** — Accélération automatique, CPU sinon

---

## 📂 Structure des nouveaux fichiers (V3.2)

```
src/
├── O4_Backup_Manager.py       ← Sauvegardes horodatées + rollback
├── O4_Memory_Manager.py       ← Protection Cache RAM
├── O4_Provider_Abstraction.py ← Provider failover automatique
├── O4_Score_Logger.py         ← Export scores CSV/JSON
├── O4_Provider_Score.py       ← IA nuages + seams (amélioré)
├── O4_XP12_Materials.py       ← Wetness/Roughness/Specular XP12
├── O4_Benchmark.py            ← Timeline + Benchmark + Debug viz
├── O4_DSF_Utils.py            ← Protection verrou (modifié minimal)
├── O4_Imagery_Utils.py        ← Score + failover branché (modifié)
├── O4_GUI_Utils.py            ← Timeline GUI + RAM live (modifié)
├── O4_Lang_EN.py              ← Traductions EN (mis à jour)
└── O4_Lang_FR.py              ← Traductions FR (mis à jour)

rollback.py                    ← Script rollback 1-clic (racine)
```

---

## 🖥️ Interfaces graphiques V3.2

### Installation et Lanceur

![Lanceur Ortho4XP V3](01_Lanceur_installation_python,_venv.jpg)

![Lanceur Ortho4XP V3](02_Lanceur_Ortho4xp_V2.jpg)

### Interface principale et Color Check

![Interface principale](03_Nouvelle_interface.jpg)

![Color Check](04_Color_Check_01.jpeg)

---

## 🛠 Utilisation rapide

### 🍎 Mac

> ⚠️ **Étape obligatoire avant tout** — Téléchargez d'abord le lanceur pré-nettoyé (sans blocage Gatekeeper) :  
> ⬇️ [Télécharger ORTHO4XP-V3_LANCEUR MAC PRE-INSTALL](https://github.com/Ypsos/ORTHO4XP_V3/releases/latest)

1. Téléchargez l'archive principale **ORTHO4XP_V3** (bouton vert "Code" → "Download ZIP")
2. Décompressez l'archive — renommez le dossier en `ORTHO4XP_V3`
3. Téléchargez le ZIP de la Release et extrayez `Lanceur_Installation_Prerequis.app` dans `ORTHO4XP_V3`
4. Placez le dossier dans **Applications** (`/Users/votre_nom/Applications/`)
5. Double-cliquez sur `Lanceur_Installation_Prerequis.app`

---

### 🪟 Windows

1. Téléchargez l'archive principale **ORTHO4XP_V3** et décompressez
2. Double-cliquez sur `LANCEUR_INSTALL_WINDOWS.bat`

---

### 🐧 Linux

1. Téléchargez l'archive principale **ORTHO4XP_V3** et décompressez
2. Double-cliquez sur `LANCEUR_INSTALL_LINUX.sh`

---

## 🔄 Rollback — restauration en 1 clic

Si un problème survient après mise à jour, depuis le terminal dans le dossier Ortho4XP :

```bash
# Lister toutes les sauvegardes disponibles
python rollback.py

# Restaurer un fichier spécifique
python rollback.py src/O4_DSF_Utils.py

# Restaurer une version précise par timestamp
python rollback.py src/O4_DSF_Utils.py 20260518_143022
```

---

## 📜 Crédits

| | |
|---|---|
| **Concept & Design** | Roland (Ypsos) |
| **Codage & Support IA** | Claude (Anthropic AI) |
| **Travaux originaux** | Oscar Pilote (Ortho4XP) |
| **Adaptation 1.40** | Shred86 |
| **Documentation** | English wiki: [xpconnect.me/ortho4xp](https://xpconnect.me/ortho4xp/) |

---

## ⚠️ Licence

Distribué sous **GNU GPL v3** dans le respect de la licence du projet original.  
Voir [AVERTISSEMENT_LICENCE_LEGAL.md](AVERTISSEMENT_LICENCE_LEGAL.MD) pour les détails complets.
