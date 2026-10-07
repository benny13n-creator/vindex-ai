// Minimalan statički server bez zavisnosti: node serve.mjs [port]
//
// DEV-ONLY API PROXY (isključen podrazumevano):
//   VINDEX_LOCAL_API_ORIGIN=http://127.0.0.1:8000 node serve.mjs
// prosleđuje `GET /api/*` na LOKALNI backend, da bi LIVE režim radio sa iste
// adrese (bez CORS-a). Prihvata ISKLJUČIVO loopback cilj (`127.0.0.1` ili
// `localhost`, `http`, eksplicitan port). Produkcija, Railway, Supabase ili bilo
// koji drugi host → server odbija da se pokrene. Samo GET: sve ostalo je 405 i
// nikad ne stiže do backend-a. Zaglavlja se NIKAD ne ispisuju (Authorization
// nosi token). Ovo nije produkciona arhitektura — samo alat za razvoj.
import http from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const koren = fileURLToPath(new URL(".", import.meta.url));
const port = Number(process.argv[2] || process.env.PORT || 4317);
const tipovi = { ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".woff2": "font/woff2", ".png": "image/png", ".svg": "image/svg+xml" };

const LOOPBACK = new Set(["127.0.0.1", "localhost"]);

/** Vraća URL loopback cilja ili baca grešku sa razlogom. */
function proveriIzvorApija(vrednost) {
  let u;
  try { u = new URL(vrednost); } catch { throw new Error("nije ispravan URL"); }
  if (u.protocol !== "http:") throw new Error("dozvoljen je samo http na loopback adresi");
  if (!LOOPBACK.has(u.hostname)) throw new Error(`host „${u.hostname}“ nije loopback (dozvoljeno: 127.0.0.1, localhost)`);
  if (!u.port) throw new Error("port mora biti naveden");
  if (u.username || u.password) throw new Error("kredencijali u URL-u nisu dozvoljeni");
  if (u.pathname !== "/" || u.search || u.hash) throw new Error("dozvoljen je samo origin, bez putanje i parametara");
  return u;
}

let cilj = null;
if (process.env.VINDEX_LOCAL_API_ORIGIN !== undefined) {
  try { cilj = proveriIzvorApija(process.env.VINDEX_LOCAL_API_ORIGIN); }
  catch (e) {
    console.error(`VINDEX_LOCAL_API_ORIGIN odbijen: ${e.message}. Server se ne pokreće.`);
    process.exit(1);
  }
}

function proksi(req, res) {
  if (req.method !== "GET") {
    res.writeHead(405, { "Allow": "GET", "Content-Type": "application/json; charset=utf-8" });
    res.end(JSON.stringify({ error: "Dev proxy prosleđuje samo GET." }));
    return;
  }
  const zaglavlja = { accept: req.headers.accept || "application/json" };
  if (req.headers.authorization) zaglavlja.authorization = req.headers.authorization;
  const zahtev = http.request({
    host: cilj.hostname, port: Number(cilj.port), method: "GET", path: req.url,
    headers: zaglavlja, timeout: 30000,
  }, (odg) => {
    res.writeHead(odg.statusCode || 502, {
      "Content-Type": odg.headers["content-type"] || "application/octet-stream",
      "Cache-Control": "no-store",
    });
    odg.pipe(res);
  });
  zahtev.on("timeout", () => zahtev.destroy(new Error("timeout")));
  zahtev.on("error", () => {
    if (!res.headersSent) res.writeHead(502, { "Content-Type": "application/json; charset=utf-8" });
    res.end(JSON.stringify({ error: "Lokalni backend nije dostupan." }));
  });
  zahtev.end();
}

http.createServer(async (req, res) => {
  const putanja = decodeURIComponent(new URL(req.url, "http://x").pathname);
  if (cilj && putanja.startsWith("/api/")) { proksi(req, res); return; }
  const rel = normalize(putanja === "/" ? "/index.html" : putanja).replace(/^([\/])+/, "");
  if (rel.startsWith("..") || rel.startsWith("node_modules")) { res.writeHead(403).end(); return; }
  try {
    const telo = await readFile(join(koren, rel));
    res.writeHead(200, { "Content-Type": tipovi[extname(rel)] || "application/octet-stream", "Cache-Control": "no-store" });
    res.end(telo);
  } catch { res.writeHead(404).end("404"); }
}).listen(port, "127.0.0.1", () => {
  console.log(`Vindex V2 NG prototip: http://127.0.0.1:${port}/`);
  if (cilj) console.log(`DEV API proxy: GET /api/* → ${cilj.origin} (samo loopback)`);
});
