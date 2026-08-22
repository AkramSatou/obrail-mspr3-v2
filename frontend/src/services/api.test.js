import { afterEach, describe, expect, it, vi } from "vitest";
import {
  AuthError,
  buildTrajetsQuery,
  envoyerMessageAgent,
  fetchAgentInfo,
  fetchTrajets,
  getApiErrorMessage,
  isAuthenticated,
} from "./api.js";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("buildTrajetsQuery", () => {
  it("removes empty filters before calling the API", () => {
    expect(
      buildTrajetsQuery({
        country: "FR",
        type_train: "",
        origin: "Lyon",
        destination: null,
        page: 1,
        page_size: 12,
      }),
    ).toEqual({
      country: "FR",
      origin: "Lyon",
      page: 1,
      page_size: 12,
    });
  });
});

describe("getApiErrorMessage", () => {
  it("reads the normalized backend error envelope first", () => {
    expect(
      getApiErrorMessage(
        {
          error: {
            message: "Trajet 'unknown-trip-id' introuvable",
          },
        },
        "Erreur API 404",
      ),
    ).toBe("Trajet 'unknown-trip-id' introuvable");
  });

  it("keeps FastAPI detail and fallback messages readable", () => {
    expect(getApiErrorMessage({ detail: "Champ invalide" }, "Erreur API 422")).toBe(
      "Champ invalide",
    );
    expect(getApiErrorMessage({}, "Erreur API 500")).toBe("Erreur API 500");
  });
});

describe("fetchTrajets", () => {
  it("does not append an empty query string", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ items: [], total: 0, total_pages: 0 }),
    });

    await fetchTrajets({});

    // Depuis l ajout de l authentification, chaque appel passe par une couche qui
    // construit un objet headers — vide tant qu aucun jeton n est present.
    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/trajets", {
      headers: {},
    });
  });
});

describe("authentification", () => {
  it("n'envoie pas d'en-tete Authorization tant que l'utilisateur n'est pas connecte", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ items: [] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await fetchTrajets({ country: "FR" });

    const [, options] = fetchMock.mock.calls[0];
    expect(options?.headers?.Authorization).toBeUndefined();
  });

  it("remonte une AuthError et purge la session sur un 401 non rattrapable", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: "Identifiants invalides ou jeton expire" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchTrajets({})).rejects.toBeInstanceOf(AuthError);
    expect(isAuthenticated()).toBe(false);
  });

  it("traduit un 403 en message de role insuffisant", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({ error: { message: "role insuffisant" } }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchTrajets({})).rejects.toThrow(/Acces refuse/);
  });
});

describe("envoyerMessageAgent", () => {
  it("envoie un POST /agent/chat avec le message et retourne la reponse", async () => {
    const mockReponse = {
      reponse: "42 trajets electriques en France.",
      session_id: "sess-001",
      mode: "rejeu",
      fournisseur: "rejeu",
      modele: "rejeu",
      duree_ms: 55,
      iterations: 1,
      trace: [],
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockReponse,
    });
    vi.stubGlobal("fetch", fetchMock);

    const resultat = await envoyerMessageAgent("Combien de trajets electriques en France ?", null);

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/agent\/chat$/);
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toMatchObject({ message: "Combien de trajets electriques en France ?" });
    expect(resultat).toEqual(mockReponse);
  });

  it("inclut le session_id dans le corps quand il est fourni", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        reponse: "ok",
        session_id: "sess-abc",
        mode: "rejeu",
        fournisseur: "rejeu",
        modele: "rejeu",
        duree_ms: 10,
        iterations: 1,
        trace: [],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await envoyerMessageAgent("Question", "sess-abc");

    const [, options] = fetchMock.mock.calls[0];
    expect(JSON.parse(options.body)).toMatchObject({ session_id: "sess-abc" });
  });
});

describe("fetchAgentInfo", () => {
  it("appelle GET /agent/info et retourne les informations du fournisseur", async () => {
    const mockInfo = {
      fournisseur: "rejeu",
      modele: "rejeu",
      mode: "rejeu",
      max_iterations: 5,
      timeout_s: 120,
      outils: ["obtenir_statistiques", "rechercher_trajets"],
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockInfo,
    });
    vi.stubGlobal("fetch", fetchMock);

    const resultat = await fetchAgentInfo();

    const [url] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/agent\/info$/);
    expect(resultat).toEqual(mockInfo);
  });
});
