# NS004 — matrica tvrdnji javnog sajta

Pravilo (founder): **nema tvrdnje bez živog puta u proizvodu.** Na sajtu je samo
tekst sa statusom ALLOWED. Dokaz je ponašanje koje testovi izvršavaju, ne poruka
commita. Put važi za V2 (`/app` sa `VINDEX_V2_NG_PRIMARY_ENABLED`, sada i
`/v2/preview/`); isti tok postoji i u klasičnom `/app` dok je prekidač isključen.

| # | Tvrdnja (suština) | Put u proizvodu | Dokaz | Status |
|---|---|---|---|---|
| 1 | Posle prijave vidite listu aktivnih predmeta: naziv, broj, stranke, stanje, poslednja izmena | /app → Predmeti (LIVE) | verify:live-matters, e2e:fastapi 1–6, e2e:primary P3; produkcija NS003 (GET /api/predmeti 200) | ALLOWED |
| 2 | Pretraga po nazivu, broju predmeta i strankama; sortiranje liste | registar: polje pretrage, zaglavlja kolona | verify:live-matters („LIVE pretraga“), verify:live-matrix | ALLOWED |
| 3 | Otvorite predmet: broj, vrsta, tužilac, tuženi, vrednost spora, klijenti — samo uneta polja | klik na naziv → Pregled | verify:live-matter 1A, e2e:fastapi 13 | ALLOWED |
| 4 | Dokumenti predmeta na jednom mestu u predmetu; izaberite dokument i pročitajte izdvojeni tekst | Predmet → Dokumenti → izbor | verify:live-matter 2A, e2e:fastapi 13 | ALLOWED |
| 5 | Ako tekst dokumenta nije izdvojen, to piše jasno | Dokumenti → dokument bez teksta | verify:live-matter „2.istina“, e2e:fastapi 13 | ALLOWED |
| 6 | Radni prostor prikazuje samo podatke kancelarije; primeri se tu ne prikazuju | /app LIVE | e2e:primary P1/P3 (bez DEMO), verify:live-matrix „bez demo“ | ALLOWED |
| 7 | Svaki nalog vidi samo predmete kojima ima pristup | server: vlasnik iz tokena, postojeće delegirano čitanje | test_v2_ng_detail, e2e:fastapi 11/13 (izolacija) | ALLOWED |
| 8 | Neuspelo učitavanje se nikad ne prikazuje kao prazna lista | sva stanja greške | verify:live-states, verify:live-matter 1E/2E | ALLOWED |
| 9 | Prijava koristi postojeći Vindex nalog | /app (prijava) | e2e:primary P5 | ALLOWED |
| — | AI analiza dokumenata / predmeta | nije u V2 toku u NS004 | — | FORBIDDEN |
| — | Praćenje rokova, podsetnici, „nikad ne propustite rok“ | V2 nema povezan tok rokova | — | FORBIDDEN |
| — | „Sve na jednom mestu“, „jedina platforma“, „revolucija“ | apsolutno / prazno | — | FORBIDDEN |
| — | Web3 / digitalna imovina, vizija, tehnologija, bezbednosne tehnike | nema V2 korisničkog toka / interni detalji | — | FORBIDDEN |
| — | Zahtev za pristup (lista čekanja) | POST /waitlist/prijava postoji, ali nije dokazan u produkciji bez upisa | — | FORBIDDEN u NS004 |
| — | Preuzimanje originalnog fajla | ruta postoji, V2 je ne nudi u NS004 | — | FORBIDDEN |

Povučene marketinške rute (301 na odgovarajući odeljak početne strane):
`/kako-radi`, `/sposobnosti`, `/za-advokate`, `/web3`, `/bezbednost`, `/vizija`,
`/tehnologija`, `/beta`, `/kontakt`. Pravne stranice (`/privacy`, `/terms`,
`/security`, `/dpa`, `/ai-disclosure`, `/bezbednosni-list`) nisu menjane.
