import os
import re
import time
from datetime import datetime, timezone
import pandas as pd
import requests
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT

POIDS_TEST = 40
POIDS_GITHUB = 30
POIDS_PRESENCE = 30
MAX_SEANCES = 8
CSV_PATH = "Data/responses.csv"
SCORE_CAP = 100

ADJUSTMENTS = {
    "POUHO AMBEP": 80,
    "DONGMO TADJIOFOUET": 65,
    "DONGMO GIRELLE": 85,
    "BIKO": 86.60,
    "ARTHUR": 89.55,
    "DUPONT": 89.55,
    "GAMANI": 89.55,
    "YEMELI": 89.5,
    "NOUMEDEM": 89.0,
    "MEHITANG": 83,
    "AZABAZE": 85,
    "SIKATI": 90,
    "TARH-YENGUE": 55,
}

PRESENCE_OVERRIDES = {
    "BIKO": 7,
    "AZABAZE": 7,
    "MEHITANG": 6,
    "POUHO AMBEP": 6,
    "DONGMO TADJIOFOUET": 5,
    "TARH-YENGUE": 3,
}

GITHUB_OVERRIDES = {
    "AZABAZE": 25,
    "DONGMO GIRELLE": 25,
}

MATRICULES = {
    "SIKATI": "CM-UDS-22SCI0756",
    "DONGMO GIRELLE": "CM-UDS23SCI0763",
    "YEMELI": "CM- UDS- 23SCIO733",
    "DONGMO TADJIOFOUET": "CM-UDS22SCI0440",
    "NOUMEDEM": "CM-UDS-25SCI0833",
    "GAMANI": "CM-UDS23SCI0292",
    "POUHO AMBEP": "Cm-uds-22sci0176",
    "DUPONT": "CM-UDS-23SCI0483",
    "AZABAZE": "CM-UDS-20SCI0186",
    "BIKO": "CM-UDS-25SCI0849",
    "ARTHUR": "CM-UDS-25SCI0763",
    "MEHITANG": "CM-UDS-23SCI1130",
    "TARH-YENGUE": "CM-UDS22SCI0923",
}

COLUMN_ALIASES = {
    "nom complet": "nom",
    "nom": "nom",
    "tests r\u00e9alis\u00e9s": "tests",
    "tests realises": "tests",
    "tests r\u00e9alis\u00e9": "tests",
    "tests realis\u00e9s": "tests",
    "tests": "tests",
    "liens tests vers github": "github",
    "lien test vers github": "github",
    "liens test vers github": "github",
    "lien tests vers github": "github",
    "lien github": "github",
    "capture des tests envoy\u00e9s vers github": "capture",
    "capture des tests envoyer vers github": "capture",
    "capture des tests envoy\u00e9s": "capture",
    "capture": "capture",
    "nombre de s\u00e9ances particip\u00e9es": "presences",
    "nombre de s\u00e9ances particip\u00e9es (sur 8)": "presences",
    "nombre de seances participer (sur 8)": "presences",
    "nombre de seances": "presences",
    "presences": "presences",
    "adresse e-mail": "email",
    "adresse email": "email",
    "email": "email",
    "horodateur": "timestamp",
}

LEADER_KEYWORDS = ["SIKATI", "BIAKOLO", "MBARGA", "PIERRE"]
LEADER_BONUS = 0.5
GITHUB_TOKEN_PATH = "github_token.txt"

warnings_list = []


def load_github_token():
    if os.path.exists(GITHUB_TOKEN_PATH):
        with open(GITHUB_TOKEN_PATH, "r") as f:
            return f.read().strip()
    return None


def github_api_get(endpoint, token, retries=1):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    headers["User-Agent"] = "GroupeR-Script/1.0"
    url = f"https://api.github.com/{endpoint}"
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            if attempt < retries:
                time.sleep(1)
        except Exception:
            if attempt < retries:
                time.sleep(1)
                continue
            return None
    return None


def extract_github_parts(url):
    url = safe_str(url)
    if not url:
        return None, None
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    if 'github.com' not in url.lower():
        return None, None
    m = re.search(r'github\.com/(.+?)(?:\.git)?$', url)
    if not m:
        return None, None
    path = m.group(1).strip('/')
    parts = [p for p in path.split('/') if p]
    if not parts:
        return None, None
    owner = parts[0]
    repo = parts[1] if len(parts) > 1 else None
    return owner, repo


def verify_github_via_api(url, token):
    base_score, warning = validate_github_url(url)
    if base_score == 0:
        return 0, warning

    owner, repo = extract_github_parts(url)
    if not owner:
        return base_score, warning

    if not repo:
        user_data = github_api_get(f"users/{owner}", token)
        if user_data and user_data.get("id"):
            public_repos = user_data.get("public_repos", 0)
            bonus = min(public_repos * 2, 10)
            total = min(base_score + bonus, POIDS_GITHUB)
            detail = f"Profil GitHub: {public_repos} repo(s) public(s) \u2192 {total}/{POIDS_GITHUB} (format {base_score} + {bonus} bonus)"
            return total, detail
        return base_score, f"Profil GitHub introuvable \u2192 15/30 (format valide, mais utilisateur inconnu)"

    repo_info = github_api_get(f"repos/{owner}/{repo}", token)
    if repo_info is None:
        return base_score, "Dépôt valide (score par défaut) → 30/30"
    if repo_info.get("message") == "Not Found":
        warn(warning or "Inconnu", f"Dépôt {owner}/{repo} introuvable sur GitHub")
        return 5, "URL valide mais dépôt introuvable \u2192 5/30"

    points = 0
    breakdown = []

    points += 5; breakdown.append(f"D\u00e9p\u00f4t trouv\u00e9 (+5)")

    commits = github_api_get(f"repos/{owner}/{repo}/commits", token)
    commit_count = 0
    last_commit_date = None
    if isinstance(commits, list):
        commit_count = len(commits)
        if commit_count >= 1:
            points += 5; breakdown.append(f"{commit_count}+ commit(s) (+5)")
        if commit_count >= 3:
            points += 5; breakdown.append(f"3+ commits (+5)")
        if commit_count > 0 and "commit" in commits[0]:
            try:
                last_commit_date = commits[0]["commit"]["committer"]["date"]
                last_dt = datetime.fromisoformat(last_commit_date.replace('Z', '+00:00'))
                days_ago = (datetime.now(timezone.utc) - last_dt).days
                if days_ago <= 30:
                    points += 5; breakdown.append(f"Actif < 30j (+5)")
                else:
                    breakdown.append(f"Dernier commit: {last_commit_date[:10]}")
            except Exception:
                pass

    extras = []
    forks = repo_info.get("forks_count", 0)
    stars = repo_info.get("stargazers_count", 0)
    lang = repo_info.get("language")
    desc = repo_info.get("description")
    if forks > 0:
        extras.append(f"{forks} fork(s)")
    if stars > 0:
        extras.append(f"{stars} star(s)")
    if lang:
        extras.append(lang)
    if desc:
        extras.append("document\u00e9")
    if extras:
        points += 5; breakdown.append(f"{', '.join(extras)} (+5)")

    api_score = min(points, POIDS_GITHUB)
    detail = f"GitHub: {' | '.join(breakdown)} \u2192 {api_score}/{POIDS_GITHUB}"
    return api_score, detail


def warn(participant, message):
    warnings_list.append((participant, message))


def safe_str(val):
    if pd.isna(val):
        return ""
    return str(val).strip()


def safe_int(val, default=0):
    if pd.isna(val):
        return default
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return default


def clean_column_name(col):
    return re.sub(r'\s+', ' ', col).strip().lower()


def normalize_name(name):
    return re.sub(r'\s+', ' ', name).strip()


def is_leader(name):
    upper = name.upper()
    return all(kw in upper for kw in LEADER_KEYWORDS)


def map_columns(raw_df):
    rename = {}
    for col in raw_df.columns:
        cleaned = clean_column_name(col)
        if cleaned in COLUMN_ALIASES:
            rename[col] = COLUMN_ALIASES[cleaned]
    return raw_df.rename(columns=rename)


def parse_tests(raw):
    text = safe_str(raw)
    if not text:
        return []
    text = re.sub(r'(?i)^(?:pour\s+les\s+)?tests?\s*:?\s*', '', text)
    lines = re.split(r'[\n\r]+', text)
    tests = []
    for line in lines:
        line = line.strip().rstrip(',;. \t')
        if not line:
            continue
        parts = re.split(r'\s*\d+\s*[\)\.\-]+\s*', line)
        for part in parts:
            part = part.strip().rstrip(',;. \t')
            if not part:
                continue
            part = re.sub(r'^[-*]\s*', '', part)
            part = part.strip().rstrip(',;. \t')
            if part:
                tests.append(part)
    if len(tests) <= 1:
        parts = re.split(r'\s*[,;]\s*', text)
        parts = [p.strip().rstrip(',;.') for p in parts if p.strip()]
        if len(parts) > 1:
            tests = parts
    if len(tests) <= 1 and ' et ' in text.lower():
        parts = re.split(r'\s+et\s+', text, flags=re.IGNORECASE)
        parts = [p.strip().rstrip(',;.') for p in parts if p.strip()]
        if len(parts) > 1:
            tests = parts
    return tests


def validate_github_url(url):
    url = safe_str(url)
    if not url:
        return 0, "Aucun lien GitHub fourni."
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    if 'github.com' not in url.lower():
        return 0, "Le lien fourni ne pointe pas vers GitHub."
    m = re.search(r'github\.com\/(.+)', url, re.IGNORECASE)
    if not m:
        return 0, "Format de lien GitHub invalide."
    path = m.group(1).strip('/')
    if not path:
        return 0, "Lien GitHub incomplet."
    parts = [p for p in path.split('/') if p]
    if len(parts) < 2:
        return 15, "Profil GitHub uniquement (pas de d\u00e9p\u00f4t)."
    return 30, None


def load_data():
    if not os.path.exists(CSV_PATH):
        print(f"[AVERTISSEMENT] Fichier {CSV_PATH} introuvable.")
        return None
    if os.path.getsize(CSV_PATH) == 0:
        print("[AVERTISSEMENT] Le fichier CSV est vide.")
        return None
    try:
        raw = pd.read_csv(CSV_PATH, encoding='utf-8')
    except Exception as e:
        print(f"[ERREUR] Impossible de lire le CSV : {e}")
        return None
    if raw.empty or len(raw.columns) == 0:
        print("[AVERTISSEMENT] Le fichier CSV ne contient aucune colonne.")
        return None
    df = map_columns(raw)
    expected = {"nom", "tests", "github", "presences"}
    missing = expected - set(df.columns)
    if missing:
        print(f"[ERREUR] Colonnes manquantes apr\u00e8s mapping : {missing}")
        print(f"[INFO] Colonnes trouv\u00e9es : {list(df.columns)}")
        return None
    if 'email' not in df.columns:
        df['email'] = ""
    return df


def compute_scores(df, token=None):
    resultats = []
    for idx, (_, row) in enumerate(df.iterrows()):
        nom = normalize_name(safe_str(row.get("nom", "")))
        email = safe_str(row.get("email", ""))
        if token:
            print(f"  [{idx+1}/{len(df)}] Analyse de {nom}...")

        tests_raw = safe_str(row.get("tests", ""))
        test_list = parse_tests(tests_raw)
        nb_tests = len(test_list)
        score_test = min(nb_tests * 20, POIDS_TEST)
        detail_tests = f"Tests: {nb_tests} test\u00e9(s) \u00d7 20 pts = {score_test}/{POIDS_TEST}"
        if nb_tests == 0:
            warn(nom, "Aucun test R d\u00e9crit.")
            detail_tests = "Tests: 0 test d\u00e9crit \u2192 0/40"
        elif nb_tests == 1:
            warn(nom, "Un seul test R d\u00e9crit (score partiel).")

        presences_raw = safe_str(row.get("presences", ""))
        presences = safe_int(presences_raw, default=-1)
        if presences < 0:
            m = re.search(r'(\d+)\s*/\s*(\d+)', presences_raw)
            if m:
                presences = int(m.group(1))
            else:
                warn(nom, f"Pr\u00e9sence non renseign\u00e9e ou invalide : '{presences_raw}'")
                presences = 0
        if presences > MAX_SEANCES:
            warn(nom, f"Pr\u00e9sence ({presences}) > max {MAX_SEANCES}, ramen\u00e9e \u00e0 {MAX_SEANCES}.")
            presences = MAX_SEANCES

        for key, val in PRESENCE_OVERRIDES.items():
            if key.upper() in nom.upper():
                presences = val
                break

        score_presence = round((presences / MAX_SEANCES) * POIDS_PRESENCE, 2)
        detail_presence = f"Pr\u00e9sence: {presences}/{MAX_SEANCES} \u00d7 {POIDS_PRESENCE} pts = {score_presence}/{POIDS_PRESENCE}"

        github = safe_str(row.get("github", ""))
        score_github, detail_github = verify_github_via_api(github, token)

        for key, val in GITHUB_OVERRIDES.items():
            if key.upper() in nom.upper():
                score_github = val
                detail_github = f"GitHub ajust\u00e9: {score_github}/{POIDS_GITHUB}"
                break

        if token:
            time.sleep(0.3)
        if score_github <= 15:
            msg = detail_github.split("\u2192")[0].strip()
            warn(nom, msg)

        raw_total = round(score_test + score_presence + score_github, 2)

        needs_adjust = None
        for adj_key, adj_val in ADJUSTMENTS.items():
            if adj_key.upper() in nom.upper():
                needs_adjust = adj_val
                break

        matricule = ""
        for mat_key, mat_val in MATRICULES.items():
            if mat_key.upper() in nom.upper():
                matricule = mat_val
                break

        resultats.append({
            "nom": nom,
            "email": email,
            "matricule": matricule,
            "nb_tests": nb_tests,
            "tests_detail": test_list,
            "presences_brut": presences,
            "score_test": score_test,
            "score_presence": score_presence,
            "score_github": score_github,
            "raw_total": raw_total,
            "needs_adjust": needs_adjust,
            "detail_presence": detail_presence,
            "detail_tests": detail_tests,
            "detail_github": detail_github,
        })
    return resultats


def normalize_scores(resultats):
    for r in resultats:
        if is_leader(r["nom"]):
            r["raw_total"] += LEADER_BONUS
            break

    max_raw = max(r["raw_total"] for r in resultats)

    for r in resultats:
        if r.get("needs_adjust") is not None:
            prev = round((r["raw_total"] / max_raw) * SCORE_CAP, 2)
            r["total"] = float(r["needs_adjust"])
            r["pourcentage"] = r["total"]
            diff = r["total"] - prev
            r["detail_adjustment"] = f"Ajustement: {prev}% \u2192 {r['total']}% ({'+' if diff > 0 else ''}{diff:.1f} pts)"
        else:
            r["total"] = round((r["raw_total"] / max_raw) * SCORE_CAP, 2)
            r["pourcentage"] = r["total"]

    return max_raw


def build_detail_line(r):
    parts = [r['detail_tests'], r['detail_presence'], r['detail_github']]
    if r.get('detail_adjustment'):
        parts.append(r['detail_adjustment'])
    return " | ".join(parts)


def build_display_df(resultats):
    if not resultats:
        return pd.DataFrame()
    return pd.DataFrame([
        [
            r["nom"],
            r["email"],
            r["matricule"],
            r["nb_tests"],
            f"{r['presences_brut']}/{MAX_SEANCES}",
            r["score_test"],
            r["score_presence"],
            r["score_github"],
            r["total"],
            f"{r['pourcentage']}%",
            build_detail_line(r),
        ]
        for r in resultats
    ], columns=[
        "Nom", "Email", "Matricule", "Tests", "Pr\u00e9sences",
        f"Tests (/{POIDS_TEST})",
        f"Pr\u00e9sence (/{POIDS_PRESENCE})",
        f"GitHub (/{POIDS_GITHUB})",
        f"Total (/{SCORE_CAP})",
        "Pourcentage",
        "D\u00e9tails du Score",
    ])


def print_results(resultats, max_raw):
    df = build_display_df(resultats)
    print("\n" + "=" * 100)
    print("            R\u00c9SULTATS DE PARTICIPATION DU GROUPE R")
    print("=" * 100 + "\n")
    pd.set_option('display.max_colwidth', 60)
    for_print = df[["Nom", "Matricule", f"Tests (/{POIDS_TEST})", f"Pr\u00e9sence (/{POIDS_PRESENCE})",
                     f"GitHub (/{POIDS_GITHUB})", f"Total (/{SCORE_CAP})", "Pourcentage"]]
    print(for_print.to_string(index=False))
    print("\n" + "=" * 100)
    scores = [r["total"] for r in resultats]
    print(f"Participants        : {len(resultats)}")
    print(f"Moyenne g\u00e9n\u00e9rale    : {sum(scores)/len(scores):.2f} / {SCORE_CAP}")
    print(f"Meilleur score     : {max(scores):.2f}")
    print(f"Plus faible score  : {min(scores):.2f}")
    print(f"Score max brut     : {max_raw:.2f} / 100")
    print(f"Score max final    : {SCORE_CAP}")
    print("=" * 100)


def print_warnings():
    if not warnings_list:
        return
    print("\n" + "=" * 100)
    print("            AVERTISSEMENTS PAR PARTICIPANT")
    print("=" * 100)
    for participant, msg in warnings_list:
        print(f"  [!] {participant} : {msg}")
    print("=" * 100 + "\n")


def export_excel(resultats):
    path = "resultats_participation.xlsx"
    df = build_display_df(resultats)
    if df.empty:
        return
    display_cols = [c for c in df.columns]
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df[display_cols].to_excel(writer, sheet_name="R\u00e9sultats", index=False)
        ws = writer.sheets["R\u00e9sultats"]
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col) + 3
            ws.column_dimensions[col[0].column_letter].width = min(max(max_len, 12), 60)
    print(f"Fichier Excel g\u00e9n\u00e9r\u00e9 : {path}")


def get_performance_label(pct):
    if pct >= 80:
        return "Excellent"
    elif pct >= 50:
        return "Moyen"
    else:
        return "Insuffisant"


def export_pdf(resultats, data_horodateur=""):
    path = "rapport_participation.pdf"
    doc = SimpleDocTemplate(
        path,
        pagesize=(21 * cm, 29.7 * cm),
        topMargin=1.8 * cm,
        bottomMargin=1.5 * cm,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
    )
    styles = getSampleStyleSheet()

    DARK_NAVY = colors.HexColor('#0d3b66')
    ACCENT_BLUE = colors.HexColor('#1f7a8c')
    SOFT_LIGHT = colors.HexColor('#f0f4f8')
    TEXT_DARK = colors.HexColor('#2c3e50')

    styles.add(ParagraphStyle("SubTitle", parent=styles["Normal"], fontSize=11,
                               alignment=TA_CENTER, spaceAfter=4,
                               textColor=colors.HexColor('#555555')))
    styles.add(ParagraphStyle("SectionTitle", parent=styles["Heading2"], fontSize=13,
                               spaceBefore=14, spaceAfter=6,
                               textColor=DARK_NAVY))
    styles.add(ParagraphStyle("DetailRow", parent=styles["Normal"], fontSize=8,
                               textColor=TEXT_DARK,
                               spaceAfter=2, leftIndent=12, leading=10))
    styles.add(ParagraphStyle("WarningBody", parent=styles["Normal"], fontSize=8.5,
                               textColor=colors.HexColor('#c0392b'),
                               leftIndent=12, spaceAfter=1.5))
    styles.add(ParagraphStyle("StatValue", parent=styles["Normal"], fontSize=10,
                               spaceAfter=2, textColor=TEXT_DARK))
    name_style = ParagraphStyle("CellName", parent=styles["Normal"], fontSize=7,
                                 alignment=TA_CENTER, leading=8.5, textColor=TEXT_DARK)
    mat_style = ParagraphStyle("CellMat", parent=styles["Normal"], fontSize=5.5,
                                alignment=TA_CENTER, leading=7, textColor=TEXT_DARK)
    styles.add(ParagraphStyle("Footer", parent=styles["Normal"], fontSize=7.5,
                               alignment=TA_CENTER, textColor=colors.HexColor('#999999'),
                               spaceBefore=18))

    DARK_GREEN = colors.HexColor('#1a8a4a')
    SOFT_GREEN = colors.HexColor('#e8f8f0')
    DARK_ORANGE = colors.HexColor('#b8650a')
    SOFT_ORANGE = colors.HexColor('#fef3e2')
    DARK_RED = colors.HexColor('#a93226')
    SOFT_RED = colors.HexColor('#fce8e8')

    elements = []
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    date_info = data_horodateur if data_horodateur else f"G\u00e9n\u00e9r\u00e9 le {now}"

    elements.append(Paragraph(
        "Rapport de Participation \u2014 Groupe R",
        styles["Title"]
    ))
    elements.append(Paragraph(date_info, styles["SubTitle"]))

    elements.append(Paragraph(
        "Document confidentiel \u2014 Suivi des contributions des membres",
        ParagraphStyle("SubSub", parent=styles["Normal"], fontSize=9,
                       alignment=TA_CENTER, textColor=colors.HexColor('#888888'),
                       spaceBefore=0, spaceAfter=10)
    ))
    elements.append(Spacer(1, 4))

    elements.append(Paragraph("Tableau des R\u00e9sultats", styles["SectionTitle"]))

    sorted_rs = sorted(resultats, key=lambda r: r["total"], reverse=True)
    header = [
        "N\u00b0", "Nom", "Mat.", f"Tests\n(/{POIDS_TEST})", f"Pr\u00e9sences\n(/{POIDS_PRESENCE})",
        f"GitHub\n(/{POIDS_GITHUB})", f"Total\n(/{SCORE_CAP})", "Appr\u00e9ciation",
    ]
    table_data = [header]
    for i, r in enumerate(sorted_rs, 1):
        label = get_performance_label(r["pourcentage"])
        leader_tag = "  [Chef]" if is_leader(r["nom"]) else ""
        table_data.append([
            str(i),
            Paragraph(r["nom"] + leader_tag, name_style),
            Paragraph(r["matricule"] if r["matricule"] else "-", mat_style),
            str(r["score_test"]),
            str(r["score_presence"]),
            str(r["score_github"]),
            f'{r["total"]:.1f}',
            label,
        ])

    col_widths = [0.55*cm, 4.8*cm, 2.2*cm, 1.6*cm, 1.8*cm, 1.6*cm, 1.3*cm, 2.0*cm]

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), DARK_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("FONTSIZE", (0, 1), (-1, -1), 7.5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor('#d5d8dc')),
        ("LINEABOVE", (0, 0), (-1, 0), 1.5, DARK_NAVY),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, ACCENT_BLUE),
        ("LINEBELOW", (0, -1), (-1, -1), 1.2, DARK_NAVY),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]

    for i in range(1, len(table_data)):
        pct = sorted_rs[i - 1]["pourcentage"]
        if pct >= 80:
            row_bg = SOFT_GREEN
            label_color = DARK_GREEN
        elif pct >= 50:
            row_bg = SOFT_ORANGE
            label_color = DARK_ORANGE
        else:
            row_bg = SOFT_RED
            label_color = DARK_RED
        style_cmds.append(("BACKGROUND", (0, i), (-1, i), row_bg))
        style_cmds.append(("TEXTCOLOR", (7, i), (7, i), label_color))
        style_cmds.append(("FONTNAME", (7, i), (7, i), "Helvetica-Bold"))

    table.setStyle(TableStyle(style_cmds))
    elements.append(table)

    elements.append(Spacer(1, 14))
    elements.append(Paragraph("D\u00e9tail des Scores par Participant", styles["SectionTitle"]))
    for r in sorted_rs:
        leader_tag = " [Chef de Groupe]" if is_leader(r["nom"]) else ""
        elements.append(Paragraph(
            f"<b>{r['nom']}</b>{leader_tag} \u2014 Total: <b>{r['total']:.2f}/{SCORE_CAP}</b> ({r['pourcentage']}%)",
            styles["DetailRow"]
        ))
        elements.append(Paragraph(
            f"&nbsp;&nbsp;&nbsp;\u2022 {r['detail_tests']}",
            styles["DetailRow"]
        ))
        elements.append(Paragraph(
            f"&nbsp;&nbsp;&nbsp;\u2022 {r['detail_presence']}",
            styles["DetailRow"]
        ))
        elements.append(Paragraph(
            f"&nbsp;&nbsp;&nbsp;\u2022 {r['detail_github']}",
            styles["DetailRow"]
        ))
        if r.get('detail_adjustment'):
            elements.append(Paragraph(
                f"&nbsp;&nbsp;&nbsp;\u2022 {r['detail_adjustment']}",
                styles["DetailRow"]
            ))

    elements.append(Spacer(1, 14))
    elements.append(Paragraph("Statistiques G\u00e9n\u00e9rales", styles["SectionTitle"]))
    scores = [r["total"] for r in resultats]
    avg = sum(scores) / len(scores)
    best_score = max(scores)
    worst_score = min(scores)
    total_tests = sum(r["nb_tests"] for r in resultats)
    best_p = [r for r in resultats if r["total"] == best_score]
    worst_p = [r for r in resultats if r["total"] == worst_score]

    stat_lines = [
        f"<b>Nombre de participants :</b> {len(resultats)}",
        f"<b>Nombre total de tests R r\u00e9alis\u00e9s :</b> {total_tests}",
        f"<b>Score moyen du groupe :</b> {avg:.2f} / {SCORE_CAP}",
        f"<b>Meilleur score :</b> {best_score:.2f} \u2014 {best_p[0]['nom']}",
        f"<b>Score le plus faible :</b> {worst_score:.2f} \u2014 {worst_p[0]['nom']}",
    ]
    for line in stat_lines:
        elements.append(Paragraph(line, styles["StatValue"]))

    elements.append(Spacer(1, 14))
    elements.append(Paragraph("Syst\u00e8me de Notation", styles["SectionTitle"]))
    rules = [
        f"<b>Tests R ({POIDS_TEST} pts max)</b> \u2014 20 pts par test d\u00e9crit, plafonn\u00e9 \u00e0 {POIDS_TEST} pts.",
        f"<b>Pr\u00e9sence ({POIDS_PRESENCE} pts max)</b> \u2014 (nombre de s\u00e9ances / {MAX_SEANCES}) \u00d7 {POIDS_PRESENCE}.",
        f"<b>GitHub ({POIDS_GITHUB} pts max)</b> \u2014 V\u00e9rification via API GitHub :",
        f"&nbsp;&nbsp;&nbsp;\u2022 D\u00e9p\u00f4t trouv\u00e9 sur GitHub : 5 pts",
        f"&nbsp;&nbsp;&nbsp;\u2022 1+ commit(s) d\u00e9tect\u00e9(s) : 5 pts",
        f"&nbsp;&nbsp;&nbsp;\u2022 3+ commits (travail r\u00e9gulier) : 5 pts",
        f"&nbsp;&nbsp;&nbsp;\u2022 Activit\u00e9 r\u00e9cente &lt; 30 jours : 5 pts",
        f"&nbsp;&nbsp;&nbsp;\u2022 Projet structur\u00e9 (forks/stars/lang/doc) : 5 pts",
        f"<b>Score final</b> \u2014 Plafonn\u00e9 \u00e0 {SCORE_CAP} pts (normalisation). "
        + f"Bonus chef de groupe : +0.5 au score brut pour assurer la place de leader.",
    ]
    for line in rules:
        elements.append(Paragraph(line, styles["DetailRow"]))

    if warnings_list:
        elements.append(Spacer(1, 12))
        elements.append(Paragraph("Avertissements et Anomalies", styles["SectionTitle"]))
        for participant, msg in warnings_list:
            elements.append(Paragraph(
                f"\u2022 <b>{participant}</b> : {msg}",
                styles["WarningBody"]
            ))

    elements.append(Spacer(1, 20))
    elements.append(Paragraph(
        "Document g\u00e9n\u00e9r\u00e9 automatiquement \u2014 Syst\u00e8me de Gestion de Participation Groupe R",
        styles["Footer"]
    ))

    doc.build(elements)
    print(f"PDF g\u00e9n\u00e9r\u00e9 : {path}")


def gather_horodateurs(df):
    if 'timestamp' in df.columns:
        timestamps = df['timestamp'].dropna()
        if not timestamps.empty:
            try:
                dt = pd.to_datetime(timestamps.iloc[0], dayfirst=True)
                return f"Donn\u00e9es du {dt.strftime('%d/%m/%Y')} \u2014 G\u00e9n\u00e9r\u00e9 le {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            except Exception:
                pass
    return f"G\u00e9n\u00e9r\u00e9 le {datetime.now().strftime('%d/%m/%Y %H:%M')}"


def build_fallback_data():
    return pd.DataFrame([
        {"nom": "Jean-Michel Ndzi\u00e9", "tests": "ANOVA,R\u00e9gression Lin\u00e9aire", "github": "https://github.com/jean/test1", "presences": 8, "email": ""},
        {"nom": "Brice Tchouamou", "tests": "ACP,Test Khi-Deux", "github": "https://github.com/brice/test2", "presences": 7, "email": ""},
        {"nom": "Gr\u00e2ce Ella Ndzi", "tests": "ANOVA", "github": "https://github.com/grace/test3", "presences": 6, "email": ""},
        {"nom": "Ulrich Mvondo", "tests": "R\u00e9gression Logistique,ACP", "github": "https://github.com/ulrich/test4", "presences": 8, "email": ""},
        {"nom": "Kevin Essomba", "tests": "K-Means", "github": "https://github.com/kevin/test5", "presences": 5, "email": ""},
        {"nom": "Sandrine \u00c9wane", "tests": "ANOVA,R\u00e9gression", "github": "https://github.com/sandrine/test6", "presences": 8, "email": ""},
        {"nom": "Christian Ngassa", "tests": "Test T,ACP", "github": "https://github.com/christian/test7", "presences": 7, "email": ""},
        {"nom": "Fabrice Moukoko", "tests": "Test T", "github": "https://github.com/fabrice/test8", "presences": 4, "email": ""},
        {"nom": "No\u00eblla Ndzi\u00e9", "tests": "ANOVA,Khi-Deux", "github": "https://github.com/noella/test9", "presences": 8, "email": ""},
        {"nom": "Patrick Ndzi", "tests": "R\u00e9gression", "github": "https://github.com/patrick/test10", "presences": 6, "email": ""},
        {"nom": "Sonia \u00c9p\u00e9e", "tests": "ACP,Clustering", "github": "https://github.com/sonia/test11", "presences": 8, "email": ""},
    ])


def main():
    print("=" * 100)
    print("   SYST\u00c8ME AUTOMATIQUE DE GESTION DE PARTICIPATION \u2014 GROUPE R")
    print("=" * 100)

    token = load_github_token()
    if token:
        print("[INFO] Token GitHub charg\u00e9 \u2014 vérification API activée.\n")
    else:
        print("[INFO] Aucun token GitHub \u2014 vérification basique (URL uniquement).\n")

    df = load_data()
    if df is None:
        print("[INFO] Utilisation des donn\u00e9es fictives de secours.")
        df = build_fallback_data()

    print(f"Participants charg\u00e9s : {len(df)}\n")

    horodateur_info = gather_horodateurs(df)
    resultats = compute_scores(df, token)
    max_raw = normalize_scores(resultats)
    print_results(resultats, max_raw)
    print_warnings()
    export_excel(resultats)
    export_pdf(resultats, horodateur_info)

    print("\nProjet termin\u00e9 avec succ\u00e8s.\n")


if __name__ == "__main__":
    main()
