import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AuthError,
  buildTrajetsQuery,
  envoyerMessageAgent,
  fetchAgentInfo,
  fetchHealth,
  fetchStats,
  fetchTrajets,
  getRole,
  isAuthenticated,
  login,
  logout,
} from "./services/api.js";
import {
  formatCarbon,
  formatDuration,
  formatInteger,
  formatKm,
  formatTimeFromMinutes,
} from "./utils/formatters.js";
import {
  IconeAssistant,
  IconeEffacer,
  IconeEnvoyer,
  IconeTableau,
  IconeTrajets,
} from "./components/icones.jsx";
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
  { id: "tableau", label: "Tableau de bord", Icone: IconeTableau },
  { id: "trajets", label: "Trajets", Icone: IconeTrajets },
  { id: "assistant", label: "Assistant IA", Icone: IconeAssistant },
];

function App() {
  const [sectionActive, setSectionActive] = useState("tableau");
  const [health, setHealth] = useState(null);
  const [stats, setStats] = useState(null);
  const [trajets, setTrajets] = useState(null);
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [page, setPage] = useState(1);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [tripsLoading, setTripsLoading] = useState(true);
  const [dashboardError, setDashboardError] = useState("");
  const [tripsError, setTripsError] = useState("");

  useEffect(() => {
    let ignore = false;

    async function loadDashboard() {
      setDashboardLoading(true);
      setDashboardError("");
      try {
        const [healthPayload, statsPayload] = await Promise.all([
          fetchHealth(),
          fetchStats(),
        ]);
        if (!ignore) {
          setHealth(healthPayload);
          setStats(statsPayload);
        }
      } catch (err) {
        if (!ignore) {
          setDashboardError(err.message);
        }
      } finally {
        if (!ignore) {
          setDashboardLoading(false);
        }
      }
    }

    loadDashboard();
    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    let ignore = false;

    async function loadTrajets() {
      setTripsLoading(true);
      setTripsError("");
      try {
        const payload = await fetchTrajets({ ...filters, page, page_size: 12 });
        if (!ignore) {
          setTrajets(payload);
        }
      } catch (err) {
        if (!ignore) {
          setTripsError(err.message);
          setTrajets(null);
        }
      } finally {
        if (!ignore) {
          setTripsLoading(false);
        }
      }
    }

    loadTrajets();
    return () => {
      ignore = true;
    };
  }, [filters, page]);

  const activeFilters = useMemo(
    () =>
      Object.values(buildTrajetsQuery(filters)).filter(
        (value) => value !== "" && value !== null && value !== undefined,
      ).length,
    [filters],
  );

  function updateFilter(event) {
    const { name, value } = event.target;
    setFilters((current) => ({ ...current, [name]: value }));
    setPage(1);
  }

  function resetFilters() {
    setFilters(DEFAULT_FILTERS);
    setPage(1);
  }

  return (
    <main className="app-shell">
      <a className="skip-link" href="#contenu-principal">
        Aller au contenu
      </a>
      <header className="topbar">
        <div>
          <p className="eyebrow">ObRail Europe</p>
          <h1>Tableau de bord ferroviaire</h1>
        </div>
        <HealthBadge health={health} />
      </header>

      {dashboardError ? (
        <section className="alert" role="alert">
          <strong>Indicateurs indisponibles.</strong>
          <span>{dashboardError}</span>
        </section>
      ) : null}

      <nav className="tab-nav" role="tablist" aria-label="Sections de l'application">
        {TABS.map(({ id, label, Icone }) => (
          <button
            key={id}
            role="tab"
            aria-selected={sectionActive === id}
            aria-controls={`panel-${id}`}
            className="tab-btn"
            type="button"
            onClick={() => setSectionActive(id)}
          >
            <Icone taille={17} />
            {label}
          </button>
        ))}
      </nav>

      <div id="contenu-principal">
        {sectionActive === "tableau" && (
          <div id="panel-tableau" role="tabpanel" aria-labelledby="tab-tableau">
            <section className="summary-grid" aria-label="Indicateurs principaux">
              <MetricCard
                label="Trajets disponibles"
                value={dashboardLoading ? "..." : stats ? formatInteger(stats.total_trajets) : "-"}
                detail={dashboardLoading ? "Chargement des indicateurs" : "Dataset harmonise"}
              />
              <MetricCard
                label="Pays couverts"
                value={dashboardLoading ? "..." : stats ? formatInteger(stats.total_countries) : "-"}
                detail={
                  stats ? stats.by_country.map((item) => item.key).join(", ") : "Aucune donnee"
                }
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
                  <span className="counter">{activeFilters}</span>
                </div>

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

                  <div className="distance-row">
                    <label>
                      Distance min
                      <input
                        min="0"
                        name="min_distance_km"
                        placeholder="km"
                        type="number"
                        value={filters.min_distance_km}
                        onChange={updateFilter}
                        aria-label="Distance minimale en kilometres"
                      />
                    </label>
                    <label>
                      Distance max
                      <input
                        min="0"
                        name="max_distance_km"
                        placeholder="km"
                        type="number"
                        value={filters.max_distance_km}
                        onChange={updateFilter}
                        aria-label="Distance maximale en kilometres"
                      />
                    </label>
                  </div>
                </div>

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

        {sectionActive === "assistant" && (
          <div id="panel-assistant" role="tabpanel" aria-labelledby="tab-assistant">
            <AssistantIA />
          </div>
        )}
      </div>
    </main>
  );
}

const SUGGESTIONS_AGENT = [
  "Combien de trajets electriques recense-t-on en France ?",
  "Le trajet Paris-Marseille en train est-il substituable a l'avion ?",
  "Quelles emissions de CO2 pour un trajet de 400 km en diesel ?",
];

function AssistantIA() {
  const role = getRole();
  const estAdmin = role === "admin";

  const [messages, setMessages] = useState([]);
  const [saisie, setSaisie] = useState("");
  const [enAttente, setEnAttente] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [badgeFournisseur, setBadgeFournisseur] = useState(null);
  const bottomRef = useRef(null);

  // Correction 2 : appel à /agent/info au montage pour afficher le badge avant
  // le premier message, sans attendre une réponse de chat.
  useEffect(() => {
    if (!estAdmin) return;
    fetchAgentInfo()
      .then((info) => {
        // Correction 3 : la clé du badge = "rejeu" ou le fournisseur réel
        // (info.fournisseur peut valoir "ollama", "openrouter", "auto", "rejeu")
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
      const resp = await envoyerMessageAgent(msg, sessionId);
      setSessionId(resp.session_id);
      // Correction 3 : lire resp.fournisseur, pas resp.mode, pour obtenir
      // "ollama" / "openrouter" / "rejeu" — resp.mode ne vaut que "direct"/"rejeu"
      const cle = resp.mode === "rejeu" ? "rejeu" : resp.fournisseur;
      setBadgeFournisseur(cle);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", contenu: resp.reponse, fournisseur: cle },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "erreur", contenu: err.message },
      ]);
    } finally {
      setEnAttente(false);
    }
  }

  function effacer() {
    setMessages([]);
    setSessionId(null);
    setBadgeFournisseur(null);
  }

  const labelMode = {
    rejeu: "Demo hors-ligne",
    ollama: "Ollama local",
    openrouter: "OpenRouter",
    auto: "Mode auto",
  };

  return (
    <div className="assistant-shell" role="region" aria-label="Assistant IA ObRail">
      <div className="assistant-header">
        <IconeAssistant taille={22} />
        <div>
          <p className="eyebrow">Intelligence artificielle</p>
          <h2>Assistant ferroviaire</h2>
        </div>
        {badgeFournisseur && (
          <span className={`assistant-mode-badge mode-${badgeFournisseur}`}>
            {labelMode[badgeFournisseur] ?? badgeFournisseur}
          </span>
        )}
      </div>

      {!estAdmin ? (
        <div className="assistant-acces-refuse">
          <IconeAssistant taille={40} />
          <p>L'assistant IA est reserve aux administrateurs.</p>
          <p style={{ fontSize: "0.82rem" }}>
            Role actuel : <strong style={{ color: "var(--verre-sombre-text)" }}>{role || "inconnu"}</strong>
          </p>
        </div>
      ) : (
        <>
          <div
            className="chat-messages"
            aria-live="polite"
            aria-label="Historique de la conversation"
          >
            {messages.length === 0 ? (
              <div className="chat-vide">
                <IconeAssistant taille={36} />
                <p>Posez une question sur le reseau ferroviaire europeen.</p>
                <div className="chat-suggestions">
                  {SUGGESTIONS_AGENT.map((s) => (
                    <button
                      key={s}
                      className="chat-suggestion-btn"
                      type="button"
                      onClick={() => envoyer(s)}
                      disabled={enAttente}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((msg, i) => (
                <div key={i} className={`chat-bubble chat-bubble-${msg.role}`}>
                  {msg.contenu}
                </div>
              ))
            )}
            {enAttente && (
              <div className="chat-typing" aria-label="Reponse en cours de generation">
                <span />
                <span />
                <span />
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="chat-input-zone">
            <textarea
              value={saisie}
              onChange={(e) => setSaisie(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  envoyer();
                }
              }}
              placeholder="Posez une question ferroviaire... (Entree pour envoyer)"
              aria-label="Message pour l'assistant IA"
              disabled={enAttente}
              rows={1}
            />
            <button
              className="chat-clear-btn"
              type="button"
              onClick={effacer}
              disabled={!messages.length || enAttente}
              aria-label="Effacer la conversation"
            >
              <IconeEffacer taille={15} />
            </button>
            <button
              className="chat-send-btn"
              type="button"
              onClick={() => envoyer()}
              disabled={!saisie.trim() || enAttente}
              aria-label="Envoyer le message"
            >
              <IconeEnvoyer taille={15} />
              Envoyer
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function HealthBadge({ health }) {
  const status = health?.status || "loading";
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

function MetricCard({ label, value, detail }) {
  return (
    <article className="metric-card">
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
            <div className="bar-track">
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

function Root() {
  const [authenticated, setAuthenticated] = useState(isAuthenticated());

  // Sondage 30 s : ramene l ecran de connexion apres expiration de session cote API
  // sans rechargement manuel (RGESN R1.8 : −93 % de requetes vs. 2 s).
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
    <>
      <div className="session-bar">
        <span aria-live="polite">
          Connecte — role <strong>{getRole()}</strong>
        </span>
        <button
          type="button"
          onClick={() => {
            logout();
            setAuthenticated(false);
          }}
          aria-label="Se deconnecter de l application"
        >
          Se deconnecter
        </button>
      </div>
      <App />
    </>
  );
}

createRoot(document.getElementById("root")).render(<Root />);
