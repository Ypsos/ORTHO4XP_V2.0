# ORTHO4XP V3.0

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

## ⚡ Tableau comparatif — V1.40 vs V2 vs V3

| Fonctionnalité | Ortho4XP 1.40 (Shred86) | Ortho4XP V2 (Roland) | **Ortho4XP V3 (Roland)** |
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
| **Event Bus** | Absent | Absent | ✅ **NOUVEAU V3** — Architecture event-driven |
| **Pipeline orchestré** | Absent | Absent | ✅ **NOUVEAU V3** — Étapes nommées, statuts, durées |
| **Cache intelligent** | Absent | Absent | ✅ **NOUVEAU V3** — Rebuild ignoré si tuile à jour |
| **Thèmes interface** | Absent | Absent | ✅ **NOUVEAU V3** — 5 thèmes + personnalisation |
| **Scoring providers** | Absent | Absent | ✅ **NOUVEAU V3** — Qualité image évaluée automatiquement |
| **GPU Backend** | Absent | Absent | ✅ **NOUVEAU V3** — CUDA auto, CPU fallback silencieux |

---

## 🆕 Nouveautés V3 — Architecture Moderne (Mai 2026)

### 🔄 Event Bus — `O4_EventBus`
- Architecture event-driven : les modules communiquent sans se connaître directement
- 6 événements : `TILE_START`, `TILE_PROGRESS`, `TILE_COMPLETE`, `TILE_ERROR`, `PIPELINE_STEP`, `CACHE_HIT`
- Singleton thread-safe — aucune interférence entre les threads de build
- Base de toute l'architecture V3

### 🔄 Pipeline Orchestrateur — `O4_Pipeline`
- Gestion propre et lisible des étapes de construction (download → convert → DSF)
- Chaque étape est nommée, chronométrée, et publie son statut en temps réel
- Arrêt propre si une étape requise échoue — sans corruption de fichiers
- Rapport lisible en fin de build

### 🛡️ Cache Intelligent — `O4_Dependency`
- Hash SHA256 des paramètres de chaque tuile
- Si la tuile est déjà construite avec les mêmes paramètres → rebuild ignoré automatiquement
- Sauvegarde dans `tile_meta.json` après chaque build réussi
- Gain de temps immédiat sur les re-builds

### 🎨 Gestionnaire de Thèmes — `O4_Theme_Manager`
- 5 thèmes inclus : **Roland** (défaut), **Ardoise**, **Sable du désert**, **Océan profond**, **Personnalisé**
- Thème sauvegardé automatiquement entre les sessions (`~/.ortho4xp_theme.json`)
- Appliqué à toute l'interface au démarrage
- Compatible Windows, macOS, Linux

### 📊 Scoring Providers — `O4_Provider_Score`
- Évaluation automatique de chaque image téléchargée
- 5 critères : bruit, compression JPEG, nuages, drift colorimétrique, risque seam
- Score global 0–100 avec label qualité (✅ Excellent / 🟡 Correct / 🟠 Médiocre / 🔴 Mauvais)
- Historique sauvegardé par provider et par tuile (`~/.ortho4xp_provider_scores.json`)
- Rapport affiché automatiquement en fin de build

### ⚡ Backend GPU/CPU — `O4_GPU_Backend`
- Détection automatique GPU (NVIDIA CUDA via CuPy ou PyTorch)
- Repli silencieux sur CPU numpy si pas de GPU — aucune configuration requise
- Calculs accélérés : histogramme, transfert couleur, DeltaE, feathering, niveaux
- Même interface pour l'appelant, quel que soit le backend

---

## 🚀 Pourquoi ORTHO4XP V3 ?

L'objectif de la V3 est de transformer ORTHO4XP en un **vrai moteur de traitement photogrammétrique moderne** tout en conservant une **compatibilité totale avec la V2** — aucun workflow existant n'est cassé.

### ✨ Les points forts

- 📦 **Zéro Terminal** — Installation et lancement entièrement automatisés
- 🖱️ **Accessibilité** — Conçu pour les simmers qui veulent créer leurs tuiles sans manipuler de code
- 🛠️ **Fiabilité** — Base solide 1.40 + architecture moderne V3 + environnement Python isolé
- 🌊 **Eau transparente XP12** — Masques côtiers automatiques depuis le mesh
- 🎨 **Colorimétrie avancée** — Normalisation sRGB et correction visuelle par tuile
- 🎨 **Thèmes personnalisables** — Interface à vos couleurs, sauvegardée automatiquement
- 📊 **Scoring automatique** — Qualité des images évaluée et mémorisée par provider
- ⚡ **GPU si disponible** — Accélération automatique, CPU sinon
- 🔄 **Cache intelligent** — Pas de rebuild inutile

---

## 🖥️ Interfaces graphiques V3.0

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
3. Téléchargez le ZIP de la Release ci-dessus et extrayez `Lanceur_Installation_Prerequis.app` directement dans le dossier `ORTHO4XP_V3`
4. Placez le dossier `ORTHO4XP_V3` dans votre dossier **Applications** (`/Users/votre_nom/Applications/`)
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
