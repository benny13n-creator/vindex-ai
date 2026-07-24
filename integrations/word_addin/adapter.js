// adapter.js — Vindex AI Word Add-in komunikacioni sloj
// KORAK C: Ambient Context & Word/Browser Copilot (2026-07-24)
//
// Ovaj fajl NAMERNO ne sadrži nikakav UI (taskpane.html još ne postoji --
// v. napomenu u manifest.xml). Ovo je čisti "adapter" između Office.js
// (Word dokument) i Vindex REST API-ja (POST /api/copilot/ambient/analyze):
//   1. Čita poslednji pasus koji korisnik kuca (Office.js Word API).
//   2. Debounce-uje (klijentska strana -- backend NE debounce-uje, v.
//      services/ambient_analyzer.py docstring).
//   3. Šalje zahtev sa Bearer tokenom, vraća sugestije preko callback-a.
//
// Token: Word add-in ne može da deli localStorage sa glavnom Vindex web
// aplikacijom (različit origin/kontekst) -- korisnik se loguje JEDNOM u
// taskpane-u (van scope-a ovog fajla), token se čuva preko
// Office.context.roamingSettings (sinhronizuje se sa Office nalogom
// korisnika kroz uređaje) sa localStorage fallback-om za razvoj/testiranje
// van stvarnog Office okruženja.

(function (global) {
  "use strict";

  const DEFAULT_API_BASE = "https://vindex.rs";
  const ANALYZE_PATH = "/api/copilot/ambient/analyze";
  const DEBOUNCE_MS = 900;
  const MIN_CHARS_TO_ANALYZE = 40;
  const TOKEN_STORAGE_KEY = "vindex_auth_token";

  let apiBase = DEFAULT_API_BASE;
  let debounceTimer = null;
  let lastRequestedText = "";
  let inFlightController = null;

  // ── Token storage ────────────────────────────────────────────────────────

  function _hasOfficeRoaming() {
    return (
      typeof Office !== "undefined" &&
      Office.context &&
      Office.context.roamingSettings
    );
  }

  function getAuthToken() {
    if (_hasOfficeRoaming()) {
      return Office.context.roamingSettings.get(TOKEN_STORAGE_KEY) || null;
    }
    try {
      return global.localStorage ? global.localStorage.getItem(TOKEN_STORAGE_KEY) : null;
    } catch (e) {
      return null;
    }
  }

  function setAuthToken(token) {
    if (_hasOfficeRoaming()) {
      Office.context.roamingSettings.set(TOKEN_STORAGE_KEY, token);
      Office.context.roamingSettings.saveAsync();
      return;
    }
    try {
      if (global.localStorage) global.localStorage.setItem(TOKEN_STORAGE_KEY, token);
    } catch (e) {
      /* no-op — bez trajnog skladišta, korisnik se loguje svaki put */
    }
  }

  function clearAuthToken() {
    setAuthToken("");
  }

  // ── Konfiguracija ─────────────────────────────────────────────────────────

  function configure(options) {
    if (options && options.apiBase) {
      apiBase = options.apiBase.replace(/\/+$/, "");
    }
  }

  // ── Čitanje tekućeg pasusa iz Word dokumenta (Office.js) ────────────────────

  async function getCurrentParagraphText() {
    if (typeof Word === "undefined") {
      throw new Error("Word JS API nije dostupan (van Office okruženja?).");
    }
    return Word.run(async (context) => {
      const selection = context.document.getSelection();
      const paragraphs = selection.paragraphs;
      paragraphs.load("text");
      await context.sync();
      if (paragraphs.items.length > 0) {
        return paragraphs.items[paragraphs.items.length - 1].text || "";
      }
      return "";
    });
  }

  // ── Poziv ka Vindex API-ju ────────────────────────────────────────────────

  async function analyzeParagraph(tekst, { predmetId, tipDokumenta } = {}) {
    const token = getAuthToken();
    if (!token) {
      throw new Error("Niste prijavljeni u Vindex AI — otvorite taskpane i prijavite se.");
    }

    if (inFlightController) {
      inFlightController.abort();
    }
    inFlightController = typeof AbortController !== "undefined" ? new AbortController() : null;

    const resp = await fetch(apiBase + ANALYZE_PATH, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + token,
      },
      body: JSON.stringify({
        tekst: tekst,
        predmet_id: predmetId || null,
        tip_dokumenta: tipDokumenta || null,
      }),
      signal: inFlightController ? inFlightController.signal : undefined,
    });

    if (resp.status === 401) {
      throw new Error("Sesija je istekla — prijavite se ponovo.");
    }
    if (resp.status === 404) {
      throw new Error("Povezan predmet nije pronađen.");
    }
    if (resp.status === 429 || resp.status === 402) {
      throw new Error("Dostignut je dnevni limit za Ambient Copilot.");
    }
    if (!resp.ok) {
      throw new Error("Vindex API greška (" + resp.status + ").");
    }
    return resp.json(); // { sugestije: [...], trajanje_ms: N }
  }

  // ── Debounced "korisnik je pauzirao kucanje" tok ────────────────────────────
  //
  // onSuggestions(fn) — poziva se sa rezultatom svakog uspešnog poziva.
  // onError(fn) — poziva se sa Error objektom; NIKAD ne prekida tok (fail-
  // soft — jedna neuspela analiza ne sme da onemogući sledeću).

  function watchParagraphChanges({ onSuggestions, onError, predmetId, tipDokumenta } = {}) {
    async function _tick() {
      let tekst;
      try {
        tekst = await getCurrentParagraphText();
      } catch (e) {
        if (onError) onError(e);
        return;
      }

      const trimmed = (tekst || "").trim();
      if (trimmed.length < MIN_CHARS_TO_ANALYZE || trimmed === lastRequestedText) {
        return;
      }
      lastRequestedText = trimmed;

      try {
        const rezultat = await analyzeParagraph(trimmed, { predmetId, tipDokumenta });
        if (onSuggestions) onSuggestions(rezultat);
      } catch (e) {
        if (e && e.name === "AbortError") return; // zamenjeno novijim zahtevom -- ne prijavljuj kao grešku
        if (onError) onError(e);
      }
    }

    function scheduleTick() {
      if (debounceTimer) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(_tick, DEBOUNCE_MS);
    }

    if (typeof Office !== "undefined" && Office.context && Office.context.document) {
      Office.context.document.addHandlerAsync(
        Office.EventType.DocumentSelectionChanged,
        scheduleTick
      );
    }

    return {
      triggerNow: scheduleTick,
      stop: function () {
        if (debounceTimer) clearTimeout(debounceTimer);
        if (
          typeof Office !== "undefined" &&
          Office.context &&
          Office.context.document
        ) {
          Office.context.document.removeHandlerAsync(Office.EventType.DocumentSelectionChanged);
        }
      },
    };
  }

  const VindexAmbientAdapter = {
    configure,
    getAuthToken,
    setAuthToken,
    clearAuthToken,
    getCurrentParagraphText,
    analyzeParagraph,
    watchParagraphChanges,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = VindexAmbientAdapter;
  } else {
    global.VindexAmbientAdapter = VindexAmbientAdapter;
  }
})(typeof window !== "undefined" ? window : globalThis);
