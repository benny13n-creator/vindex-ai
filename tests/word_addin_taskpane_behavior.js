"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const source = fs.readFileSync(path.join(root, "integrations/word_addin/taskpane.js"), "utf8");
let paneId = 0;

function createElement(id) {
  const handlers = {};
  const classes = new Set();
  const children = [];
  let textContent = "";
  const element = {
    id,
    handlers,
    disabled: false,
    hidden: false,
    attributes: {},
    children,
    get options() { return children; },
    appendChild(child) { children.push(child); return child; },
    classList: {
      toggle(name, enabled) {
        if (enabled) classes.add(name);
        else classes.delete(name);
      },
      contains(name) { return classes.has(name); }
    },
    addEventListener(name, handler) { handlers[name] = handler; },
    setAttribute(name, value) { this.attributes[name] = value; }
  };
  Object.defineProperty(element, "textContent", {
    get() { return textContent; },
    set(value) {
      textContent = String(value);
      if (id === "matter-select") children.length = 0;
    }
  });
  return element;
}

function makePane(initialSelection = "Selected test sentence.", safeRewrite = true) {
  const id = ++paneId;
  const names = ["login-view", "session-view", "login-button", "logout-button", "retry-logout-button", "analyze-button", "rewrite-button", "rewrite-availability", "proposal-view", "proposal-original", "proposal-text", "apply-rewrite-button", "cancel-rewrite-button", "matter-select", "analysis-results", "status"];
  const elements = Object.fromEntries(names.map(name => [name, createElement(name)]));
  const posts = [];
  const calls = [];
  const analysisCalls = [];
  const rewriteCalls = [];
  const applyCalls = [];
  const pendingAnalysis = [];
  const pendingRewrite = [];
  let currentSelection = initialSelection;
  let currentPosition = 10;
  const timers = [];
  let dialogCount = 0;
  const origin = "https://vindex.test";

  const Office = {
    AsyncResultStatus: { Succeeded: "succeeded" },
    EventType: { DialogMessageReceived: "dialog-message", DialogEventReceived: "dialog-event" },
    context: {
      requirements: { isSetSupported: () => true },
      document: { getSelection() { return { text:currentSelection, load() {} }; } },
      sync() { return Promise.resolve(); },
      ui: {
        displayDialogAsync(url, options, callback) {
          dialogCount += 1;
          assert.equal(url, origin + "/word_addin/auth.html");
          assert.equal(options.targetOrigin, undefined);
          let messageHandler;
          const dialog = {
            addEventHandler(type, handler) {
              if (type === Office.EventType.DialogMessageReceived) messageHandler = handler;
            },
            messageChild(message, messageOptions) {
              assert.equal(messageOptions.targetOrigin, origin);
              const challenge = JSON.parse(message);
              messageHandler({
                origin,
                message: JSON.stringify({
                  type: "vindex-auth-result",
                  nonce: challenge.nonce,
                  access_token: "source.jwt.signature"
                })
              });
            },
            close() {}
          };
          callback({ status: "succeeded", value: dialog });
          messageHandler({ origin, message: "vindex-auth-ready" });
        }
      }
    },
    onReady() { return Promise.resolve(); }
  };

  const window = {
    Office,
    location: { protocol: "https:", hostname: "vindex.test", origin },
    crypto: { getRandomValues(bytes) { bytes.fill(id); return bytes; } },
    VindexWordAuthFlow: {
      isDialogSupported() { return true; },
      createNonce(cryptoApi) {
        const bytes = new Uint8Array(32);
        cryptoApi.getRandomValues(bytes);
        return Array.from(bytes, value => value.toString(16).padStart(2, "0")).join("");
      },
      parseAuthResult(message, actualOrigin, expectedOrigin, nonce) {
        assert.equal(actualOrigin, expectedOrigin);
        const value = JSON.parse(message);
        assert.equal(value.nonce, nonce);
        return value.access_token;
      },
      isOpaqueSessionToken(value) { return typeof value === "string" && /^[A-Za-z0-9_-]{43}$/.test(value); }
    },
    VindexAmbientAdapter: {
      clearLegacyAuthToken: () => Promise.resolve(),
      readSelectedText: async () => currentSelection,
      supportsSafeRewrite: () => safeRewrite,
      readSelectionSnapshot: async () => ({
        text:currentSelection,
        start:currentPosition,
        end:currentPosition + currentSelection.length,
        storyType:"MainText"
      }),
      async applyApprovedRewrite(snapshot, replacement) {
        applyCalls.push({ snapshot, replacement });
        if (snapshot.text !== currentSelection || snapshot.start !== currentPosition) {
          throw new Error("word_selection_stale");
        }
        currentSelection = replacement;
        return { applied:true };
      }
    },
    Word:{},
    addEventListener() {}
  };

  function fakeFetch(url, options) {
    calls.push({ url, options });
    if (options.method === "GET" && url === "/api/word/matters") {
      return Promise.resolve({
        ok:true, status:200,
        async json() { return { predmeti:[{ id:"matter-1", naziv:"Predmet 1" }, { id:"matter-2", naziv:"Predmet 2" }] }; }
      });
    }
    if (options.method === "POST" && url === "/api/word/sessions") {
      return new Promise(resolve => posts.push({ resolve, options }));
    }
    if (options.method === "POST" && url === "/api/word/analyze") {
      analysisCalls.push({ url, options });
      return new Promise(resolve => pendingAnalysis.push({ resolve, options }));
    }
    if (options.method === "POST" && url === "/api/word/rewrite") {
      rewriteCalls.push({ url, options });
      return new Promise(resolve => pendingRewrite.push({ resolve, options }));
    }
    if (options.method === "DELETE") return Promise.resolve({ ok: true, status: 200 });
    throw new Error("unexpected request");
  }
  const document = {
    getElementById(id) { return elements[id]; },
    createElement(tag) { return { tag, value:"", textContent:"" }; }
  };
  const context = {
    window, document, Office, fetch: fakeFetch, AbortController,
    setTimeout(callback, delay) { timers.push({ callback, delay }); return timers.length; },
    clearTimeout() {},
    console
  };
  vm.runInNewContext(source, context, { filename: "taskpane.js" });

  return {
    elements,
    posts,
    calls,
    analysisCalls,
    rewriteCalls,
    applyCalls,
    pendingAnalysis,
    pendingRewrite,
    timers,
    get dialogCount() { return dialogCount; },
    async ready() { await new Promise(resolve => setImmediate(resolve)); },
    setSelection(text) { currentSelection = text; },
    setSelectionPosition(position) { currentPosition = position; },
    resolveAnalysis(index, body, status = 200) {
      pendingAnalysis[index].resolve({
        ok: status >= 200 && status < 300,
        status,
        async json() { return body; }
      });
    },
    resolveRewrite(index, body, status = 200) {
      pendingRewrite[index].resolve({
        ok: status >= 200 && status < 300,
        status,
        async json() { return body; }
      });
    },
    resolvePost(index, token) {
      posts[index].resolve({
        ok: true,
        status: 200,
        async json() {
          return { session_token: token, expires_at: new Date(Date.now() + 60000).toISOString() };
        }
      });
    }
  };
}

async function waitFor(test, label) {
  for (let i = 0; i < 20; i += 1) {
    if (test()) return;
    await new Promise(resolve => setImmediate(resolve));
  }
  assert.fail("timed out waiting for " + label);
}

async function main() {
  const unsupportedHost = makePane("Host does not expose safe range checks.", false);
  await unsupportedHost.ready();
  assert.equal(unsupportedHost.elements["rewrite-button"].disabled, true);
  assert.match(unsupportedHost.elements["rewrite-availability"].textContent, /predlog nije dostupan/);

  const cancelled = makePane();
  await cancelled.ready();
  const pendingLogin = cancelled.elements["login-button"].handlers.click();
  await waitFor(() => cancelled.posts.length === 1, "first session exchange");
  await cancelled.elements["login-button"].handlers.click();
  assert.equal(cancelled.dialogCount, 1);
  assert.equal(cancelled.posts.length, 1);
  await cancelled.elements["logout-button"].handlers.click();
  cancelled.resolvePost(0, "x".repeat(43));
  await pendingLogin;
  assert.equal(cancelled.calls.filter(call => call.options.method === "DELETE").length, 1);
  assert.equal(cancelled.elements["session-view"].classList.contains("active"), false);
  assert.equal(cancelled.elements["status"].textContent, "Odjavljeni ste.");

  const first = makePane();
  const second = makePane();
  await Promise.all([first.ready(), second.ready()]);
  const firstLogin = first.elements["login-button"].handlers.click();
  const secondLogin = second.elements["login-button"].handlers.click();
  await Promise.all([
    waitFor(() => first.posts.length === 1, "first pane exchange"),
    waitFor(() => second.posts.length === 1, "second pane exchange")
  ]);
  first.resolvePost(0, "a".repeat(43));
  await firstLogin;
  assert.equal(first.elements["session-view"].classList.contains("active"), true);
  assert.equal(second.elements["session-view"].classList.contains("active"), false);
  second.resolvePost(0, "b".repeat(43));
  await secondLogin;
  assert.equal(second.elements["session-view"].classList.contains("active"), true);
  await first.elements["logout-button"].handlers.click();
  assert.equal(first.elements["session-view"].classList.contains("active"), false);
  assert.equal(second.elements["session-view"].classList.contains("active"), true);

  const expiry = makePane();
  await expiry.ready();
  const expiryLogin = expiry.elements["login-button"].handlers.click();
  await waitFor(() => expiry.posts.length === 1, "expiry pane exchange");
  expiry.resolvePost(0, "c".repeat(43));
  await expiryLogin;
  const expiryTimer = expiry.timers.find(timer => timer.delay > 5000 && timer.delay < 300000);
  assert.equal(expiryTimer.delay > 0, true);
  expiryTimer.callback();
  assert.equal(expiry.elements["session-view"].classList.contains("active"), false);
  assert.match(expiry.elements["status"].textContent, /istekla/);

  const empty = makePane("   ");
  await empty.ready();
  const emptyLogin = empty.elements["login-button"].handlers.click();
  await waitFor(() => empty.posts.length === 1, "empty-selection pane login");
  empty.resolvePost(0, "d".repeat(43));
  await emptyLogin;
  await empty.elements["analyze-button"].handlers.click();
  assert.equal(empty.analysisCalls.length, 0);
  assert.match(empty.elements["status"].textContent, /Izaberite tekst/);

  const oversized = makePane("x".repeat(4001));
  await oversized.ready();
  const oversizedLogin = oversized.elements["login-button"].handlers.click();
  await waitFor(() => oversized.posts.length === 1, "oversized-selection pane login");
  oversized.resolvePost(0, "e".repeat(43));
  await oversizedLogin;
  await oversized.elements["analyze-button"].handlers.click();
  assert.equal(oversized.analysisCalls.length, 0);
  assert.match(oversized.elements["status"].textContent, /4.000/);

  const exactSelection = "Deo rečenice.\nDrugi pasus.\tTabela ćelija.";
  const analysis = makePane(exactSelection);
  await analysis.ready();
  const analysisLogin = analysis.elements["login-button"].handlers.click();
  await waitFor(() => analysis.posts.length === 1, "analysis pane login");
  analysis.resolvePost(0, "f".repeat(43));
  await analysisLogin;
  const analysisPromise = analysis.elements["analyze-button"].handlers.click();
  await waitFor(() => analysis.analysisCalls.length === 1, "selected-text request");
  assert.deepEqual(JSON.parse(analysis.analysisCalls[0].options.body), { text:exactSelection });
  assert.equal(analysis.analysisCalls[0].options.headers.Authorization, "Bearer " + "f".repeat(43));
  await analysis.elements["analyze-button"].handlers.click();
  assert.equal(analysis.analysisCalls.length, 1);
  analysis.resolveAnalysis(0, {
    sugestije:[{
      tekst:"Proverite ovaj predlog.",
      izvor:"Zakon o radu, član 179",
      verification_status:"verified_identity",
      claim_support_status:"unverified",
      sources:[{
        identity_match:true,
        kind:"clan_zakona",
        title:"Zakon o radu",
        identifier:"179",
        locator:"Zakon o radu, član 179",
        excerpt:"<img src=x onerror=alert(1)>",
        source_url:"javascript:alert(1)",
        version_status:"unknown"
      }]
    }]
  });
  await analysisPromise;
  assert.match(analysis.elements["analysis-results"].textContent, /Proverite ovaj predlog/);
  assert.match(analysis.elements["analysis-results"].textContent, /Identitet citata odgovara Vindex zapisu/);
  assert.match(analysis.elements["analysis-results"].textContent, /potkrepljuje predlog nije nezavisno provereno/);
  assert.match(analysis.elements["analysis-results"].textContent, /<img src=x onerror=alert\(1\)>/);
  assert.match(analysis.elements["analysis-results"].textContent, /javascript:alert\(1\)/);

  const scoped = makePane("selected matter phrase");
  await scoped.ready();
  const scopedLogin = scoped.elements["login-button"].handlers.click();
  await waitFor(() => scoped.posts.length === 1, "selected-matter pane login");
  scoped.resolvePost(0, "i".repeat(43));
  await scopedLogin;
  const matterSelect = scoped.elements["matter-select"];
  assert.deepEqual(matterSelect.options.map(option => option.value), ["", "matter-1", "matter-2"]);
  matterSelect.value = "matter-1";
  matterSelect.handlers.change();
  const scopedAnalysis = scoped.elements["analyze-button"].handlers.click();
  await waitFor(() => scoped.analysisCalls.length === 1, "selected-matter analysis");
  assert.deepEqual(JSON.parse(scoped.analysisCalls[0].options.body), {
    text:"selected matter phrase", predmet_id:"matter-1"
  });
  matterSelect.value = "matter-2";
  matterSelect.handlers.change();
  assert.equal(scoped.analysisCalls[0].options.signal.aborted, true);
  scoped.resolveAnalysis(0, { sugestije:[{ tekst:"stale matter result", izvor:"" }] });
  await scopedAnalysis;
  assert.equal(scoped.elements["analysis-results"].textContent, "");
  assert.match(scoped.elements["status"].textContent, /Predmet je promenjen/);
  await scoped.elements["logout-button"].handlers.click();
  assert.deepEqual(matterSelect.options.map(option => option.value), [""]);
  assert.equal(matterSelect.value, "");

  const changed = makePane("initial selected phrase");
  await changed.ready();
  const changedLogin = changed.elements["login-button"].handlers.click();
  await waitFor(() => changed.posts.length === 1, "changed-selection pane login");
  changed.resolvePost(0, "g".repeat(43));
  await changedLogin;
  const changedPromise = changed.elements["analyze-button"].handlers.click();
  await waitFor(() => changed.analysisCalls.length === 1, "changed-selection request");
  changed.setSelection("a different selection");
  changed.resolveAnalysis(0, { sugestije:[{ tekst:"stale", izvor:"" }] });
  await changedPromise;
  assert.equal(changed.elements["analysis-results"].textContent, "");
  assert.match(changed.elements["status"].textContent, /Izbor se promenio/);

  const loggedOut = makePane("selected before logout");
  await loggedOut.ready();
  const logoutLogin = loggedOut.elements["login-button"].handlers.click();
  await waitFor(() => loggedOut.posts.length === 1, "logout-request pane login");
  loggedOut.resolvePost(0, "h".repeat(43));
  await logoutLogin;
  const pendingAnalysis = loggedOut.elements["analyze-button"].handlers.click();
  await waitFor(() => loggedOut.analysisCalls.length === 1, "logout-request analysis");
  await loggedOut.elements["logout-button"].handlers.click();
  loggedOut.resolveAnalysis(0, { sugestije:[{ tekst:"must not appear", izvor:"" }] });
  await pendingAnalysis;
  assert.equal(loggedOut.elements["analysis-results"].textContent, "");
  assert.equal(loggedOut.elements["session-view"].classList.contains("active"), false);

  const rewrite = makePane("Izabrana rečenica za preformulisanje.");
  await rewrite.ready();
  const rewriteLogin = rewrite.elements["login-button"].handlers.click();
  await waitFor(() => rewrite.posts.length === 1, "rewrite pane login");
  rewrite.resolvePost(0, "j".repeat(43));
  await rewriteLogin;
  const rewritePromise = rewrite.elements["rewrite-button"].handlers.click();
  await waitFor(() => rewrite.rewriteCalls.length === 1, "rewrite request");
  assert.deepEqual(JSON.parse(rewrite.rewriteCalls[0].options.body), {
    text:"Izabrana rečenica za preformulisanje."
  });
  await rewrite.elements["rewrite-button"].handlers.click();
  assert.equal(rewrite.rewriteCalls.length, 1);
  assert.equal(rewrite.elements["apply-rewrite-button"].disabled, true);
  assert.equal(rewrite.applyCalls.length, 0);
  rewrite.resolveRewrite(0, {
    original_text:"Izabrana rečenica za preformulisanje.",
    proposal_text:"Predložena pravna formulacija.",
    document_changed:false
  });
  await rewritePromise;
  assert.equal(rewrite.elements["proposal-view"].hidden, false);
  assert.equal(rewrite.elements["proposal-original"].textContent, "Izabrana rečenica za preformulisanje.");
  assert.equal(rewrite.elements["proposal-text"].textContent, "Predložena pravna formulacija.");
  assert.equal(rewrite.applyCalls.length, 0);
  const applyPromise = rewrite.elements["apply-rewrite-button"].handlers.click();
  const duplicateApplyPromise = rewrite.elements["apply-rewrite-button"].handlers.click();
  assert.equal(rewrite.applyCalls.length, 1);
  await Promise.all([applyPromise, duplicateApplyPromise]);
  assert.equal(rewrite.applyCalls[0].replacement, "Predložena pravna formulacija.");
  assert.equal(rewrite.elements["proposal-view"].hidden, true);
  assert.match(rewrite.elements["status"].textContent, /Word Undo/);

  const cancelledProposal = makePane("Keep this original text.");
  await cancelledProposal.ready();
  const cancelledProposalLogin = cancelledProposal.elements["login-button"].handlers.click();
  await waitFor(() => cancelledProposal.posts.length === 1, "cancel proposal pane login");
  cancelledProposal.resolvePost(0, "m".repeat(43));
  await cancelledProposalLogin;
  const cancelledProposalRequest = cancelledProposal.elements["rewrite-button"].handlers.click();
  await waitFor(() => cancelledProposal.rewriteCalls.length === 1, "cancel proposal request");
  cancelledProposal.resolveRewrite(0, {
    original_text:"Keep this original text.",
    proposal_text:"A different proposal.",
    document_changed:false
  });
  await cancelledProposalRequest;
  await cancelledProposal.elements["cancel-rewrite-button"].handlers.click();
  assert.equal(cancelledProposal.elements["proposal-view"].hidden, true);
  assert.equal(cancelledProposal.applyCalls.length, 0);
  assert.match(cancelledProposal.elements["status"].textContent, /nije promenjen/);

  const staleRewrite = makePane("Original selected sentence.");
  await staleRewrite.ready();
  const staleRewriteLogin = staleRewrite.elements["login-button"].handlers.click();
  await waitFor(() => staleRewrite.posts.length === 1, "stale rewrite pane login");
  staleRewrite.resolvePost(0, "k".repeat(43));
  await staleRewriteLogin;
  const staleRewritePromise = staleRewrite.elements["rewrite-button"].handlers.click();
  await waitFor(() => staleRewrite.rewriteCalls.length === 1, "stale rewrite request");
  staleRewrite.setSelection("Same original selected sentence.");
  staleRewrite.resolveRewrite(0, {
    original_text:"Original selected sentence.",
    proposal_text:"Do not apply to a changed selection.",
    document_changed:false
  });
  await staleRewritePromise;
  assert.equal(staleRewrite.elements["proposal-view"].hidden, true);
  assert.equal(staleRewrite.applyCalls.length, 0);
  assert.match(staleRewrite.elements["status"].textContent, /Izbor ili tekst se promenio/);

  const movedRewrite = makePane("Same text selected twice.");
  await movedRewrite.ready();
  const movedLogin = movedRewrite.elements["login-button"].handlers.click();
  await waitFor(() => movedRewrite.posts.length === 1, "moved rewrite pane login");
  movedRewrite.resolvePost(0, "l".repeat(43));
  await movedLogin;
  const movedProposalPromise = movedRewrite.elements["rewrite-button"].handlers.click();
  await waitFor(() => movedRewrite.rewriteCalls.length === 1, "moved rewrite proposal");
  movedRewrite.resolveRewrite(0, {
    original_text:"Same text selected twice.",
    proposal_text:"A new formulation.",
    document_changed:false
  });
  await movedProposalPromise;
  movedRewrite.setSelectionPosition(200);
  await movedRewrite.elements["apply-rewrite-button"].handlers.click();
  assert.equal(movedRewrite.elements["proposal-view"].hidden, true);
  assert.match(movedRewrite.elements["status"].textContent, /Izbor ili tekst se promenio/);
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
