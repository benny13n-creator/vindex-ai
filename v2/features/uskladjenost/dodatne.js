/* Vindex V2 — Usklađenost, dodatne analize (G7 Wallet Provenance, G8
 * Source-of-Funds Dossier).
 *
 * Zasebni blokovi, NE deo ANALIZE kataloga: oba imaju drugaciji ugovor od
 * "tekst -> tekst" (G7 trazi Ethereum adresu i vraca deterministicke
 * on-chain nalaze; G8 vraca PDF, ne JSON). Prisiljavanje u zajednicki
 * oblik bi zakomplikovalo obrazac koji je upravo ispravljen za preostalih
 * pet (v. domain/uskladjenost.js, Z017.2 G4/G5 popravka).
 */

import { posalji } from "../../platform/http.js";
import { jePrekid, porukaZaKorisnika, VRSTA } from "../../platform/errors.js";
import { naPrijavu, token } from "../../platform/auth.js";
import { ostavi } from "../../platform/obavestenje.js";
import { uWalletProvenance, validnaEthAdresa } from "../../domain/walletProvenance.js";

function el(tag, klasa, tekst) {
  const e = document.createElement(tag);
  if (klasa) e.className = klasa;
  if (tekst !== undefined) e.textContent = tekst;
  return e;
}

function nalazRed(n) {
  const li = el("li");
  const red = el("p", "v2-forma__red");
  red.appendChild(el("span", "", n.opis));
  if (n.poverenje) red.appendChild(el("span", "v2-meta", " · " + n.poverenje));
  li.appendChild(red);
  return li;
}

function prikaziWalletRezultat(kontejner, w) {
  kontejner.replaceChildren();
  const okvir = el("div", "v2-podblok");
  okvir.appendChild(el("h4", "v2-natkapa", "Nalaz za " + w.adresa));

  if (w.pokrivenost.lanac) {
    okvir.appendChild(el("p", "v2-meta",
      `${w.pokrivenost.lanac} · izvor: ${w.pokrivenost.izvor}`
      + (w.pokrivenost.ethTransakcija !== null ? ` · ${w.pokrivenost.ethTransakcija} transakcija analizirano` : "")));
  }

  if (w.sankcionisan !== null) {
    const p = el("p", w.sankcionisan ? "v2-forma__poruka v2-forma__poruka--greska" : "v2-forma__poruka v2-forma__poruka--uspeh");
    p.textContent = w.sankcionisan
      ? "Novčanik JESTE pronađen na OFAC SDN listi."
      : "Novčanik NIJE pronađen na trenutno učitanoj OFAC SDN listi.";
    okvir.appendChild(p);
  }

  if (w.sankcioni.length) {
    okvir.appendChild(el("h5", "v2-natkapa", "Sankcioni nalazi"));
    const ul = el("ul", "v2-lista-tanka");
    for (const n of w.sankcioni) ul.appendChild(nalazRed(n));
    okvir.appendChild(ul);
  }
  if (w.analiticki.length) {
    okvir.appendChild(el("h5", "v2-natkapa", "Analitičke opservacije"));
    const ul = el("ul", "v2-lista-tanka");
    for (const n of w.analiticki) ul.appendChild(nalazRed(n));
    okvir.appendChild(ul);
  }

  if (w.ogranicenja.length) {
    okvir.appendChild(el("h5", "v2-natkapa", "Ograničenja analize"));
    const ul = el("ul", "v2-lista-tanka");
    for (const o of w.ogranicenja) ul.appendChild(el("li", "v2-meta", o));
    okvir.appendChild(ul);
  }

  kontejner.appendChild(okvir);
}

/** G7 -- Wallet Provenance. */
export function blokWalletProvenance(ciklus) {
  const b = el("div", "v2-podblok");
  b.appendChild(el("h3", "v2-natkapa", "Provera novčanika (Wallet Provenance)"));
  b.appendChild(el("p", "v2-meta",
    "Starost/aktivnost novčanika i provera direktnih kontakata protiv OFAC SDN liste. "
    + "Ethereum mainnet, samo direktni (1-hop) kontakti."));

  const red = el("div", "v2-forma__red");
  const adresa = el("input");
  adresa.type = "text";
  adresa.placeholder = "0x...";
  adresa.setAttribute("aria-label", "Ethereum adresa novčanika");
  const dugme = el("button", "v2-dugme", "Proveri");
  dugme.type = "button";
  red.append(adresa, dugme);
  b.appendChild(red);

  const poruka = el("div", "v2-forma__poruka");
  poruka.setAttribute("role", "alert");
  poruka.hidden = true;
  b.appendChild(poruka);

  const rezultatMesto = el("div");
  b.appendChild(rezultatMesto);

  ciklus.slusaj(dugme, "click", async () => {
    if (!validnaEthAdresa(adresa.value)) {
      poruka.className = "v2-forma__poruka v2-forma__poruka--greska";
      poruka.textContent = "Unesite ispravnu Ethereum adresu (0x + 40 hex znakova).";
      poruka.hidden = false;
      return;
    }
    dugme.disabled = true;
    dugme.textContent = "Proverava se…";
    poruka.hidden = true;
    try {
      const r = await posalji("/web3/wallet-provenance", {
        telo: { adresa: adresa.value.trim() }, signal: ciklus.prekidac().signal,
      });
      if (ciklus.ugasen) return;
      prikaziWalletRezultat(rezultatMesto, uWalletProvenance(r));
    } catch (err) {
      if (jePrekid(err) || ciklus.ugasen) return;
      if (err && err.vrsta === VRSTA.NEPRIJAVLJEN) { naPrijavu(); return; }
      poruka.className = "v2-forma__poruka v2-forma__poruka--greska";
      poruka.textContent = "Provera nije uspela. " + porukaZaKorisnika(err);
      poruka.hidden = false;
    } finally {
      dugme.disabled = false;
      dugme.textContent = "Proveri";
    }
  });

  return b;
}

/** G8 -- Source-of-Funds Dossier (PDF). Isti fetch+Bearer+blob obrazac kao
 * H8 (Kancelarija/Nalog izvoz) -- ruta zahteva Authorization header, obican
 * <a href> ne bi ga poneo. */
export function blokSourceOfFundsDossier(ciklus) {
  const b = el("div", "v2-podblok");
  b.appendChild(el("h3", "v2-natkapa", "Source-of-Funds izveštaj (PDF)"));
  b.appendChild(el("p", "v2-meta",
    "Kombinuje spremnost dokumentacije, CARF/DAC8 pregled i (opciono) proveru novčanika u jedan PDF."));

  const opis = el("textarea");
  opis.placeholder = "Opis posedovane dokumentacije o kripto imovini i transakcijama (najmanje 30 znakova).";
  opis.rows = 3;
  b.appendChild(opis);

  const walletRed = el("div", "v2-forma__red");
  const wallet = el("input");
  wallet.type = "text";
  wallet.placeholder = "Ethereum adresa (opciono, 0x...)";
  wallet.setAttribute("aria-label", "Ethereum adresa (opciono)");
  walletRed.appendChild(wallet);
  b.appendChild(walletRed);

  const dugme = el("button", "v2-dugme", "Preuzmi PDF");
  dugme.type = "button";
  b.appendChild(dugme);

  const poruka = el("div", "v2-forma__poruka");
  poruka.setAttribute("role", "alert");
  poruka.hidden = true;
  b.appendChild(poruka);

  ciklus.slusaj(dugme, "click", async () => {
    if (opis.value.trim().length < 30) {
      poruka.className = "v2-forma__poruka v2-forma__poruka--greska";
      poruka.textContent = "Opis dokumentacije mora imati najmanje 30 znakova.";
      poruka.hidden = false;
      return;
    }
    if (wallet.value.trim() && !validnaEthAdresa(wallet.value)) {
      poruka.className = "v2-forma__poruka v2-forma__poruka--greska";
      poruka.textContent = "Adresa novčanika nije ispravna (0x + 40 hex znakova) — ostavite prazno ako je nemate.";
      poruka.hidden = false;
      return;
    }
    dugme.disabled = true;
    dugme.textContent = "Priprema se…";
    poruka.hidden = true;
    try {
      const t = token();
      const odgovor = await fetch("/web3/source-of-funds-dossier", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(t ? { Authorization: "Bearer " + t } : {}),
        },
        credentials: "same-origin",
        body: JSON.stringify({
          opis_dokumentacije: opis.value.trim(),
          wallet_adresa: wallet.value.trim(),
        }),
      });
      if (!odgovor.ok) throw new Error("HTTP " + odgovor.status);
      const blob = await odgovor.blob();
      const url = URL.createObjectURL(blob);
      const cd = odgovor.headers.get("Content-Disposition") || "";
      const m = cd.match(/filename="([^"]+)"/);
      const a = el("a");
      a.href = url;
      a.download = m ? m[1] : "vindex-source-of-funds-dossier.pdf";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      ostavi("Izveštaj je preuzet.", "uspeh");
    } catch (err) {
      poruka.className = "v2-forma__poruka v2-forma__poruka--greska";
      poruka.textContent = "Izveštaj nije generisan. Pokušajte ponovo.";
      poruka.hidden = false;
    } finally {
      dugme.disabled = false;
      dugme.textContent = "Preuzmi PDF";
    }
  });

  return b;
}
