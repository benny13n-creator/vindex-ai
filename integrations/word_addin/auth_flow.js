(function (root) {
  "use strict";
  var JWT_PATTERN = /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/;
  var OPAQUE_SESSION_PATTERN = /^[A-Za-z0-9_-]{43}$/;

  function createNonce(cryptoApi) {
    var cryptoRef = cryptoApi || root.crypto;
    if (!cryptoRef || typeof cryptoRef.getRandomValues !== "function") throw new Error("secure_random_unavailable");
    var bytes = new Uint8Array(32);
    cryptoRef.getRandomValues(bytes);
    var output = "";
    for (var i = 0; i < bytes.length; i += 1) output += bytes[i].toString(16).padStart(2, "0");
    return output;
  }

  function isDialogSupported(office) {
    var req = office && office.context && office.context.requirements;
    return !!(req && typeof req.isSetSupported === "function" &&
      req.isSetSupported("DialogApi", "1.2") && req.isSetSupported("DialogOrigin", "1.1"));
  }

  function parseEnvelope(message) {
    if (typeof message !== "string" || message.length > 10000) throw new Error("invalid_dialog_message");
    var value;
    try { value = JSON.parse(message); } catch (error) { throw new Error("invalid_dialog_message"); }
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("invalid_dialog_message");
    return value;
  }

  function parseAuthResult(message, actualOrigin, expectedOrigin, expectedNonce) {
    if (!expectedOrigin || actualOrigin !== expectedOrigin) throw new Error("invalid_callback_origin");
    var value = parseEnvelope(message);
    if (value.type !== "vindex-auth-result" || value.nonce !== expectedNonce ||
        typeof value.access_token !== "string" || value.access_token.length > 8192 ||
        !JWT_PATTERN.test(value.access_token)) throw new Error("invalid_auth_callback");
    return value.access_token;
  }

  function isOpaqueSessionToken(value) {
    return typeof value === "string" && OPAQUE_SESSION_PATTERN.test(value);
  }

  var api = { createNonce:createNonce, isDialogSupported:isDialogSupported, parseEnvelope:parseEnvelope,
    parseAuthResult:parseAuthResult, isOpaqueSessionToken:isOpaqueSessionToken };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.VindexWordAuthFlow = api;
})(typeof window !== "undefined" ? window : globalThis);