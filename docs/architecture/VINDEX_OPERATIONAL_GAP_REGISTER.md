# Vindex AI — Operational Gap Register

**2026-07-19.** Osmi i poslednji planski dokument u ovoj seriji. Ovo
NIJE analiza — ovo je operativna radna lista. Founderova formulacija:
posle ovog dokumenta, rad se prati kao "zatvaram G-003", ne "radim D6".

**Kolone:** ID | Tok | Prekid | Uzrok | Rešenje (D-broj u
`VINDEX_2_1_ARCHITECTURE_ROADMAP.md`) | Status.

Svaki red je izveden iz `VINDEX_OPERATING_SYSTEM_CONTRACTS.md` Deo B —
dubok dokaz (file:line) za svaki red je tamo, ne ponovljen ovde.

| ID | Tok | Prekid | Uzrok | Rešenje | Status |
|---|---|---|---|---|---|
| G-001 | Upload tužbe | `PredmetKreiran` se ne emituje | Event nikad pozvan iz `routers/intake.py` | D3 | Open |
| G-002 | Upload tužbe | `run_case_pipeline()` se ne pokreće za standardni put | Zavisi od G-001 | D9 | Open |
| G-003 | Upload tužbe | Audit ne beleži kreiranje predmeta/upload dokumenta | `predmet_create`/`dokument_upload` nikad pozvani | D22 | Open |
| G-004 | Upload presude | Klasifikator ne razlikuje tužbu/žalbu/odgovor na tužbu | Sve u kategoriji `podnesak` | D1 | Open |
| G-005 | Upload presude | Klasifikator ne razlikuje presudu/rešenje | Sve u kategoriji `sudska_odluka` | D1 | Open |
| G-006 | Upload presude | Datum dostave/prijema se ne hvata pouzdano | Nema polje/logiku za ekstrakciju tog datuma specifično | D2 | Open |
| G-007 | Upload presude | Ne postoji event za "dokument klasifikovan kao procesni akt" | Nedostaje čak i definicija u enum-u | D4 | Open |
| G-008 | Upload presude | Klasifikacija se ne mapira na ZPP tip roka | Nema determinstičku vezu tip→`rokovi_lanac.py` ključ | D6 | Blocked na G-004/G-005/G-006 |
| G-009 | Upload presude | Nema koraka gde advokat potvrđuje predloženi rok | UI ne postoji | D6 | Blocked na G-008 |
| G-010 | Upload presude | Deadline Guardian ne registruje rok po predmetu | Nema UI/trigering | D8 | Open |
| G-011 | Upload presude | Nema jedinstven izvor istine za rok podatak | 3 paralelne tabele (`predmet_hronologija`/`rokovi`/`zadaci.rok_datum`) | D21 | **Blocker za G-008/G-009/G-010** |
| G-012 | Upload presude | Task se ne kreira iz predloženog roka | Nema veze između rok-lanca i `zadaci` tabele | D12 | Blocked na G-009 |
| G-013 | Upload presude | Notifikacija za rok se ne raspoređuje pouzdano | Cron isporuka neizvesna (`Procfile` samo `web`) | D10 | Open, **kandidat za hitan izuzetak** |
| G-014 | Upload presude | Audit ne beleži lanac odluka (predlog→potvrda→rok) | Nijedna akcija u ovom lancu nije u `AUDITABLE_ACTIONS` | D22 | Open |
| G-015 | Dodavanje ročišta | `RociscteZakazano` se ne emituje | Event nikad pozvan | D25 | Open |
| G-016 | Dodavanje ročišta | Ročište nije sinhronizovano sa jedinstvenim rok-izvorom | Isti uzrok kao G-011 | D21 | Blocked na D21 odluci |
| G-017 | Dodavanje ročišta | Guardian ne registruje datum ročišta | Isti uzrok kao G-010 | D8 | Open |
| G-018 | Dodavanje ročišta | Podsetnik pre ročišta se ne raspoređuje | Isti uzrok kao G-013 | D10 | Open |
| G-019 | Dodavanje ročišta | Audit za unos ročišta — **neprovereno**, ne potvrđeno kao gap | `rociste_add` prisustvo u `AUDITABLE_ACTIONS` nije provereno | D22 | **Needs verification pre Open/Closed** |
| G-020 | Zatvaranje predmeta | Ne postoji event za zatvaranje/pravosnažnost predmeta | Nedostaje čak i definicija | D24 | Open |
| G-021 | Zatvaranje predmeta | Style profile update trigering — **neprovereno** | Da li `_update_style_profile` reaguje na zatvaranje ili samo na 10+ korekcija nezavisno | — (istraživanje, ne D-broj) | **Needs verification** |
| G-022 | Zatvaranje predmeta | Firm-nivo statistika ažuriranje — **neprovereno** | Nije praćeno u ovoj sesiji | — (istraživanje) | **Needs verification** |
| G-023 | Zatvaranje predmeta | Audit za `predmet_close` — **neprovereno** | Prisustvo u `AUDITABLE_ACTIONS` nije potvrđeno | D22 | **Needs verification** |
| G-024 | Arhitektonski (svi tokovi) | Predloženi 13-stanja lifecycle nije usklađen sa Kanban statusom | Dva nezavisna "status predmeta" koncepta ako se lifecycle uvede bez odluke | D23 | **Blocker za bilo koju lifecycle implementaciju** |
| G-025 | Arhitektonski | "Žalba" i "Pravosnažno" nemaju definisan tok/ugovor | Van obima 4 postojeća CONTRACT-a | D24 | Open, čeka D23 |

---

## Kako se ovaj registar koristi

- **"Zatvaram G-003"** znači: implementiran je audit poziv za
  `predmet_create`+`dokument_upload`, red testiran E2E (CONTRACT 01
  test stavka), status menja na Closed, `VINDEX_OPERATING_SYSTEM_
  CONTRACTS.md` Coverage/Critical Coverage brojevi se preračunaju.
- **"Needs verification"** stavke (G-019, G-021, G-022, G-023) NISU
  potvrđeni gapovi — ne planirati implementaciju za njih dok se prvo ne
  potvrdi da li stvarno nedostaju. Provera dolazi pre popravke.
- **Blokeri** (G-011 blokira G-008/009/010; G-024 blokira svaku
  lifecycle implementaciju) — ne pokušavati zatvoriti blokiranu stavku
  pre blokera, bez obzira koliko izgleda jednostavno izolovano.
- Novi gap otkriven u budućoj implementaciji dobija sledeći slobodan
  G-broj (G-026+) — ne prepravlja se numeracija postojećih.

## Protokol zatvaranja G-stavke (2026-07-19, founderov zahtev — obavezan format)

Rad se od sada ne zadaje kao "implementiraj feature" — zadaje se kao
**"zatvori G-XXX"**. Kad je G-stavka zatvorena, izveštaj MORA sadržati
svih 6 elemenata, ne manje:

1. **Diff** — tačna izmena koda.
2. **Koji CONTRACT je promenjen** — koja tabela/red u
   `VINDEX_OPERATING_SYSTEM_CONTRACTS.md` Deo B se ažurira.
3. **Koji KPI se promenio** — novi Coverage/Critical Coverage/Verified
   Coverage brojevi, sa računicom (ne samo novi broj — stara i nova
   vrednost).
4. **Koji testovi su pokrenuti** — automatizovan test rezultat, ručni
   test opis, (kad primenjivo) pilot scenario status.
5. **Koje G-stavke su zatvorene** — može biti više od jedne ako je
   izmena rešila lančanu zavisnost.
6. **Potvrda da nisu otvorene nove G-stavke slučajno** — ili
   eksplicitna lista ako jesu (novi gap otkriven tokom rada je
   normalan i očekivan ishod, ne greška — ali mora biti prijavljen, ne
   prećutan).

Zatvaranje bez svih 6 elemenata se ne broji kao zatvaranje — status
ostaje Open dok izveštaj nije kompletan.

## Pravilo redosleda rada (founderov zahtev)

**Dok postoji Open G-stavka koja prekida OSNOVNI operativni tok** (bilo
koja stavka bez "Needs verification" oznake, u bilo kom od 4
CONTRACT-a) **, ne razvija se nijedna nova funkcija.** Redosled je:
zatvori prekid → dokaži da radi (Verified Coverage raste) → ažuriraj
KPI → tek onda sledeći prekid. Ovo ne znači da se nikad više ne dodaju
nove mogućnosti — znači da G-registar ima prioritet nad svakim novim
predlogom dok je bar jedna osnovna stavka Open. Redosled zatvaranja
prati zavisnosti već utvrđene u `VINDEX_2_1_ARCHITECTURE_ROADMAP.md`
Deo E (infrastruktura → semantička preciznost → povezivanje).

## Kad je ovaj registar "gotov"

Kad nema više Open/Blocked/Needs-verification stavki — u tom trenutku
(i tek tada) Integration Coverage u `VINDEX_OPERATING_SYSTEM_
CONTRACTS.md` dostiže 28/28, i Vindex AI prestaje da bude "kolekcija
modula" po definiciji iz `VINDEX_INTEGRATION_MASTER_PLAN.md`.

---

**Poslednja napomena, founderova, vredna ponavljanja ovde direktno:**
sledeći pravi pomak nije novi dokument. Sledeći pravi pomak je trenutak
kad prvi red u ovoj tabeli pređe iz Open u Closed. Ovaj registar se
ažurira posle svake implementacione runde (kad Beta Freeze prestane) —
ne piše se deveti planski dokument dok se bar par ovih redova ne
zatvori.
