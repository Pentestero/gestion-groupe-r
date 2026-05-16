# Dashboard Groupe R

Système automatisé de gestion de participation pour le Groupe R.

## Fonctionnalités

### 1. Scoring automatique (`main.py`)
- **Tests (/40)** : Parsing des tests R décrits dans le formulaire Google (séparés par numéros, puces ou "et"). 20 pts par test, max 40.
- **Présence (/30)** : (Nombre de séances / 8) × 30.
- **GitHub (/30)** : Vérification via API GitHub (dépôt trouvé, commits, activité récente, forks/stars/langue/description). Fallback format-based si API injoignable.
- **Normalisation** : Score brut ramené sur 100 avec leader bonus (+0.5) pour SIKATI.

### 2. Rapports générés
- **PDF** : `rapport_participation.pdf` — tableau coloré, détails par participant, règles de scoring.
- **Excel** : `resultats_participation.xlsx` — données complètes + colonne Détails.

### 3. Dashboard interactif (`app.py`)
- Flask + Plotly.js
- Classement trié avec barres de progression
- Graphiques (scores individuels, répartition)
- Filtre par nom
- Modal de détails par participant
- Bouton copier le lien / éteindre le serveur
- Design responsive mobile
- Prêt pour déploiement Render

### 4. Scores actuels (/100)

| Participant | Score |
|---|---|---|
| SIKATI BIAKOLO MBARGA PIERRE | **90.00** |
| GAMANI KAMDOM PIEERE DJIBRIL | **89.55** |
| DJEAGUE PRINCE DUPONT | **89.55** |
| MBONDE NGARARY ARTHUR | **89.55** |
| YEMELI MAFOUO CHARONNE LUCHRECE | **89.50** |
| NOUMEDEM RICHELLE | **89.00** |
| TSOMEJIO NKONG-DEM STEEVE BIKO | **86.60** |
| DONGMO GIRELLE MAËVA | **85.00** |
| AZABAZE JIONGO ISMAEL BRICE | **85.00** |
| MEHITANG ANDERSON BEBE | **83.00** |
| POUHO AMBEP RÉGIS RONY | **80.00** |
| DONGMO TADJIOFOUET Ivan Cabrel | **65.00** |
| TARH-YENGUE YANNICK | **55.00** |

## Données

- **Source** : Formulaire Google → `Data/responses.csv` (13 participants)
- **Colonnes** : Horodateur, Email, Tests réalisés, Capture tests, Lien GitHub, Nombre de séances, Nom complet
- **Colonne Matricule** : présente dans l'Excel et le PDF mais vide en attente du formulaire dédié

⚠️ **Les matricules ne sont pas encore renseignés** — un formulaire de collecte est à créer et à intégrer.

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Utilisation

```bash
# Générer les rapports (Excel + PDF)
python main.py

# Lancer le dashboard
python app.py
# → http://127.0.0.1:5000
```

## Déploiement

Projet prêt pour Render :
1. Pusher sur GitHub
2. Connecter le dépôt à Render
3. Render détecte automatiquement Python + Gunicorn

## Structure

```
├── app.py                  # Application Flask (dashboard)
├── main.py                 # Script principal (scoring + rapports)
├── Data/
│   └── responses.csv       # Réponses du formulaire Google
├── templates/
│   └── dashboard.html      # Template du dashboard
├── resultats_participation.xlsx
├── rapport_participation.pdf
├── requirements.txt
├── Procfile
├── render.yaml
└── .gitignore
```
