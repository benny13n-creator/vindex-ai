// Vindex V2 NG — otisak DEMO ekrana (tekst + struktura, bez piksela).
//
// Zašto postoji: snimci postojećih suite-ova NISU deterministični (animirana
// pozadina — dva uzastopna pokretanja istog koda daju različite PNG-ove), pa ne
// mogu dokazati da DEMO nije promenjen. Ovaj otisak meri ono što korisnik čita:
// redove registra, broj, panel, oznaku demo podataka, placeholder pretrage.
//
// `node tests/demo-fingerprint.mjs`            → upoređuje sa OCEKIVANO ispod
// `node tests/demo-fingerprint.mjs --ispisi`   → samo ispisuje trenutne otiske
//
// OCEKIVANO je izmereno na nepromenjenom foundation commit-u `1eb20976`.

import { chromium } from "playwright";
import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import http from "node:http";
import { fileURLToPath } from "node:url";

// Sopstveni server (port 4393), da test ne zavisi od spolja pokrenutog 4317.
const PORT = 4393;
const server = spawn(process.execPath, ["serve.mjs", String(PORT)], {
  cwd: fileURLToPath(new URL("..", import.meta.url)), stdio: "ignore",
});
for (let i = 0; i < 100; i++) {
  const ok = await new Promise(r => http.get({ host: "127.0.0.1", port: PORT, path: "/" }, s => { s.resume(); r(true); }).on("error", () => r(false)));
  if (ok) break;
  await new Promise(r => setTimeout(r, 50));
}
const BASE = `http://127.0.0.1:${PORT}/`;
const ISPISI = process.argv.includes("--ispisi");

const OCEKIVANO = {
  "standard": "a2d28685dc5e4234",
  "veliko": "953a2b6b12f471b7",
  "prazno": "8f1039512b0383f7",
};
const SCENARIJI = { standard: "", veliko: "?predmeti=veliko", prazno: "?predmeti=prazno&paznja=prazno" };

const browser = await chromium.launch();
let pada = 0;
for (const [ime, upit] of Object.entries(SCENARIJI)) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
  const p = await ctx.newPage();
  await p.goto(BASE + upit);
  await p.evaluate(() => document.fonts.ready);
  const otisak = await p.evaluate(() => {
    const t = (sel) => Array.from(document.querySelectorAll(sel)).map(e => (e.hidden ? "[H]" : "") + e.textContent.replace(/\s+/g, " ").trim());
    return JSON.stringify({
      redovi: t("#rows tr"),
      broj: t("#count"),
      prazno: t("#empty, #empty-title, #empty-text"),
      panel: t("#attention li, #attention-empty, #attention-more, #demo-date, .panel__note"),
      oznaka: t(".demo-badge, .account"),
      placeholder: document.getElementById("pretraga").placeholder,
      pretragaOnemogucena: document.getElementById("pretraga").disabled,
      caption: t(".cases caption"),
    });
  });
  const h = createHash("sha256").update(otisak).digest("hex").slice(0, 16);
  if (ISPISI) console.log(`${ime}: ${h}`);
  else {
    const ok = h === OCEKIVANO[ime];
    if (!ok) pada++;
    console.log(`${ok ? "PASS" : "FAIL"}  [demo-otisak] ${ime} — ${h}${ok ? "" : " (očekivano " + OCEKIVANO[ime] + ")"}`);
  }
  await ctx.close();
}
await browser.close();
server.kill();
process.exit(pada ? 1 : 0);
