// Synthetic browser regression for restoring Smart Intake jobs in an existing matter.
import { chromium } from "playwright";
import { pokreniFixture } from "./fixtures/api-fixture.mjs";
import { napraviPredmete, predmetiRuta, predmetDetaljRuta, kombinuj } from "./fixtures/predmeti-api.mjs";
import { prijemRuta } from "./fixtures/pisanje-api.mjs";

const AUTH_KEY = "sb-czsxymueizfqrbbgqqob-auth-token";
const PREFIX = "vindex:smart-intake:resume:v1:";
const A = napraviPredmete("uid-A", 2), B = napraviPredmete("uid-B", 1);
const JOBS_A = {}, JOBS_B = {};
const USERS = { "tok-A": { id: "uid-A", predmeti: A, poslovi: JOBS_A }, "tok-B": { id: "uid-B", predmeti: B, poslovi: JOBS_B } };
let nextJob = 0, passed = 0, failed = 0;
function check(group, name, ok, detail = "") {
  if (ok) passed++; else failed++;
  console.log(`${ok ? "PASS" : "FAIL"} [${group}] ${name}${detail ? " — " + detail : ""}`);
}
const auth = (id, token) => JSON.stringify({ access_token: token, refresh_token: "synthetic", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id } });
const keyFor = (user, matter) => PREFIX + encodeURIComponent(user) + ":" + encodeURIComponent(matter);
const resumeRecord = (user, matter, ids) => JSON.stringify({ verzija: 1, korisnik: user, predmet_id: matter, poslovi: ids });
async function waitFor(page, fn, ms = 5000, arg) {
  try { await page.waitForFunction(fn, arg, { timeout: ms }); return true; } catch { return false; }
}
const rows = (page) => page.evaluate(() => [...document.querySelectorAll("#pd-poslovi .intake")].map((li) => ({
  id: li.dataset.posao, tekst: li.innerText,
  stanje: li.querySelector(".intake__state")?.dataset.stanje || "",
  dugmad: [...li.querySelectorAll("button")].map((b) => b.textContent.trim()),
})));
async function go(page, hash) {
  await page.evaluate((h) => new Promise((resolve) => {
    if (location.hash === h) { resolve(); return; }
    window.addEventListener("hashchange", () => resolve(), { once: true });
    location.hash = h;
  }), hash);
}
async function newScenario(options = {}) {
  const fixture = await pokreniFixture(kombinuj(
    prijemRuta(USERS, { idPosla: () => "resume-job-" + (++nextJob), napreduj: options.napreduj || (() => {}) }),
    predmetiRuta(USERS), predmetDetaljRuta(USERS, {}),
  ));
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
  await context.addInitScript(({ seedKey, seedValue, blocked }) => {
    if (!localStorage.getItem("vx-resume-test-auth-seeded")) {
      localStorage.setItem("sb-czsxymueizfqrbbgqqob-auth-token", JSON.stringify({
        access_token: "tok-A", refresh_token: "synthetic", expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id: "uid-A" },
      }));
      localStorage.setItem("vx-resume-test-auth-seeded", "1");
    }
    if (blocked) Object.defineProperty(window, "sessionStorage", {
      configurable: true, get() { throw new DOMException("blocked", "SecurityError"); },
    });
    else if (seedKey && seedValue !== null) sessionStorage.setItem(seedKey, seedValue);
    window.__jobGets = [];
    window.__active = Object.create(null);
    window.__maxActive = Object.create(null);
    const originalFetch = window.fetch.bind(window);
    window.fetch = (input, init) => {
      const match = /^\/api\/smart-intake\/jobs\/([^/]+)$/.exec(new URL(String(input), location.href).pathname);
      const isGet = match && (!init || !init.method || init.method === "GET");
      const id = isGet ? decodeURIComponent(match[1]) : null;
      if (isGet) {
        window.__jobGets.push(id);
        window.__active[id] = (window.__active[id] || 0) + 1;
        window.__maxActive[id] = Math.max(window.__maxActive[id] || 0, window.__active[id]);
      }
      return originalFetch(input, init).finally(() => {
        if (isGet) window.__active[id] = Math.max(0, (window.__active[id] || 1) - 1);
      });
    };
  }, { seedKey: options.seedKey || "", seedValue: options.seedValue === undefined ? null : options.seedValue, blocked: options.blocked === true });

  const overrides = options.overrides || Object.create(null);
  const omitSignal = new Set(options.omitSignal || []);
  const delays = options.delays || Object.create(null);
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname !== "127.0.0.1") { await route.abort(); return; }
    const match = /^\/api\/smart-intake\/jobs\/([^/]+)$/.exec(url.pathname);
    if (match && route.request().method() === "GET") {
      const id = decodeURIComponent(match[1]), override = overrides[id];
      if (override) {
        if (override.delay) await new Promise((resolve) => setTimeout(resolve, override.delay));
        if (override.status) {
          await route.fulfill({ status: override.status, contentType: "application/json", body: JSON.stringify({ detail: "synthetic" }) }).catch(() => {});
          return;
        }
      }
      if (delays[id]) await new Promise((resolve) => setTimeout(resolve, delays[id]));
      if (omitSignal.has(id)) {
        const response = await route.fetch().catch(() => null);
        if (!response) return;
        const body = await response.text();
        try { const data = JSON.parse(body); delete data.job.prikacivanje; await route.fulfill({ response, body: JSON.stringify(data) }); }
        catch { await route.fulfill({ response, body }); }
        return;
      }
    }
    await route.continue().catch(() => {});
  });
  const page = await context.newPage(), pageErrors = [];
  page.on("pageerror", (e) => pageErrors.push(String(e)));
  await page.clock.install();
  await page.goto(`http://127.0.0.1:${fixture.port}/?rezim=live#/predmeti/${A[0].id}/prijem`);
  const ready = await waitFor(page, () => !document.getElementById("odeljak-prijem").hidden
    && document.getElementById("predmet-naslov").textContent.length > 0);
  return { fixture, context, page, pageErrors, ready, overrides,
    async close() { await context.close(); await fixture.zatvori(); } };
}
async function upload(page, names) {
  await page.setInputFiles("#pd-fajlovi", names.map((name) => ({
    name, mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 synthetic content " + name),
  })));
  await page.click("#pd-otpremi");
  return waitFor(page, (n) => document.querySelectorAll("#pd-poslovi .intake").length === n, 7000, names.length);
}
async function fastForward(page, milliseconds) {
  for (let elapsed = 0; elapsed < milliseconds; elapsed += 1000) {
    await page.clock.runFor(Math.min(1000, milliseconds - elapsed));
    await new Promise((resolve) => setTimeout(resolve, 12));
  }
}
const browser = await chromium.launch({ headless: true });
try {
  // Full upload -> refresh -> other matter -> return path with the actual V2 UI and status GETs.
  {
    const s = await newScenario({ omitSignal: ["resume-job-6"] }), p = s.page;
    check("setup", "authenticated existing matter is open", s.ready);
    const didUpload = await upload(p, ["review.pdf", "completed.pdf", "partial.pdf", "active.pdf", "other.pdf", "no-signal.pdf"]);
    const uploadedRows = await rows(p), ids = uploadedRows.map((r) => r.id);
    if (ids.length !== 6) throw new Error("Synthetic upload did not produce all expected jobs.");
    check("upload", "six accepted jobs appear once", didUpload && ids.length === 6 && new Set(ids).size === 6);
    for (const id of ids) JOBS_A[id].ime = "server-" + JOBS_A[id].ime;
    Object.assign(JOBS_A[ids[0]], { status: "awaiting_review", predmet_id: null, prikacivanje: "NIJE_PRIKACENO",
      dokument: { tip: "other", tip_pouzdanost: 0.91, ocr_koriscen: false }, provera: { razlog: "classification_uncertain", polja: [] } });
    Object.assign(JOBS_A[ids[1]], { status: "completed", predmet_id: null, prikacivanje: "NIJE_PRIKACENO" });
    Object.assign(JOBS_A[ids[2]], { status: "completed", predmet_id: A[0].id, prikacivanje: "NEPOTPUNO" });
    Object.assign(JOBS_A[ids[3]], { status: "extracting", predmet_id: null, prikacivanje: "U_TOKU" });
    Object.assign(JOBS_A[ids[4]], { status: "completed", predmet_id: A[1].id, prikacivanje: "PRIKACENO" });
    Object.assign(JOBS_A[ids[5]], { status: "completed", predmet_id: A[0].id, prikacivanje: "PRIKACENO" });

    const resumeKey = keyFor("uid-A", A[0].id);
    const raw = await p.evaluate((key) => sessionStorage.getItem(key), resumeKey);
    let saved; try { saved = JSON.parse(raw); } catch {}
    check("storage", "accepted IDs are persisted in a versioned user/matter-scoped record",
      !!saved && saved.verzija === 1 && saved.korisnik === "uid-A" && saved.predmet_id === A[0].id
      && ids.every((id) => saved.poslovi.includes(id)), raw || "missing record");
    check("storage", "no filenames, extracted data, tokens, or response copies are persisted",
      !!saved && Object.keys(saved).sort().join(",") === "korisnik,poslovi,predmet_id,verzija"
      && !raw.includes("server-") && !raw.includes("tok-A") && !raw.includes("entiteti"));

    const mutationPosts = () => s.fixture.zahtevi.filter((x) => x.metod === "POST"
      && /\/api\/smart-intake\/(documents|jobs\/.*\/(finalize|review\/))/.test(x.putanja)).length;
    const postsBefore = mutationPosts();
    await p.reload();
    const restored = await waitFor(p, (n) => document.querySelectorAll("#pd-poslovi .intake").length === n, 6000, ids.length);
    let r = await rows(p);
    check("refresh", "refresh restores every accepted job via status GET", restored && r.length === ids.length);
    check("server", "restored document names are taken from server status", r.length === ids.length && r.every((x) => x.tekst.includes("server-")));
    check("states", "awaiting_review remains available for explicit human review",
      r.find((x) => x.id === ids[0])?.dugmad.includes("Potvrđujem pregled"));
    check("states", "completed means processed, not attached",
      r.find((x) => x.id === ids[1])?.tekst.includes("spremno za prikačivanje")
      && !r.find((x) => x.id === ids[1])?.tekst.includes("Prikačeno ovom predmetu"));
    check("states", "NEPOTPUNO remains explicit and retryable",
      r.find((x) => x.id === ids[2])?.tekst.includes("Prikačivanje nije završeno")
      && r.find((x) => x.id === ids[2])?.dugmad.includes("Ponovi prikačivanje"));
    check("states", "U_TOKU is not presented as a completed attachment",
      r.find((x) => x.id === ids[3])?.tekst.includes("Prikačivanje je u toku")
      && !r.find((x) => x.id === ids[3])?.tekst.includes("Prikačeno ovom predmetu"));
    check("states", "attachment to another matter is identified without claiming current attachment",
      r.find((x) => x.id === ids[4])?.tekst.includes("drugom vašem predmetu")
      && !r.find((x) => x.id === ids[4])?.tekst.includes("Prikačeno ovom predmetu"));
    check("states", "predmet_id without explicit prikacivanje is not proof of attachment",
      r.find((x) => x.id === ids[5])?.tekst.includes("Stanje prikačivanja nije potvrđeno")
      && !r.find((x) => x.id === ids[5])?.tekst.includes("Prikačeno ovom predmetu"));
    check("states", "unknown attachment state retains a manual status check",
      r.find((x) => x.id === ids[5])?.dugmad.includes("Proveri stanje obrade"));
    const getIds = await p.evaluate(() => window.__jobGets.slice());
    check("pollers", "no duplicate rows or parallel polling for a restored job",
      new Set(r.map((x) => x.id)).size === ids.length
      && await p.evaluate(() => Object.values(window.__maxActive).every((n) => n <= 1))
      && ids.every((id) => getIds.filter((x) => x === id).length === 1));
    check("resume-no-write", "refresh causes no upload/review/finalize requests", mutationPosts() === postsBefore);

    await go(p, `#/predmeti/${A[1].id}/prijem`);
    const another = await waitFor(p, (id) => location.hash === `#/predmeti/${id}/prijem`
      && document.getElementById("predmet-naslov").textContent.includes("broj 1"), 5000, A[1].id);
    const matterRows = await rows(p);
    check("matter", "different case displays no prior jobs", another && matterRows.length === 0,
      JSON.stringify({ another, rows: matterRows.map((x) => x.id) }));
    await go(p, "#/danas");
    await go(p, `#/predmeti/${A[0].id}/prijem`);
    const returned = await waitFor(p, (n) => document.querySelectorAll("#pd-poslovi .intake").length === n, 6000, ids.length);
    r = await rows(p);
    check("navigation", "leaving and returning in the same tab restores the jobs", returned && r.length === ids.length
      && new Set(r.map((x) => x.id)).size === ids.length);
    check("resume-no-write", "navigation recovery sends no upload/review/finalize requests", mutationPosts() === postsBefore);
    check("browser", "no uncaught frontend errors", s.pageErrors.length === 0, s.pageErrors.join(" | "));
    await s.close();
  }

  // A delayed old-matter response cannot repopulate the next matter.
  {
    const id = "resume-delayed-context";
    JOBS_A[id] = { id, ime: "server-delayed.pdf", status: "extracting", attempts: 0, predmet_id: null, dokument: null, entiteti: [], provera: null, prikacivanje: "U_TOKU" };
    const s = await newScenario({ seedKey: keyFor("uid-A", A[0].id), seedValue: resumeRecord("uid-A", A[0].id, [id]), delays: { [id]: 450 } });
    const p = s.page;
    await waitFor(p, (job) => window.__jobGets.includes(job), 2500, id);
    await go(p, `#/predmeti/${A[1].id}/prijem`);
    const switched = await waitFor(p, (caseId) => location.hash === `#/predmeti/${caseId}/prijem`
      && document.getElementById("predmet-naslov").textContent.includes("broj 1"), 5000, A[1].id);
    await new Promise((resolve) => setTimeout(resolve, 600));
    const rowsInNewMatter = await rows(p);
    check("stale-response", "delayed old-matter response cannot populate the new matter",
      switched && rowsInNewMatter.length === 0, JSON.stringify({ switched, rows: rowsInNewMatter.map((x) => x.id) }));
    check("stale-response", "old-matter continuation pointer remains scoped and intact",
      await p.evaluate((k) => JSON.parse(sessionStorage.getItem(k) || "null")?.poslovi.includes("resume-delayed-context"), keyFor("uid-A", A[0].id)));
    await go(p, `#/predmeti/${A[0].id}/prijem`);
    const returned = await waitFor(p, (job) => document.querySelector("#pd-poslovi .intake")?.dataset.posao === job
      && document.querySelector("#pd-poslovi .intake .intake__name")?.textContent === "server-delayed.pdf", 5000, id);
    check("stale-response", "return to the original matter obtains fresh server state",
      returned && (await p.evaluate((job) => window.__jobGets.filter((x) => x === job).length, id)) >= 2);
    check("stale-response", "delayed-context scenario has no parallel poller or frontend error",
      await p.evaluate(() => Object.values(window.__maxActive).every((n) => n <= 1)) && s.pageErrors.length === 0);
    await s.close();
  }

  // A status response started for user A must not render or recreate state after switching to user B.
  {
    const id = "resume-delayed-identity";
    JOBS_A[id] = { id, ime: "private-user-a.pdf", status: "extracting", attempts: 0, predmet_id: null, dokument: null, entiteti: [], provera: null, prikacivanje: "U_TOKU" };
    const aKey = keyFor("uid-A", A[0].id);
    const s = await newScenario({ seedKey: aKey, seedValue: resumeRecord("uid-A", A[0].id, [id]), delays: { [id]: 450 } });
    const p = s.page;
    await p.evaluate(() => sessionStorage.setItem("unrelated-marker", "keep"));
    const requestStarted = await waitFor(p, (job) => window.__jobGets.includes(job), 2500, id);
    await p.evaluate(({ key, value }) => { localStorage.setItem(key, value); window.VxSesija.proveri(); }, {
      key: AUTH_KEY, value: auth("uid-B", "tok-B"),
    });
    await go(p, `#/predmeti/${B[0].id}/prijem`);
    const switched = await waitFor(p, (caseId) => location.hash === `#/predmeti/${caseId}/prijem`
      && document.getElementById("predmet-naslov").textContent.includes("broj 0"), 5000, B[0].id);
    await new Promise((resolve) => setTimeout(resolve, 600));
    const rowsForB = await rows(p);
    check("identity-stale", "delayed A status response cannot render A data for B",
      requestStarted && switched && rowsForB.length === 0
      && !await p.evaluate(() => document.body.innerText.includes("private-user-a.pdf")));
    check("identity-stale", "switch clears only A continuation pointer and preserves unrelated storage",
      !await p.evaluate((k) => !!sessionStorage.getItem(k), aKey)
      && await p.evaluate(() => sessionStorage.getItem("unrelated-marker") === "keep"));
    check("identity-stale", "old response does not restart polling or issue another status GET",
      await p.evaluate((job) => window.__jobGets.filter((x) => x === job).length === 1, id));
    check("browser", "no uncaught error after delayed response and user switch", s.pageErrors.length === 0, s.pageErrors.join(" | "));
    await s.close();
  }

  // Unavailable browser storage does not break accepted upload.
  {
    const s = await newScenario({ blocked: true }), p = s.page;
    const ok = await upload(p, ["blocked-storage.pdf"]);
    const row = (await rows(p))[0]?.tekst || "";
    const msg = await p.locator("#pd-poruka").textContent().catch(() => "");
    check("storage", "unavailable sessionStorage does not break accepted upload", ok && (await rows(p)).length === 1);
    check("storage", "UI says same-tab continuation was not saved", /nastavak|prikaz|sačuvan/i.test(msg + row), msg || row);
    check("browser", "no uncaught storage error", s.pageErrors.length === 0, s.pageErrors.join(" | "));
    await s.close();
  }

  // Corrupt pointers are never trusted as job IDs.
  {
    const s = await newScenario({ seedKey: keyFor("uid-A", A[0].id), seedValue: "{broken" }), p = s.page;
    const warned = await waitFor(p, () => /nastavak poslova nije mogao da se učita/i.test(document.getElementById("pd-poruka").textContent), 2500);
    check("storage", "malformed session record is warned and creates no rows", warned && (await rows(p)).length === 0);
    check("storage", "malformed record triggers no status GET", (await p.evaluate(() => window.__jobGets.length)) === 0);
    check("browser", "no uncaught error for malformed storage", s.pageErrors.length === 0);
    await s.close();
  }

  // Structurally valid JSON with a malformed ID is also rejected before any GET.
  {
    const invalid = resumeRecord("uid-A", A[0].id, ["foreign/job-id"]);
    const s = await newScenario({ seedKey: keyFor("uid-A", A[0].id), seedValue: invalid }), p = s.page;
    const warned = await waitFor(p, () => /nastavak poslova nije mogao da se učita/i.test(document.getElementById("pd-poruka").textContent), 2500);
    check("storage", "malformed job ID is rejected without rendering rows", warned && (await rows(p)).length === 0);
    check("storage", "malformed job ID never reaches the status endpoint", (await p.evaluate(() => window.__jobGets.length)) === 0);
    await s.close();
  }

  // Authentication/temporary errors retain pointers; only confirmed 404 removes its ID.
  {
    const authId = "resume-auth", tempId = "resume-temp", missingId = "resume-missing";
    JOBS_A[authId] = { id: authId, ime: "auth.pdf", status: "extracting", attempts: 0, predmet_id: null, dokument: null, entiteti: [], provera: null, prikacivanje: "U_TOKU" };
    JOBS_A[tempId] = { id: tempId, ime: "temporary.pdf", status: "extracting", attempts: 0, predmet_id: null, dokument: null, entiteti: [], provera: null, prikacivanje: "U_TOKU" };
    const key = keyFor("uid-A", A[0].id);
    const s = await newScenario({ seedKey: key, seedValue: resumeRecord("uid-A", A[0].id, [authId, tempId, missingId]),
      overrides: { [authId]: { status: 401 }, [tempId]: { status: 503 } } });
    const p = s.page;
    await waitFor(p, (n) => document.querySelectorAll("#pd-poslovi .intake").length === n, 2500, 3);
    await waitFor(p, () => document.querySelectorAll("#pd-poslovi .intake .intake__msg:not([hidden])").length >= 2, 2500);
    let saved = JSON.parse(await p.evaluate((k) => sessionStorage.getItem(k), key));
    check("errors", "401 auth failure is distinct and retains its pointer",
      /Prijava više nije važeća/.test((await rows(p)).find((x) => x.id === authId)?.tekst || "") && saved.poslovi.includes(authId));
    check("errors", "503 is temporary and retains its pointer",
      /ne znači da obrada nije uspela/i.test((await rows(p)).find((x) => x.id === tempId)?.tekst || "") && saved.poslovi.includes(tempId));
    check("errors", "confirmed 404 removes only the inaccessible job ID",
      !saved.poslovi.includes(missingId) && saved.poslovi.includes(authId) && saved.poslovi.includes(tempId));
    s.overrides[authId] = null; s.overrides[tempId] = null;
    await go(p, "#/danas");
    await go(p, `#/predmeti/${A[0].id}/prijem`);
    const recovered = await waitFor(p, (n) => document.querySelectorAll("#pd-poslovi .intake").length === n, 4000, 2);
    check("errors", "return after auth/network recovery rereads authorized jobs", recovered && (await rows(p)).some((x) => x.id === authId));
    check("browser", "no uncaught error for failure responses", s.pageErrors.length === 0);
    await s.close();
  }

  // The five-minute auto window ends with a single safe manual status GET.
  {
    const id = "resume-long";
    JOBS_A[id] = { id, ime: "long.pdf", status: "extracting", attempts: 0, predmet_id: null, dokument: null, entiteti: [], provera: null, prikacivanje: "U_TOKU" };
    const s = await newScenario({ seedKey: keyFor("uid-A", A[0].id), seedValue: resumeRecord("uid-A", A[0].id, [id]) });
    const p = s.page;
    await waitFor(p, () => document.querySelectorAll("#pd-poslovi .intake").length === 1, 2500);
    await fastForward(p, 306000);
    let r = await rows(p);
    const button = p.locator("#pd-poslovi .intake").getByRole("button", { name: "Proveri stanje obrade" });
    const manualAvailable = await button.count() === 1;
    check("manual", "manual status check is available after bounded auto window", manualAvailable, r[0]?.tekst.slice(-100));
    const before = await p.evaluate((job) => window.__jobGets.filter((x) => x === job).length, id);
    let oneGet = false, after = before;
    if (manualAvailable) {
      await button.click();
      oneGet = await waitFor(p, (n) => window.__jobGets.filter((x) => x === n.job).length === n.count + 1, 2500, { job: id, count: before });
      await fastForward(p, 30000);
      after = await p.evaluate((job) => window.__jobGets.filter((x) => x === job).length, id);
      r = await rows(p);
    }
    check("manual", "manual control issues exactly one status GET", manualAvailable && oneGet);
    check("manual", "manual check does not restart unbounded polling", manualAvailable && after === before + 1 && /Proveri stanje obrade/.test(r[0]?.tekst || ""));
    check("manual", "refresh recovery caused no upload/review/finalize POST", s.fixture.zahtevi.every((x) => x.metod !== "POST"
      || !/\/api\/smart-intake\/(documents|jobs\/.*\/(finalize|review\/))/.test(x.putanja)));
    check("browser", "no uncaught error after manual check", s.pageErrors.length === 0);
    await s.close();
  }

  // User change/logout clears only the old user's keys and leaves unrelated tab storage intact.
  {
    const s = await newScenario(), p = s.page;
    await p.evaluate(() => sessionStorage.setItem("unrelated-marker", "keep"));
    await upload(p, ["user-a.pdf"]);
    const aId = (await rows(p))[0]?.id, aKey = keyFor("uid-A", A[0].id);
    const hadA = !!await p.evaluate((k) => sessionStorage.getItem(k), aKey);
    await p.evaluate(({ key, value }) => { localStorage.setItem(key, value); window.VxSesija.proveri(); }, {
      key: AUTH_KEY, value: auth("uid-B", "tok-B"),
    });
    await go(p, `#/predmeti/${B[0].id}/prijem`);
    await waitFor(p, () => document.getElementById("predmet-naslov").textContent.includes("broj 0"));
    check("identity", "switching user does not show previous user's job", hadA && !(await rows(p)).some((x) => x.id === aId));
    check("identity", "prior user's pointers are removed without clearing unrelated storage",
      !await p.evaluate((k) => !!sessionStorage.getItem(k), aKey)
      && await p.evaluate(() => sessionStorage.getItem("unrelated-marker") === "keep"));
    await upload(p, ["user-b.pdf"]);
    const bKey = keyFor("uid-B", B[0].id), bId = (await rows(p))[0]?.id;
    check("identity", "new user receives a separate continuation record", !!bId && !!await p.evaluate((k) => sessionStorage.getItem(k), bKey));
    await p.evaluate((key) => localStorage.removeItem(key), AUTH_KEY);
    await p.evaluate(() => window.VxSesija.proveri());
    check("identity", "logout clears only prior user's record", !await p.evaluate((k) => !!sessionStorage.getItem(k), bKey)
      && await p.evaluate(() => sessionStorage.getItem("unrelated-marker") === "keep"));
    check("browser", "no uncaught error during identity changes", s.pageErrors.length === 0);
    await s.close();
  }
} finally {
  await browser.close();
}
console.log(`\n${passed}/${passed + failed} PASS; ${failed} FAIL`);
process.exitCode = failed ? 1 : 0;
