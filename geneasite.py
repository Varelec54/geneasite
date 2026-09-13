import os
import json
import re
from datetime import datetime
import unicodedata
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, colorchooser, ttk
from gedcom.parser import Parser
from gedcom.element.individual import IndividualElement
from gedcom.element.family import FamilyElement

def nettoyer_html(texte):
    if not texte: return ""
    return re.sub(r'<[^>]+>', '', texte)

def charger_gedcom(chemin_gedcom):
    gedcom_parser = Parser()
    gedcom_parser.parse_file(chemin_gedcom)
    return gedcom_parser

def generer_nom_fichier_php(ind_element):
    p = ind_element.get_pointer().replace('@', '')
    n = "".join(ind_element.get_name()[1]).strip().lower()
    pr = "".join(ind_element.get_name()[0]).strip().lower()
    nom_brut = f"{p}-{pr}-{n}"
    nom_nettoye = "".join(c for c in unicodedata.normalize("NFD", nom_brut) if unicodedata.category(c) != 'Mn')
    nom_nettoye = re.sub(r'[^a-z0-9\-]', '', nom_nettoye)
    return f"{nom_nettoye}.php"

def trouver_individu_par_id(target_id, gedcom_parser):
    for e in gedcom_parser.get_root_element().get_child_elements():
        if isinstance(e, IndividualElement) and e.get_pointer() == target_id:
            return e
    return None

def est_individu_vivant(ind_element, annee_actuelle):
    birth_date = "Inconnue"
    a_une_date_deces = False
    for child in ind_element.get_child_elements():
        if child.get_tag() == 'BIRT':
            for sub in child.get_child_elements():
                if sub.get_tag() == 'DATE': birth_date = sub.get_value().strip()
        if child.get_tag() == 'DEAT':
            a_une_date_deces = True

    if a_une_date_deces:
        return False

    annee_naissance = None
    if birth_date and birth_date not in ["Inconnu", "Inconnue", ""]:
        mots = birth_date.split()
        for mot in mots:
            if mot.isdigit() and len(mot) == 4:
                annee_naissance = int(mot)
                break

    if annee_naissance:
        if (annee_actuelle - annee_naissance) >= 100:
            return False
        else:
            return True
    else:
        return True

def generer_fichier_stats_inc(output_dir, ip_exclue, url_domaine=""):
    ip_filtrage = ip_exclue.strip() if ip_exclue.strip() else "0.0.0.0"
    
    code_redirection_https = ""
    if url_domaine.strip():
        domaine_clean = url_domaine.strip().replace("https://", "").replace("http://", "").rstrip("/")
        code_redirection_https = f"""
if (empty($_SERVER['HTTPS']) || $_SERVER['HTTPS'] === 'off') {{
    $url_securisee = 'https://{domaine_clean}' . $_SERVER['REQUEST_URI'];
    header('HTTP/1.1 301 Moved Permanently');
    header('Location: ' . $url_securisee);
    exit();
}}"""

    contenu_stats_inc = f"""<?php
{code_redirection_https}

$ip_filtrage = '{ip_filtrage}';
$fichier_stats = __DIR__ . '/stats.json';

function obtenir_os($user_agent) {{
    $os_platform = "Inconnu";
    $os_array = array(
        '/windows nt 10/i'      =>  'Windows 10/11',
        '/windows nt 6.3/i'     =>  'Windows 8.1',
        '/windows nt 6.2/i'     =>  'Windows 8',
        '/windows nt 6.1/i'     =>  'Windows 7',
        '/macintosh|mac os x/i' =>  'Mac OS X',
        '/linux/i'              =>  'Linux',
        '/ubuntu/i'             =>  'Ubuntu',
        '/iphone/i'             =>  'iPhone (iOS)',
        '/ipod/i'               =>  'iPod (iOS)',
        '/ipad/i'               =>  'iPad (iOS)',
        '/android/i'            =>  'Android'
    );
    foreach ($os_array as $regex => $value) {{
        if (preg_match($regex, $user_agent)) {{ $os_platform = $value; break; }}
    }}
    return $os_platform;
}}

function est_robot($user_agent) {{
    $bots = array('googlebot', 'bingbot', 'slurp', 'duckduckbot', 'baiduspider', 'yandexbot', 'sogou', 'exabot', 'facebot', 'ia_archiver', 'scan', 'bot');
    foreach ($bots as $bot) {{
        if (strpos(strtolower($user_agent), $bot) !== false) {{ return "Robot/Scan"; }}
    }}
    return "Utilisateur";
}}

$ip_brute = isset($_SERVER['REMOTE_ADDR']) ? $_SERVER['REMOTE_ADDR'] : '0.0.0.0';

if ($ip_brute !== $ip_filtrage) {{
    if (strpos($ip_brute, '.') !== false) {{
        $ip = preg_replace('/\\.\\d+$/', '.0', $ip_brute);
    }} else {{
        $ip = preg_replace('/:[a-f0-9]+$/i', ':0', $ip_brute);
    }}

    $page = (dirname($_SERVER['PHP_SELF']) != '/' ? basename(dirname($_SERVER['PHP_SELF'])). '/' : '') . basename($_SERVER['PHP_SELF']);
    $referer = isset($_SERVER['HTTP_REFERER']) ? $_SERVER['HTTP_REFERER'] : 'Direct';
    $user_agent = isset($_SERVER['HTTP_USER_AGENT']) ? $_SERVER['HTTP_USER_AGENT'] : '';
    $date_complete = date('Y-m-d H:i:s');

    $os = obtenir_os($user_agent);
    $type_visiteur = est_robot($user_agent);

    $nouvelle_visite = array(
        "date" => $date_complete,
        "page" => $page,
        "ip" => $ip,
        "referer" => $referer,
        "robot" => $type_visiteur,
        "os" => $os
    );

    $historique = array();

    if (file_exists($fichier_stats)) {{
        $contenu = @file_get_contents($fichier_stats);
        if ($contenu) {{
            $json = json_decode($contenu, true);
            if (is_array($json)) {{ $historique = $json; }}
        }}
    }}

    $historique[] = $nouvelle_visite;

    if (count($historique) > 10000) {{
        $historique = array_slice($historique, -10000);
    }}

    @file_put_contents($fichier_stats, json_encode($historique), LOCK_EX);
}}
?>"""
    with open(os.path.join(output_dir, "stats_inc.php"), "w", encoding="utf-8") as f:
        f.write(contenu_stats_inc)

def generer_page_stats(output_dir, config):
    mot_de_passe = config.get("pass_stats", "123456")
    titre_clean = nettoyer_html(config.get('titre_principal', 'Généalogie'))

    html_stats = f"""<?php
session_start();
$mot_de_passe_correct = "{mot_de_passe}";
$erreur = "";

if (isset($_POST['password'])) {{
    if ($_POST['password'] === $mot_de_passe_correct) {{
        $_SESSION['auth_stats'] = true;
    }} else {{
        $erreur = "Mot de passe incorrect.";
    }}
}}

if (isset($_GET['action'])) {{
    if ($_GET['action'] === 'logout') {{
        unset($_SESSION['auth_stats']);
        session_destroy();
        header('Location: stats.php');
        exit();
    }}
    if ($_GET['action'] === 'download' && isset($_SESSION['auth_stats'])) {{
        $fichier = __DIR__ . '/stats.json';
        if (file_exists($fichier)) {{
            header('Content-Type: application/json');
            header('Content-Disposition: attachment; filename="stats.json"');
            readfile($fichier);
            exit();
        }}
    }}
    if ($_GET['action'] === 'reset_all' && isset($_SESSION['auth_stats'])) {{
        file_put_contents(__DIR__ . '/stats.json', json_encode(array()));
        header('Location: stats.php');
        exit();
    }}
}}

$est_connecte = isset($_SESSION['auth_stats']) && $_SESSION['auth_stats'] === true;
$fichier_json = __DIR__ . '/stats.json';
?>
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Statistiques - {titre_clean}</title>
    <link rel="stylesheet" href="assets/style.css?v=5">
    <style>
        .stats-table {{ width: 100%; border-collapse: collapse; font-size: 0.9em; }}
        .stats-table th, .stats-table td {{ border: 1px solid rgba(255, 255, 255, 0.2); padding: 8px 10px; text-align: left; color: inherit; }}
        .stats-table th {{ 
            background-color: #1a2234 !important; 
            font-weight: bold; 
            position: sticky; 
            top: 0; 
            z-index: 10; 
            box-shadow: 0 2px 5px rgba(0,0,0,0.5);
        }}
        .scrollable-table {{ max-height: 380px; overflow-y: auto; border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 4px; margin-top: 10px; }}
        .badge-robot {{ color: #e74c3c !important; font-weight: bold; }}
        .badge-visiteur {{ color: #2ecc71 !important; font-weight: bold; }}
        .badge-ip {{ color: #3498db !important; font-weight: bold; font-family: monospace; }}
        .badge-page {{ background-color: #111; color: #00d2ff; padding: 3px 6px; border-radius: 4px; font-family: monospace; display: inline-block; word-break: break-all; }}
        .btn-action {{ display: inline-block; padding: 6px 12px; border-radius: 4px; text-decoration: none; color: white !important; font-size: 0.85em; font-weight: bold; }}
        .btn-blue {{ background-color: #3498db; }}
        .btn-grey {{ background-color: #7f8c8d; }}
        .btn-red {{ background-color: #e74c3c; }}
    </style>
</head>
<body>
    <main class="container" style="max-width: 1000px; margin: 20px auto;">
        <?php if (!$est_connecte): ?>
            <div class="section-fiche" style="max-width: 400px; margin: 40px auto; text-align: center;">
                <h2>Connexion aux Statistiques</h2>
                <?php if (!empty($erreur)): ?>
                    <p style="color: #e74c3c; font-weight: bold;"><?php echo $erreur; ?></p>
                <?php endif; ?>
                <form method="POST" action="stats.php">
                    <input type="password" name="password" placeholder="Mot de passe" required style="width: 100%; padding: 10px; margin-bottom: 12px; border-radius: 4px; border: 1px solid #ccc;">
                    <button type="submit" class="btn-action btn-grey" style="width: 100%; padding: 10px; border: none; cursor: pointer;">Se connecter</button>
                </form>
            </div>
        <?php else: ?>
            <h2>📊 Tableau de bord privé des statistiques</h2>
            <div style="display: flex; align-items: center; gap: 10px; margin: 15px 0; flex-wrap: wrap;">
                <a href="index.php" style="color: inherit; text-decoration: underline; font-weight: bold;">← Retourner à l'accueil</a>
                <a href="stats.php?action=download" class="btn-action btn-blue">💾 Télécharger stats.json</a>
                <a href="stats.php?action=logout" class="btn-action btn-grey">🔒 Déconnexion</a>
                <a href="stats.php?action=reset_all" onclick="return confirm('Voulez-vous vraiment effacer toutes les statistiques ?');" class="btn-action btn-red">🗑️ Effacer les statistiques</a>
            </div>
            <hr style="border: none; border-top: 2px solid rgba(255, 255, 255, 0.2); margin: 20px 0;">
            <?php
            $visites = array();
            if (file_exists($fichier_json)) {{
                $contenu = @file_get_contents($fichier_json);
                if ($contenu) {{
                    $json = json_decode($contenu, true);
                    if (is_array($json)) {{ $visites = $json; }}
                }}
            }}
            $stats_mois = array();
            foreach ($visites as $v) {{
                $date_str = isset($v['date']) ? $v['date'] : '';
                $mois = (strlen($date_str) >= 7) ? substr($date_str, 0, 7) : 'Inconnu';
                if (!isset($stats_mois[$mois])) {{
                    $stats_mois[$mois] = array('total' => 0, 'humains' => 0, 'robots' => 0);
                }}
                $stats_mois[$mois]['total']++;
                if (isset($v['robot']) && $v['robot'] === 'Robot/Scan') {{
                    $stats_mois[$mois]['robots']++;
                }} else {{
                    $stats_mois[$mois]['humains']++;
                }}
            }}
            ksort($stats_mois);
            ?>
            <h3>📅 50 dernières visites enregistrées (Affichage défilant)</h3>
            <div class="scrollable-table">
                <table class="stats-table">
                    <thead>
                        <tr><th>Date</th><th>Page visitée</th><th>Adresse IP anonymisée</th><th>Provenance</th><th>Type</th><th>Système</th></tr>
                    </thead>
                    <tbody>
                    <?php 
                    $dernieres = array_slice(array_reverse($visites), 0, 50);
                    if (empty($dernieres)):
                    ?>
                        <tr><td colspan="6">Aucune visite enregistrée.</td></tr>
                    <?php else: ?>
                        <?php foreach ($dernieres as $v): 
                            $is_robot = isset($v['robot']) && $v['robot'] === 'Robot/Scan';
                            $ip = isset($v['ip']) ? htmlspecialchars($v['ip']) : 'Inconnue';
                            $page = isset($v['page']) ? htmlspecialchars($v['page']) : '';
                        ?>
                            <tr>
                                <td><strong><?php echo htmlspecialchars(isset($v['date']) ? $v['date'] : ''); ?></strong></td>
                                <td><code class="badge-page"><?php echo $page; ?></code></td>
                                <td>
                                        <a href="https://ipapi.co/<?php echo urlencode($visite['ip']); ?>/" target="_blank" rel="noopener noreferrer" style="color: var(--accent-color); text-decoration: underline; font-weight: bold;">
                                            <span class="badge-ip"><?php echo $ip; ?> 🔗</span>
                                        </a>
                                </td>
                                <td><?php echo htmlspecialchars(isset($v['referer']) && $v['referer'] ? $v['referer'] : 'Direct / Favoris'); ?></td>
                                <td><?php echo $is_robot ? '<span class="badge-robot">Robot/Scan</span>' : '<span class="badge-visiteur">Visiteur</span>'; ?></td>
                                <td><?php echo htmlspecialchars(isset($v['os']) ? $v['os'] : 'Inconnu'); ?></td>
                            </tr>
                        <?php endforeach; ?>
                    <?php endif; ?>
                    </tbody>
                </table>
            </div>
            <hr style="border: none; border-top: 2px solid rgba(255, 255, 255, 0.2); margin: 30px 0;">
            <h3>📈 Historique global par mois</h3>
            <div style="max-width: 500px;">
                <table class="stats-table">
                    <thead><tr><th>Mois</th><th>Visites globales</th><th>Humains</th><th>Robots / Scans</th></tr></thead>
                    <tbody>
                    <?php if (empty($stats_mois)): ?>
                        <tr><td colspan="4">Aucun historique mensuel.</td></tr>
                    <?php else: ?>
                        <?php foreach ($stats_mois as $m => $d): ?>
                            <tr>
                                <td><strong><?php echo htmlspecialchars($m); ?></strong></td>
                                <td><?php echo $d['total']; ?></td>
                                <td style="color: #2ecc71; font-weight: bold;"><?php echo $d['humains']; ?></td>
                                <td style="color: #e74c3c; font-weight: bold;"><?php echo $d['robots']; ?></td>
                            </tr>
                        <?php endforeach; ?>
                    <?php endif; ?>
                    </tbody>
                </table>
            </div>
        <?php endif; ?>
        {obtenir_pied_de_page_html(config, niveau_relatif="")}
        <p style="margin-top: 20px; text-align: center;"><a href="../index.php">← Retour à l'accueil principal</a></p>
    </main>
</body>
</html>"""
    with open(os.path.join(output_dir, "stats.php"), "w", encoding="utf-8") as f:
        f.write(html_stats)

def obtenir_php_tracking_header(niveau_relatif=""):
    return f"""<?php
require_once __DIR__ . '/{niveau_relatif}stats_inc.php';
$protocol_canonical = (isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] === 'on' ? 'https' : 'http');
$url_canonical_page = $protocol_canonical . '://' . (isset($_SERVER['HTTP_HOST']) ? $_SERVER['HTTP_HOST'] : 'localhost') . strtok($_SERVER['REQUEST_URI'], '?');
?>"""

def obtenir_pied_de_page_html(config, niveau_relatif=""):
    html_contact = f'<p>📧 <a href="{niveau_relatif}contact.php" id="contact-link">Contacter l\'auteur</a></p>' if config.get("contact") else ""
    return f"""
    <footer style="margin-top: 50px; text-align: center; font-size: 0.9em; border-top: 1px solid rgba(255, 255, 255, 0.1); padding-top: 15px;">
        <p>Données rassemblées par {config.get('auteur', '')}</p>
        {html_contact}
        <p style="margin-top: 15px; font-size: 0.85em;">
            <a href="http://geneasite.free.fr" target="_blank">Généré via l'application GénéaSite, du GEDCOM au site web</a><br> |
            <a href="{niveau_relatif}stats.php">Statistiques</a> | 
            <a href="{niveau_relatif}mentions.php" style="text-decoration: underline;">Mentions légales & Confidentialité</a>
        </p>
        <p style="margin-top: 20px; text-align: center;"><a href="../index.php">← Retour à l'accueil principal</a></p>
    </footer>"""

def generer_barre_recherche_html():
    return """
    <div class="search-container" style="max-width: 500px; margin: 0 auto;">
        <input type="text" id="input-recherche" placeholder="🔍 Rechercher une personne..." oninput="filtrerRecherche(this.value, '../')" onkeydown="gererEntreeRecherche(event)">
        <div id="resultats-recherche" class="search-results"></div>
    </div>"""

def generer_page_individu(individu, gedcom_parser, output_dir, config):
    annee_actuelle = datetime.now().year
    if est_individu_vivant(individu, annee_actuelle): return

    pointer = individu.get_pointer()
    nom = "".join(individu.get_name()[1]).strip()
    prenom = "".join(individu.get_name()[0]).strip()
    
    birth_date, birth_place = "Inconnue", "Inconnu"
    death_date, death_place = "Inconnu", "Inconnu"

    for child in individu.get_child_elements():
        if child.get_tag() == 'BIRT':
            for sub in child.get_child_elements():
                if sub.get_tag() == 'DATE': birth_date = sub.get_value().strip()
                if sub.get_tag() == 'PLAC': birth_place = sub.get_value().strip()
        if child.get_tag() == 'DEAT':
            for sub in child.get_child_elements():
                if sub.get_tag() == 'DATE': death_date = sub.get_value().strip()
                if sub.get_tag() == 'PLAC': death_place = sub.get_value().strip()

    ligne_deces_html = f"<p><strong>⚰️ Décès :</strong> Le {death_date} — 📍 {death_place}</p>" if (death_date != "Inconnu" and death_date != "") else "<p><strong>⚰️ Décès :</strong> Supposé(e) décédé(e)</p>"

    parents_html = ""
    id_familles_parents = [c.get_value() for c in individu.get_child_elements() if c.get_tag() == 'FAMC']

    for root_child in gedcom_parser.get_root_element().get_child_elements():
        if isinstance(root_child, FamilyElement) and root_child.get_pointer() in id_familles_parents:
            id_pere, id_mere = "", ""
            for sub in root_child.get_child_elements():
                if sub.get_tag() == 'HUSB': id_pere = sub.get_value()
                if sub.get_tag() == 'WIFE': id_mere = sub.get_value()
            if id_pere:
                p_obj = trouver_individu_par_id(id_pere, gedcom_parser)
                if p_obj:
                    parents_html += "<li><strong>Père :</strong> Confidentiel</li>" if est_individu_vivant(p_obj, annee_actuelle) else f"<li><strong>Père :</strong> <a href='{generer_nom_fichier_php(p_obj)}'>{' '.join(p_obj.get_name()).strip()}</a></li>"
            if id_mere:
                m_obj = trouver_individu_par_id(id_mere, gedcom_parser)
                if m_obj:
                    parents_html += "<li><strong>Mère :</strong> Confidentiel</li>" if est_individu_vivant(m_obj, annee_actuelle) else f"<li><strong>Mère :</strong> <a href='{generer_nom_fichier_php(m_obj)}'>{' '.join(m_obj.get_name()).strip()}</a></li>"

    if not parents_html: parents_html = "<li>Aucun parent répertorié.</li>"

    conjoints_html, enfants_html = "", ""
    id_familles_unions = [c.get_value() for c in individu.get_child_elements() if c.get_tag() == 'FAMS']

    for root_child in gedcom_parser.get_root_element().get_child_elements():
        if isinstance(root_child, FamilyElement) and root_child.get_pointer() in id_familles_unions:
            id_pere, id_mere = "", ""
            for sub in root_child.get_child_elements():
                if sub.get_tag() == 'HUSB': id_pere = sub.get_value()
                if sub.get_tag() == 'WIFE': id_mere = sub.get_value()

            id_conjoint = id_mere if id_pere == pointer else id_pere
            has_marriage, m_date, m_place = False, "Date inconnue", "Lieu inconnu"
            for sub in root_child.get_child_elements():
                if sub.get_tag() == 'MARR':
                    has_marriage = True
                    for m_sub in sub.get_child_elements():
                        if m_sub.get_tag() == 'DATE': m_date = m_sub.get_value()
                        if m_sub.get_tag() == 'PLAC': m_place = m_sub.get_value()

            if id_conjoint:
                c_obj = trouver_individu_par_id(id_conjoint, gedcom_parser)
                if c_obj:
                    if est_individu_vivant(c_obj, annee_actuelle):
                        conjoints_html += "<li>💑 Confidentiel</li>"
                    else:
                        mariage_info = f" - 💍 Mariage le {m_date} à {m_place}" if has_marriage else ""
                        conjoints_html += f"<li>💑 <a href='{generer_nom_fichier_php(c_obj)}'>{' '.join(c_obj.get_name()).strip()}</a>{mariage_info}</li>"
            
            for sub in root_child.get_child_elements():
                if sub.get_tag() == 'CHIL':
                    e_obj = trouver_individu_par_id(sub.get_value(), gedcom_parser)
                    if e_obj:
                        enfants_html += "<li>👶 Confidentiel</li>" if est_individu_vivant(e_obj, annee_actuelle) else f"<li>👶 <a href='{generer_nom_fichier_php(e_obj)}'>{' '.join(e_obj.get_name()).strip()}</a></li>"

    if not conjoints_html: conjoints_html = "<li>Célibataire ou aucune union enregistrée.</li>"
    if not enfants_html: enfants_html = "<li>Aucun enfant enregistré.</li>"

    filename = generer_nom_fichier_php(individu)
    filepath = os.path.join(output_dir, "individus", filename)

    php_header = obtenir_php_tracking_header("../")
    html_content = php_header + f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{prenom} {nom}</title>
    <link rel="canonical" href="<?php echo $url_canonical_page; ?>">
    <link rel="stylesheet" href="../assets/style.css?v=5">
</head>
<body>
    <main class="container">
        <header><h1>{prenom} {nom}</h1></header>
        <div style="margin-bottom: 20px;">{generer_barre_recherche_html()}</div>
        <section class="section-fiche">
            <h2>⏳ Événements de vie</h2>
            <p><strong>👶 Naissance :</strong> {birth_date} — 📍 {birth_place}</p>
            {ligne_deces_html}
        </section>
        <section class="section-fiche"><h2>👪 Parents</h2><ul class="parentes-list">{parents_html}</ul></section>
        <section class="section-fiche"><h2>💑 Unions & Conjoints</h2><ul class="parentes-list">{conjoints_html}</ul></section>
        <section class="section-fiche"><h2>👶 Enfants</h2><ul class="parentes-list">{enfants_html}</ul></section>
        {obtenir_pied_de_page_html(config, niveau_relatif="../")}
    </main>
    <script src="../assets/donnees_recherche.js"></script>
    <script src="../assets/search.js"></script>
</body>
</html>"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)

def generer_page_mentions(output_dir, config):
    hebergeur_texte = f"Ce site est hébergé gracieusement sur les Pages Personnelles de Free.<br>Identifiant : {config.get('identifiant_free', '')}" if config.get("type_hebergeur") == "Free" else "Ce site est hébergé sur des serveurs privés autonomes."
    titre_clean = nettoyer_html(config.get('titre_principal', ''))

    html_body = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mentions légales - {titre_clean}</title>
    <link rel="canonical" href="<?php echo $url_canonical_page; ?>">
    <link rel="stylesheet" href="assets/style.css?v=5">
</head>
<body>
    <div class="container">
        <a href="index.php" style="display:block; text-align:left; margin-bottom:15px;">← Retour au site</a>
        <h1>Mentions Légales & Confidentialité</h1>
        <section class="section-fiche">

        <div class="alert">
            <strong>✏️ Note à l'attention de l'administrateur :</strong> Pensez à compléter cette page avec vos informations personnelles en modifiant directement le fichier <code>mentions.php</code>.
        </div>        
        
            <h2>1. Éditeur du site</h2>
            <p><strong>Auteur :</strong> {config.get('auteur', '')}<br><strong>Contact :</strong> {config.get('contact', '')}</p>
            <h2>2. Hébergement</h2><p>{hebergeur_texte}</p>
            <h2>3. Vie privée & RGPD</h2>
            <p>Les personnes vivantes sont totalement masquées de la consultation publique.</p>
        </section>
        {obtenir_pied_de_page_html(config, niveau_relatif="")}
    </div>
</body>
</html>"""
    with open(os.path.join(output_dir, "mentions.php"), "w", encoding="utf-8") as f:
        f.write(obtenir_php_tracking_header("") + "\n" + html_body)

def generer_page_contact(output_dir, config):
    html_body = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8"><title>Contact</title>
    <link rel="stylesheet" href="assets/style.css?v=5">
</head>
<body>
    <div class="container" style="max-width: 600px; margin: 40px auto;">
        <a href="index.php">← Retour au site</a>
        <h1>✉️ Contacter l'auteur</h1>
        <form action="https://formsubmit.co/{config.get('contact', '')}" method="POST">
            <input type="text" name="nom" placeholder="Votre nom" required style="width:100%; margin-bottom:10px; padding:8px;">
            <input type="email" name="email" placeholder="Votre email" required style="width:100%; margin-bottom:10px; padding:8px;">
            <textarea name="message" placeholder="Votre message" required style="width:100%; height:100px; margin-bottom:10px; padding:8px;"></textarea>
            <button type="submit" style="width:100%; padding:10px; background:#27ae60; color:white; border:none; cursor:pointer;">🚀 Envoyer</button>
        </form>
        {obtenir_pied_de_page_html(config, niveau_relatif="")}
    </div>
</body>
</html>"""
    with open(os.path.join(output_dir, "contact.php"), "w", encoding="utf-8") as f:
        f.write(obtenir_php_tracking_header("") + "\n" + html_body)

def generer_page_liste_lettre(lettre, liste_individus, output_dir, config):
    elements_liste = "".join(f'<li><a href="../{lien}">{nom}</a></li>' for nom, lien in sorted(liste_individus))
    
    html_content = obtenir_php_tracking_header("../") + f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Individus commençant par {lettre}</title>
    <link rel="stylesheet" href="../assets/style.css?v=5">
</head>
<body>
    <main class="container">
        <h1>Individus - Lettre {lettre}</h1>
        <div style="margin-bottom: 20px;">{generer_barre_recherche_html()}</div>
        <div class="section-fiche">
            <ul>
                {elements_liste}
            </ul>
        </div>
        {obtenir_pied_de_page_html(config, niveau_relatif="../")}
    </main>
    <script src="../assets/donnees_recherche.js"></script>
    <script src="../assets/search.js"></script>
</body>
</html>"""
    
    os.makedirs(os.path.join(output_dir, "listes"), exist_ok=True)
    with open(os.path.join(output_dir, "listes", f"lettre_{lettre}.php"), "w", encoding="utf-8") as f:
        f.write(html_content)

def execution_generation(config):
    chemin_ged = config["ged_path"]
    output_dir = "./site_web"
    
    if os.path.exists(os.path.join(output_dir, "individus")):
        shutil.rmtree(os.path.join(output_dir, "individus"))
    if os.path.exists(os.path.join(output_dir, "listes")):
        shutil.rmtree(os.path.join(output_dir, "listes"))
        
    os.makedirs(os.path.join(output_dir, "individus"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "listes"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "assets"), exist_ok=True)
    
    generer_fichier_stats_inc(output_dir, config.get("mon_ip", ""), config.get("url_domaine", ""))
    generer_page_stats(output_dir, config)
    
    police_choisie = config.get('police', 'Segoe UI')
    font_declaration = f"@import url('https://fonts.googleapis.com/css2?family={police_choisie.replace(' ', '+')}:wght@300;400;500;700&display=swap');\n"
    police_alternative = f"'{police_choisie}', sans-serif"

    with open(os.path.join(output_dir, "assets", "style.css"), "w", encoding="utf-8") as f:
        f.write(f"""{font_declaration}
:root {{
    --bg-principal: {config.get('c_fond_principal', '#0b0f19')};
    --bg-cadre-principal: {config.get('c_fond_cadre_principal', '#0d111a')};
    --bg-cadre-secondaire: {config.get('c_fond_cadre_secondaire', '#111625')};
    --border-cadre-secondaire: {config.get('c_bord_cadre_secondaire', '#00d2ff')};
    --color-titre: {config.get('c_titres', '#00d2ff')};
    --color-texte: {config.get('c_police', '#e0e0e0')};
}}
* {{ box-sizing: border-box; }}
body {{ font-family: {police_alternative} !important; background-color: var(--bg-principal); color: var(--color-texte); margin: 0; padding: 20px; }}
.container {{ max-width: 900px; margin: auto; background: var(--bg-cadre-principal); padding: 20px; border-radius: 8px; text-align: center; }}
h1, h2, h3 {{ color: var(--color-titre); text-align: center; }}
a {{ color: var(--color-titre); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.section-fiche, .encadre {{ background: var(--bg-cadre-secondaire); border: 1px solid var(--border-cadre-secondaire); padding: 15px; border-radius: 6px; margin-bottom: 15px; text-align: left; }}
.search-container {{ position: relative; width: 100%; border-radius: 20px; }}
.search-container input {{ width: 100%; padding: 10px 15px; border-radius: 20px; border: 1px solid var(--border-cadre-secondaire); background: var(--bg-principal); color: var(--color-texte); outline: none; }}
.search-results {{ position: absolute; width: 100%; max-height: 200px; overflow-y: auto; background: var(--bg-cadre-secondaire); border: 1px solid var(--border-cadre-secondaire); z-index: 100; display: none; text-align: left; border-radius: 8px; margin-top: 5px; }}
.search-results a {{ display: block; padding: 8px 12px; border-bottom: 1px solid rgba(255,255,255,0.1); }}

/* Grille Alphabétique Ancienne Disposition */
.index-alpha-grid {{
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 8px;
    margin-top: 15px;
}}
.alpha-btn {{
    display: inline-block;
    padding: 6px 12px;
    border: 1px solid var(--border-cadre-secondaire);
    border-radius: 4px;
    color: var(--color-titre);
    font-weight: bold;
    text-decoration: none;
    background: rgba(0, 0, 0, 0.2);
    min-width: 32px;
    text-align: center;
}}
.alpha-btn:hover {{
    background: var(--border-cadre-secondaire);
    color: var(--bg-principal);
    text-decoration: none;
}}
""")

    js_search = """
function filtrerRecherche(valeur, relPath) {
    var resDiv = document.getElementById('resultats-recherche');
    if (valeur.length < 2) { resDiv.style.display = 'none'; return; }
    var matches = donnees_recherche.filter(function(p) {
        return p.nom.toLowerCase().includes(valeur.toLowerCase());
    });
    if (matches.length === 0) { resDiv.style.display = 'none'; return; }
    var html = '';
    matches.slice(0, 10).forEach(function(m) {
        html += '<a href="' + relPath + m.lien + '">' + m.nom + '</a>';
    });
    resDiv.innerHTML = html;
    resDiv.style.display = 'block';
}
function gererEntreeRecherche(e) {
    if (e.key === 'Enter') {
        var first = document.querySelector('#resultats-recherche a');
        if (first) { window.location.href = first.href; }
    }
}
"""
    with open(os.path.join(output_dir, "assets", "search.js"), "w", encoding="utf-8") as f:
        f.write(js_search)

    parser = charger_gedcom(chemin_ged)
    annee_actuelle = datetime.now().year
    
    donnees_recherche = []
    alphabet = {}
    total_individus = 0

    for elem in parser.get_root_element().get_child_elements():
        if isinstance(elem, IndividualElement):
            if not est_individu_vivant(elem, annee_actuelle):
                generer_page_individu(elem, parser, output_dir, config)
                
                nom_complet = " ".join(elem.get_name()).strip()
                lien_relative = f"individus/{generer_nom_fichier_php(elem)}"
                
                donnees_recherche.append({"nom": nom_complet, "lien": lien_relative})
                total_individus += 1
                
                nom_seul = "".join(elem.get_name()[1]).strip()
                premiere_lettre = nom_seul[0].upper() if nom_seul else (nom_complet[0].upper() if nom_complet else '#')
                
                # Gestion des caractères accentués pour l'index
                premiere_lettre = "".join(c for c in unicodedata.normalize("NFD", premiere_lettre) if unicodedata.category(c) != 'Mn')
                
                if not premiere_lettre.isalpha():
                    premiere_lettre = '#'
                if premiere_lettre not in alphabet:
                    alphabet[premiere_lettre] = []
                alphabet[premiere_lettre].append((nom_complet, lien_relative))

    with open(os.path.join(output_dir, "assets", "donnees_recherche.js"), "w", encoding="utf-8") as f:
        f.write("var donnees_recherche = " + json.dumps(donnees_recherche, ensure_ascii=False) + ";")

    liens_index_lettres = []
    for lettre, personnes in sorted(alphabet.items()):
        generer_page_liste_lettre(lettre, personnes, output_dir, config)
        liens_index_lettres.append(f'<a href="listes/lettre_{lettre}.php" class="alpha-btn">{lettre}</a>')

    html_alphabet = "".join(liens_index_lettres)

    generer_page_mentions(output_dir, config)
    if config.get("contact"):
        generer_page_contact(output_dir, config)

    texte_intro = config.get("texte_intro", "")

    html_index = obtenir_php_tracking_header("") + f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{nettoyer_html(config.get('titre_principal', 'Généalogie'))}</title>
    <link rel="canonical" href="<?php echo $url_canonical_page; ?>">
    <link rel="stylesheet" href="assets/style.css?v=5">
</head>
<body>
    <main class="container">
        <h1 style="margin-bottom: 25px;">{config.get('titre_principal', 'Arbre Généalogique')}</h1>
        
        <div style="margin-bottom: 25px;">
            {texte_intro}
        </div>

        <div style="margin-bottom: 25px;">
            {generer_barre_recherche_html()}
        </div>

        <div class="section-fiche" style="text-align: center; padding: 20px;">
            <h2 style="margin-top: 0;">Accès alphabétique ({total_individus} individus)</h2>
            <p style="margin-bottom: 15px;">Cliquez sur une lettre pour afficher les personnes correspondantes :</p>
            <div class="index-alpha-grid">
                {html_alphabet}
            </div>
        </div>

        {obtenir_pied_de_page_html(config, niveau_relatif="")}
    </main>
    <script src="assets/donnees_recherche.js"></script>
    <script src="assets/search.js"></script>
</body>
</html>"""
    
    with open(os.path.join(output_dir, "index.php"), "w", encoding="utf-8") as f:
        f.write(html_index)


class AppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("GénéaSite - Configuration Web")
        self.root.geometry("680x920")

        self.config_data = {
            "ged_path": "fichier.ged",
            "titre_principal": "MA GENEALOGIE",
            "auteur": "Votre nom",
            "contact": "votre adresse mail",
            "pass_stats": "123456",
            "mon_ip": "Votre IP public",
            "url_domaine": "",
            "identifiant_free": "ma-genealogie",
            "type_hebergeur": "Free",
            "police": "Segoe UI",
            "c_fond_principal": "#0b0f19",
            "c_fond_cadre_principal": "#0d111a",
            "c_fond_cadre_secondaire": "#111625",
            "c_bord_cadre_secondaire": "#00d2ff",
            "c_titres": "#00d2ff",
            "c_police": "#e0e0e0",
            "texte_intro": "Ce site a été mis en ligne pour vous présenter mes recherches généalogiques,\n\n"
        "avec toutes les personnes qui peuvent constituer notre famille.\n\n"
        "N'hésitez pas à naviguer à travers ces pages ou à utiliser la "
        "<b style='color:#27ae60;'>barre de recherche</b>. Bonne découverte."
        }

        self.creer_widgets()

    def choisir_couleur(self, cle, bouton):
        color_tuple, color_hex = colorchooser.askcolor(
            color=self.config_data[cle],
            title=f"Choisir la couleur : {cle}"
        )
        if color_hex:
            self.config_data[cle] = color_hex
            bouton.config(bg=color_hex)

    def choisir_fichier_ged(self):
        filename = filedialog.askopenfilename(filetypes=[("Fichiers GEDCOM", "*.ged"), ("Tous les fichiers", "*.*")])
        if filename:
            self.config_data["ged_path"] = filename
            self.entry_ged.delete(0, tk.END)
            self.entry_ged.insert(0, filename)

    def lancer_generation(self):
        self.config_data["ged_path"] = self.entry_ged.get()
        if not self.config_data["ged_path"]:
            messagebox.showerror("Erreur", "Veuillez sélectionner un fichier GEDCOM.")
            return

        self.config_data["titre_principal"] = self.entry_titre.get()
        self.config_data["auteur"] = self.entry_auteur.get()
        self.config_data["contact"] = self.entry_contact.get()
        self.config_data["pass_stats"] = self.entry_pass.get()
        self.config_data["mon_ip"] = self.entry_ip.get()
        self.config_data["identifiant_free"] = self.entry_id_free.get()
        self.config_data["type_hebergeur"] = self.combo_hebergeur.get()
        self.config_data["police"] = self.combo_police.get()
        self.config_data["texte_intro"] = self.txt_intro.get("1.0", tk.END).strip()

        try:
            execution_generation(self.config_data)
            messagebox.showinfo("Succès", "Le site web a été généré avec succès dans le dossier 'site_web' !")
        except Exception as e:
            messagebox.showerror("Erreur", f"Une erreur est survenue lors de la génération :\n{str(e)}")

    def creer_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill="both", expand=True)

        f_guide = ttk.LabelFrame(main_frame, text="💡 GUIDE DE MISE EN FORME (Pour le Titre et l'Introduction) :")
        f_guide.pack(fill="x", pady=5)
        guide_txt = (
            "Vous pouvez embellir vos textes en ajoutant directement des balises HTML :\n"
            "• <b>Mon texte</b> : pour mettre en gras.\n"
            "• <i>Mon texte</i> : pour mettre en italique.\n"
            "• <center>Mon texte</center> : pour centrer les mots ou lignes.\n"
            "• <span style='font-family: Arial;'>Mon texte</span> : pour personnaliser la typographie."
        )
        ttk.Label(f_guide, text=guide_txt, justify="left").pack(anchor="w", padx=5, pady=5)

        f_heb = ttk.LabelFrame(main_frame, text="🌐 Hébergement & Configuration Domaine")
        f_heb.pack(fill="x", pady=5)

        ttk.Label(f_heb, text="Votre hébergeur web :").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.combo_hebergeur = ttk.Combobox(f_heb, values=["Free", "Autre/Privé"], state="readonly", width=15)
        self.combo_hebergeur.set(self.config_data["type_hebergeur"])
        self.combo_hebergeur.grid(row=0, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(f_heb, text="Identifiant Free (ex: nom1-nom2) :").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.entry_id_free = ttk.Entry(f_heb, width=40)
        self.entry_id_free.insert(0, self.config_data["identifiant_free"])
        self.entry_id_free.grid(row=1, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(f_heb, text="💡 Chez Free, un login 'nom1.nom2' devient 'nom1-nom2.pages-perso.free.fr' en HTTPS.", font=("Segoe UI", 8, "italic")).grid(row=2, column=0, columnspan=2, sticky="w", padx=5, pady=2)

        ttk.Label(main_frame, text="Fichier GEDCOM (.ged) :").pack(anchor="w", pady=(5, 0))
        f_ged = ttk.Frame(main_frame)
        f_ged.pack(fill="x", pady=2)
        self.entry_ged = ttk.Entry(f_ged)
        self.entry_ged.insert(0, self.config_data["ged_path"])
        self.entry_ged.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Button(f_ged, text="Parcourir...", command=self.choisir_fichier_ged).pack(side="right")

        f_row1 = ttk.Frame(main_frame)
        f_row1.pack(fill="x", pady=5)
        f_row1.columnconfigure(0, weight=1)
        f_row1.columnconfigure(1, weight=1)

        f_t1 = ttk.Frame(f_row1)
        f_t1.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Label(f_t1, text="Titre principal du site :").pack(anchor="w")
        self.entry_titre = ttk.Entry(f_t1)
        self.entry_titre.insert(0, self.config_data["titre_principal"])
        self.entry_titre.pack(fill="x", pady=2)

        f_t2 = ttk.Frame(f_row1)
        f_t2.grid(row=0, column=1, sticky="ew", padx=(5, 0))
        ttk.Label(f_t2, text="Nom de l'auteur / Famille :").pack(anchor="w")
        self.entry_auteur = ttk.Entry(f_t2)
        self.entry_auteur.insert(0, self.config_data["auteur"])
        self.entry_auteur.pack(fill="x", pady=2)

        f_row2 = ttk.Frame(main_frame)
        f_row2.pack(fill="x", pady=5)
        f_row2.columnconfigure(0, weight=1)
        f_row2.columnconfigure(1, weight=1)
        f_row2.columnconfigure(2, weight=1)

        f_e1 = ttk.Frame(f_row2)
        f_e1.grid(row=0, column=0, sticky="ew", padx=(0, 2))
        ttk.Label(f_e1, text="Email de contact :").pack(anchor="w")
        self.entry_contact = ttk.Entry(f_e1)
        self.entry_contact.insert(0, self.config_data["contact"])
        self.entry_contact.pack(fill="x", pady=2)

        f_e2 = ttk.Frame(f_row2)
        f_e2.grid(row=0, column=1, sticky="ew", padx=2)
        ttk.Label(f_e2, text="Mot de passe (stats.php) :").pack(anchor="w")
        self.entry_pass = ttk.Entry(f_e2)
        self.entry_pass.insert(0, self.config_data["pass_stats"])
        self.entry_pass.pack(fill="x", pady=2)

        f_e3 = ttk.Frame(f_row2)
        f_e3.grid(row=0, column=2, sticky="ew", padx=(2, 0))
        ttk.Label(f_e3, text="IP à exclure :").pack(anchor="w")
        self.entry_ip = ttk.Entry(f_e3)
        self.entry_ip.insert(0, self.config_data["mon_ip"])
        self.entry_ip.pack(fill="x", pady=2)

        ttk.Label(main_frame, text="Police de caractères générale du site :").pack(anchor="w", pady=(5, 0))
        self.combo_police = ttk.Combobox(main_frame, values=["Segoe UI", "Roboto", "Open Sans", "Lato", "Montserrat", "Arial"], state="readonly")
        self.combo_police.set(self.config_data["police"])
        self.combo_police.pack(anchor="w", pady=2)

        f_couleurs = ttk.LabelFrame(main_frame, text="🎨 Personnalisation des Couleurs")
        f_couleurs.pack(fill="x", pady=5)
        f_couleurs.columnconfigure(0, weight=1)
        f_couleurs.columnconfigure(1, weight=1)

        btn_fond = tk.Button(f_couleurs, text="Fond Principal", bg=self.config_data["c_fond_principal"], fg="white", font=("Segoe UI", 9, "bold"), padx=10, pady=5)
        btn_fond.config(command=lambda: self.choisir_couleur("c_fond_principal", btn_fond))
        btn_fond.grid(row=0, column=0, sticky="ew", padx=5, pady=5)

        btn_cadre_p = tk.Button(f_couleurs, text="Fond Cadre Principal", bg=self.config_data["c_fond_cadre_principal"], fg="white", font=("Segoe UI", 9, "bold"), padx=10, pady=5)
        btn_cadre_p.config(command=lambda: self.choisir_couleur("c_fond_cadre_principal", btn_cadre_p))
        btn_cadre_p.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        btn_cadre_s = tk.Button(f_couleurs, text="Fond Cadre Secondaire", bg=self.config_data["c_fond_cadre_secondaire"], fg="white", font=("Segoe UI", 9, "bold"), padx=10, pady=5)
        btn_cadre_s.config(command=lambda: self.choisir_couleur("c_fond_cadre_secondaire", btn_cadre_s))
        btn_cadre_s.grid(row=1, column=0, sticky="ew", padx=5, pady=5)

        btn_bords = tk.Button(f_couleurs, text="Bord Cadre Secondaire", bg=self.config_data["c_bord_cadre_secondaire"], fg="black", font=("Segoe UI", 9, "bold"), padx=10, pady=5)
        btn_bords.config(command=lambda: self.choisir_couleur("c_bord_cadre_secondaire", btn_bords))
        btn_bords.grid(row=1, column=1, sticky="ew", padx=5, pady=5)

        btn_titres = tk.Button(f_couleurs, text="Couleur des Titres", bg=self.config_data["c_titres"], fg="black", font=("Segoe UI", 9, "bold"), padx=10, pady=5)
        btn_titres.config(command=lambda: self.choisir_couleur("c_titres", btn_titres))
        btn_titres.grid(row=2, column=0, sticky="ew", padx=5, pady=5)

        btn_police = tk.Button(f_couleurs, text="Couleur de la Police", bg=self.config_data["c_police"], fg="black", font=("Segoe UI", 9, "bold"), padx=10, pady=5)
        btn_police.config(command=lambda: self.choisir_couleur("c_police", btn_police))
        btn_police.grid(row=2, column=1, sticky="ew", padx=5, pady=5)

        ttk.Label(main_frame, text="Texte d'introduction sur la page d'accueil (Accroche) :").pack(anchor="w", pady=(5, 0))
        self.txt_intro = scrolledtext.ScrolledText(main_frame, height=8)
        self.txt_intro.insert(tk.END, self.config_data["texte_intro"])
        self.txt_intro.pack(fill="both", expand=True, pady=2)

        btn_generer = tk.Button(main_frame, text="🚀 Générer le site Internet (PHP)", bg="#27ae60", fg="white", font=("Segoe UI", 12, "bold"), pady=8, command=self.lancer_generation)
        btn_generer.pack(fill="x", pady=10)

if __name__ == "__main__":
    root = tk.Tk()
    app = AppGUI(root)
    root.mainloop()
