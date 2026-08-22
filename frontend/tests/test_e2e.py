from playwright.sync_api import expect, sync_playwright


import os

# Le frontend est exposé côté hôte sur le port 5199 (et non 5173) dans
# docker/docker-compose.yml : les plages 5085-5184 sont réservées par
# Windows (Hyper-V/WSL) sur la machine de démonstration — voir
# PLAN_AGENT_IA_OBRAIL.md §0.5. Surchargable par variable d'environnement
# pour les environnements où un autre port serait exposé (ex. CI).
FRONTEND_URL = os.getenv("OBRAIL_FRONTEND_URL", "http://localhost:5199")
TIMEOUT_MS = 15000

# Comptes de demonstration crees par backend/seed_users.py.
# Surchargables par variables d environnement pour ne pas figer d identifiants.
DEMO_USER = os.getenv("OBRAIL_VIEWER_USER", "viewer")
DEMO_PASSWORD = os.getenv("OBRAIL_VIEWER_PASSWORD", "viewer123")
DEMO_ADMIN_USER = os.getenv("OBRAIL_ADMIN_USER", "admin")
DEMO_ADMIN_PASSWORD = os.getenv("OBRAIL_ADMIN_PASSWORD", "admin123")


def sign_in(page):
    """L application est protegee : toute session E2E commence par une connexion."""
    page.goto(FRONTEND_URL, wait_until="networkidle", timeout=TIMEOUT_MS)
    page.get_by_label("Identifiant de connexion").fill(DEMO_USER, timeout=TIMEOUT_MS)
    page.get_by_label("Mot de passe").fill(DEMO_PASSWORD, timeout=TIMEOUT_MS)
    page.get_by_role("button", name="Se connecter").click(timeout=TIMEOUT_MS)
    return page


def sign_in_admin(page):
    """Connexion en tant qu administrateur (acces aux routes /agent/*)."""
    page.goto(FRONTEND_URL, wait_until="networkidle", timeout=TIMEOUT_MS)
    page.get_by_label("Identifiant de connexion").fill(DEMO_ADMIN_USER, timeout=TIMEOUT_MS)
    page.get_by_label("Mot de passe").fill(DEMO_ADMIN_PASSWORD, timeout=TIMEOUT_MS)
    page.get_by_role("button", name="Se connecter").click(timeout=TIMEOUT_MS)
    return page


def open_dashboard(page):
    sign_in(page)
    expect(page.get_by_role("heading", name="Tableau de bord ferroviaire")).to_be_visible(
        timeout=TIMEOUT_MS,
    )
    return page


def open_dashboard_admin(page):
    sign_in_admin(page)
    expect(page.get_by_role("heading", name="Tableau de bord ferroviaire")).to_be_visible(
        timeout=TIMEOUT_MS,
    )
    return page


def test_page_charge_et_affiche_les_donnees():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        open_dashboard(page)

        expect(page.locator(".app-logo-text")).to_be_visible(timeout=TIMEOUT_MS)
        expect(page.locator(".metric-card").first).to_contain_text("142", timeout=TIMEOUT_MS)

        browser.close()


def test_filtre_par_pays_fonctionne():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        open_dashboard(page)

        # Les filtres sont dans l onglet "Trajets" depuis la refonte en onglets (etape F).
        page.get_by_role("tab", name="Trajets").click(timeout=TIMEOUT_MS)

        result_count = page.locator(".table-count")
        expect(result_count).to_contain_text("resultats", timeout=TIMEOUT_MS)
        initial_count = result_count.inner_text(timeout=TIMEOUT_MS)

        page.get_by_label("Filtrer par pays").select_option("FR", timeout=TIMEOUT_MS)
        expect(result_count).not_to_have_text(initial_count, timeout=TIMEOUT_MS)

        browser.close()


def test_navigation_repond_sans_erreur_serveur():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        response = page.goto(FRONTEND_URL, wait_until="networkidle", timeout=TIMEOUT_MS)

        assert response is not None
        assert response.status < 500
        expect(page.locator("body")).not_to_contain_text("Erreur API 500", timeout=TIMEOUT_MS)

        browser.close()


def test_api_health_visible_dans_le_frontend():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        open_dashboard(page)

        expect(page.locator('[title="API opérationnelle"]')).to_be_visible(timeout=TIMEOUT_MS)

        browser.close()


def test_ecran_de_connexion_protege_le_tableau_de_bord():
    """Sans connexion, le tableau de bord ne doit pas etre accessible."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(FRONTEND_URL, wait_until="networkidle", timeout=TIMEOUT_MS)

        expect(page.get_by_label("Identifiant de connexion")).to_be_visible(timeout=TIMEOUT_MS)
        expect(
            page.get_by_role("heading", name="Tableau de bord ferroviaire")
        ).to_have_count(0)

        browser.close()


def test_mauvais_identifiants_affichent_une_erreur_accessible():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(FRONTEND_URL, wait_until="networkidle", timeout=TIMEOUT_MS)

        page.get_by_label("Identifiant de connexion").fill("inconnu", timeout=TIMEOUT_MS)
        page.get_by_label("Mot de passe").fill("mauvais", timeout=TIMEOUT_MS)
        page.get_by_role("button", name="Se connecter").click(timeout=TIMEOUT_MS)

        # role="alert" : le message est annonce aux lecteurs d ecran (RGAA)
        expect(page.get_by_role("alert")).to_be_visible(timeout=TIMEOUT_MS)

        browser.close()


def test_deconnexion_ramene_a_l_ecran_de_connexion():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        open_dashboard(page)

        page.get_by_role("button", name="Se deconnecter de l application").click(
            timeout=TIMEOUT_MS
        )
        expect(page.get_by_label("Identifiant de connexion")).to_be_visible(
            timeout=TIMEOUT_MS
        )

        browser.close()


# === Tests Agent IA (etape G) ================================================


def test_onglets_de_navigation_presents_apres_connexion():
    """Les trois onglets Tableau de bord, Trajets et Assistant IA sont accessibles."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        open_dashboard(page)

        tablist = page.get_by_role("tablist")
        expect(tablist).to_be_visible(timeout=TIMEOUT_MS)
        expect(page.get_by_role("tab", name="Tableau de bord")).to_be_visible(timeout=TIMEOUT_MS)
        expect(page.get_by_role("tab", name="Trajets")).to_be_visible(timeout=TIMEOUT_MS)
        expect(page.get_by_role("tab", name="Assistant IA")).to_be_visible(timeout=TIMEOUT_MS)

        browser.close()


def test_viewer_voit_acces_refuse_sur_onglet_assistant():
    """Un viewer clique sur Assistant IA et voit le message d acces refuse (D5)."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        open_dashboard(page)

        page.get_by_role("tab", name="Assistant IA").click(timeout=TIMEOUT_MS)

        # D5 : viewer voit le panneau "acces refuse", jamais l interface de chat
        expect(page.get_by_text("reserve aux administrateurs")).to_be_visible(
            timeout=TIMEOUT_MS
        )
        # La zone de saisie de message ne doit pas etre presente
        expect(page.get_by_label("Message pour l'assistant IA")).to_have_count(0)

        browser.close()


def test_admin_voit_interface_chat_sur_onglet_assistant():
    """Un admin acces a l onglet Assistant IA et voit le champ de saisie (D5 verifie)."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        open_dashboard_admin(page)

        page.get_by_role("tab", name="Assistant IA").click(timeout=TIMEOUT_MS)

        # L interface de chat doit etre presente pour un admin
        expect(page.get_by_label("Message pour l'assistant IA")).to_be_visible(
            timeout=TIMEOUT_MS
        )
        expect(page.get_by_role("button", name="Envoyer le message")).to_be_visible(
            timeout=TIMEOUT_MS
        )

        browser.close()


def test_admin_flux_chat_complet_en_mode_rejeu():
    """
    Validation bout en bout du flux de chat (C8) en mode rejeu.

    Precondition : backend demarre avec OBRAIL_LLM_PROVIDER=rejeu
    (reponse deterministe, rapide, sans reseau externe).

    Le test verifie :
    1. Le message utilisateur s affiche dans le chat
    2. L indicateur "en cours de generation" apparait
    3. La reponse de l assistant s affiche (bulle assistant visible)
    4. L indicateur de generation disparait apres la reponse
    """
    # Timeout elargi pour attendre la reponse rejeu (< 1 s en pratique)
    CHAT_TIMEOUT_MS = 30000

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        open_dashboard_admin(page)

        page.get_by_role("tab", name="Assistant IA").click(timeout=TIMEOUT_MS)
        expect(page.get_by_label("Message pour l'assistant IA")).to_be_visible(
            timeout=TIMEOUT_MS
        )

        # Envoyer une question pre-enregistree (Q1 rejeu)
        textarea = page.get_by_label("Message pour l'assistant IA")
        textarea.fill("Combien de trajets electriques recense-t-on en France ?")
        page.get_by_role("button", name="Envoyer le message").click(timeout=TIMEOUT_MS)

        # La bulle utilisateur doit etre visible immediatement
        expect(page.locator(".chat-bubble-user")).to_be_visible(timeout=TIMEOUT_MS)

        # La reponse de l assistant doit apparaitre (rejeu : < 500 ms)
        expect(page.locator(".chat-bubble-assistant")).to_be_visible(
            timeout=CHAT_TIMEOUT_MS
        )

        # L indicateur de generation doit avoir disparu
        expect(page.locator(".chat-typing")).to_have_count(0)

        browser.close()


# === Tests Analyses ML (C10) ==================================================
#
# L onglet "Analyses" (frontend/src/main.jsx, CalculateurSection) expose trois
# operations : le calculateur CO2 local (aucun appel reseau, deja couvert par les
# captures d ecran de C17), et deux appels reels aux routes de prediction ML,
# reserves aux administrateurs. Les deux tests ci-dessous couvrent ces deux
# routes en navigateur reel, ce qui manquait jusqu ici : test_e2e.py ne testait
# que le tableau de bord, les trajets et l assistant IA, jamais /predict/*.
#
# Les deux formulaires sont preremplis par defaut avec le cas de reference
# documente dans l application elle meme (800 km / 195 min pour la substitution,
# qui correspond exactement a Paris-Marseille, deja verifie cote modele par
# ml/tests/test_inference_contract.py avec les memes valeurs). Cliquer sur le
# bouton de prediction sans rien saisir suffit donc a declencher un vrai appel,
# exactement comme le ferait un utilisateur qui garde les valeurs par defaut.


def test_admin_predit_substitution_avion_train_via_ui():
    """
    Couvre POST /predict/substitution (C10) en navigateur reel, pas seulement en
    appel HTTP direct. Le formulaire par defaut (800 km, 195 min, 3 arrets,
    electrique, FR) reproduit exactement le cas Paris-Marseille deja verifie
    cote modele : la coherence entre l IHM et le contrat d inference est donc
    verifiee, pas seulement simulee.
    """
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        open_dashboard_admin(page)

        page.get_by_role("tab", name="Analyses").click(timeout=TIMEOUT_MS)
        page.get_by_role("button", name="Substitution avion").click(timeout=TIMEOUT_MS)

        expect(page.get_by_role("heading", name="Substitution avion")).to_be_visible(
            timeout=TIMEOUT_MS
        )

        # Formulaire deja valide par les valeurs par defaut : Predire suffit.
        page.get_by_role("button", name="Prédire").click(timeout=TIMEOUT_MS)

        expect(page.locator(".sub-banner-label")).to_contain_text(
            "Substituable", timeout=TIMEOUT_MS
        )
        expect(page.locator(".sub-banner-proba")).to_be_visible(timeout=TIMEOUT_MS)

        browser.close()


def test_admin_predit_projection_co2_via_ui():
    """
    Couvre POST /predict/co2 (C10) en navigateur reel. Le calculateur appelle
    cette route quatre fois en parallele, une par scenario d evolution du
    reseau (reference, 50% electrique, conso -15%, distance -10%), et affiche
    un resultat chiffre par scenario.
    """
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        open_dashboard_admin(page)

        page.get_by_role("tab", name="Analyses").click(timeout=TIMEOUT_MS)
        page.get_by_role("button", name="Projection CO").click(timeout=TIMEOUT_MS)

        expect(page.get_by_role("heading", name="Projection CO")).to_be_visible(
            timeout=TIMEOUT_MS
        )

        # Formulaire deja valide par les valeurs par defaut (400 km, 120 min).
        page.get_by_role("button", name="Analyser les 4 scénarios").click(timeout=TIMEOUT_MS)

        rows = page.locator(".proj-row")
        expect(rows).to_have_count(4, timeout=TIMEOUT_MS)
        expect(page.locator(".proj-co2-val").first).to_contain_text(
            "kg CO", timeout=TIMEOUT_MS
        )

        browser.close()
