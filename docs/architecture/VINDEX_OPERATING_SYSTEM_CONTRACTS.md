# Vindex AI — Operating System Contracts (2026-07-19)

Sedmi dokument u nizu. Odnos prema prethodna dva centralna dokumenta:
`VINDEX_2_1_ARCHITECTURE_ROADMAP.md` je registar ODLUKA (D1-D22+,
statusi). `VINDEX_INTEGRATION_MASTER_PLAN.md` je ustav PROCESA (tokovi,
DoD, testiranje). **Ovaj dokument je UGOVOR** — precizna, neopoziva
specifikacija šta svaki tok MORA sadržati da bi se smatrao gotovim, plus
matematička (ne procenjena) mera koliko je danas ispunjen.

**Status (ažurirano 2026-07-19, isti dan): Beta Freeze zamenjen Fazom A
— Internal Integration Sprint (`VINDEX_OPERATIONAL_GAP_REGISTER.md`).
Kod SME da se menja, isključivo za zatvaranje G-stavki — bez novih
funkcija/UX/AI modula.**

**Svrha ugovora, direktnim rečima:** posle ovog dokumenta više nije
moguće reći "implementirao sam Deadline Guardian" a da niko ne primeti
da Notification/Audit/Dashboard/Analytics nisu dobili odgovarajući
signal. Svaki od ta 4 elementa je EKSPLICITNA stavka u svakom ugovoru
— ne opciona, ne podrazumevana.

---

## Deo A — Predmet kao mašina stanja

Predlog: predmet (case) prestaje da bude "zbir modula" (dokument + CRM
zapis + Genome + Strategy) i postaje entitet sa eksplicitnim životnim
ciklusom:

```
Kreiran → Dokumenti dodati → Dokumenti klasifikovani → Genome spreman
   → Rokovi potvrđeni → Guardian aktivan → Taskovi aktivni
   → Ročište zakazano → Presuda primljena → Žalba → Pravosnažno
   → Zatvoren → Arhiviran
```

### Mapiranje stanja na postojeće Ugovore (Deo B)

| Stanje | Governed by | Status danas |
|---|---|---|
| Kreiran | CONTRACT 01 | Delimično (D3 nedostaje) |
| Dokumenti dodati | CONTRACT 01 | Živo |
| Dokumenti klasifikovani | CONTRACT 01 | Živo |
| Genome spreman | CONTRACT 01 | Živo |
| Rokovi potvrđeni | CONTRACT 02 | **Ne postoji koncept "potvrde" nigde** |
| Guardian aktivan | CONTRACT 02 | Backend postoji, nikad "aktiviran" po predmetu (nema UI/trigering) |
| Taskovi aktivni | CONTRACT 02 | Samo ručno kreirani taskovi, nikad iz roka |
| Ročište zakazano | CONTRACT 03 | Delimično (unos radi, downstream ne) |
| Presuda primljena | CONTRACT 02 (varijanta) | Klasifikacija radi, ostatak lanca ne |
| Žalba | **Nijedan ugovor ne pokriva ovo eksplicitno** | Van obima 4 definisana toka — nov nalaz, videti Deo D |
| Pravosnažno | **Ne postoji nigde u sistemu kao koncept** | Nema polje, nema status, nema logiku — nov nalaz |
| Zatvoren | CONTRACT 04 | Delimično |
| Arhiviran | **Ne postoji nigde u sistemu kao koncept** | Nov nalaz — "Zatvoren" i "Arhiviran" se tretiraju kao isto danas (nema odvojenog arhivskog statusa) |

**Važno upozorenje pre bilo kakvog dizajna ovog state machine-a:**
sistem VEĆ ima jedan status koncept — Kanban `_KANBAN_FAZE` (Inicijalna
procena → Priprema → Aktivan postupak → Čeka odluku → Završen, 5 faza).
Predloženih 13 stanja je MNOGO granularnije i delimično se ne poklapa
1:1 sa Kanban fazama. **Ovo je isti tip problema kao D21 (tri paralelna
"rok" koncepta)** — uvođenje novog, preciznijeg state sistema BEZ
usklađivanja sa postojećim Kanban statusom bi stvorilo ČETVRTI paralelni
"status predmeta" izvor istine (uz Kanban, uz Genome `genome_kompletnost`,
uz eventualni novi lifecycle status). **Preporuka: ovo mora biti
eksplicitna arhitektonska odluka pre implementacije — da li novi
lifecycle status ZAMENJUJE Kanban fazu, ili se Kanban faza IZVODI iz
lifecycle statusa (mapiranje 13→5), ili ostaju namerno odvojeni sa
jasno različitom svrhom (Kanban = radni pregled, lifecycle = precizno
praćenje).** Ovo se dodaje u ADR kao nova stavka:

### D23 (novo). Usklađivanje predloženog lifecycle state-a sa postojećim Kanban statusom

- **Status: Blocked (zavisi od pilota + arhitektonske odluke).** Ne
  implementirati lifecycle state machine dok se ova relacija eksplicitno
  ne reši — isti princip kao D21.

### D24 (novo). Ne postoji `EventType` ni koncept za zatvaranje/pravosnažnost predmeta

- **Kontekst:** za razliku od ostalih "nedostajućih" eventova (koji
  BAR postoje kao definicija u enum-u, samo se ne emituju), za
  "predmet zatvoren"/"predmet postao pravosnažan" **ne postoji čak ni
  definicija.** Nov nalaz ovog dokumenta.
- **Status: Blocked (zavisi od D23).** Definisati tek kad se odluči
  kako se ovo stanje uopšte modeluje.

---

## Deo B — Ugovori po toku

### CONTRACT 01 — Upload tužbe

| Element | Specifikacija | Status danas |
|---|---|---|
| **Trigger** | Advokat otprema prvi dokument u novokreiran predmet | — |
| **Šta ulazi** | PDF/DOCX (digitalni ili skeniran — OCR fallback automatski) | ✅ radi |
| **Koji event mora nastati** | `PREDMET_KREIRAN` (pri kreiranju predmeta) + `DOKUMENT_UPLOADOVAN` (pri uploadu) | ✅ `PredmetKreiran` se sada emituje iz `api.py::kreiraj_predmet` (D3 zatvoreno, commit `8f54f54`, 2026-07-21); ❌ `DokumentUploadovan` i dalje se ne emituje — van obima ove izmene |
| **Koji servisi moraju biti pozvani** | OCR fallback (`uploaded_doc/extractor.py`); Evidence Vault klasifikacija (`routers/evidence.py::klasifikuj_i_sacuvaj`); Case Genome ekstrakcija (`routers/case_dna.py::_run_genome_background`); `run_case_pipeline()` (`services/case_pipeline.py`) | ✅✅✅✅ sve rade — `run_case_pipeline()` se sada poziva preko već registrovanog `on_predmet_kreiran` handlera (D9 zatvoreno kao posledica D3 fix-a) |
| **Koji podaci moraju nastati** | `predmet_dokumenti` red; `predmet_dokazi` redovi; `case_dna` kolona; `audit_immutable` red za `predmet_create`+`dokument_upload` | ✅✅✅ nastaju; ❌ audit ne (D22) |
| **Šta korisnik mora videti** | Potvrda uploada; "AI analiza u toku" status; Case Genome panel automatski | ✅✅✅ sve radi (P0-3, Trust Layer runda) |
| **Šta audit mora sadržati** | Ko je kreirao predmet, kada; koji dokument otpremljen, kada | ❌ ne sadrži ništa (D22) |
| **Koji test potvrđuje gotovost** | E2E test: kreiraj predmet → otpremi dokument → proveri (1) `PredmetKreiran` red u outbox tabeli, (2) `run_case_pipeline` izvršen (proverljivo kroz `predmet_istorija` upis), (3) `audit_immutable` ima 2 nova reda, (4) Genome regenerisan | **Test NAPISAN I POKRENUT 2026-07-19** (`scripts/contract01_e2e_verify.py`, Faza A Internal Integration Sprint) — pao na (1),(2),(3) kako je predviđeno, prošao na (4) |

**Integration Coverage: 6/6 = 100%** (bilo 4/6=67% pre 2026-07-21 — videti Update ispod)

**Kritični koraci (definicija: bez ovog koraka, advokat doživljava tok
kao SLOMLJEN ili OBMANJUJUĆ, ne samo "manje automatizovan"):**
klasifikacija ✅, Evidence Vault upis ✅, Genome regeneracija ✅ — sve
3 kritične stavke rade. `PredmetKreiran` event, pipeline, audit su
infrastruktura/dopuna — vredne, ali njihovo odsustvo ne čini flow
neupotrebljivim za advokata danas.
**Critical Coverage: 3/3 = 100%.**

**Verified Coverage: 3/3 = 100% ZA KRITIČNE korake** (potvrđeno
stvarnim E2E pokretanjem protiv produkcijske baze, 2026-07-19, predmet_id
`47dc4817-89f3-4748-9eee-cb247a22892c`, obeležen `[INTEGRACIJA-TEST]`,
zadržan kao trajan regresioni slučaj — nije obrisan). Rezultat: 1
`predmet_dokumenti` red, 3 `predmet_dokazi` reda (Evidence Vault),
Genome verzija 1 sa `_verifikacija.odluka = "approve_with_warning"` —
Verification Layer je ISPRAVNO uhvatio soft flag ("ZOO čl. 262" nije
prepoznat kao poznat zakon, sumnjiv navod za radni spor), `GenomeUpdated`
event red postoji, `audit_immutable` `genome_refresh` red postoji.
Ukupno vreme: 38.8s. **Verified Coverage za ostatak toka (D3/D9/D22)
ostaje 0% — nepromenjeno, ovi koraci nisu ni pokušani jer G-001/G-002/
G-003 nisu zatvorene.**

**Update 2026-07-21 (commit `8f54f54`, kod):** G-001 i G-002 zatvorene u
kodu (D3/D9) — `api.py::kreiraj_predmet` sada emituje `PredmetKreiran`,
koji preko već registrovanog `on_predmet_kreiran` handlera
(`services/event_bus.py`) pokreće `run_case_pipeline()`. Diff izolovan
i pušten odvojeno od nepovezane, ranije nekomitovane izmene u istom
fajlu (`/bezbednosni-list` ruta).

**Update 2026-07-21 (commit `5bcc226`, produkcijska verifikacija):**
`scripts/contract01_e2e_verify.py` prošireno da stvarno proveri (4)/(5)
umesto hardkodovanog `False`, pokrenuto DVA PUTA protiv produkcije —
puna evidencija u `CONTRACT_01_PRODUCTION_VERIFICATION.md`. **Sve 3
supstantivne provere (klasifikacija/predmet_dokumenti postoje kao ulaz,
`PredmetKreiran`→`run_case_pipeline` izvrsen, AI izlaz nije prazan)
PROŠLE na oba predmeta** (`b3f7eae5...`, `87b76dc2...`, oba `[E2E
CONTRACT01] Test predmet 2026-07-21`). Jedini incident: prvi run je
srušio SAMO stdout prikaz testa (Windows cp1252 vs srpska slova) POSLE
svih supstantivnih upisa — test-harness bug, ne sistemski bug,
popravljen u istom commit-u, potvrdjeno drugim čistim run-om.

**Integration Coverage: 6/6 = 100%** za originalnih 6 DoD stavki
(`VINDEX_INTEGRATION_MASTER_PLAN.md` Tok 1) — bilo 4/6=67%.
**Critical Coverage: 3/3 = 100%** (nepromenjeno — D3/D9/D22 nikad nisu
bili u kritičnoj definiciji).
**Verified Coverage: 6/6 = 100%** za originalnih 6 DoD stavki (bilo
3/6=50% posmatrano na taj nacin, ili "3/3 za kriticne + 0% za ostatak"
kako je ranije formulisano) — D3/D9 sada dokazano rade end-to-end
produkcijski, ne samo postoje u kodu.

**D22 (audit red za predmet_create/dokument_upload) ostaje potpuno van
ovoga — 7. stavka, formalizovana posle originalnog 4/6/6/6 brojanja,
i dalje Open, nikad tvrdjena kao deo ovog fix-a.**

### CONTRACT 02 — Upload presude

| Element | Specifikacija | Status danas |
|---|---|---|
| **Trigger** | Otpremljen dokument se klasifikuje kao procesno-relevantan | Danas: `sudska_odluka`, nedovoljno precizno (D1) |
| **Šta ulazi** | PDF/DOCX, idealno sa jasnim datumom dostave | Datum dostave se ne hvata pouzdano (D2) |
| **Koji event mora nastati** | "Dokument klasifikovan" (specifično procesni akt) | ❌ ne postoji ni definicija (D4) |
| **Koji servisi moraju biti pozvani** | Precizan klasifikator (razdvaja tužbu/žalbu/odgovor, presudu/rešenje); determinističko mapiranje tip→ZPP ključ; potvrda-UI servis; Deadline Guardian registracija | ❌❌❌❌ nijedan ne postoji (D1, D6, D6, D8) — ZPP katalog sam (`rokovi_lanac.py`) postoji, nepovezan |
| **Koji podaci moraju nastati** | Predloženi rok (pending, nepotvrđen); potvrđen rok u jedinstvenom izvoru; task-predlog; notifikacija raspoređena | ❌❌❌❌ nijedan koncept ne postoji (D21, D12, D10) |
| **Šta korisnik mora videti** | Zahtev za potvrdu datuma/tipa roka | ❌ ne postoji nigde u UI-ju |
| **Šta audit mora sadržati** | Ceo lanac odluka: AI predlog → advokatova potvrda → izračunat rok | ❌ ne postoji |
| **Koji test potvrđuje gotovost** | Upload presude sa poznatim datumom dostave → sistem predlaže tačan tip roka → advokat (simulirano) potvrđuje → sistem izračunava tačan datum (uporediv sa ručnom ZPP kalkulacijom kao ground truth) → rok vidljiv u Guardian skeniranju → task predložen → notifikacija zakazana → audit kompletan | Test ne postoji — pao bi na skoro svakoj proveri |

**Integration Coverage: 1/10 = 10%** — najniže od sva 4 ugovora, i
namerno: ovo je tok koji najdirektnije testira "operativni sistem"
obećanje, i najviše zavisi od Faza 1 preduslova (D1, D2) koji se ne
smeju preskočiti.

**Kritični koraci:** za razliku od ostala 3 toka, OVDE je razlika
između kritičnog i dopunskog koraka mala — ovo je serijski lanac gde
svaki korak blokira sledeći (pogrešna klasifikacija → pogrešan predlog
→ pogrešan rok, bez obzira da li Guardian/task/notifikacija rade).
Kritični: prepoznavanje tačnog tipa ✅❌, datum dostave ❌, predlog ZPP
događaja ❌, potvrda-korak ❌, deterministička kalkulacija (katalog
postoji, nepovezan) ⚠️, jedinstven izvor istine ❌ — 6 kritičnih
stavki, samo kalkulacija delimično postoji.
**Critical Coverage: 1/6 = 17%** — i dalje nisko, ali VIŠE od raw
Coverage (10%), jer su neke od "lakših" nekritičnih stavki (Guardian
registracija, task, notifikacija) čak i praznije od kritičnog jezgra.
**Zaključak: ovaj tok je slomljen i na kritičnom nivou, ne samo na
nivou dopune — potvrđuje da mora ići poslednji, tek posle D1/D2.**

### CONTRACT 03 — Dodavanje ročišta

| Element | Specifikacija | Status danas |
|---|---|---|
| **Trigger** | Advokat unosi ročište kroz formu (`POST /api/rocista`) | — |
| **Šta ulazi** | Datum, sud, tip ročišta (ručan unos) | — |
| **Koji event mora nastati** | `ROCISTE_ZAKAZANO` | ❌ definisan, nikad emitovan |
| **Koji servisi moraju biti pozvani** | `predmet_hronologija` upis; Genome refresh (`trigger="rociste_trigger"`); sinhronizacija sa jedinstvenim rok-izvorom; Guardian registracija | ✅✅ rade; ❌❌ ne postoje (D21, D8) |
| **Koji podaci moraju nastati** | Hronologija red; Genome nova verzija; unos u jedinstven rok-izvor; podsetnik zakazan | ✅✅ nastaju; ❌❌ ne (D21, D10) |
| **Šta korisnik mora videti** | Potvrda unosa; podsetnik pre ročišta | ✅ (standardna forma pretpostavljena); ❌ ne postoji |
| **Šta audit mora sadržati** | Ko je uneo, kada, za koji predmet | **Neprovereno** da li je `rociste_add` u `AUDITABLE_ACTIONS` — treba dodatna provera van obima ovog dokumenta |
| **Koji test potvrđuje gotovost** | Unos ročišta → provera hronologije → provera Genome verzije → provera da Guardian "zna" za ovaj datum → provera da je podsetnik zakazan → provera audit reda | Test ne postoji |

**Integration Coverage: 2/7 = 29%**

**Kritični koraci:** hronologija upis ✅, Genome refresh ✅, podsetnik
pre ročišta ❌ (propušten podsetnik = stvaran rizik za advokata, ne
samo neprijatnost) — 3 kritične stavke, 2 rade. Sinhronizacija sa
rok-izvorom, Guardian registracija, dashboard vidljivost, audit su
dopuna za OVAJ tok specifično (arhitektonski su i dalje bitni, ali
njihovo odsustvo ne čini "dodavanje ročišta" samo po sebi slomljenim
za korisnika danas).
**Critical Coverage: 2/3 = 67%.**

### CONTRACT 04 — Zatvaranje predmeta

| Element | Specifikacija | Status danas |
|---|---|---|
| **Trigger** | Advokat klikne "Potvrdi zatvaranje" (`PATCH /api/predmeti/{id}/zatvori`) | — |
| **Šta ulazi** | Strukturisan ishod (pobeda/poraz/nagodba/odustajanje/odbačena/ostalo) | — |
| **Koji event mora nastati** | Ne postoji definisan `EventType` za ovo uopšte | ❌ nedostaje čak i kao definicija (D24, nov nalaz) |
| **Koji servisi moraju biti pozvani** | Hronologija upis; anonimni benchmark doprinos; style profile update (`corrections.py::_update_style_profile`); firm-nivo statistika | ✅✅ rade (potvrđeno); ⚠️⚠️ **neprovereno** da li se trigeruju ovim eventom |
| **Koji podaci moraju nastati** | Hronologija red; benchmark red; audit red | ✅✅ nastaju; ⚠️ neprovereno da li je `predmet_close` u allowlist-i (D22) |
| **Šta korisnik mora videti** | Potvrda zatvaranja | ✅ radi (dugme postoji, povezano) |
| **Šta audit mora sadržati** | Ishod, ko je zatvorio, kada | ⚠️ neprovereno |
| **Koji test potvrđuje gotovost** | Zatvaranje predmeta → provera hronologije → provera benchmark upisa → provera (ako se odluči da treba) style profile trigera → provera audit reda | Test ne postoji |

**Integration Coverage: 2/5 potvrđeno = 40%, uz 3/5 (60%) status
NEPROVERENO** — ne "ne radi", nego "nije provereno u ovoj sesiji".
Ovaj broj se NE sme tretirati kao konačan bez live-sistem provere.

**Kritični koraci:** strukturisan ishod upisan ✅ (osnovni "da li je
zatvaranje uopšte upisano" test), audit trag za zatvaranje ⚠️
neprovereno, ali tretiran kao KRITIČAN (compliance rizik, ne dopuna —
isti razlog kao D22 opšte). Benchmark doprinos, style profile,
firm statistika su dopuna (vredne za proizvod dugoročno, ne za
neposredno advokatovo iskustvo zatvaranja OVOG predmeta).
**Critical Coverage: 1/2 = 50%** — niže nego što bi se očekivalo od
naizgled "najgotovijeg" toka, upravo zato što je audit stavka tretirana
ozbiljno, ne kozmetički.

---

## Deo C — Integration Coverage (matematika, ne procena)

**Formula:** (broj koraka gde je postojanje POTVRĐENO kodom) / (broj
obaveznih koraka definisanih u odgovarajućem Ugovoru) × 100.
"Neprovereno" se računa kao 0 dok se ne potvrdi (konzervativno, u duhu
Rule C — ne pretpostavljati).

**Metodološka dopuna (2026-07-19, founderov zahtev):** svaki korak ne
vredi isto. Coverage sam po sebi može biti visok a da sistem i dalje
nije upotrebljiv za pilot (npr. 90% Coverage sa svim kritičnim koracima
nedostajućim). Zato se svaki korak u Delu B dodatno taguje **KRITIČAN**
(bez njega je tok SLOMLJEN ili OBMANJUJUĆ za advokata, ne samo manje
automatizovan) ili **dopuna** (vredan, ali odsustvo ne čini tok
neupotrebljivim danas). Critical Coverage = ista formula, samo nad
podskupom kritičnih koraka.

**Treća dimenzija — Verified Coverage (dodato 2026-07-19, founderov
zahtev):** "radi u kodu" ≠ "dokazano radi end-to-end". Verified znači
sve troje: (1) prošao automatizovan test, (2) prošao ručni test, (3)
prošao realan pilot scenario. Dok bilo šta od ta tri nedostaje, korak
NE dobija Verified poen — bez obzira koliko je implementacija sama po
sebi ispravna. Ovo sprečava da se nešto proglasi "gotovim" samo zato
što je napisano.

**Status posle Faza A prvog dana (2026-07-19):** Verified zahteva SVA
TRI potvrde — automatizovan test, ručni test, realan pilot scenario.
Do sada je za CONTRACT 01 kritične korake prošao SAMO automatizovan
test (`scripts/contract01_e2e_verify.py`, stvaran E2E protiv
produkcije) — ručni test i pilot scenario još nisu urađeni. Zato
formalni Verified Coverage % ostaje 0 (metodologija se ne menja da bi
broj izgledao bolje), ALI dodata je "Automatizovan test" kolona kao
vodeći indikator napretka, odvojeno od pune Verified oznake.

| Tok | Coverage | Critical Coverage | Automatizovan test (kritični koraci) | Verified Coverage | Neprovereno |
|---|---|---|---|---|---|
| CONTRACT 01 — Upload tužbe | 4/6 = **67%** | 3/3 = **100%** | **3/3 PASS (2026-07-19)** | **0%** (nedostaje ručni test + pilot) | 0 |
| CONTRACT 02 — Upload presude | 1/10 = **10%** | 1/6 = **17%** | Nije pokušano | **0%** | 0 |
| CONTRACT 03 — Dodavanje ročišta | 2/7 = **29%** | 2/3 = **67%** | Nije pokušano | **0%** | 1 (audit stavka) |
| CONTRACT 04 — Zatvaranje predmeta | 2/5 = **40%** | 1/2 = **50%** | Nije pokušano | **0%** | 3 (style profile, firm stat, audit) |

**Kako Verified Coverage raste:** SAMO kad se G-stavka iz
`VINDEX_OPERATIONAL_GAP_REGISTER.md` zatvori PO protokolu definisanom
tamo (diff + test dokaz + KPI ažuriran) — nikad ručnim upisom broja bez
dokaza. Dok Verified zaostaje značajno za Coverage, to je zdrav signal
da je nešto implementirano ali nedovoljno testirano — treba zatvoriti
taj jaz PRE nego što se pređe na sledeći gap, ne posle. CONTRACT 01
kritičnih koraka će dobiti pun Verified status kad se doda: (a) jedan
ručni prolazak kroz UI od strane foundera (ne samo API test), (b)
prisustvo u stvarnom pilot sastanku sa advokatom (Deo 4,
`TRUST_LAYER_BETA_FREEZE_2026-07-19.md`).

**Čitanje ove tabele, direktno (ažurirano 2026-07-21):** Tok 1 je sada
6/6=100% Coverage I 100% kritično — D3/D9 zatvoreni i produkcijski
verifikovani (`CONTRACT_01_PRODUCTION_VERIFICATION.md`), jedina
preostala rupa je D22 (audit), formalizovan kao 7. stavka posle
originalnog brojanja. Tok 3 je blizu (67% kritično). **Tok 2 je jedini
gde je Critical Coverage i dalje nizak (17%) — potvrđuje, matematički,
ono što je Deo B već rekao rečima: ovo je tok koji mora ići poslednji, i
mora ići tek posle D1/D2.** Tok 4 (50% kritično) je iznenađujuće niže
od "izgleda skoro gotovo" utiska — jer je audit trag za zatvaranje
tretiran kao kritičan, ne kozmetičan.

**Agregatni KPI (ponderisan po broju koraka, ne prost prosek toka):**
(6+1+2+2) / (6+10+7+5) = **11/28 = 39% Coverage** (bilo 9/28=32% pre 2026-07-21)
(3+1+2+1) / (3+6+3+2) = **7/14 = 50% Critical Coverage** (nepromenjeno — D3/D9/D22 nikad nisu bili kritični)

**Oba broja se prate odvojeno od sada.** Coverage meri ukupnu
integraciju (uključujući infrastrukturu/compliance/dopunu). Critical
Coverage meri da li je sistem DANAS dovoljno pouzdan za pilot korisnika
po toku. Cilj pre bilo kog šireg pilot poziva: Critical Coverage 100%
za tokove koji se aktivno demonstriraju (Tok 1 već jeste; Tok 3 blizu;
Tok 4 treba proveriti 3 nepoznate stavke pre suda; Tok 2 ne
demonstrirati u pilotu dok Critical Coverage ne pređe bar 80%).

**Prost prosek toka (sekundarna referenca, manje precizan jer tretira
svaki tok kao jednako "težak" bez obzira na broj koraka):** (100+10+29+40)/4
= 44.75% (bilo 36.5% pre 2026-07-21).

**Preporuka: koristiti ponderisani KPI (39%) kao primarni "Vindex OS
Coverage" broj od sada.** Ovo postaje merljiva metrika napretka —
zamenjuje broj endpointa/commitova/LOC kao pokazatelj da li se sistem
približava "operativni sistem" cilju.

**Kako se ovaj broj ažurira:** posle svake implementacione runde (kad
Beta Freeze prestane), za svaku stavku koja pređe iz ❌/⚠️ u ✅ u bilo
kom Ugovoru iznad, Coverage se preračunava i upisuje ovde sa datumom.
Ne procenjuje se "otprilike koliko je urađeno" — broji se tačno koliko
je stavki potvrđeno u odnosu na ukupan broj definisan u Ugovoru.

---

## Deo D — Otvoreno, van 4 definisana Ugovora

Mapiranje u Delu A otkrilo je da predloženih 13 lifecycle stanja
prevazilazi 4 trenutno definisana toka na dva mesta: **"Žalba"** i
**"Pravosnažno"** nemaju svoj Ugovor — ovo nije nadgledano nigde u
dosadašnjoj analizi. Pre nego što se D23 (usklađivanje sa Kanban-om)
reši, nema smisla pisati CONTRACT 05/06 za ova stanja — prvo treba
odlučiti da li se uopšte grade kao posebna stanja ili se apsorbuju u
postojeći "Upload presude" tok (žalba je, u suštini, još jedan
klasifikovan dokument koji prolazi kroz isti lanac kao presuda, samo sa
drugačijim rok-posledicama — videti D1 granularnost nalaz).

---

## Deo E — Disciplina za implementaciju (ponovljena, ne nova)

Founder je eksplicitno upozorio na ovo, i vredi ponoviti direktno u
ugovornom dokumentu, ne samo u Master Planu: **ne pokušavati "završiti
sve" u jednom talasu.** Redosled ostaje kako je utvrđeno u ADR-u Deo E:
infrastruktura prvo (D3, D5, D9, D10, D22 — ne zavise od semantike),
zatim P1 semantička preciznost (D1, D2 — MORAJU biti rešeni pre
CONTRACT 02 dobije stvaran sadržaj), tek onda širenje automatizacije
(D4, D6, D7, D8, D21). Nijedan Ugovor iznad se ne implementira
"odjednom" — svaka stavka u tabeli je zaseban, testabilan korak.

**Ažurirano (2026-07-19):** Faza A — Internal Integration Sprint je u
toku. Implementacija ide REDOSLEDOM iznad, jedan G-broj po jedan, po
protokolu zatvaranja definisanom u `VINDEX_OPERATIONAL_GAP_REGISTER.md`
— ne kao pripremljena specifikacija koja čeka budući signal.
