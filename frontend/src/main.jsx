import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AuthError,
  buildTrajetsQuery,
  envoyerMessageAgent,
  fetchAgentInfo,
  fetchHealth,
  fetchStats,
  fetchTrajets,
  geocoderTrajet,
  getRole,
  getUsername,
  isAuthenticated,
  login,
  logout,
  predictSubstitution,
  predictCO2Futur,
} from "./services/api.js";
import {
  formatCarbon,
  formatDuration,
  formatInteger,
  formatKm,
  formatTimeFromMinutes,
} from "./utils/formatters.js";
import {
  IconeAnalyses,
  IconeAssistant,
  IconeAvion,
  IconeCadenas,
  IconeCloseChip,
  IconeDeconnexion,
  IconeEffacer,
  IconeEnvoyer,
  IconeFiltres,
  IconeLocalisation,
  IconeRail,
  IconeTableau,
  IconeTrajets,
  IconeTrainDiesel,
  IconeTrainElec,
  IconeVoiture,
} from "./components/icones.jsx";
import { AnneauProgression, GrilleActivite, GraphiqueAires } from "./components/visualisations.jsx";
import "./styles.css";

const DEFAULT_FILTERS = {
  country: "",
  type_train: "",
  origin: "",
  destination: "",
  min_distance_km: "",
  max_distance_km: "",
};

const COUNTRIES = [
  { value: "", label: "Tous les pays" },
  { value: "FR", label: "France" },
  { value: "DE", label: "Allemagne" },
  { value: "ES", label: "Espagne" },
  { value: "IT", label: "Italie" },
];

const TRAIN_TYPES = [
  { value: "", label: "Tous types" },
  { value: "electric", label: "Electrique" },
  { value: "diesel", label: "Diesel" },
];

const TABS = [
  { id: "tableau",   label: "Tableau de bord", Icone: IconeTableau  },
  { id: "trajets",   label: "Trajets",          Icone: IconeTrajets  },
  { id: "assistant", label: "Assistant IA",      Icone: IconeAssistant },
  { id: "analyses",  label: "Analyses",          Icone: IconeAnalyses  },
];

const DIST_MAX = 3000;

function App({ onLogout }) {
  const [sectionActive, setSectionActive] = useState("tableau");
  const [health, setHealth] = useState(null);
  const [stats, setStats] = useState(null);
  const [trajets, setTrajets] = useState(null);
  const [filters, setFilters] = useState(DEFAULT_FILTERS);

  /* Chat state lifted here so it survives tab switches */
  const [chatMessages, setChatMessages] = useState(() => {
    const u = getUsername() || "anonymous";
    // Delete legacy global keys — no migration to avoid cross-user history leakage.
    ["obrail.chat.current", "obrail.chat.sessionid", "obrail.chat.history", "obrail.chat.counter"]
      .forEach(k => localStorage.removeItem(k));
    try { return JSON.parse(localStorage.getItem(`obrail.chat.current.${u}`) || "[]"); } catch { return []; }
  });
  const [chatSessionId, setChatSessionId] = useState(() => {
    const u = getUsername() || "anonymous";
    return localStorage.getItem(`obrail.chat.sessionid.${u}`) || null;
  });
  const [chatEnAttente, setChatEnAttente] = useState(false);
  const [chatBadgeFournisseur, setChatBadgeFournisseur] = useState(null);
  const [chatHistory, setChatHistory] = useState(() => {
    const u = getUsername() || "anonymous";
    try { return JSON.parse(localStorage.getItem(`obrail.chat.history.${u}`) || "[]"); } catch { return []; }
  });

  useEffect(() => { const u = getUsername() || "anonymous"; localStorage.setItem(`obrail.chat.current.${u}`, JSON.stringify(chatMessages)); }, [chatMessages]);
  useEffect(() => { const u = getUsername() || "anonymous"; if (chatSessionId) localStorage.setItem(`obrail.chat.sessionid.${u}`, chatSessionId); }, [chatSessionId]);
  useEffect(() => { const u = getUsername() || "anonymous"; localStorage.setItem(`obrail.chat.history.${u}`, JSON.stringify(chatHistory)); }, [chatHistory]);
  const [page, setPage] = useState(1);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [tripsLoading, setTripsLoading] = useState(true);
  const [dashboardError, setDashboardError] = useState("");
  const [tripsError, setTripsError] = useState("");
  const [panneauFiltreOuvert, setPanneauFiltreOuvert] = useState(true);

  /* Sliding tab indicator */
  const navRef = useRef(null);
  const [indicatorStyle, setIndicatorStyle] = useState(null);

  useLayoutEffect(() => {
    const nav = navRef.current;
    if (!nav) return;
    const btn = nav.querySelector('[aria-selected="true"]');
    if (!btn) return;
    const navRect = nav.getBoundingClientRect();
    const btnRect = btn.getBoundingClientRect();
    setIndicatorStyle({
      width: btnRect.width + "px",
      transform: `translateX(${btnRect.left - navRect.left - 4}px)`,
    });
  }, [sectionActive]);

  /* Focus keyboard nav: focus the newly active tab after arrow key selection */
  const prevSection = useRef(sectionActive);
  useEffect(() => {
    if (prevSection.current !== sectionActive) {
      navRef.current?.querySelector('[aria-selected="true"]')?.focus();
    }
    prevSection.current = sectionActive;
  }, [sectionActive]);

  useEffect(() => {
    let ignore = false;
    async function loadDashboard() {
      setDashboardLoading(true);
      setDashboardError("");
      try {
        const [healthPayload, statsPayload] = await Promise.all([fetchHealth(), fetchStats()]);
        if (!ignore) {
          setHealth(healthPayload);
          setStats(statsPayload);
        }
      } catch (err) {
        if (!ignore) setDashboardError(err.message);
      } finally {
        if (!ignore) setDashboardLoading(false);
      }
    }
    loadDashboard();
    return () => { ignore = true; };
  }, []);

  useEffect(() => {
    let ignore = false;
    async function loadTrajets() {
      setTripsLoading(true);
      setTripsError("");
      try {
        const payload = await fetchTrajets({ ...filters, page, page_size: 12 });
        if (!ignore) setTrajets(payload);
      } catch (err) {
        if (!ignore) { setTripsError(err.message); setTrajets(null); }
      } finally {
        if (!ignore) setTripsLoading(false);
      }
    }
    loadTrajets();
    return () => { ignore = true; };
  }, [filters, page]);

  const activeFilters = useMemo(
    () =>
      Object.values(buildTrajetsQuery(filters)).filter(
        (v) => v !== "" && v !== null && v !== undefined,
      ).length,
    [filters],
  );

  function updateFilter(event) {
    const { name, value } = event.target;
    setFilters((current) => ({ ...current, [name]: value }));
    setPage(1);
  }

  function removeFilter(key) {
    setFilters((current) => ({ ...current, [key]: "" }));
    setPage(1);
  }

  function resetFilters() {
    setFilters(DEFAULT_FILTERS);
    setPage(1);
  }

  function handleTabKeyDown(e, index) {
    if (e.key === "ArrowRight") {
      e.preventDefault();
      setSectionActive(TABS[(index + 1) % TABS.length].id);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      setSectionActive(TABS[(index - 1 + TABS.length) % TABS.length].id);
    } else if (e.key === "Home") {
      e.preventDefault();
      setSectionActive(TABS[0].id);
    } else if (e.key === "End") {
      e.preventDefault();
      setSectionActive(TABS[TABS.length - 1].id);
    }
  }

  /* Données pour visualisations */
  const pointsCourbe = useMemo(() => {
    if (!stats?.by_country) return [];
    return [...stats.by_country]
      .sort((a, b) => b.total_trajets - a.total_trajets)
      .map((c) => ({ label: c.key, valeur: c.total_trajets }));
  }, [stats]);

  const { pctElectrique, totalTraction } = useMemo(() => {
    if (!stats?.by_type_train) return { pctElectrique: 0, totalTraction: 0 };
    const total = stats.by_type_train.reduce((acc, t) => acc + t.total_trajets, 0);
    const elec = stats.by_type_train.find((t) => t.key === "electric")?.total_trajets || 0;
    return { pctElectrique: total > 0 ? (elec / total) * 100 : 0, totalTraction: total };
  }, [stats]);

  const donneesGrille = useMemo(() => {
    if (!stats?.by_country || !stats?.by_type_train) return {};
    const total = stats.by_type_train.reduce((acc, t) => acc + t.total_trajets, 0) || 1;
    const result = {};
    stats.by_country.forEach((pays) => {
      stats.by_type_train.forEach((type) => {
        result[`${pays.key}-${type.key}`] = Math.round(
          pays.total_trajets * (type.total_trajets / total),
        );
      });
    });
    return result;
  }, [stats]);

  const lignesGrille = useMemo(
    () => stats?.by_country?.map((c) => c.key) || [],
    [stats],
  );
  const colonnesGrille = useMemo(
    () => stats?.by_type_train?.map((t) => t.key) || [],
    [stats],
  );

  return (
    <main className="app-shell">
      <a className="skip-link" href="#contenu-principal">
        Aller au contenu
      </a>

      <header className="app-header">
        <div className="navbar-pill">

          {/* Zone gauche : marque + rôle utilisateur */}
          <div className="navbar-left">
            <div className="app-logo">
              <span className="app-logo-icon" aria-hidden="true">
                <IconeRail taille={14} />
              </span>
              <span className="app-logo-text">ObRail</span>
            </div>
            <div className="user-pill" aria-live="polite">
              <span className="user-role-dot" aria-hidden="true" />
              <span>{getRole()}</span>
            </div>
          </div>

          {/* Zone centrale : onglets de navigation */}
          <nav
            ref={navRef}
            className="tab-nav"
            role="tablist"
            aria-label="Sections de l'application"
          >
            {indicatorStyle && (
              <span className="tab-indicator" style={indicatorStyle} aria-hidden="true" />
            )}
            {TABS.map(({ id, label, Icone }, index) => (
              <button
                key={id}
                role="tab"
                aria-selected={sectionActive === id}
                aria-controls={`panel-${id}`}
                className="tab-btn"
                type="button"
                onClick={() => setSectionActive(id)}
                onKeyDown={(e) => handleTabKeyDown(e, index)}
              >
                <Icone taille={15} />
                {label}
              </button>
            ))}
          </nav>

          {/* Zone droite : statut API + déconnexion */}
          <div className="navbar-right">
            <HealthBadge health={health} compact />
            <button
              className="logout-btn"
              type="button"
              onClick={onLogout}
              aria-label="Se deconnecter de l application"
            >
              <IconeDeconnexion taille={15} />
            </button>
          </div>

        </div>
      </header>

      <div className="app-content">
        {dashboardError ? (
          <section className="alert" role="alert">
            <strong>Indicateurs indisponibles.</strong>
            <span>{dashboardError}</span>
          </section>
        ) : null}

        <div id="contenu-principal">
          {sectionActive === "tableau" && (
            <div id="panel-tableau" role="tabpanel" aria-labelledby="tab-tableau">
              {/* h1 accessible pour les tests E2E et lecteurs d écran */}
              <h1 className="sr-only">Tableau de bord ferroviaire</h1>
              <section className="summary-grid" aria-label="Indicateurs principaux">
              {/* Carte hero — pleine largeur */}
              <article className="metric-card metric-card-hero">
                <p>Trajets disponibles</p>
                <strong>
                  {dashboardLoading ? "..." : stats ? formatInteger(stats.total_trajets) : "-"}
                </strong>
                <span>
                  {dashboardLoading ? "Chargement des indicateurs" : "Dataset harmonise"}
                </span>
                {pointsCourbe.length >= 2 && (
                  <div className="hero-graphique" aria-hidden="true">
                    <GraphiqueAires
                      points={pointsCourbe}
                      couleur="rgb(255 255 255 / 0.55)"
                      hauteur={60}
                      label="Repartition des trajets par pays"
                    />
                  </div>
                )}
              </article>

              <MetricCard
                label="Pays couverts"
                value={dashboardLoading ? "..." : stats ? formatInteger(stats.total_countries) : "-"}
                detail={stats ? stats.by_country.map((item) => item.key).join(", ") : "Aucune donnee"}
              />
              <MetricCard
                label="Routes distinctes"
                value={dashboardLoading ? "..." : stats ? formatInteger(stats.total_routes) : "-"}
                detail="Lignes et relations"
              />
              <MetricCard
                label="CO2 estime"
                value={dashboardLoading ? "..." : stats ? formatCarbon(stats.total_kg_co2_emis) : "-"}
                detail="Cumul kgCO2 dataset"
              />
            </section>

            <section
              className="panel distribution-panel"
              aria-label="Repartition des volumes"
              aria-busy={dashboardLoading}
            >
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Volumes</p>
                  <h2>Repartition par pays et energie</h2>
                </div>
              </div>
              <div className="bars-grid">
                <VolumeBars title="Pays" items={stats?.by_country || []} />
                <VolumeBars title="Traction" items={stats?.by_type_train || []} />
              </div>
              <div className="distrib-bas">
                {lignesGrille.length > 0 && colonnesGrille.length > 0 && (
                  <GrilleActivite
                    lignes={lignesGrille}
                    colonnes={colonnesGrille}
                    donnees={donneesGrille}
                    couleur="#818cf8"
                    label="Repartition estimee trajets par pays et type de traction"
                  />
                )}
                {totalTraction > 0 && (
                  <AnneauProgression
                    valeur={pctElectrique}
                    max={100}
                    label="Electrique"
                    couleur="#818cf8"
                    taille={96}
                  />
                )}
                {totalTraction > 0 && (
                  <AnneauProgression
                    valeur={100 - pctElectrique}
                    max={100}
                    label="Diesel"
                    couleur="#fb923c"
                    taille={96}
                  />
                )}
              </div>
            </section>
          </div>
        )}

        {sectionActive === "trajets" && (
          <div id="panel-trajets" role="tabpanel" aria-labelledby="tab-trajets">
            <section className="dashboard-grid">
              <aside className="panel filters-panel" aria-label="Filtres trajets">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">Recherche</p>
                    <h2>Filtres</h2>
                  </div>
                  <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                    <span className="counter" aria-label={`${activeFilters} filtres actifs`}>
                      {activeFilters}
                    </span>
                    <button
                      className="panel-toggle-btn"
                      type="button"
                      onClick={() => setPanneauFiltreOuvert((o) => !o)}
                      aria-expanded={panneauFiltreOuvert}
                      aria-label={panneauFiltreOuvert ? "Masquer les filtres" : "Afficher les filtres"}
                    >
                      <IconeFiltres taille={15} />
                      {panneauFiltreOuvert ? "Masquer" : "Filtres"}
                    </button>
                  </div>
                </div>

                {panneauFiltreOuvert && (
                  <div className="filter-stack">
                    <label>
                      Pays
                      <select
                        name="country"
                        value={filters.country}
                        onChange={updateFilter}
                        aria-label="Filtrer par pays"
                      >
                        {COUNTRIES.map((country) => (
                          <option key={country.value || "all"} value={country.value}>
                            {country.label}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      Type de train
                      <select
                        name="type_train"
                        value={filters.type_train}
                        onChange={updateFilter}
                        aria-label="Filtrer par type de train"
                      >
                        {TRAIN_TYPES.map((type) => (
                          <option key={type.value || "all"} value={type.value}>
                            {type.label}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      Gare de depart
                      <input
                        name="origin"
                        placeholder="Ex. Lyon"
                        value={filters.origin}
                        onChange={updateFilter}
                        aria-label="Filtrer par gare de depart"
                      />
                    </label>

                    <label>
                      Gare d'arrivee
                      <input
                        name="destination"
                        placeholder="Ex. Dijon"
                        value={filters.destination}
                        onChange={updateFilter}
                        aria-label="Filtrer par gare d'arrivee"
                      />
                    </label>

                    <div className="distance-slider-group">
                      <div className="distance-slider">
                        <label>
                          <span className="slider-val-row">
                            <span>Distance min</span>
                            <span className="slider-val">
                              {filters.min_distance_km || 0} km
                            </span>
                          </span>
                          <input
                            type="range"
                            name="min_distance_km"
                            min="0"
                            max={filters.max_distance_km ? Number(filters.max_distance_km) : DIST_MAX}
                            value={filters.min_distance_km || 0}
                            onChange={updateFilter}
                            aria-label="Distance minimale en kilometres"
                          />
                        </label>
                      </div>
                      <div className="distance-slider">
                        <label>
                          <span className="slider-val-row">
                            <span>Distance max</span>
                            <span className="slider-val">
                              {filters.max_distance_km || DIST_MAX} km
                            </span>
                          </span>
                          <input
                            type="range"
                            name="max_distance_km"
                            min={filters.min_distance_km ? Number(filters.min_distance_km) : 0}
                            max={DIST_MAX}
                            value={filters.max_distance_km || DIST_MAX}
                            onChange={updateFilter}
                            aria-label="Distance maximale en kilometres"
                          />
                        </label>
                      </div>
                    </div>
                  </div>
                )}

                <button
                  className="secondary-button"
                  type="button"
                  onClick={resetFilters}
                  disabled={!activeFilters}
                >
                  Reinitialiser
                </button>
              </aside>

              <section className="content-stack">
                <ChipFiltres filters={filters} onRemove={removeFilter} />

                <section
                  className="panel trips-panel"
                  id="trajets"
                  aria-label="Liste des trajets"
                  aria-busy={tripsLoading}
                >
                  <div className="panel-header table-header">
                    <div>
                      <p className="eyebrow">Trajets</p>
                      <h2>Liste exploitable</h2>
                    </div>
                    <p className="table-count" aria-live="polite">
                      {tripsLoading
                        ? "Chargement des trajets"
                        : trajets
                          ? `${formatInteger(trajets.total)} resultats`
                          : "Aucun resultat"}
                    </p>
                  </div>

                  {tripsError ? (
                    <section className="alert alert-inline" role="alert">
                      <strong>Trajets indisponibles.</strong>
                      <span>{tripsError}</span>
                    </section>
                  ) : null}

                  <TripsTable loading={tripsLoading && !trajets} trajets={trajets} />

                  <Pagination
                    page={page}
                    totalPages={trajets?.total_pages || 0}
                    onPrevious={() => setPage((current) => Math.max(1, current - 1))}
                    onNext={() =>
                      setPage((current) =>
                        trajets?.total_pages
                          ? Math.min(trajets.total_pages, current + 1)
                          : current,
                      )
                    }
                  />
                </section>
              </section>
            </section>
          </div>
        )}

          <div id="panel-assistant" role="tabpanel" aria-labelledby="tab-assistant"
            hidden={sectionActive !== "assistant"}>
            <AssistantIA
              messages={chatMessages} setMessages={setChatMessages}
              sessionId={chatSessionId} setSessionId={setChatSessionId}
              enAttente={chatEnAttente} setEnAttente={setChatEnAttente}
              badgeFournisseur={chatBadgeFournisseur} setBadgeFournisseur={setChatBadgeFournisseur}
              chatHistory={chatHistory} setChatHistory={setChatHistory}
            />
          </div>

          {sectionActive === "analyses" && (
            <div id="panel-analyses" role="tabpanel" aria-labelledby="tab-analyses">
              <h1 className="sr-only">Analyses et calculateur ferroviaire</h1>
              <CalculateurSection />
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

/* Chips de filtres actifs au-dessus du tableau */
function ChipFiltres({ filters, onRemove }) {
  const actifs = [];
  if (filters.country) actifs.push({ key: "country", label: `Pays : ${filters.country}` });
  if (filters.type_train) actifs.push({ key: "type_train", label: `Train : ${filters.type_train}` });
  if (filters.origin) actifs.push({ key: "origin", label: `Depart : ${filters.origin}` });
  if (filters.destination) actifs.push({ key: "destination", label: `Arrivee : ${filters.destination}` });
  if (filters.min_distance_km && Number(filters.min_distance_km) > 0) {
    actifs.push({ key: "min_distance_km", label: `≥ ${filters.min_distance_km} km` });
  }
  if (filters.max_distance_km && Number(filters.max_distance_km) < DIST_MAX) {
    actifs.push({ key: "max_distance_km", label: `≤ ${filters.max_distance_km} km` });
  }

  if (!actifs.length) return null;

  return (
    <div className="filtres-chips" aria-label="Filtres actifs">
      {actifs.map((chip) => (
        <span key={chip.key} className="filtre-chip">
          {chip.label}
          <button
            type="button"
            className="chip-remove"
            onClick={() => onRemove(chip.key)}
            aria-label={`Supprimer le filtre ${chip.label}`}
          >
            <IconeCloseChip taille={12} />
          </button>
        </span>
      ))}
    </div>
  );
}

const SUGGESTIONS_AGENT = [
  "Combien de trajets electriques recense-t-on en France ?",
  "Le trajet Paris-Marseille en train est-il substituable a l'avion ?",
  "Quelles emissions de CO2 pour un trajet de 400 km en diesel ?",
];

function useElapsedSeconds(active) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!active) { setElapsed(0); return; }
    const t0 = Date.now();
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - t0) / 1000)), 1000);
    return () => clearInterval(id);
  }, [active]);
  return elapsed;
}

const AI_NAME = "ObRail";

function AssistantIA({ messages, setMessages, sessionId, setSessionId, enAttente, setEnAttente, badgeFournisseur, setBadgeFournisseur, chatHistory, setChatHistory }) {
  const role = getRole();
  const estAdmin = role === "admin";
  const username = getUsername();

  const [saisie, setSaisie] = useState("");
  const [agentInfo, setAgentInfo] = useState(null);
  const [fournisseurChoisi, setFournisseurChoisi] = useState("auto");
  const [editingId, setEditingId] = useState(null);
  const [editingTitre, setEditingTitre] = useState("");
  const [convCounter, setConvCounter] = useState(() => {
    const u = getUsername() || "anonymous";
    return parseInt(localStorage.getItem(`obrail.chat.counter.${u}`) || "1", 10);
  });
  // null = nouvelle conversation non sauvegardée ; id = conversation de l'historique active
  const [activeConvId, setActiveConvId] = useState(null);
  const bottomRef = useRef(null);
  const elapsedS = useElapsedSeconds(enAttente);

  useEffect(() => {
    if (!estAdmin) return;
    fetchAgentInfo()
      .then((info) => {
        setAgentInfo(info);
        const cle = info.mode === "rejeu" ? "rejeu" : info.fournisseur;
        setBadgeFournisseur(cle);
      })
      .catch(() => {});
  }, [estAdmin]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, enAttente]);

  async function envoyer(texte) {
    const msg = texte ?? saisie;
    if (!msg.trim() || enAttente) return;
    setSaisie("");
    setEnAttente(true);
    setMessages((prev) => [...prev, { role: "user", contenu: msg }]);
    try {
      const resp = await envoyerMessageAgent(msg, sessionId, fournisseurChoisi !== "auto" ? fournisseurChoisi : null);
      setSessionId(resp.session_id);
      const cle = resp.mode === "rejeu" ? "rejeu" : resp.fournisseur;
      setBadgeFournisseur(cle);
      setMessages((prev) => [...prev, { role: "assistant", contenu: resp.reponse, fournisseur: cle }]);
    } catch (err) {
      setMessages((prev) => [...prev, { role: "erreur", contenu: err.message }]);
    } finally {
      setEnAttente(false);
    }
  }

  function _sauverAvantNavigation() {
    if (activeConvId !== null) {
      // Mettre à jour la conv active dans l'historique avec les messages en cours
      setChatHistory(prev => prev.map(h =>
        h.id === activeConvId ? { ...h, messages: [...messages] } : h
      ));
    } else if (messages.length > 0) {
      // Nouvelle conversation non sauvegardée → créer une entrée numérotée
      const date = new Date().toLocaleDateString("fr-FR", { day: "numeric", month: "short" });
      const num  = convCounter;
      setChatHistory(prev => [{ id: Date.now(), titre: `Conversation ${num}`, date, messages: [...messages] }, ...prev].slice(0, 30));
      const next = num + 1;
      setConvCounter(next);
      localStorage.setItem(`obrail.chat.counter.${getUsername() || "anonymous"}`, String(next));
    }
  }

  function effacer() {
    _sauverAvantNavigation();
    setActiveConvId(null);
    setMessages([]);
    setSessionId(null);
    setBadgeFournisseur(null);
    const u = getUsername() || "anonymous";
    localStorage.removeItem(`obrail.chat.current.${u}`);
    localStorage.removeItem(`obrail.chat.sessionid.${u}`);
  }

  function restaurer(item) {
    if (item.id === activeConvId) return;
    _sauverAvantNavigation();
    setActiveConvId(item.id);
    // Relire depuis l'historique courant (peut avoir été mis à jour)
    setChatHistory(prev => {
      const found = prev.find(h => h.id === item.id);
      setMessages(found ? [...found.messages] : [...item.messages]);
      return prev;
    });
    setSessionId(null);
    setBadgeFournisseur(null);
    const u = getUsername() || "anonymous";
    localStorage.removeItem(`obrail.chat.current.${u}`);
    localStorage.removeItem(`obrail.chat.sessionid.${u}`);
  }

  function supprimerHistorique(id, e) {
    e.stopPropagation();
    if (id === activeConvId) {
      setActiveConvId(null);
      setMessages([]);
    }
    setChatHistory(prev => prev.filter(h => h.id !== id));
  }

  function démarrerEdit(id, titre, e) {
    e.stopPropagation();
    setEditingId(id);
    setEditingTitre(titre);
  }

  function sauvegarderTitre(id) {
    if (editingTitre.trim()) {
      setChatHistory(prev => prev.map(h => h.id === id ? { ...h, titre: editingTitre.trim() } : h));
    }
    setEditingId(null);
  }

  const labelMode = { rejeu: "Demo", ollama: "Ollama", openrouter: "GPT-4o mini", auto: "Auto" };

  return (
    <div className="assistant-shell" role="region" aria-label="Assistant IA ObRail">

      {/* Sidebar historique */}
      <div className="chat-sidebar">
        <div className="chat-sidebar-header">
          <span>Historique</span>
          <button className="chat-sidebar-new" onClick={effacer} disabled={!messages.length || enAttente} title="Sauvegarder et nouveau chat">
            + Nouveau
          </button>
        </div>
        <div className="chat-sidebar-list">
          {/* Nouvelle conversation (non encore sauvegardée) — affichée en haut quand active */}
          {activeConvId === null && (
            <div className="chat-history-item chat-history-active">
              <span className="chat-history-title">
                {messages.length > 0 ? `Conversation ${convCounter}` : "Nouvelle conversation"}
              </span>
              <div className="chat-history-meta">
                <span className="chat-history-date">● Actuelle</span>
              </div>
            </div>
          )}

          {activeConvId === null && chatHistory.length > 0 && <div className="chat-sidebar-sep" />}

          {/* Toutes les conversations sauvegardées — elles ne bougent jamais */}
          {chatHistory.length === 0 && activeConvId === null && (
            <p className="chat-sidebar-empty">Les conversations apparaîtront ici après votre premier échange.</p>
          )}
          {chatHistory.map(h => {
            const estActive = h.id === activeConvId;
            return (
              <div
                key={h.id}
                className={`chat-history-item${estActive ? " chat-history-active" : ""}`}
                onClick={() => !estActive && editingId !== h.id && restaurer(h)}
                role="button"
                tabIndex={0}
              >
                {editingId === h.id ? (
                  <input
                    className="chat-history-edit-input"
                    value={editingTitre}
                    onChange={e => setEditingTitre(e.target.value)}
                    onBlur={() => sauvegarderTitre(h.id)}
                    onKeyDown={e => { if (e.key === "Enter") sauvegarderTitre(h.id); if (e.key === "Escape") setEditingId(null); }}
                    onClick={e => e.stopPropagation()}
                    autoFocus
                  />
                ) : (
                  <span className="chat-history-title">{h.titre}</span>
                )}
                <div className="chat-history-meta">
                  <span className="chat-history-date">{estActive ? "● Actuelle" : h.date}</span>
                  {!estActive && (
                    <div className="chat-history-actions">
                      <button className="chat-history-action-btn" onClick={(e) => démarrerEdit(h.id, h.titre, e)} title="Renommer">✎</button>
                      <button className="chat-history-action-btn chat-history-del" onClick={(e) => supprimerHistorique(h.id, e)} title="Supprimer">✕</button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Colonne principale */}
      <div className="chat-main">
        <div className="assistant-header">
          <div className="assistant-header-left">
            <div className="assistant-avatar" aria-hidden="true">
              <IconeAssistant taille={18} />
            </div>
            <div>
              <h2>{AI_NAME}</h2>
              {badgeFournisseur && (
                <span className={`assistant-mode-badge mode-${badgeFournisseur}`}>
                  {labelMode[badgeFournisseur] ?? badgeFournisseur}
                </span>
              )}
            </div>
          </div>
          <div className="assistant-header-right">
            <div className="chat-provider-select" role="group" aria-label="Fournisseur IA">
              {[["auto", "Auto"], ["ollama", "Ollama"], ["openrouter", "GPT-4o mini"]].map(([val, lib]) => (
                <button key={val} type="button"
                  className={`chat-provider-btn${fournisseurChoisi === val ? " active" : ""}`}
                  onClick={() => setFournisseurChoisi(val)}
                  title={val === "auto" ? "Sélection automatique" : val === "ollama" ? "Ollama (local)" : "LLaMA 3.1 via OpenRouter"}>
                  {lib}
                </button>
              ))}
            </div>
          </div>
        </div>

        {!estAdmin ? (
          <div className="assistant-acces-refuse">
            <div className="chat-vide-icon"><IconeAssistant taille={26} /></div>
            <p>L'assistant IA est reserve aux administrateurs.</p>
            <p style={{ fontSize: "0.82rem" }}>Role actuel : <strong style={{ color: "var(--text-1)" }}>{role || "inconnu"}</strong></p>
          </div>
        ) : (
          <>
            <div className="chat-messages" aria-live="polite" aria-label="Historique de la conversation">
              {messages.length === 0 ? (
                <div className="chat-vide">
                  <div className="chat-vide-icon"><IconeAssistant taille={26} /></div>
                  <h3>Comment puis-je vous aider ?</h3>
                  <p>Posez une question sur le réseau ferroviaire européen.</p>
                  <div className="chat-empty-suggestions" role="list">
                    {SUGGESTIONS_AGENT.map((s) => (
                      <button key={s} className="chat-empty-suggestion-btn" type="button" role="listitem" onClick={() => envoyer(s)} disabled={enAttente}>
                        <span className="suggestion-icon" aria-hidden="true">→</span>
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                messages.map((msg, i) => (
                  <div key={i} className={`chat-message chat-message-${msg.role}`}>
                    {msg.role !== "user" && (
                      <div className="chat-avatar" aria-hidden="true"><IconeAssistant taille={14} /></div>
                    )}
                    <div className="chat-bubble-col">
                      <span className={`chat-sender-name chat-sender-${msg.role}`}>
                        {msg.role === "user" ? (username || "Vous") : AI_NAME}
                      </span>
                      <div className={`chat-bubble chat-bubble-${msg.role}`}>
                        {msg.role === "assistant" ? renderMd(msg.contenu) : msg.contenu}
                      </div>
                    </div>
                  </div>
                ))
              )}
              {enAttente && (
                <div className="chat-message chat-message-assistant">
                  <div className="chat-avatar" aria-hidden="true"><IconeAssistant taille={14} /></div>
                  <div className="chat-bubble-col">
                    <span className="chat-sender-name">{AI_NAME}</span>
                    <div className="chat-bubble chat-bubble-assistant chat-attente-bubble">
                      <div className="chat-typing" aria-hidden="true"><span /><span /><span /></div>
                      <div className="chat-attente-info" aria-live="polite">
                        <span className="chat-attente-temps">{elapsedS}s</span>
                        <span className="chat-attente-label">
                          {agentInfo?.fournisseur === "ollama" || badgeFournisseur === "ollama"
                            ? "Ollama local — jusqu'à 2 min selon le modèle"
                            : "Génération en cours…"}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            <div className="chat-suggestions-bar" aria-label="Suggestions rapides">
              {SUGGESTIONS_AGENT.map((s) => (
                <button key={s} className="chat-suggestion-chip" type="button" onClick={() => envoyer(s)} disabled={enAttente}>
                  {s.length > 44 ? s.slice(0, 44) + "…" : s}
                </button>
              ))}
            </div>

            <div className="chat-input-zone">
              <div className="chat-input-wrapper">
                <textarea
                  value={saisie}
                  onChange={(e) => setSaisie(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); envoyer(); } }}
                  placeholder={`Message à ${AI_NAME}… (Entrée pour envoyer)`}
                  aria-label="Message pour l'assistant IA"
                  disabled={enAttente}
                  rows={1}
                />
                <button className="chat-send-btn" type="button" onClick={() => envoyer()} disabled={!saisie.trim() || enAttente} aria-label="Envoyer le message">
                  <IconeEnvoyer taille={16} />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function HealthBadge({ health, compact }) {
  const status = health?.status || "loading";

  /* Mode compact (dans la navbar) : point coloré + préfixe "API" + statut lisible */
  if (compact) {
    const shortLabel = { ok: "OK", degraded: "Dégradée", unavailable: "Indispo.", loading: "…" }[status] ?? "?";
    const title = { ok: "API opérationnelle", degraded: "API dégradée", unavailable: "API indisponible", loading: "Vérification API" }[status];
    return (
      <div className={`health-badge health-${status} health-badge-compact`} aria-live="polite" title={title}>
        <span className="status-dot" aria-hidden="true" />
        <span className="badge-api-prefix" aria-hidden="true">API</span>
        <strong>{shortLabel}</strong>
      </div>
    );
  }

  const label = {
    ok: "API operationnelle",
    degraded: "API degradee",
    unavailable: "API indisponible",
    loading: "Verification API",
  }[status] || "Etat inconnu";

  return (
    <div className={`health-badge health-${status}`} aria-live="polite">
      <span className="status-dot" aria-hidden="true" />
      <div>
        <strong>{label}</strong>
        <span>
          {health?.timestamp
            ? new Date(health.timestamp).toLocaleString("fr-FR")
            : "En cours"}
        </span>
      </div>
    </div>
  );
}

function MetricCard({ label, value, detail, accent }) {
  return (
    <article className={`metric-card${accent ? ` metric-card-${accent}` : ""}`}>
      <p>{label}</p>
      <strong>{value}</strong>
      <span>{detail}</span>
    </article>
  );
}

function VolumeBars({ title, items }) {
  const max = Math.max(...items.map((item) => item.total_trajets), 1);

  return (
    <div className="volume-group">
      <h3>{title}</h3>
      {items.length ? (
        items.map((item) => (
          <div className="bar-row" key={item.key}>
            <div className="bar-label">
              <span>{item.key}</span>
              <span>{formatInteger(item.total_trajets)}</span>
            </div>
            <div
              className="bar-track"
              role="meter"
              aria-valuenow={item.total_trajets}
              aria-valuemin={0}
              aria-valuemax={max}
              aria-label={`${item.key} : ${formatInteger(item.total_trajets)} trajets`}
            >
              <span style={{ width: `${(item.total_trajets / max) * 100}%` }} />
            </div>
          </div>
        ))
      ) : (
        <p className="empty-state">Volumes en cours de chargement.</p>
      )}
    </div>
  );
}

function TripsTable({ loading, trajets }) {
  if (loading) {
    return (
      <p className="empty-state" role="status">
        Chargement des trajets...
      </p>
    );
  }

  if (!trajets?.items?.length) {
    return (
      <p className="empty-state" role="status">
        Aucun trajet ne correspond aux filtres.
      </p>
    );
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Relation</th>
            <th scope="col">Pays</th>
            <th scope="col">Train</th>
            <th scope="col">Distance</th>
            <th scope="col">Duree</th>
            <th scope="col">Depart</th>
            <th scope="col">CO2</th>
          </tr>
        </thead>
        <tbody>
          {trajets.items.map((trajet) => (
            <tr key={trajet.id}>
              <td>
                <strong>{trajet.origin_stop_name}</strong>
                <span>{trajet.destination_stop_name}</span>
              </td>
              <td>{trajet.country}</td>
              <td>
                <span className={`pill pill-${trajet.type_train}`}>
                  {trajet.type_train}
                </span>
              </td>
              <td>{formatKm(trajet.distance_km)}</td>
              <td>{formatDuration(trajet.duration_minutes)}</td>
              <td>{formatTimeFromMinutes(trajet.departure_minutes)}</td>
              <td>{formatCarbon(trajet.kg_co2_emis)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Pagination({ page, totalPages, onPrevious, onNext }) {
  return (
    <nav className="pagination" aria-label="Pagination trajets">
      <button
        type="button"
        onClick={onPrevious}
        disabled={page <= 1}
        aria-label="Afficher la page precedente"
      >
        Precedent
      </button>
      <span aria-live="polite">
        Page {page} / {totalPages || 1}
      </span>
      <button
        type="button"
        onClick={onNext}
        disabled={!totalPages || page >= totalPages}
        aria-label="Afficher la page suivante"
      >
        Suivant
      </button>
    </nav>
  );
}

/* ── Facteurs d'émission CO₂ (ADEME 2023, kg/km/passager) ────────── */
const EMISSION = { electric: 0.014, diesel: 0.049 };
const CMP_MODES = [
  { label: "Train électrique", facteur: EMISSION.electric, couleur: "var(--accent)",  Icon: IconeTrainElec },
  { label: "Train diesel",      facteur: EMISSION.diesel,   couleur: "#a3e635",        Icon: IconeTrainDiesel },
  { label: "Voiture (essence)", facteur: 0.218,             couleur: "#f97316",        Icon: IconeVoiture },
  { label: "Avion court-courrier", facteur: 0.255,          couleur: "#ef4444",        Icon: IconeAvion },
];

function formatCO2(kg) {
  return kg < 0.1 ? `${(kg * 1000).toFixed(0)} g` : `${kg.toFixed(2)} kg`;
}

const SCENARIOS_CO2 = [
  { id: "reference",            label: "Référence (baseline)",           desc: "Aucune modification" },
  { id: "diesel_50_electrique", label: "50 % diesel → électrique",       desc: "Moitié des trains diesel convertis" },
  { id: "conso_moins_15",       label: "Consommation −15 %",             desc: "Efficacité énergétique améliorée" },
  { id: "distance_moins_10",    label: "Distances −10 %",                desc: "Optimisation des trajets" },
];

const GCO2_PER_KWH_PRESETS = [
  { label: "France (nucléaire) — 21.7",  value: 21.7  },
  { label: "Espagne — 250",              value: 250   },
  { label: "Italie — 233",               value: 233   },
  { label: "Allemagne (mix) — 400",      value: 400   },
];

const CALC_OPS = [
  { id: "co2",          label: "Calculateur CO₂",         methode: "LOCAL", desc: "Estimation des émissions et comparaison train / voiture / avion." },
  { id: "substitution", label: "Substitution avion→train", methode: "POST",  desc: "Modèle ML XGBoost — prédit si la liaison peut remplacer un vol aérien.", admin: true },
  { id: "projection",   label: "Projection CO₂ — scénarios", methode: "POST", desc: "Régression ML — CO₂ estimé selon 4 scénarios d'évolution du réseau.", admin: true },
];

/* ── Rendu Markdown minimal pour les bulles de l'assistant ──────── */
function inlineMd(text, keyBase) {
  const re = /(\*\*(.+?)\*\*|\*([^*]+?)\*|`([^`]+?)`)/g;
  const parts = [];
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    if (m[2] !== undefined) parts.push(<strong key={`${keyBase}-b${m.index}`}>{m[2]}</strong>);
    else if (m[3] !== undefined) parts.push(<em key={`${keyBase}-i${m.index}`}>{m[3]}</em>);
    else if (m[4] !== undefined) parts.push(<code key={`${keyBase}-c${m.index}`} className="md-code">{m[4]}</code>);
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

function renderMd(text) {
  if (!text) return null;
  const blocks = text.split(/\n{2,}/);
  return blocks.map((block, bi) => {
    const lines = block.split('\n').map(l => l.trimEnd()).filter(Boolean);
    if (!lines.length) return null;
    if (lines.every(l => /^[-*] /.test(l)))
      return <ul key={bi} className="md-list">{lines.map((l, i) => <li key={i}>{inlineMd(l.replace(/^[-*] /, ''), `${bi}-${i}`)}</li>)}</ul>;
    if (lines.every(l => /^\d+\. /.test(l)))
      return <ol key={bi} className="md-list">{lines.map((l, i) => <li key={i}>{inlineMd(l.replace(/^\d+\. /, ''), `${bi}-${i}`)}</li>)}</ol>;
    if (/^#{1,3} /.test(lines[0])) {
      const lvl = lines[0].match(/^(#{1,3}) /)[1].length;
      return React.createElement(`h${lvl + 2}`, { key: bi, className: 'md-h' }, inlineMd(lines[0].replace(/^#{1,3} /, ''), bi));
    }
    return <p key={bi} className="md-p">{lines.map((l, i) => [i > 0 && <br key={`br${i}`}/>, inlineMd(l, `${bi}-${i}`)])}</p>;
  });
}

function minutesEnHHMM(minutes) {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return h > 0 ? `${h}h ${m}min` : `${m} min`;
}

function GeocodageAuto({ typeTrain, onResult }) {
  const [origine, setOrigine] = useState("");
  const [destination, setDestination] = useState("");
  const [loading, setLoading] = useState(false);
  const [erreur, setErreur] = useState("");
  const [resultat, setResultat] = useState(null);
  const [dureeManuellementModifiee, setDureeManuellementModifiee] = useState(false);

  async function calculer() {
    if (!origine.trim() || !destination.trim()) return;
    setLoading(true);
    setErreur("");
    setResultat(null);
    setDureeManuellementModifiee(false);
    try {
      const data = await geocoderTrajet(origine.trim(), destination.trim(), typeTrain);
      setResultat(data);
      onResult(data);
    } catch (e) {
      setErreur(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <fieldset className="geocode-block">
      <legend>
        <IconeLocalisation taille={13} />
        Calculer automatiquement (optionnel)
      </legend>
      <div className="geocode-inner">
        <label>
          Origine
          <input
            type="text"
            placeholder="Ex. Paris Gare de Lyon"
            value={origine}
            onChange={e => { setOrigine(e.target.value); setResultat(null); }}
            onKeyDown={e => e.key === "Enter" && calculer()}
          />
        </label>
        <label>
          Destination
          <input
            type="text"
            placeholder="Ex. Berlin Hbf"
            value={destination}
            onChange={e => { setDestination(e.target.value); setResultat(null); }}
            onKeyDown={e => e.key === "Enter" && calculer()}
          />
        </label>
        <button
          type="button"
          className="geocode-run-btn"
          onClick={calculer}
          disabled={loading || !origine.trim() || !destination.trim()}
        >
          {loading ? "…" : "Calculer"}
        </button>
      </div>
      {erreur && <p className="geocode-error">{erreur}</p>}
      {resultat && !erreur && (
        <p className="geocode-result">
          <span className="geocode-badge-estimation">estimation</span>
          {" "}
          <strong>{resultat.distance_km} km</strong> à vol d'oiseau
          {" · durée ≈ "}
          <strong>{minutesEnHHMM(resultat.duree_estimee_minutes)}</strong>
          {` (${Math.round(resultat.duree_estimee_minutes)} min)`}
        </p>
      )}
    </fieldset>
  );
}

function AccesRefuseML() {
  return (
    <div className="calc-acces-refuse">
      <strong>Accès réservé aux administrateurs</strong>
      <p>Les modèles de prédiction ML nécessitent le rôle <em>admin</em>.</p>
    </div>
  );
}

function CalculateurSection() {
  const [op, setOp]   = useState("co2");
  const estAdmin = getRole() === "admin";

  /* — CO₂ client-side — */
  const [co2P, setCo2P] = useState({ distance_km: "", passagers: "1" });
  const [co2R, setCo2R] = useState(null);

  function runCo2() {
    const dist = Number(co2P.distance_km);
    const pax  = Math.max(1, Number(co2P.passagers) || 1);
    if (!dist || dist <= 0) return;
    const comparaisons = CMP_MODES.map(m => ({
      label: m.label, co2: m.facteur * dist * pax, couleur: m.couleur, Icon: m.Icon,
    }));
    const maxVal = Math.max(...comparaisons.map(c => c.co2));
    setCo2R({ dist, pax, maxVal, comparaisons });
  }

  /* — Substitution ML — */
  const [subP, setSubP] = useState({
    distance_km: "800", duration_minutes: "195", n_stops: "3",
    type_train: "electric", country: "FR",
  });
  const [subR, setSubR] = useState(null);
  const [subL, setSubL] = useState(false);
  const [subE, setSubE] = useState("");
  useEffect(() => { if (op !== "substitution") setSubR(null); }, [op]);

  const SUB_CO2_G_PER_KM  = { electric: 562.5,  diesel: 1969 };
  const SUB_KWH_PER_KM    = { electric: 20,      diesel: 40 };

  async function runSubstitution() {
    setSubL(true); setSubE(""); setSubR(null);
    try {
      const dist = Number(subP.distance_km);
      const traction = subP.type_train;
      const payload = {
        distance_km:         dist,
        duration_minutes:    Number(subP.duration_minutes),
        n_stops:             parseInt(subP.n_stops, 10),
        co2_estime:          Math.round(dist * SUB_CO2_G_PER_KM[traction]),
        consommation_totale: Math.round(dist * SUB_KWH_PER_KM[traction]),
        type_train:          traction,
        country:             subP.country,
      };
      setSubR(await predictSubstitution(payload));
    } catch (e) { setSubE(e.message); }
    finally { setSubL(false); }
  }

  /* — Projection CO₂ ML — */
  const [projP, setProjP] = useState({
    distance_km: "400", duration_minutes: "120", n_stops: "2",
    consommation_energy: "10", gco2_per_kwh: "21.7",
    consommation_totale: "4000", type_train: "diesel",
  });
  const [projR, setProjR] = useState(null);
  const [projL, setProjL] = useState(false);
  const [projE, setProjE] = useState("");

  async function runProjection() {
    setProjL(true); setProjE(""); setProjR(null);
    try {
      const base = {
        distance_km:         Number(projP.distance_km),
        duration_minutes:    Number(projP.duration_minutes),
        n_stops:             parseInt(projP.n_stops, 10),
        consommation_energy: Number(projP.consommation_energy),
        gco2_per_kwh:        Number(projP.gco2_per_kwh),
        consommation_totale: Number(projP.consommation_totale),
        type_train:          projP.type_train,
      };
      const results = await Promise.all(
        SCENARIOS_CO2.map(s => predictCO2Futur({ ...base, scenario: s.id }))
      );
      const maxCO2 = Math.max(...results.map(r => r.co2_estime_kg));
      setProjR(SCENARIOS_CO2.map((s, i) => ({ ...s, co2: results[i].co2_estime_kg, maxCO2 })));
    } catch (e) { setProjE(e.message); }
    finally { setProjL(false); }
  }

  const subFormValid = subP.distance_km && subP.duration_minutes;
  const projFormValid = projP.distance_km && projP.duration_minutes;

  return (
    <div className="calc-shell">
      {/* Sidebar */}
      <aside className="calc-sidebar">
        <p className="eyebrow">Opérations</p>
        {CALC_OPS.map(o => (
          <button key={o.id} type="button"
            className={`calc-op-btn${op === o.id ? " calc-op-active" : ""}`}
            onClick={() => setOp(o.id)}>
            <span className={`calc-badge calc-badge-${o.methode.toLowerCase()}`}>{o.methode}</span>
            <span>{o.label}</span>
            {o.admin && <span className="calc-admin-lock" aria-hidden="true"><IconeCadenas taille={13} /></span>}
          </button>
        ))}
        <p className="calc-sidebar-hint">
          Les modèles ML requièrent le rôle <em>admin</em>. Le calculateur CO₂ est accessible à tous.
        </p>
      </aside>

      {/* Panneau principal */}
      <div className="calc-main">

        {/* ── CO₂ local ─────────────────────────────────────────── */}
        {op === "co2" && (
          <section className="calc-panel">
            <div className="calc-panel-header">
              <span className="calc-badge calc-badge-local">LOCAL</span>
              <div>
                <h2>Calculateur CO₂</h2>
                <p className="calc-desc">Estimez les émissions de CO₂ selon la distance et le mode de traction. Comparaison avec voiture et avion court-courrier.</p>
              </div>
            </div>
            <div className="calc-form">
              <div className="calc-form-grid">
                <GeocodageAuto
                  typeTrain="electric"
                  onResult={({ distance_km }) =>
                    setCo2P(p => ({ ...p, distance_km: String(distance_km) }))
                  }
                />
                <label>
                  Distance (km)
                  <input type="number" min="1" max="10000" placeholder="Ex. 750"
                    value={co2P.distance_km}
                    onChange={e => setCo2P(p => ({...p, distance_km: e.target.value}))}
                    onKeyDown={e => e.key === "Enter" && runCo2()} />
                </label>
                <label>
                  Passagers
                  <input type="number" min="1" max="1000" value={co2P.passagers}
                    onChange={e => setCo2P(p => ({...p, passagers: e.target.value}))}
                    onKeyDown={e => e.key === "Enter" && runCo2()} />
                </label>
              </div>
              <button className="calc-run-btn" type="button"
                onClick={runCo2} disabled={!co2P.distance_km}>
                Calculer
              </button>
            </div>
            {co2R && (
              <div className="calc-result">
                <div className="co2-chart-header">
                  <p className="eyebrow">Émissions CO₂ comparées</p>
                  <span className="co2-chart-meta">
                    {formatInteger(co2R.dist)} km · {co2R.pax} passager{co2R.pax > 1 ? "s" : ""}
                  </span>
                </div>
                <div className="co2-chart">
                  {co2R.comparaisons.map(c => {
                    const pct = (c.co2 / co2R.maxVal) * 100;
                    return (
                      <div key={c.label} className="co2-chart-row">
                        <div className="co2-chart-icon" style={{ color: c.couleur }}>
                          <c.Icon taille={18} />
                        </div>
                        <span className="co2-chart-label">{c.label}</span>
                        <div className="co2-chart-bar-wrap">
                          <div className="co2-chart-bar"
                            style={{ width: `${pct}%`, background: c.couleur }} />
                        </div>
                        <strong className="co2-chart-val">{formatCO2(c.co2)}</strong>
                      </div>
                    );
                  })}
                </div>
                {co2R.comparaisons.length >= 4 && co2R.comparaisons[0].co2 > 0 && (
                  <p className="co2-insight">
                    Train électrique :{" "}
                    <strong>{Math.round(co2R.comparaisons[3].co2 / co2R.comparaisons[0].co2)}×</strong>{" "}
                    moins d'émissions que l'avion
                  </p>
                )}
                <p className="calc-source">
                  Sources ADEME 2023 — élec. 14 gCO₂/km/pass. · diesel 49 g · voiture 218 g · avion 255 g.
                </p>
              </div>
            )}
          </section>
        )}

        {/* ── Substitution ML ───────────────────────────────────── */}
        {op === "substitution" && (
          !estAdmin ? <AccesRefuseML /> : (
          <section className="calc-panel">
            <div className="calc-panel-header">
              <span className="calc-badge calc-badge-post">POST</span>
              <div>
                <h2>Substitution avion → train</h2>
                <p className="calc-desc">
                  Modèle <strong>XGBoost</strong> entraîné sur le dataset ObRail — prédit si une liaison ferroviaire
                  peut remplacer un vol aérien (distance 300–1 500 km, durée &lt; 8 h).
                  Cas de référence : Paris–Marseille (800 km, 3h15) → substituable.
                </p>
              </div>
            </div>
            <div className="calc-form">
              <p className="calc-endpoint">POST /predict/substitution</p>
              <div className="calc-form-grid">
                <GeocodageAuto
                  typeTrain={subP.type_train}
                  onResult={({ distance_km, duree_estimee_minutes }) =>
                    setSubP(p => ({ ...p, distance_km: String(distance_km), duration_minutes: String(duree_estimee_minutes) }))
                  }
                />
                <label>
                  Distance (km)
                  <input type="number" min="1" value={subP.distance_km}
                    onChange={e => setSubP(p => ({...p, distance_km: e.target.value}))} />
                </label>
                <label>
                  Durée (min)
                  <input type="number" min="1" value={subP.duration_minutes}
                    onChange={e => setSubP(p => ({...p, duration_minutes: e.target.value}))} />
                </label>
                <label>
                  Nombre d'arrêts
                  <input type="number" min="0" max="20" value={subP.n_stops}
                    onChange={e => setSubP(p => ({...p, n_stops: e.target.value}))} />
                  <span className="field-hint">Arrêts intermédiaires hors terminus</span>
                </label>
                <label>
                  Type de traction
                  <select value={subP.type_train}
                    onChange={e => setSubP(p => ({...p, type_train: e.target.value}))}>
                    <option value="electric">Électrique</option>
                    <option value="diesel">Diesel</option>
                  </select>
                </label>
                <label>
                  Pays
                  <select value={subP.country}
                    onChange={e => setSubP(p => ({...p, country: e.target.value}))}>
                    {["FR","DE","ES","IT"].map(c => <option key={c}>{c}</option>)}
                  </select>
                </label>
              </div>
              <button className="calc-run-btn" type="button"
                onClick={runSubstitution} disabled={subL || !subFormValid}>
                {subL ? "Analyse en cours…" : "Prédire"}
              </button>
            </div>
            {subE && <div className="calc-error">{subE}</div>}
            {subR && (
              <div className="calc-result">
                <div className={`sub-banner sub-banner-${subR.substitution_avion ? "yes" : "no"}`}>
                  <span className="sub-banner-label">
                    {subR.substitution_avion ? "Substituable" : "Non substituable"}
                  </span>
                  <span className="sub-banner-proba">{Math.round(subR.probabilite * 100)} %</span>
                </div>
                <p className="sub-banner-detail">{subR.label}</p>
                <div className="sub-proba-track">
                  <div className="sub-proba-fill"
                    style={{
                      width: `${subR.probabilite * 100}%`,
                      background: subR.substitution_avion ? "var(--accent)" : "var(--danger)",
                    }} />
                </div>
                <p className="calc-source">
                  XGBoost classifieur — seuil métier : 300–1 500 km &amp; durée &lt; 8h (Back-on-Track / Transport &amp; Environment).
                </p>
              </div>
            )}
          </section>
          )
        )}

        {/* ── Projection CO₂ ML ─────────────────────────────────── */}
        {op === "projection" && (
          !estAdmin ? <AccesRefuseML /> : (
          <section className="calc-panel">
            <div className="calc-panel-header">
              <span className="calc-badge calc-badge-post">POST</span>
              <div>
                <h2>Projection CO₂ — 4 scénarios</h2>
                <p className="calc-desc">
                  Régression ML — estime les émissions CO₂ d'une liaison selon 4 scénarios d'évolution du réseau.
                  Compare l'impact de l'électrification, de l'efficacité énergétique et de l'optimisation des distances.
                </p>
              </div>
            </div>
            <div className="calc-form">
              <p className="calc-endpoint">POST /predict/co2 × 4 scénarios</p>
              <div className="calc-form-grid">
                <GeocodageAuto
                  typeTrain={projP.type_train}
                  onResult={({ distance_km, duree_estimee_minutes }) =>
                    setProjP(p => ({ ...p, distance_km: String(distance_km), duration_minutes: String(duree_estimee_minutes) }))
                  }
                />
                <label>
                  Distance (km)
                  <input type="number" min="1" value={projP.distance_km}
                    onChange={e => setProjP(p => ({...p, distance_km: e.target.value}))} />
                </label>
                <label>
                  Durée (min)
                  <input type="number" min="1" value={projP.duration_minutes}
                    onChange={e => setProjP(p => ({...p, duration_minutes: e.target.value}))} />
                </label>
                <label>
                  Nombre d'arrêts
                  <input type="number" min="0" value={projP.n_stops}
                    onChange={e => setProjP(p => ({...p, n_stops: e.target.value}))} />
                  <span className="field-hint">Arrêts intermédiaires hors terminus</span>
                </label>
                <label>
                  Consommation énergétique (kWh/km)
                  <input type="number" min="0" step="0.1" value={projP.consommation_energy}
                    onChange={e => setProjP(p => ({...p, consommation_energy: e.target.value}))} />
                  <span className="field-hint">Énergie consommée par kilomètre parcouru</span>
                </label>
                <label>
                  Facteur carbone (gCO₂/kWh)
                  <select value={projP.gco2_per_kwh}
                    onChange={e => setProjP(p => ({...p, gco2_per_kwh: e.target.value}))}>
                    {GCO2_PER_KWH_PRESETS.map(g => (
                      <option key={g.value} value={g.value}>{g.label}</option>
                    ))}
                  </select>
                  <span className="field-hint">gCO₂ émis par kWh consommé, selon le mix énergétique du pays</span>
                </label>
                <label>
                  Consommation totale (kWh)
                  <input type="number" min="0" value={projP.consommation_totale}
                    onChange={e => setProjP(p => ({...p, consommation_totale: e.target.value}))} />
                  <span className="field-hint">Énergie consommée sur l'ensemble du trajet</span>
                </label>
                <label>
                  Type de traction
                  <select value={projP.type_train}
                    onChange={e => setProjP(p => ({...p, type_train: e.target.value}))}>
                    <option value="diesel">Diesel</option>
                    <option value="electric">Électrique</option>
                  </select>
                </label>
              </div>
              <button className="calc-run-btn" type="button"
                onClick={runProjection} disabled={projL || !projFormValid}>
                {projL ? "Calcul en cours…" : "Analyser les 4 scénarios"}
              </button>
            </div>
            {projE && <div className="calc-error">{projE}</div>}
            {projR && (
              <div className="calc-result">
                <p className="eyebrow">Résultats par scénario</p>
                {projR.map((s, i) => (
                  <div key={s.id} className="proj-row">
                    <div className="proj-row-header">
                      <div>
                        <strong className="proj-scenario-label">{s.label}</strong>
                        <span className="proj-scenario-desc">{s.desc}</span>
                      </div>
                      <strong className="proj-co2-val">
                        {s.co2.toFixed(2)} <span>kg CO₂</span>
                      </strong>
                    </div>
                    <div className="co2-bar-track">
                      <div className="co2-bar-fill"
                        style={{
                          width: `${(s.co2 / s.maxCO2) * 100}%`,
                          background: i === 0 ? "var(--text-3)" : "var(--accent)",
                          opacity: i === 0 ? 0.6 : 1,
                        }} />
                    </div>
                    {i > 0 && projR[0].co2 > 0 && (
                      <p className="proj-saving">
                        Économie vs référence : <strong>
                          {((1 - s.co2 / projR[0].co2) * 100).toFixed(1)} %
                        </strong>
                      </p>
                    )}
                  </div>
                ))}
                <p className="calc-source">
                  Régression XGBoost — scénarios : Back-on-Track 2040, IEA Net Zero 2050. gCO₂/kWh : ADEME / ElectricityMaps 2023.
                </p>
              </div>
            )}
          </section>
          )
        )}

      </div>
    </div>
  );
}

function LoginScreen({ onSuccess }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      await login(username, password);
      onSuccess();
    } catch (err) {
      setError(err instanceof AuthError ? err.message : "Connexion impossible.");
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="login-screen">
      <form className="login-card" onSubmit={handleSubmit}>
        <h1>ObRail Europe</h1>
        <p className="login-intro">
          Observatoire ferroviaire europeen — acces reserve aux utilisateurs autorises.
        </p>

        <label htmlFor="username">Identifiant</label>
        <input
          id="username"
          name="username"
          type="text"
          autoComplete="username"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          aria-label="Identifiant de connexion"
          required
        />

        <label htmlFor="password">Mot de passe</label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          aria-label="Mot de passe"
          required
        />

        {error && (
          <p className="login-error" role="alert">
            {error}
          </p>
        )}

        <button type="submit" disabled={pending} aria-busy={pending}>
          {pending ? "Connexion..." : "Se connecter"}
        </button>
      </form>
    </main>
  );
}

class FrontiereErreur extends React.Component {
  constructor(props) {
    super(props);
    this.state = { erreur: null };
  }

  static getDerivedStateFromError(erreur) {
    return { erreur };
  }

  render() {
    if (this.state.erreur) {
      return (
        <main className="login-screen">
          <div className="login-card">
            <h1>ObRail — Erreur inattendue</h1>
            <p role="alert" style={{ color: "var(--color-danger, #e53e3e)", marginBottom: "1rem" }}>
              {String(this.state.erreur)}
            </p>
            <button type="button" onClick={() => window.location.reload()}>
              Recharger la page
            </button>
          </div>
        </main>
      );
    }
    return this.props.children;
  }
}

function Root() {
  const [authenticated, setAuthenticated] = useState(isAuthenticated());

  useEffect(() => {
    const interval = setInterval(() => {
      setAuthenticated(isAuthenticated());
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  if (!authenticated) {
    return <LoginScreen onSuccess={() => setAuthenticated(true)} />;
  }

  return (
    <FrontiereErreur>
      <App
        onLogout={() => {
          logout();
          setAuthenticated(false);
        }}
      />
    </FrontiereErreur>
  );
}

createRoot(document.getElementById("root")).render(
  <FrontiereErreur>
    <Root />
  </FrontiereErreur>
);
