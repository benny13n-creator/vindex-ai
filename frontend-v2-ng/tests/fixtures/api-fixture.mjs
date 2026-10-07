// Fixture server za LIVE testove: statika V2 ekrana + programabilan `/api/*`.
//
// Isti izvor (origin) kao stranica, isto kao produkcija gde V2 i API dele host.
// Sluša ISKLJUČIVO na 127.0.0.1. Nikad ne kontaktira produkciju, Supabase ni
// bilo koji spoljni host — svaki odgovor je ovde napisan.
//
// const f = await pokreniFixture((req, url, res) => {...vrati true ako je obradio...});
// f.port, f.zahtevi (svaki /api zahtev: metod, putanja, auth), await f.zatvori()

import http from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const KOREN = fileURLToPath(new URL("../..", import.meta.url));
const TIPOVI = { ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".woff2": "font/woff2", ".png": "image/png", ".svg": "image/svg+xml" };

export function json(res, status, telo, zaglavlja = {}) {
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", ...zaglavlja });
  res.end(typeof telo === "string" ? telo : JSON.stringify(telo));
}

export async function pokreniFixture(api) {
  const zahtevi = [];
  const otvoreni = new Set();
  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, "http://127.0.0.1");
    if (url.pathname.startsWith("/api/")) {
      zahtevi.push({
        metod: req.method, putanja: url.pathname, upit: url.search,
        parametri: Object.fromEntries(url.searchParams), auth: req.headers.authorization || null,
        kolacic: req.headers.cookie || null, vreme: Date.now(),
      });
      try {
        const obradjeno = await api(req, url, res);
        if (!obradjeno && !res.headersSent) json(res, 404, { error: "fixture: nepoznata ruta" });
      } catch (e) {
        if (!res.headersSent) json(res, 500, { error: "fixture izuzetak" });
      }
      return;
    }
    const rel = normalize(url.pathname === "/" ? "/index.html" : decodeURIComponent(url.pathname)).replace(/^([\/\\])+/, "");
    if (rel.startsWith("..") || rel.startsWith("node_modules")) { res.writeHead(403).end(); return; }
    try {
      const telo = await readFile(join(KOREN, rel));
      res.writeHead(200, { "Content-Type": TIPOVI[extname(rel)] || "application/octet-stream", "Cache-Control": "no-store" });
      res.end(telo);
    } catch { res.writeHead(404).end("404"); }
  });
  server.on("connection", (s) => { otvoreni.add(s); s.on("close", () => otvoreni.delete(s)); });
  await new Promise(r => server.listen(0, "127.0.0.1", r));
  return {
    port: server.address().port,
    zahtevi,
    async zatvori() {
      for (const s of otvoreni) s.destroy();
      await new Promise(r => server.close(r));
    },
  };
}
