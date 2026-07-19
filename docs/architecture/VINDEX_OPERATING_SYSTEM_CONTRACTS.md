# Vindex AI — Operating System Contracts (2026-07-19)

Sedmi dokument u nizu. Odnos prema prethodna dva centralna dokumenta:
`VINDEX_2_1_ARCHITECTURE_ROADMAP.md` je registar ODLUKA (D1-D22+,
statusi). `VINDEX_INTEGRATION_MASTER_PLAN.md` je ustav PROCESA (tokovi,
DoD, testiranje). **Ovaj dokument je UGOVOR** — precizna, neopoziva
specifikacija šta svaki tok MORA sadržati da bi se smatrao gotovim, plus
matematička (ne procenjena) mera koliko je danas ispunjen.

**Nijedna linija koda nije menjana. Beta Freeze i dalje na snazi.**

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
| **Koji event mora nastati** | `PREDMET_KREIRAN` (pri kreiranju predmeta) + `DOKUMENT_UPLOADOVAN` (pri uploadu) | ❌ nijedan se ne emituje (D3) |
| **Koji servisi moraju biti pozvani** | OCR fallback (`uploaded_doc/extractor.py`); Evidence Vault klasifikacija (`routers/evidence.py::klasifikuj_i_sacuvaj`); Case Genome ekstrakcija (`routers/case_dna.py::_run_genome_background`); `run_case_pipeline()` (`services/case_pipeline.py`) | ✅✅✅ rade; ❌ pipeline se ne poziva (D9, zavisi od D3) |
| **Koji podaci moraju nastati** | `predmet_dokumenti` red; `predmet_dokazi` redovi; `case_dna` kolona; `audit_immutable` red za `predmet_create`+`dokument_upload` | ✅✅✅ nastaju; ❌ audit ne (D22) |
| **Šta korisnik mora videti** | Potvrda uploada; "AI analiza u toku" status; Case Genome panel automatski | ✅✅✅ sve radi (P0-3, Trust Layer runda) |
| **Šta audit mora sadržati** | Ko je kreirao predmet, kada; koji dokument otpremljen, kada | ❌ ne sadrži ništa (D22) |
| **Koji test potvrđuje gotovost** | E2E test: kreiraj predmet → otpremi dokument → proveri (1) `PredmetKreiran` red u outbox tabeli, (2) `run_case_pipeline` izvršen (proverljivo kroz `predmet_istorija` upis), (3) `audit_immutable` ima 2 nova reda, (4) Genome regenerisan | Test ne postoji — kad se napiše, danas bi pao na (1),(2),(3) |

**Integration Coverage: 4/6 = 67%**

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

---

## Deo C — Integration Coverage (matematika, ne procena)

**Formula:** (broj koraka gde je postojanje POTVRĐENO kodom) / (broj
obaveznih koraka definisanih u odgovarajućem Ugovoru) × 100.
"Neprovereno" se računa kao 0 dok se ne potvrdi (konzervativno, u duhu
Rule C — ne pretpostavljati).

| Tok | Potvrđeno / Ukupno | Coverage | Neprovereno (odvojeno od "ne radi") |
|---|---|---|---|
| CONTRACT 01 — Upload tužbe | 4/6 | **67%** | 0 |
| CONTRACT 02 — Upload presude | 1/10 | **10%** | 0 |
| CONTRACT 03 — Dodavanje ročišta | 2/7 | **29%** | 1 (audit stavka) |
| CONTRACT 04 — Zatvaranje predmeta | 2/5 | **40%** | 3 (style profile, firm stat, audit) |

**Agregatni KPI (ponderisan po broju koraka, ne prost prosek toka):**
(4+1+2+2) / (6+10+7+5) = **9/28 = 32%**

**Prost prosek toka (sekundarna referenca, manje precizan jer tretira
svaki tok kao jednako "težak" bez obzira na broj koraka):** (67+10+29+40)/4
= 36.5%.

**Preporuka: koristiti ponderisani KPI (32%) kao primarni "Vindex OS
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

**Ništa od ovoga se ne implementira dok Beta Freeze traje.** Ovaj
dokument je specifikacija spremna za implementaciju KAD founder da
signal da je pilot feedback stigao — ne pre.
