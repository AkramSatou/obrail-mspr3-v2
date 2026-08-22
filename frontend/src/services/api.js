const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

// Les jetons sont conserves en sessionStorage : ils disparaissent a la fermeture
// de l'onglet, ce qui limite l'exposition sur un poste partage. Le jeton d'acces
// est aussi garde en memoire pour eviter une lecture disque a chaque requete.
const ACCESS_KEY = "obrail.access_token";
const REFRESH_KEY = "obrail.refresh_token";
const ROLE_KEY = "obrail.role";
const USERNAME_KEY = "obrail.username";

// Acces defensif : sessionStorage n existe pas sous Node (tests unitaires Vitest),
// ni lorsque le navigateur bloque le stockage. Le module doit rester importable.
const store = {
  get(key) {
    try {
      return globalThis.sessionStorage?.getItem(key) ?? null;
    } catch {
      return null;
    }
  },
  set(key, value) {
    try {
      globalThis.sessionStorage?.setItem(key, value);
    } catch {
      /* stockage indisponible : la session reste valable en memoire */
    }
  },
  remove(key) {
    try {
      globalThis.sessionStorage?.removeItem(key);
    } catch {
      /* idem */
    }
  },
};

let accessToken = store.get(ACCESS_KEY);

export class AuthError extends Error {}

export function getRole() {
  return store.get(ROLE_KEY);
}

export function isAuthenticated() {
  return Boolean(accessToken);
}

function storeSession({ access_token, refresh_token, role }, username = null) {
  accessToken = access_token;
  store.set(ACCESS_KEY, access_token);
  store.set(REFRESH_KEY, refresh_token);
  store.set(ROLE_KEY, role);
  if (username) store.set(USERNAME_KEY, username);
}

export function getUsername() {
  return store.get(USERNAME_KEY);
}

export function logout() {
  accessToken = null;
  store.remove(ACCESS_KEY);
  store.remove(REFRESH_KEY);
  store.remove(ROLE_KEY);
}

export function buildTrajetsQuery(filters = {}) {
  return Object.fromEntries(
    Object.entries(filters).filter(
      ([, value]) => value !== "" && value !== null && value !== undefined,
    ),
  );
}

export function getApiErrorMessage(payload, fallback) {
  return (
    payload?.error?.message ||
    payload?.detail?.message ||
    (typeof payload?.detail === "string" ? payload.detail : null) ||
    fallback
  );
}

export async function login(username, password) {
  // OAuth2PasswordRequestForm cote FastAPI attend un formulaire, pas du JSON.
  const body = new URLSearchParams({ username, password });
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!response.ok) {
    throw new AuthError("Identifiants invalides.");
  }
  const payload = await response.json();
  storeSession(payload, username);
  return payload;
}

// Renouvellement silencieux : appele une seule fois quand une requete renvoie 401,
// pour eviter de deconnecter l'utilisateur des l'expiration du jeton d'acces.
async function refreshAccessToken() {
  const refresh = store.get(REFRESH_KEY);
  if (!refresh) return false;
  try {
    const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!response.ok) return false;
    storeSession(await response.json());
    return true;
  } catch {
    return false;
  }
}

async function rawRequest(path, options) {
  const headers = { ...(options.headers || {}) };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  return fetch(`${API_BASE_URL}${path}`, { ...options, headers });
}

async function requestJson(path, options = {}) {
  let response;
  try {
    response = await rawRequest(path, options);
  } catch {
    throw new Error(
      "Impossible de contacter l'API ObRail. Verifiez que le backend est demarre.",
    );
  }

  // 401 : jeton absent, invalide ou expire. On tente un renouvellement, une fois.
  if (response.status === 401 && (await refreshAccessToken())) {
    try {
      response = await rawRequest(path, options);
    } catch {
      throw new Error("Impossible de contacter l'API ObRail.");
    }
  }

  if (response.status === 401) {
    logout();
    throw new AuthError("Session expiree. Reconnectez-vous.");
  }

  if (response.status === 403) {
    throw new Error(
      "Acces refuse : votre role ne permet pas cette operation.",
    );
  }

  if (!response.ok) {
    let message = `Erreur API ${response.status}`;
    try {
      const payload = await response.json();
      message = getApiErrorMessage(payload, message);
    } catch {
      // La reponse peut etre vide ou non JSON en cas d'erreur reseau/proxy.
    }
    throw new Error(message);
  }

  try {
    return await response.json();
  } catch {
    throw new Error("La reponse API est illisible.");
  }
}

// /health reste public : le badge d'etat doit fonctionner avant la connexion.
export function fetchHealth() {
  return requestJson("/health");
}

export function fetchStats() {
  return requestJson("/stats/volumes");
}

export function fetchTrajets(filters) {
  const params = new URLSearchParams(buildTrajetsQuery(filters));
  const query = params.toString();
  return requestJson(query ? `/trajets?${query}` : "/trajets");
}

export function fetchCurrentUser() {
  return requestJson("/auth/me");
}

export function envoyerMessageAgent(message, sessionId = null, fournisseurForce = null) {
  const corps = { message };
  if (sessionId) corps.session_id = sessionId;
  if (fournisseurForce && fournisseurForce !== "auto") corps.fournisseur_force = fournisseurForce;
  return requestJson("/agent/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(corps),
  });
}

export function fetchAgentInfo() {
  return requestJson("/agent/info");
}

export function predictSubstitution(data) {
  return requestJson("/predict/substitution", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function predictCO2Futur(data) {
  return requestJson("/predict/co2", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function geocoderTrajet(origine, destination, type_train = "electric") {
  const params = new URLSearchParams({ origine, destination, type_train });
  return requestJson(`/geocode?${params}`);
}
