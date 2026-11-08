(function () {
  "use strict";
  var challengeNonce = null;
  var client = null;
  var busy = false;
  var form = document.getElementById("login-form");
  var submitButton = document.getElementById("login-submit");
  var emailInput = document.getElementById("email");
  var passwordInput = document.getElementById("password");
  var statusNode = document.getElementById("auth-status");

  function setStatus(text, isError) {
    statusNode.textContent = text;
    statusNode.setAttribute("data-error", isError ? "true" : "false");
  }

  function failClosed(message) {
    submitButton.disabled = true;
    setStatus(message, true);
  }

  function sendReady() {
    try {
      Office.context.ui.messageParent("vindex-auth-ready", { targetOrigin: window.location.origin });
    } catch (error) {
      failClosed("Bezbedna veza sa Word dodatkom nije dostupna. Zatvorite prozor i pokušajte ponovo.");
    }
  }

  function acceptParentMessage(args) {
    if (!args || args.origin !== window.location.origin) {
      failClosed("Veza sa dodatkom nije potvrđena.");
      return;
    }
    var challenge;
    try { challenge = window.VindexWordAuthFlow.parseEnvelope(args.message); }
    catch (error) {
      failClosed("Nevažeća prijava. Zatvorite prozor i pokušajte ponovo.");
      return;
    }
    if (challenge.type !== "vindex-auth-challenge" ||
        typeof challenge.nonce !== "string" || !/^[a-f0-9]{64}$/.test(challenge.nonce) ||
        challengeNonce !== null) {
      failClosed("Nevažeća prijava. Zatvorite prozor i pokušajte ponovo.");
      return;
    }
    challengeNonce = challenge.nonce;
    submitButton.disabled = false;
    setStatus("Prijavite se svojim postojećim Vindex nalogom.", false);
  }

  async function onSubmit(event) {
    event.preventDefault();
    if (busy || !challengeNonce || !client) return;
    busy = true;
    submitButton.disabled = true;
    setStatus("Prijavljivanje…", false);
    var email = emailInput.value.trim();
    var password = passwordInput.value;
    passwordInput.value = "";
    try {
      if (!email || !password) throw new Error("missing_credentials");
      var result = await client.auth.signInWithPassword({ email:email, password:password });
      var accessToken = result && result.data && result.data.session ? result.data.session.access_token : null;
      if (result.error || typeof accessToken !== "string") throw new Error("authentication_failed");
      if (accessToken.length > 8192 ||
          !/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(accessToken)) {
        throw new Error("invalid_provider_session");
      }
      var message = JSON.stringify({ type:"vindex-auth-result", nonce:challengeNonce, access_token:accessToken });
      accessToken = "";
      Office.context.ui.messageParent(message, { targetOrigin:window.location.origin });
      message = "";
      setStatus("Prijava je potvrđena. Vratite se u Word.", false);
      form.hidden = true;
    } catch (error) {
      setStatus("Prijava nije uspela. Proverite podatke i pokušajte ponovo.", true);
      submitButton.disabled = false;
    } finally {
      password = "";
      busy = false;
    }
  }

  async function initialize() {
    var config = window.VindexAuthConfig;
    if (window.location.protocol !== "https:" || !config ||
        typeof config.supabaseUrl !== "string" || typeof config.supabaseAnonKey !== "string" ||
        !window.supabase || !window.VindexWordAuthFlow || typeof Office === "undefined" ||
        !Office.context || !Office.context.ui || !Office.context.requirements ||
        !Office.context.requirements.isSetSupported("DialogOrigin", "1.1")) {
      failClosed("Bezbedna prijava trenutno nije dostupna u ovom Word okruženju.");
      return;
    }
    client = window.supabase.createClient(config.supabaseUrl, config.supabaseAnonKey, {
      auth:{ persistSession:false, autoRefreshToken:false, detectSessionInUrl:false }
    });
    Office.context.ui.addHandlerAsync(
      Office.EventType.DialogParentMessageReceived,
      acceptParentMessage,
      function (result) {
        if (result.status !== Office.AsyncResultStatus.Succeeded) {
          failClosed("Bezbedna veza sa Word dodatkom nije dostupna.");
          return;
        }
        sendReady();
      }
    );
  }

  form.addEventListener("submit", onSubmit);
  if (typeof Office !== "undefined" && Office.onReady) {
    Office.onReady().then(initialize).catch(function () {
      failClosed("Bezbedna prijava trenutno nije dostupna u ovom Word okruženju.");
    });
  } else {
    failClosed("Ovaj prozor mora biti otvoren iz Microsoft Word-a.");
  }
})();