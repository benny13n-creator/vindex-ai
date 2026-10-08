// Vindex V2 NG — NS003 Task 3: ugovor kanonske sesije u pregledaču.
// Pokretanje: `node tests/session-contract.mjs` (bez servera, bez mreže).
//
// V2 NG nema svoj login: čita zapis koji upisuje POSTOJEĆA prijava na /app.
// Ovaj test pada ako se V2 NG ključ ili oblik zapisa razidu od onoga što
// postojeći Vindex STVARNO upisuje. Kanonski ključ se ne prepisuje kao još
// jedna magična konstanta, već se IZVODI iz izvora:
//   index.html (/app) učitava /static/supabase.min.js i /static/vindex.js;
//   vindex.js zove createClient(SUPABASE_URL, SUPABASE_ANON_KEY) bez opcija;
//   supabase-js tada podrazumeva ključ `sb-<prvi deo hosta>-auth-token`.
// Isti ključ mora da izvede i postojeći /app-v2 (v2/platform/auth.js) i V2 NG
// (src/session.js, izvršen u izolovanom kontekstu sa instrumentisanim
// localStorage-om, konzolom i mrežom).
//
// Namerna razlika: /app-v2 osvežava istekao token; V2 NG NE (istekla sesija =
// „Sesija je istekla“, bez Supabase refresh zahteva). Ovaj test to zaključava.

import { readFileSync } from "node:fs";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const KOREN = fileURLToPath(new URL("../..", import.meta.url));
const NG = fileURLToPath(new URL("..", import.meta.url));
const procitaj = (p) => readFileSync(p, "utf8");
let pada = 0, ukupno = 0;
function zapisi(grupa, naziv, ok, detalj = "") {
  ukupno++; if (!ok) pada++;
  console.log(`${ok ? "PASS" : "FAIL"}  [${grupa}] ${naziv}${detalj ? " — " + detalj : ""}`);
}
// Komentari se uklanjaju pre statičkih provera koda (u komentarima se te reči
// legitimno pominju, npr. „nema POST na Supabase refresh“).
const bezKomentara = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`\\])\/\/[^\n]*/g, "$1");
const izvedi = (url) => "sb-" + new URL(url).hostname.split(".")[0] + "-auth-token";

// ── 1. Kanonski upisivač: postojeći /app ─────────────────────────────────
const indexHtml = procitaj(KOREN + "index.html");
const vindexJs = procitaj(KOREN + "static/vindex.js");
const sbJs = procitaj(KOREN + "static/supabase.min.js");
zapisi("kanon", "/app (index.html) učitava vendored supabase-js i vindex.js",
  /<script src="\/static\/supabase\.min\.js[^"]*"><\/script>/.test(indexHtml) && /<script src="\/static\/vindex\.js[^"]*"><\/script>/.test(indexHtml));
const urlV1 = (vindexJs.match(/var SUPABASE_URL\s*=\s*'([^']+)'/) || [])[1];
zapisi("kanon", "vindex.js definiše tačno jedan SUPABASE_URL", !!urlV1 && (vindexJs.match(/var SUPABASE_URL\s*=/g) || []).length === 1, urlV1);
const pozivi = bezKomentara(vindexJs).match(/createClient\([^)]*\)/g) || [];
zapisi("kanon", "vindex.js: jedini createClient je (SUPABASE_URL, SUPABASE_ANON_KEY), bez opcija",
  pozivi.length === 1 && /^createClient\(\s*SUPABASE_URL\s*,\s*SUPABASE_ANON_KEY\s*\)$/.test(pozivi[0]), pozivi.join(" | "));
zapisi("kanon", "vindex.js ne menja ključ skladišta (nema storageKey)", !/storageKey/.test(vindexJs));
const sablon = sbJs.match(/let (\w+)=`sb-\$\{(\w+)\.hostname\.split\("\."\)\[0\]\}-auth-token`/);
zapisi("kanon", "supabase-js podrazumeva ključ sb-<host[0]>-auth-token", !!sablon);
zapisi("kanon", "taj podrazumevani ključ ide u auth.storageKey kad klijent ne zada opcije",
  !!sablon && sbJs.includes(`auth:{...St,storageKey:${sablon[1]}}`) && /this\.storageKey=a\.auth\.storageKey/.test(sbJs));
const KANON = urlV1 ? izvedi(urlV1) : null;
const REF = urlV1 ? new URL(urlV1).hostname.split(".")[0] : null;
console.log(`INFO  [kanon] izveden ključ: ${KANON} (ref ${REF})`);

// ── 2. Postojeći /app-v2 ─────────────────────────────────────────────────
const authV2 = procitaj(KOREN + "v2/platform/auth.js");
const urlV2 = (authV2.match(/const SUPABASE_URL\s*=\s*"([^"]+)"/) || [])[1];
zapisi("app-v2", "/app-v2 koristi isti Supabase projekat", urlV2 === urlV1, `${urlV2}`);
zapisi("app-v2", "/app-v2 izvodi ključ istim pravilom (sb-<ref>-auth-token)",
  /const REF = new URL\(SUPABASE_URL\)\.hostname\.split\("\."\)\[0\];/.test(authV2) && /const KLJUC = `sb-\$\{REF\}-auth-token`;/.test(authV2));
zapisi("app-v2", "/app-v2: access_token na vrhu zapisa, base64- prefiks podržan, expires_at u sekundama",
  /!o\.access_token/.test(authV2) && /startsWith\("base64-"\)/.test(authV2) && /o\.expires_at \* 1000/.test(authV2));

// ── 3. V2 NG: izvor ──────────────────────────────────────────────────────
const izvorNg = procitaj(NG + "src/session.js");
const kodNg = bezKomentara(izvorNg);
const urlNg = (izvorNg.match(/var SUPABASE_URL\s*=\s*"([^"]+)"/) || [])[1];
zapisi("ng-izvor", "V2 NG koristi isti Supabase projekat (ref)", urlNg === urlV1 && new URL(urlNg).hostname.split(".")[0] === REF, `${urlNg}`);
const zabranjeno = ["setItem", "removeItem", ".clear(", "fetch", "XMLHttpRequest", "sendBeacon", "WebSocket", "refresh_token", "grant_type", "/auth/v1",
  "console.", "sessionStorage", "document.cookie", "indexedDB", "location.", "innerHTML", "textContent", "setAttribute"];
const nadjeno = zabranjeno.filter(z => kodNg.includes(z));
zapisi("ng-izvor", "kod session.js ne piše/briše sesiju, nema mreže, refresh-a, logovanja, URL-a ni DOM-a", nadjeno.length === 0, nadjeno.join(", "));

// ── 4. V2 NG: izvršavanje u izolovanom kontekstu ─────────────────────────
const tragovi = { upisi: [], mreza: [], konzola: [], dom: [] };
function napraviKontekst(sirovo, { bacaPriCitanju = false } = {}) {
  const skladiste = new Map(sirovo === null ? [] : [[KANON, sirovo]]);
  const localStorage = {
    getItem: (k) => { if (bacaPriCitanju) throw new Error("SecurityError"); return skladiste.has(k) ? skladiste.get(k) : null; },
    setItem: (k) => { tragovi.upisi.push("setItem " + k); },
    removeItem: (k) => { tragovi.upisi.push("removeItem " + k); },
    clear: () => { tragovi.upisi.push("clear"); },
    key: () => null, get length() { return skladiste.size; },
  };
  const mreza = (ime) => (...a) => { tragovi.mreza.push(ime + " " + String(a[0]).slice(0, 60)); throw new Error("mreža zabranjena"); };
  const konzola = new Proxy({}, { get: (_, ime) => (...a) => tragovi.konzola.push(ime + " " + a.map(String).join(" ")) });
  const document = new Proxy({ hidden: false, addEventListener() {} }, {
    get: (t, ime) => (ime in t ? t[ime] : (tragovi.dom.push(String(ime)), undefined)),
  });
  const window = {
    localStorage, document, console: konzola, URL, Date, JSON, Math, atob: (s) => Buffer.from(s, "base64").toString("latin1"),
    escape, decodeURIComponent, setTimeout: () => 0, clearTimeout: () => {}, addEventListener() {},
    fetch: mreza("fetch"), XMLHttpRequest: function () { mreza("XMLHttpRequest")(); }, navigator: { sendBeacon: mreza("sendBeacon") },
    location: { href: "https://vindex.rs/v2/preview/?rezim=live", search: "?rezim=live", hash: "" },
  };
  window.window = window;
  const ctx = vm.createContext(window);
  vm.runInContext(izvorNg, ctx, { filename: "session.js" });
  return { S: ctx.VxSesija, window };
}
const sad = () => Math.floor(Date.now() / 1000);
const zapis = (dodatak = {}) => ({ access_token: "vx-ugovor-TOKEN-NE-U-LOG-77", refresh_token: "vx-ugovor-REFRESH-NE-U-LOG-88", expires_at: sad() + 3600,
  token_type: "bearer", user: { id: "korisnik-ugovor", email: "k@primer.test" }, ...dodatak });
const b64 = (o) => "base64-" + Buffer.from(JSON.stringify(o), "utf8").toString("base64");

{
  const { S, window } = napraviKontekst(JSON.stringify(zapis()));
  zapisi("ng-ključ", "V2 NG čita IZVEDENI kanonski ključ", S.KLJUC === KANON, S.KLJUC);
  zapisi("ng-zapis", "običan JSON zapis supabase-js → prijavljen", S.proveri() === "prijavljen");
  zapisi("ng-zapis", "user.id iz zapisa je korisnik", S.stanje().korisnik === "korisnik-ugovor");
  zapisi("ng-zapis", "access_token sa vrha zapisa je token", S.token() === "vx-ugovor-TOKEN-NE-U-LOG-77");
  zapisi("ng-zapis", "javni opis stanja ne nosi token ni refresh_token", !/NE-U-LOG/.test(JSON.stringify(S.stanje())));
  zapisi("ng-zapis", "adresa stranice nije promenjena", window.location.href === "https://vindex.rs/v2/preview/?rezim=live" && window.location.hash === "");
}
{
  const { S } = napraviKontekst(b64(zapis()));
  zapisi("ng-zapis", "base64- zapis → isto stanje, korisnik i token", S.proveri() === "prijavljen" && S.stanje().korisnik === "korisnik-ugovor" && S.token() === "vx-ugovor-TOKEN-NE-U-LOG-77");
}
{
  const { S } = napraviKontekst(JSON.stringify({ currentSession: zapis(), expiresAt: sad() + 3600 }));
  zapisi("ng-zapis", "zastareli oblik (currentSession) nije prihvaćen kao prijava", S.proveri() === "greska" && S.token() === null);
}
{
  const o = zapis(); delete o.user; o.user_id = "korisnik-ugovor";
  const { S } = napraviKontekst(JSON.stringify(o));
  zapisi("ng-zapis", "korisnik van user.id nije prihvaćen", S.proveri() === "greska" && S.token() === null);
}
{
  const { S } = napraviKontekst(JSON.stringify({ session: zapis(), user: { id: "korisnik-ugovor" } }));
  zapisi("ng-zapis", "token van vrha zapisa nije prihvaćen", S.proveri() === "greska" && S.token() === null);
}
for (const [naziv, istice, ocekivano] of [
  ["expires_at je u sekundama: +3600 s → važeća", sad() + 3600, "prijavljen"],
  ["istekao (−60 s) → „istekla“", sad() - 60, "istekla"],
  ["ističe za 10 s → „istekla“ (rezerva, bez pokušaja osvežavanja)", sad() + 10, "istekla"],
]) {
  const { S } = napraviKontekst(JSON.stringify(zapis({ expires_at: istice })));
  zapisi("ng-istek", naziv, S.proveri() === ocekivano && (ocekivano === "prijavljen") === (S.token() !== null), S.stanje().stanje);
}
{
  const { S } = napraviKontekst(null);
  zapisi("ng-istek", "bez zapisa → „neprijavljen“, bez tokena", S.proveri() === "neprijavljen" && S.token() === null);
}
{
  const { S } = napraviKontekst("x", { bacaPriCitanju: true });
  zapisi("ng-istek", "localStorage nedostupan → „greska“ (fail closed)", S.proveri() === "greska" && S.token() === null);
}
const app = procitaj(NG + "src/app.js");
zapisi("ng-istek", "istekla sesija se prikazuje kao „Sesija je istekla“", /"istekla": \["Sesija je istekla",/.test(app));
zapisi("bezbednost", "nijedan upis/brisanje localStorage-a ni u jednom slučaju", tragovi.upisi.length === 0, tragovi.upisi.slice(0, 3).join(","));
zapisi("bezbednost", "nijedan mrežni pokušaj (nema Supabase refresh POST-a)", tragovi.mreza.length === 0, tragovi.mreza.slice(0, 3).join(","));
zapisi("bezbednost", "nijedan ispis u konzolu (token se ne loguje)", tragovi.konzola.length === 0, tragovi.konzola.slice(0, 2).join(" | ").replace(/vx-ugovor-\S+/g, "<token>"));
zapisi("bezbednost", "session.js ne dodiruje DOM osim hidden/addEventListener", tragovi.dom.length === 0, tragovi.dom.join(","));

console.log(`\n${ukupno - pada}/${ukupno} PASS`);
process.exit(pada ? 1 : 0);
