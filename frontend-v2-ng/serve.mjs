// Minimalan statički server bez zavisnosti: node serve.mjs [port]
import http from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const koren = fileURLToPath(new URL(".", import.meta.url));
const port = Number(process.argv[2] || process.env.PORT || 4317);
const tipovi = { ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".woff2": "font/woff2", ".png": "image/png", ".svg": "image/svg+xml" };

http.createServer(async (req, res) => {
  const putanja = decodeURIComponent(new URL(req.url, "http://x").pathname);
  const rel = normalize(putanja === "/" ? "/index.html" : putanja).replace(/^([\/])+/, "");
  if (rel.startsWith("..") || rel.startsWith("node_modules")) { res.writeHead(403).end(); return; }
  try {
    const telo = await readFile(join(koren, rel));
    res.writeHead(200, { "Content-Type": tipovi[extname(rel)] || "application/octet-stream", "Cache-Control": "no-store" });
    res.end(telo);
  } catch { res.writeHead(404).end("404"); }
}).listen(port, "127.0.0.1", () => console.log(`Vindex V2 NG prototip: http://127.0.0.1:${port}/`));
