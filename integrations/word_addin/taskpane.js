(function () {
  "use strict";
  var SESSION_PATH = "/api/word/sessions";
  var ANALYSIS_PATH = "/api/word/analyze";
  var REWRITE_PATH = "/api/word/rewrite";
  var MATTERS_PATH = "/api/word/matters";
  var loginView = document.getElementById("login-view");
  var sessionView = document.getElementById("session-view");
  var loginButton = document.getElementById("login-button");
  var logoutButton = document.getElementById("logout-button");
  var retryLogoutButton = document.getElementById("retry-logout-button");
  var analyzeButton = document.getElementById("analyze-button");
  var rewriteButton = document.getElementById("rewrite-button");
  var rewriteAvailability = document.getElementById("rewrite-availability");
  var proposalView = document.getElementById("proposal-view");
  var proposalOriginal = document.getElementById("proposal-original");
  var proposalText = document.getElementById("proposal-text");
  var applyRewriteButton = document.getElementById("apply-rewrite-button");
  var cancelRewriteButton = document.getElementById("cancel-rewrite-button");
  var matterSelect = document.getElementById("matter-select");
  var resultsNode = document.getElementById("analysis-results");
  var statusNode = document.getElementById("status");
  var sessionToken = null;
  var pendingRevokeToken = null;
  var sessionExpiryTimer = null;
  var dialog = null;
  var generation = 0;
  var analysisGeneration = 0;
  var loginInProgress = false;
  var analysisInProgress = false;
  var analysisAbortController = null;
  var rewriteGeneration = 0;
  var rewriteInProgress = false;
  var rewriteApplying = false;
  var rewriteAbortController = null;
  var pendingProposal = null;
  var proposalCounter = 0;
  var selectedMatterId = "";
  var matterListGeneration = 0;
  var MAX_SELECTED_TEXT_CHARS = 4000;

  function setStatus(message, isError) {
    statusNode.textContent = message || "";
    statusNode.setAttribute("data-error", isError ? "true" : "false");
  }

  function showSession(authenticated) {
    loginView.classList.toggle("active", !authenticated);
    sessionView.classList.toggle("active", !!authenticated);
    updateActionButtons();
    matterSelect.disabled = !authenticated;
  }

  function updateActionButtons() {
    var busy = analysisInProgress || rewriteInProgress || rewriteApplying;
    var safeRewriteAvailable = window.VindexAmbientAdapter.supportsSafeRewrite(window.Word);
    analyzeButton.disabled = !sessionToken || busy;
    rewriteButton.disabled = !sessionToken || busy || !safeRewriteAvailable;
    rewriteAvailability.textContent = safeRewriteAvailable ?
      "Predlog ćete pregledati pre primene; Word se menja tek kada to izričito odobrite." :
      "Ovo Word okruženje ne može bezbedno da proveri opseg izmene; predlog nije dostupan.";
  }

  function clearProposal() {
    pendingProposal = null;
    proposalOriginal.textContent = "";
    proposalText.textContent = "";
    proposalView.hidden = true;
    applyRewriteButton.disabled = true;
    cancelRewriteButton.disabled = false;
    updateActionButtons();
  }

  function cancelRewrite() {
    rewriteGeneration += 1;
    if (rewriteAbortController) {
      try { rewriteAbortController.abort(); } catch (error) { /* request already settled */ }
    }
    rewriteAbortController = null;
    rewriteInProgress = false;
    if (!rewriteApplying) clearProposal();
    updateActionButtons();
  }

  function clearResults() {
    resultsNode.textContent = "";
    clearProposal();
  }

  function clearMatterOptions() {
    selectedMatterId = "";
    matterListGeneration += 1;
    matterSelect.textContent = "";
    var publicOnly = document.createElement("option");
    publicOnly.value = "";
    publicOnly.textContent = "Bez predmeta — samo javni pravni izvori";
    matterSelect.appendChild(publicOnly);
    matterSelect.value = "";
    matterSelect.disabled = !sessionToken;
  }

  async function loadMatters() {
    var token = sessionToken;
    var sessionAttempt = generation;
    if (!token) return;
    clearMatterOptions();
    var listAttempt = ++matterListGeneration;
    matterSelect.disabled = true;
    var controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    var timer = setTimeout(function () {
      if (controller) controller.abort();
    }, 5000);
    try {
      var options = {
        method:"GET",
        headers:{ Authorization:"Bearer " + token },
        credentials:"same-origin",
        cache:"no-store"
      };
      if (controller) options.signal = controller.signal;
      var response = await fetch(MATTERS_PATH, options);
      if (listAttempt !== matterListGeneration || sessionAttempt !== generation || token !== sessionToken) return;
      if (response.status === 401) {
        expireSession();
        return;
      }
      if (!response.ok) throw new Error("matter_list_failed");
      var body = await response.json();
      if (listAttempt !== matterListGeneration || sessionAttempt !== generation || token !== sessionToken) return;
      if (!body || !Array.isArray(body.predmeti)) throw new Error("invalid_matter_list");
      clearMatterOptions();
      body.predmeti.forEach(function (matter) {
        if (!matter || typeof matter.id !== "string" || !matter.id || typeof matter.naziv !== "string") return;
        var option = document.createElement("option");
        option.value = matter.id;
        option.textContent = matter.naziv;
        matterSelect.appendChild(option);
      });
      matterSelect.value = "";
      matterSelect.disabled = false;
      setStatus(body.predmeti.length ?
        "Prijava je završena. Predmet birate samo ako želite njegov poverljivi kontekst." :
        "Prijava je završena. Dostupan je režim bez poverljivog konteksta predmeta.", false);
    } catch (error) {
      if (listAttempt !== matterListGeneration || sessionAttempt !== generation || token !== sessionToken) return;
      clearMatterOptions();
      matterSelect.disabled = false;
      setStatus("Predmeti nisu dostupni. Analiza će koristiti samo javne pravne izvore.", false);
    } finally {
      clearTimeout(timer);
    }
  }

  function expireSession() {
    generation += 1;
    cancelAnalysis();
    cancelRewrite();
    sessionToken = null;
    clearMatterOptions();
    showSession(false);
    loginButton.disabled = !!pendingRevokeToken;
    setStatus("Sesija je istekla. Prijavite se ponovo.", false);
  }

  function matterChanged() {
    var nextMatterId = typeof matterSelect.value === "string" ? matterSelect.value : "";
    if (nextMatterId === selectedMatterId) return;
    selectedMatterId = nextMatterId;
    cancelRewrite();
    cancelAnalysis();
    setStatus(selectedMatterId ?
      "Predmet je promenjen. Stari rezultati su uklonjeni." :
      "Analiza će koristiti javne pravne izvore bez poverljivog konteksta.", false);
  }

  function cancelAnalysis() {
    analysisGeneration += 1;
    if (analysisAbortController) {
      try { analysisAbortController.abort(); } catch (error) { /* request already settled */ }
    }
    analysisAbortController = null;
    analysisInProgress = false;
    updateActionButtons();
    clearResults();
  }

  function getTrustedOrigin() {
    if (window.location.protocol !== "https:" &&
        window.location.hostname !== "localhost" &&
        window.location.hostname !== "127.0.0.1") throw new Error("insecure_origin");
    return window.location.origin;
  }

  function closeDialog() {
    if (!dialog) return;
    var current = dialog;
    dialog = null;
    try { current.close(); } catch (error) { /* dialog is already closed */ }
  }

  function openSignInDialog() {
    var office = window.Office;
    var origin = getTrustedOrigin();
    if (!window.VindexWordAuthFlow.isDialogSupported(office)) {
      return Promise.reject(new Error("dialog_requirement_unavailable"));
    }
    var nonce = window.VindexWordAuthFlow.createNonce(window.crypto);
    var settled = false;
    var challenged = false;

    return new Promise(function (resolve, reject) {
      var timer = setTimeout(function () { finish(new Error("dialog_timeout")); }, 300000);
      function finish(error, token) {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        closeDialog();
        if (error) reject(error);
        else resolve(token);
      }

      try {
        office.context.ui.displayDialogAsync(origin + "/word_addin/auth.html",
          { height:58, width:42 }, function (result) {
            if (!result || result.status !== office.AsyncResultStatus.Succeeded || !result.value) {
              finish(new Error("dialog_open_failed"));
              return;
            }
            dialog = result.value;
            try {
              dialog.addEventHandler(office.EventType.DialogMessageReceived, function (args) {
                if (!args || args.origin !== origin) {
                  finish(new Error("invalid_callback_origin"));
                  return;
                }
                if (args.message === "vindex-auth-ready") {
                  if (challenged) {
                    finish(new Error("duplicate_dialog_ready"));
                    return;
                  }
                  challenged = true;
                  try {
                    dialog.messageChild(JSON.stringify({ type:"vindex-auth-challenge", nonce:nonce }),
                      { targetOrigin:origin });
                  } catch (error) { finish(new Error("challenge_delivery_failed")); }
                  return;
                }
                try {
                  var accessToken = window.VindexWordAuthFlow.parseAuthResult(
                    args.message, args.origin, origin, nonce);
                  finish(null, accessToken);
                } catch (error) { finish(error); }
              });
              dialog.addEventHandler(office.EventType.DialogEventReceived, function () {
                finish(new Error("dialog_closed"));
              });
            } catch (error) { finish(new Error("dialog_handler_unavailable")); }
          });
      } catch (error) { finish(new Error("dialog_open_failed")); }
    });
  }

  async function revokeOpaqueToken(token) {
    if (!token) return true;
    try {
      var response = await fetch(SESSION_PATH + "/current", {
        method:"DELETE",
        headers:{ Authorization:"Bearer " + token },
        credentials:"same-origin",
        cache:"no-store",
        keepalive:true
      });
      return response.ok || response.status === 401;
    } catch (error) { return false; }
  }

  function armExpiry(expiresAt) {
    if (sessionExpiryTimer) clearTimeout(sessionExpiryTimer);
    var delay = Math.max(0, expiresAt - Date.now());
    sessionExpiryTimer = setTimeout(function () {
      generation += 1;
      cancelAnalysis();
      cancelRewrite();
      sessionToken = null;
      sessionExpiryTimer = null;
      clearMatterOptions();
      showSession(false);
      loginButton.disabled = !!pendingRevokeToken;
      setStatus("Sesija je istekla. Prijavite se ponovo.", false);
    }, delay);
  }

  async function exchangeSourceToken(sourceToken, attempt) {
    var pendingResponse = fetch(SESSION_PATH, {
      method:"POST",
      headers:{ Authorization:"Bearer " + sourceToken },
      credentials:"same-origin",
      cache:"no-store"
    });
    sourceToken = "";
    var response = await pendingResponse;
    if (!response.ok) throw new Error("session_exchange_failed");
    var body = await response.json();
    if (!body || !window.VindexWordAuthFlow.isOpaqueSessionToken(body.session_token) ||
        typeof body.expires_at !== "string" || !Number.isFinite(Date.parse(body.expires_at)) ||
        Date.parse(body.expires_at) <= Date.now()) throw new Error("invalid_session_response");

    if (attempt !== generation) {
      var revoked = await revokeOpaqueToken(body.session_token);
      if (!revoked) {
        pendingRevokeToken = body.session_token;
        retryLogoutButton.hidden = false;
        loginButton.disabled = true;
      }
      body.session_token = "";
      return;
    }

    sessionToken = body.session_token;
    body.session_token = "";
    showSession(true);
    armExpiry(Date.parse(body.expires_at));
    await loadMatters();
  }

  async function login() {
    if (loginInProgress || sessionToken || pendingRevokeToken) return;
    loginInProgress = true;
    loginButton.disabled = true;
    setStatus("Otvara se bezbedan prozor za prijavu…", false);
    var attempt = ++generation;
    var accessToken = "";
    try {
      accessToken = await openSignInDialog();
      if (attempt !== generation) return;
      var exchange = exchangeSourceToken(accessToken, attempt);
      accessToken = "";
      await exchange;
    } catch (error) {
      if (attempt === generation) setStatus("Prijava nije uspela. Pokušajte ponovo.", true);
    } finally {
      accessToken = "";
      loginInProgress = false;
      if (attempt === generation && !pendingRevokeToken) loginButton.disabled = false;
    }
  }

  function countCodePoints(value) {
    return Array.from(value).length;
  }

  function describeAnalysisError(status) {
    if (status === 401) return "Sesija je istekla. Prijavite se ponovo.";
    if (status === 402 || status === 429) return "Dostignut je limit za AI funkcije. Pokušajte kasnije.";
    if (status === 413 || status === 422) return "Izaberite kraći tekst koji nije prazan.";
    if (status === 503) return "Vindex trenutno ne može da završi analizu.";
    return "Analiza nije uspela. Pokušajte ponovo.";
  }

  function displaySuggestions(body) {
    if (!body || !Array.isArray(body.sugestije)) throw new Error("invalid_analysis_response");
    if (body.sugestije.length === 0) {
      resultsNode.textContent = "Nema predloga za ovaj izbor.";
      return;
    }

    resultsNode.textContent = body.sugestije.map(function (item) {
      var lines = [];
      lines.push(item && typeof item.tekst === "string" ? item.tekst : "Predlog nije dostupan.");
      if (item && typeof item.izvor === "string" && item.izvor) {
        lines.push("Navedeni izvor: " + item.izvor);
      }
      if (item && item.verification_status === "verified_identity") {
        lines.push("Identitet citata odgovara Vindex zapisu. Da li odlomak potkrepljuje predlog nije nezavisno provereno.");
      } else if (item && item.verification_status === "source_outdated") {
        lines.push("Identitet citata odgovara Vindex zapisu, ali zapis je označen kao zastareo. Potkrepljenost predloga nije proverena.");
      } else if (item && item.verification_status === "source_unavailable") {
        lines.push("Izvor trenutno nije dostupan za proveru. Predlog i citat nisu nezavisno provereni.");
      } else if (item && item.verification_status === "source_not_found") {
        lines.push("U pretraženim Vindex zapisima nije pronađen odgovarajući izvor. Citat nije nezavisno proveren.");
      } else if (item && item.verification_status === "unverified") {
        lines.push("Izvor nije nezavisno proveren. Citat se ne podudara sa strukturiranim zapisom ili identitet nije potpun; potkrepljenost predloga takođe nije proverena.");
      } else if (item && item.verification_status === "not_applicable") {
        lines.push("Ova napomena nije pravni izvor.");
      } else {
        lines.push("Status pravnog izvora nije potvrđen.");
      }
      if (item && item.claim_support_status === "unverified" && item.verification_status === "verified_identity") {
        lines.push("Vindex proverava samo identitet zapisa, ne pravnu ispravnost ili potkrepljenost tvrdnje.");
      }
      (item && Array.isArray(item.sources) ? item.sources : []).slice(0, 3).forEach(function (source) {
        if (!source || typeof source !== "object") return;
        lines.push(source.identity_match ? "Vindex pronađeni izvor:" : "Mogući Vindex izvor — citat nije usklađen:");
        if (typeof source.title === "string" && source.title) lines.push("Naslov: " + source.title);
        if (typeof source.identifier === "string" && source.identifier) lines.push("Identifikator: " + source.identifier);
        if (typeof source.court === "string" && source.court) lines.push("Sud: " + source.court);
        if (typeof source.decision_date === "string" && source.decision_date) lines.push("Datum odluke: " + source.decision_date);
        if (typeof source.locator === "string" && source.locator) lines.push("Mesto u izvoru: " + source.locator);
        if (typeof source.excerpt === "string" && source.excerpt) lines.push("Odlomak: " + source.excerpt);
        if (typeof source.source_url === "string" && source.source_url) lines.push("Adresa izvora iz Vindex zapisa: " + source.source_url);
        if (source.kind === "clan_zakona") {
          lines.push(source.version_status === "outdated" ?
            "Važenje/verzija: Vindex zapis je označen kao zastareo." :
            "Važenje/verzija: nije potvrđeno iz dostupnih metapodataka.");
        }
      });
      return lines.join("\n");
    }).join("\n\n");
  }

  function sameSelectionSnapshot(left, right) {
    return !!left && !!right && left.text === right.text &&
      left.start === right.start && left.end === right.end &&
      left.storyType === right.storyType;
  }

  function describeRewriteError(error) {
    if (error && error.message === "word_selection_stale") return "Izbor ili tekst se promenio. Predlog nije primenjen; zatražite novi predlog za trenutni izbor.";
    if (error && error.message === "word_rewrite_capability_unavailable") return "Ovaj Word host ne može bezbedno da proveri opseg izmene.";
    if (error && /^word_(?:table|content_control|field|numbered|notes|tracked_changes|revisions|format|story|multiline)_/.test(error.message || "")) {
      return "Izabrani opseg sadrži formatiranje ili strukturu koju ova verzija dodatka ne menja. Dokument nije izmenjen.";
    }
    if (error && error.message === "word_rewrite_already_applied") return "Ovaj predlog je već primenjen ili se njegova izmena još proverava.";
    return "Word nije mogao da potvrdi izmenu. Proverite dokument pre bilo kakvog novog pokušaja.";
  }

  async function requestRewriteProposal() {
    if (!sessionToken || analysisInProgress || rewriteInProgress || rewriteApplying ||
        !window.VindexAmbientAdapter.supportsSafeRewrite(window.Word)) return;
    clearProposal();
    rewriteInProgress = true;
    var attempt = ++rewriteGeneration;
    var requestGeneration = generation;
    var requestToken = sessionToken;
    var controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    rewriteAbortController = controller;
    var timer = setTimeout(function () {
      if (controller) controller.abort();
    }, 15000);
    updateActionButtons();
    setStatus("Proverava se izabrani opseg pre pripreme predloga…", false);

    try {
      var snapshot = await window.VindexAmbientAdapter.readSelectionSnapshot(window.Word);
      if (attempt !== rewriteGeneration || requestGeneration !== generation || requestToken !== sessionToken) return;
      if (!snapshot.text.trim()) {
        setStatus("Izaberite tekst u dokumentu pre nego što zatražite formulaciju.", true);
        return;
      }
      if (countCodePoints(snapshot.text) > MAX_SELECTED_TEXT_CHARS) {
        setStatus("Izbor je duži od dozvoljenih 4.000 znakova. Skratite izbor i pokušajte ponovo.", true);
        return;
      }
      if (snapshot.storyType !== "MainText" || /[\r\n\t\u000b]/.test(snapshot.text)) {
        setStatus("Izaberite tekst iz jednog običnog pasusa glavnog dokumenta.", true);
        return;
      }

      var options = {
        method:"POST",
        headers:{
          Authorization:"Bearer " + requestToken,
          "Content-Type":"application/json"
        },
        credentials:"same-origin",
        cache:"no-store",
        body:JSON.stringify({ text:snapshot.text })
      };
      if (controller) options.signal = controller.signal;
      setStatus("Šalje se samo izabrani tekst. Priprema se predlog bez izmene dokumenta…", false);
      var response = await fetch(REWRITE_PATH, options);
      if (attempt !== rewriteGeneration || requestGeneration !== generation || requestToken !== sessionToken) return;
      if (!response.ok) {
        if (response.status === 401) expireSession();
        setStatus(describeAnalysisError(response.status), true);
        return;
      }
      var body = await response.json();
      if (attempt !== rewriteGeneration || requestGeneration !== generation || requestToken !== sessionToken) return;
      if (!body || body.original_text !== snapshot.text || typeof body.proposal_text !== "string" ||
          !body.proposal_text.trim() || body.proposal_text.length > MAX_SELECTED_TEXT_CHARS ||
          body.document_changed !== false) throw new Error("invalid_rewrite_response");

      var currentSnapshot = await window.VindexAmbientAdapter.readSelectionSnapshot(window.Word);
      if (attempt !== rewriteGeneration || requestGeneration !== generation || requestToken !== sessionToken) return;
      if (!sameSelectionSnapshot(snapshot, currentSnapshot)) {
        setStatus("Izbor ili tekst se promenio tokom pripreme. Predlog je odbačen; dokument nije izmenjen.", true);
        return;
      }

      snapshot.operationId = "word-proposal-" + (++proposalCounter);
      pendingProposal = {
        snapshot:snapshot,
        originalText:snapshot.text,
        proposalText:body.proposal_text.trim(),
        requestToken:requestToken,
        requestGeneration:requestGeneration
      };
      proposalOriginal.textContent = pendingProposal.originalText;
      proposalText.textContent = pendingProposal.proposalText;
      proposalView.hidden = false;
      applyRewriteButton.disabled = false;
      cancelRewriteButton.disabled = false;
      setStatus("Predlog je spreman za pregled. Word dokument još nije promenjen.", false);
    } catch (error) {
      if (attempt !== rewriteGeneration || requestGeneration !== generation || requestToken !== sessionToken) return;
      if (error && error.name === "AbortError") {
        setStatus("Priprema predloga je otkazana. Dokument nije izmenjen.", false);
      } else {
        setStatus("Predlog nije mogao biti pripremljen. Dokument nije izmenjen.", true);
      }
    } finally {
      clearTimeout(timer);
      if (attempt === rewriteGeneration) {
        rewriteAbortController = null;
        rewriteInProgress = false;
        updateActionButtons();
      }
    }
  }

  function cancelRewriteProposal() {
    if (rewriteApplying) return;
    clearProposal();
    setStatus("Predlog je otkazan. Word dokument nije promenjen.", false);
  }

  async function applyRewriteProposal() {
    if (!pendingProposal || rewriteApplying || !sessionToken) return;
    var proposal = pendingProposal;
    if (proposal.requestToken !== sessionToken || proposal.requestGeneration !== generation) {
      clearProposal();
      setStatus("Sesija je promenjena. Zatražite novi predlog.", true);
      return;
    }
    rewriteApplying = true;
    applyRewriteButton.disabled = true;
    cancelRewriteButton.disabled = true;
    updateActionButtons();
    setStatus("Proverava se isti Word opseg pre primene…", false);
    try {
      await window.VindexAmbientAdapter.applyApprovedRewrite(
        proposal.snapshot,
        proposal.proposalText,
        window.Word
      );
      clearProposal();
      setStatus("Predlog je primenjen na izabrani tekst. Word Undo može da vrati izmenu.", false);
    } catch (error) {
      clearProposal();
      setStatus(describeRewriteError(error), true);
    } finally {
      rewriteApplying = false;
      updateActionButtons();
    }
  }

  async function analyzeSelection() {
    if (!sessionToken || analysisInProgress || rewriteInProgress || rewriteApplying) return;
    clearResults();
    analysisInProgress = true;
    updateActionButtons();
    var attempt = ++analysisGeneration;
    var requestToken = sessionToken;
    var requestMatterId = selectedMatterId;
    setStatus("Proverava se izabrani tekst…", false);

    try {
      var selectedText = await window.VindexAmbientAdapter.readSelectedText(window.Word);
      if (attempt !== analysisGeneration || requestToken !== sessionToken || requestMatterId !== selectedMatterId) return;
      if (!selectedText.trim()) {
        setStatus("Izaberite tekst u dokumentu pre analize.", true);
        return;
      }
      if (countCodePoints(selectedText) > MAX_SELECTED_TEXT_CHARS) {
        setStatus("Izbor je duži od dozvoljenih 4.000 znakova. Skratite izbor i pokušajte ponovo.", true);
        return;
      }

      var controller = typeof AbortController !== "undefined" ? new AbortController() : null;
      analysisAbortController = controller;
      setStatus("Šalje se samo izabrani tekst. Analiza je u toku…", false);
      var payload = { text:selectedText };
      if (requestMatterId) payload.predmet_id = requestMatterId;
      var options = {
        method:"POST",
        headers:{
          Authorization:"Bearer " + requestToken,
          "Content-Type":"application/json"
        },
        credentials:"same-origin",
        cache:"no-store",
        body:JSON.stringify(payload)
      };
      if (controller) options.signal = controller.signal;
      var response = await fetch(ANALYSIS_PATH, options);
      if (attempt !== analysisGeneration || requestToken !== sessionToken || requestMatterId !== selectedMatterId) return;
      if (!response.ok) {
        if (response.status === 401) expireSession();
        setStatus(describeAnalysisError(response.status), true);
        return;
      }

      var body = await response.json();
      if (attempt !== analysisGeneration || requestToken !== sessionToken || requestMatterId !== selectedMatterId) return;
      var currentSelection = await window.VindexAmbientAdapter.readSelectedText(window.Word);
      if (attempt !== analysisGeneration || requestToken !== sessionToken || requestMatterId !== selectedMatterId) return;
      if (currentSelection !== selectedText) {
        clearResults();
        setStatus("Izbor se promenio tokom analize. Izaberite tekst i pokušajte ponovo.", true);
        return;
      }
      displaySuggestions(body);
      setStatus("Analiza je završena. Pregledajte izvor pre nego što se oslonite na predlog.", false);
    } catch (error) {
      if (attempt !== analysisGeneration || requestToken !== sessionToken) return;
      if (error && error.name === "AbortError") return;
      setStatus("Analiza nije uspela. Proverite dokument i pokušajte ponovo.", true);
    } finally {
      if (attempt === analysisGeneration) {
        analysisAbortController = null;
        analysisInProgress = false;
        updateActionButtons();
      }
    }
  }

  async function retryRevoke() {
    if (!pendingRevokeToken) {
      retryLogoutButton.hidden = true;
      loginButton.disabled = false;
      return;
    }
    retryLogoutButton.disabled = true;
    var revoked = await revokeOpaqueToken(pendingRevokeToken);
    retryLogoutButton.disabled = false;
    if (revoked) {
      pendingRevokeToken = null;
      retryLogoutButton.hidden = true;
      loginButton.disabled = false;
      setStatus("Odjava je potvrđena.", false);
    } else {
      retryLogoutButton.hidden = false;
      loginButton.disabled = true;
      setStatus("Server nije potvrdio odjavu. Pokušajte ponovo.", true);
    }
  }

  async function logout() {
    generation += 1;
    cancelAnalysis();
    cancelRewrite();
    closeDialog();
    if (sessionExpiryTimer) clearTimeout(sessionExpiryTimer);
    sessionExpiryTimer = null;
    var token = sessionToken;
    sessionToken = null;
    clearMatterOptions();
    showSession(false);
    loginButton.disabled = true;
    setStatus("Završava se Word sesija…", false);
    if (token) pendingRevokeToken = token;
    await retryRevoke();
    if (!pendingRevokeToken) setStatus("Odjavljeni ste.", false);
  }

  async function initialize() {
    try { await window.VindexAmbientAdapter.clearLegacyAuthToken(); }
    catch (error) {
      loginButton.disabled = true;
      setStatus("Stara prijava nije mogla biti uklonjena. Zatvorite dodatak i pokušajte ponovo.", true);
      return;
    }

    showSession(false);
    if (typeof Office === "undefined" || !Office.context || !Office.context.ui) {
      loginButton.disabled = true;
      setStatus("Otvorite Vindex AI iz Microsoft Word-a.", true);
      return;
    }
    if (!window.Word || typeof window.Word.run !== "function") {
      loginButton.disabled = true;
      setStatus("Ovaj Word host ne podržava čitanje izbora.", true);
      return;
    }
    if (!window.VindexWordAuthFlow.isDialogSupported(Office)) {
      loginButton.disabled = true;
      setStatus("Ovo Word okruženje ne podržava bezbednu prijavu.", true);
      return;
    }
    try { getTrustedOrigin(); }
    catch (error) {
      loginButton.disabled = true;
      setStatus("Bezbedna prijava zahteva HTTPS vezu.", true);
      return;
    }
    loginButton.disabled = false;
    analyzeButton.disabled = true;
    setStatus("", false);
  }

  loginButton.addEventListener("click", login);
  logoutButton.addEventListener("click", logout);
  retryLogoutButton.addEventListener("click", retryRevoke);
  analyzeButton.addEventListener("click", analyzeSelection);
  rewriteButton.addEventListener("click", requestRewriteProposal);
  applyRewriteButton.addEventListener("click", applyRewriteProposal);
  cancelRewriteButton.addEventListener("click", cancelRewriteProposal);
  matterSelect.addEventListener("change", matterChanged);
  if (typeof Office !== "undefined" && Office.onReady) {
    Office.onReady().then(initialize).catch(function () { setStatus("Microsoft Word nije spreman.", true); });
  } else initialize();

  window.addEventListener("pagehide", function () {
    generation += 1;
    cancelAnalysis();
    cancelRewrite();
    if (sessionExpiryTimer) clearTimeout(sessionExpiryTimer);
    if (sessionToken) {
      fetch(SESSION_PATH + "/current", {
        method:"DELETE",
        headers:{ Authorization:"Bearer " + sessionToken },
        credentials:"same-origin",
        cache:"no-store",
        keepalive:true
      }).catch(function () {});
    }
    closeDialog();
    sessionToken = null;
    clearMatterOptions();
    pendingRevokeToken = null;
  });
})();
