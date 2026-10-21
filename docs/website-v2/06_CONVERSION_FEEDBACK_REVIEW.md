# Website V2 — Conversion & Feedback delta (2026-10-21)

## Problem i dokazi
Prethodni javni tekst isticao je roadmap i listu ograničenja pre nego što je objašnjavao korisničku korist. Osnivač je izričito naložio da budući planovi ne budu javni i tražio neposrednu prijavu greške iz aplikacije. Repozitorijum već ima autentifikovani `POST /api/support/poruka`, ali je vraćao uspeh čak i kada SMTP nije konfigurisan.

## Odluke / scope
- Marketinški hero, konkretna korist, kartice vrednosti i diskretna animacija (uz prefers-reduced-motion), CTA `Prijavi se za rani pristup`.
- `Razvoj` uklonjen iz globalne navigacije. Stara ruta ostaje samo kao generički kompatibilni URL bez roadmap stavki. Interni katalog sposobnosti nije falsifikovan niti brisan.
- Funkcionalnosti imaju benefit-first uvod. Prave oznake dostupnosti u katalogu ostaju: uklanjanje činjenica o dostupnosti pravilo bi lažnu korisničku očekivanje.
- Šire industrije su opisane kao potencijalne primene, ne kao regulatorno odobrena bankarska/notarska funkcionalnost.
- Bezbednost: poznati dobavljači i tok podataka, izvoz, razlika u nameni prema ChatGPT-u; ne tvrdimo da je Vindex objektivno bezbedniji bez uporedivog audita.
- V2: floating feedback forma u LIVE režimu, kategorije tehnički/AI/podatak/ostalo, bez uvođenja zasebnog backend servisa. Samo prijavljeni korisnik, bez automatskog screenshot-a ili poverljivog sadržaja; nema lažno pozitivnog slanja kada SMTP ne radi.
- Osnivačev privremeni javni kontakt: `benny13.n@gmail.com`.
- Srpski standardni oblik jeste **podaci**, ne **podatci**. Pogrešna globalna zamena nije urađena.

## Adversarial challenge
- Objavljivanje planiranih, neisporučenih funkcija i predstavljenje bankarskog nivoa usklađenosti kao dokazanog bilo bi obmanjujuće. Odbijeno.
- Marketinški prikaz može biti pozitivan bez prikrivanja stvarnog statusa funkcija; pravni/bezbednosni dokumenti zadržavaju stvarna ograničenja.
- Postojeći support API prethodno je davao `ok:true` čak i bez SMTP-a. Sada mail failure daje HTTP 503; aktivna produkcijska isporuka zahteva proveru SMTP-a i jedne autorizovane testne prijave.

## Acceptance evidence
PR CI proverava Python, security, production-parity i V2 NG. Pre merge-a proveriti `python scripts/gradi_sajt.py --provera`, marketinške rute i app feedback UI sa pravom autorizacijom i negativnim ishodom. Bez nezavisnog dokaza prijema nemoj tvrditi `mejl je stigao`.

## Non-goals
Nema novih funkcija za banke/notare, nema promene tenant izolacije, pravnog osnova, retention-a, baze, migracija, legacy redizajna niti izmene internog registra istine.