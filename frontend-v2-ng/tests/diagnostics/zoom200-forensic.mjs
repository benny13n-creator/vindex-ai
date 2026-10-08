// Vindex V2 NG — forenzika jednog piksela pri zumu 200% (NS002B). SAMO DIJAGNOSTIKA.
// Pokretanje: `node tests/diagnostics/zoom200-forensic.mjs` (sam podiže servere; treba git).
// Izlaz: shots/zoom200-forensic/ (5 snimaka HEAD, 2 foundation, isečci, heatmap, json).
//
//  1. 5 nezavisnih snimaka ISTOG HEAD-a istim postupkom kao live-browser-matrix
//     (persistent context, zoom ekstenzija, chrome.tabs.setZoom(2), CDP snimak);
//     svaki par: broj, koordinate i RGBA svakog različitog piksela, bbox, isečci ±20 px
//  2. svaki nestabilan piksel → CSS koordinata (/DPR) → elementFromPoint + stilovi
//  3. semantički ugovor HEAD protiv foundation-a (tests/fixtures/zoom-contract.mjs)

import { chromium } from "playwright";
import { spawn, execFileSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import http from "node:http";
import { fileURLToPath } from "node:url";
import { ugovor, fokusBezPomeranja, razlikeUgovora } from "../fixtures/zoom-contract.mjs";

const KOREN = fileURLToPath(new URL("../..", import.meta.url));
const REPO = fileURLToPath(new URL("../../..", import.meta.url));
const EXT = fileURLToPath(new URL("../fixtures/zoom-ext", import.meta.url));
const OUT = fileURLToPath(new URL("../../shots/zoom200-forensic/", import.meta.url));
await mkdir(OUT, { recursive: true });
const log = (...a) => console.log(...a);

const refDir = await mkdtemp(join(tmpdir(), "vx-zref-"));
execFileSync("tar", ["-xf", "-"], { cwd: refDir, input: execFileSync("git", ["archive", "--format=tar", "1eb20976", "frontend-v2-ng"], { cwd: REPO, maxBuffer: 64 << 20 }) });
const server = (dir, port) => spawn(process.execPath, ["serve.mjs", String(port)], { cwd: dir, stdio: "ignore" });
async function spreman(port) {
  for (let i = 0; i < 100; i++) {
    if (await new Promise(r => http.get({ host: "127.0.0.1", port, path: "/" }, s => { s.resume(); r(true); }).on("error", () => r(false)))) return;
    await new Promise(r => setTimeout(r, 50));
  }
}
const P_HEAD = 4481, P_REF = 4482;
const sH = server(KOREN, P_HEAD), sR = server(join(refDir, "frontend-v2-ng"), P_REF);
await spreman(P_HEAD); await spreman(P_REF);

/* Isti postupak kao snimakZoom u live-browser-matrix.mjs, plus ugovor i DOM mapiranje. */
async function zoomSesija(port, { tacke = [] } = {}) {
  const ctx = await chromium.launchPersistentContext("", { channel: "chromium", headless: true, viewport: null, reducedMotion: "reduce",
    args: [`--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`, "--window-size=1440,900"] });
  let [sw] = ctx.serviceWorkers(); if (!sw) sw = await ctx.waitForEvent("serviceworker", { timeout: 15000 });
  await ctx.addInitScript(() => { localStorage.setItem("vx-ng-tema", "dark"); localStorage.setItem("vx-ng-nav", "puna"); });
  const p = await ctx.newPage();
  await p.goto(`http://127.0.0.1:${port}/`);
  await p.addStyleTag({ content: "#pozadina{visibility:hidden!important}" });
  await p.evaluate(() => document.fonts.ready);
  const z = await sw.evaluate(async () => { const t = (await chrome.tabs.query({})).find(x => x.url && x.url.startsWith("http://127.0.0.1")); await chrome.tabs.setZoom(t.id, 2); return chrome.tabs.getZoom(t.id); });
  await p.waitForTimeout(400);
  const s = await p.context().newCDPSession(p);
  const { data } = await s.send("Page.captureScreenshot", { format: "png" });
  const u = await ugovor(p);
  const dom = await p.evaluate((tacke) => tacke.map(([x, y]) => {
    const cx = x / devicePixelRatio, cy = y / devicePixelRatio;
    const e = document.elementFromPoint(cx, cy);
    if (!e) return { x, y, css: [cx, cy], element: null };
    const c = getComputedStyle(e); const b = e.getBoundingClientRect();
    return { x, y, css: [cx, cy], element: e.tagName.toLowerCase() + (e.id ? "#" + e.id : "") + (e.className && typeof e.className === "string" ? "." + e.className.split(" ").join(".") : ""),
      rect: [b.x, b.y, b.width, b.height].map(v => +v.toFixed(2)), naIvici: Math.min(Math.abs(cx - b.left), Math.abs(cx - b.right), Math.abs(cy - b.top), Math.abs(cy - b.bottom)).toFixed(2),
      font: c.fontFamily, size: c.fontSize, lh: c.lineHeight, border: c.borderTopWidth + " " + c.borderBottomWidth, bg: c.backgroundColor, color: c.color, transform: c.transform, opacity: c.opacity };
  }), tacke);
  const fokus = await fokusBezPomeranja(p);
  await ctx.close();
  return { png: Buffer.from(data, "base64"), zoom: z, ugovor: u, dom, fokus };
}

const browser = await chromium.launch();
const alat = await (await browser.newContext()).newPage();
/* Dekodiranje neprovidnih PNG snimaka u pregledaču (bez gubitka) i poređenje. */
async function parovi(pngs) {
  return alat.evaluate(async (b64s) => {
    const ucitaj = (s) => new Promise((r, x) => { const i = new Image(); i.onload = () => r(i); i.onerror = x; i.src = "data:image/png;base64," + s; });
    const slike = await Promise.all(b64s.map(ucitaj));
    const podaci = slike.map(i => { const c = document.createElement("canvas"); c.width = i.width; c.height = i.height; const g = c.getContext("2d"); g.drawImage(i, 0, 0); return g.getImageData(0, 0, c.width, c.height).data; });
    const W = slike[0].width, H = slike[0].height, out = [];
    for (let a = 0; a < podaci.length; a++) for (let b = a + 1; b < podaci.length; b++) {
      const A = podaci[a], B = podaci[b], px = [];
      let maks = 0;
      for (let i = 0; i < A.length; i += 4) {
        const m = Math.max(Math.abs(A[i] - B[i]), Math.abs(A[i + 1] - B[i + 1]), Math.abs(A[i + 2] - B[i + 2]), Math.abs(A[i + 3] - B[i + 3]));
        if (m) { if (m > maks) maks = m; if (px.length < 200) { const k = i / 4; px.push({ x: k % W, y: (k / W) | 0, a: [A[i], A[i + 1], A[i + 2], A[i + 3]], b: [B[i], B[i + 1], B[i + 2], B[i + 3]], d: m }); } }
      }
      out.push({ par: [a, b], razlicitih: px.length, maks, dim: [W, H, slike[b].width, slike[b].height], px });
    }
    return out;
  }, pngs.map(b => b.toString("base64")));
}
async function isecak(png, x, y, ime) {
  const b64 = await alat.evaluate(async ([s, x, y]) => {
    const i = await new Promise((r) => { const im = new Image(); im.onload = () => r(im); im.src = "data:image/png;base64," + s; });
    const c = document.createElement("canvas"); c.width = 41 * 8; c.height = 41 * 8; const g = c.getContext("2d"); g.imageSmoothingEnabled = false;
    g.drawImage(i, x - 20, y - 20, 41, 41, 0, 0, 41 * 8, 41 * 8); g.strokeStyle = "red"; g.strokeRect(20 * 8, 20 * 8, 8, 8);
    return c.toDataURL("image/png").split(",")[1];
  }, [png.toString("base64"), x, y]);
  await writeFile(OUT + ime, Buffer.from(b64, "base64"));
}

// ── KORAK 1: 5 nezavisnih snimaka HEAD-a + 2 foundation-a ───────────────
const head = [];
for (let i = 0; i < 5; i++) { head.push(await zoomSesija(P_HEAD)); await writeFile(OUT + `head-${i}.png`, head[i].png); }
const ref = [await zoomSesija(P_REF), await zoomSesija(P_REF)];
await writeFile(OUT + "foundation-0.png", ref[0].png); await writeFile(OUT + "foundation-1.png", ref[1].png);
log(`Korak 1: zoom HEAD ${head.map(h => h.zoom).join(",")} | DPR ${head.map(h => h.ugovor.dpr).join(",")} | dimenzije ${head.map(h => h.png.length && "").join("")}`);
const sve = [...head.map(h => h.png), ...ref.map(r => r.png)];
const rez = await parovi(sve);
const nestabilni = new Map();
const oznaka = (k) => (k < 5 ? `H${k}` : `F${k - 5}`);
for (const r of rez) {
  log(`  par ${oznaka(r.par[0])}-${oznaka(r.par[1])}: ${r.razlicitih} piksela, maks ${r.maks}/255, dim ${r.dim.join("x")}` + (r.px.length ? " — " + r.px.slice(0, 4).map(p => `(${p.x},${p.y}) ${JSON.stringify(p.a)}→${JSON.stringify(p.b)} Δ${p.d}`).join("; ") : ""));
  for (const p of r.px) nestabilni.set(p.x + "," + p.y, [p.x, p.y]);
}
// Koji snimak je „drugačiji“ na svakoj koordinati (vrednost po snimku).
const tacke = [...nestabilni.values()].slice(0, 20);
const vrednosti = await alat.evaluate(async ([b64s, tacke]) => {
  const ucitaj = (s) => new Promise((r) => { const i = new Image(); i.onload = () => r(i); i.src = "data:image/png;base64," + s; });
  const slike = await Promise.all(b64s.map(ucitaj));
  return tacke.map(([x, y]) => slike.map(i => { const c = document.createElement("canvas"); c.width = 1; c.height = 1; const g = c.getContext("2d"); g.drawImage(i, x, y, 1, 1, 0, 0, 1, 1); return [...g.getImageData(0, 0, 1, 1).data]; }));
}, [sve.map(b => b.toString("base64")), tacke]);
tacke.forEach(([x, y], i) => log(`  piksel (${x},${y}) po snimku [H0..H4,F0,F1]: ${vrednosti[i].map(v => v.slice(0, 3).join("/")).join("  ")}`));
for (const [i, [x, y]] of tacke.slice(0, 6).entries()) for (const k of [0, 1]) await isecak(sve[k], x, y, `isecak-${i}-${oznaka(k)}-${x}x${y}.png`);

// ── KORAK 2: piksel → DOM ────────────────────────────────────────────────
const mapa = tacke.length ? (await zoomSesija(P_HEAD, { tacke })).dom : [];
for (const d of mapa) log(`Korak 2: (${d.x},${d.y}) → CSS (${d.css.join(",")}) → ${d.element} rect ${JSON.stringify(d.rect)} udaljenost od ivice ${d.naIvici}px font ${d.size}/${d.lh} border ${d.border} transform ${d.transform} opacity ${d.opacity}`);

// ── KORAK 3: semantički ugovor HEAD vs foundation ───────────────────────
const razUgovora = razlikeUgovora(head[0].ugovor, ref[0].ugovor);
const razHead = head.slice(1).flatMap(h => razlikeUgovora(head[0].ugovor, h.ugovor));
log(`Korak 3: ugovor HEAD == foundation: ${razUgovora.length === 0}${razUgovora.length ? " — " + razUgovora.slice(0, 5).join(" | ") : ""}`);
log(`         ugovor stabilan kroz 5 HEAD sesija: ${razHead.length === 0}${razHead.length ? " — " + razHead.slice(0, 3).join(" | ") : ""}`);
log(`         fokus: HEAD ${JSON.stringify(head[0].fokus)} foundation ${JSON.stringify(ref[0].fokus)}`);
log(`         ključno: zoom ${head[0].zoom}, DPR ${head[0].ugovor.dpr}, preliv ${head[0].ugovor.preliv}, nav ${head[0].ugovor.nav}, panel ${head[0].ugovor.panel}, naziv ≤ ${head[0].ugovor.najviseRedovaNaziva} reda, min font ${head[0].ugovor.minFont.join(" ")}`);

await writeFile(OUT + "zoom200-forensic.json", JSON.stringify({ platforma: process.platform, parovi: rez, vrednosti: tacke.map((t, i) => ({ t, v: vrednosti[i] })), dom: mapa,
  ugovorHead: head[0].ugovor, ugovorRef: ref[0].ugovor, razlikeUgovora: razUgovora, razlikeHead: razHead, fokus: { head: head.map(h => h.fokus), ref: ref.map(r => r.fokus) } }, null, 2));
await browser.close();
await Promise.all([sH, sR].map(d => new Promise(r => { d.once("exit", r); d.kill(); })));
await rm(refDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
log("Gotovo: shots/zoom200-forensic/");
