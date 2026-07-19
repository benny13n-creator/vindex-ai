# Vindex AI — Known Reliability Risks

Ovaj dokument prati poznate, ali namerno neotklonjene rizike u sistemu —
stvari koje NISU hitne (nema dokaza da se dešavaju u praksi) ali imaju
pogrešan princip iza sebe i zato ne smeju biti tiho zaboravljene. Razlika
prema `UX_IMPROVEMENT_PLAN.md`: to su UI/UX nalazi; ovo su backend/
arhitektonski rizici gde je posledica netačnosti (ne samo neprijatnosti).

Svaki unos: šta je rizik, zašto princip nije u redu (ne "da li je
verovatno"), šta bi ispravan fallback trebalo da bude, status.

---

## 1. `verify_genome()` — tiho "odobreno" ako sve podprovere padnu

**Otvoreno:** 2026-07-19, nađeno tokom self-review-a posle P0 UX
implementacije (Genome Verification narativ), founder eksplicitno tražio
da se formalizuje kao praćen rizik, ne samo pomene i zaboravi.

**Lokacija:** `shared/genome_validator.py`, `verify_genome()` (Faza 1.3
dizajn, `docs/architecture/CASE_GENOME_GAP_ANALYSIS_2026-07-18.md` i
Reliability Patch izveštaj).

**Šta je rizik:** `verify_genome()` je namerno projektovan da nikad ne
baca izuzetak — svaka od 4 podprovere (`_validate_dokazi_rang`,
`_validate_kontradikcije_lokacije`, `_validate_relevantni_zakoni`,
`_validate_snaga_konzistentnost` + `_validate_clan_brojevi`) je omotana u
`try/except: pass`. Ovo je bila ispravna odluka za ono što je rešavala
(jedna loša provera ne sme da obori ceo zahtev za snimanje Genome-a) —
ali ima posledicu koja nije bila eksplicitno razmotrena: **ako SVE
podprovere istovremeno padnu** (npr. promena oblika `genome` ili `docs`
strukture koju nijedna provera više ne prepoznaje), `hard` i `soft` liste
ostaju prazne, `odluka` postaje `"approve"` — identično stanju kad je
verifikacija stvarno prošla i ništa nije našla.

**Zašto je ovo pogrešan princip, ne pitanje verovatnoće (founderova
formulacija, direktan citat):** "Ako Verification nije izvršen, sistem ne
sme izgledati kao da jeste." Trenutni sistem ima samo dva vidljiva stanja
prema korisniku — "ima upozorenja" ili "nema upozorenja" — a treba tri:

1. Verifikacija uspela → prikaži rezultat (postojeće ponašanje, ispravno).
2. Verifikacija delimično uspela (npr. 2 od 4 provere pale, ali ostale su
   dale rezultat) → prikazati DA je delimična, ne tretirati kao potpunu.
3. Verifikacija nije izvršena (npr. sve provere pale) → jasno reći da
   nije izvršena, NIKAD "sve je u redu".

**Trenutna frontend odbrana (delimična, ne rešava koren):** Case Genome
panel (`_caseDnaRender`, `static/vindex.js`) ne prikazuje narativ uopšte
ako `dna._verifikacija` ne postoji (npr. stariji Genome zapisi pre Faze
1.3) — ali AKO `_verifikacija` postoji sa `odluka: "approve"` zato što je
SVE tiho palo, frontend nema način da to razlikuje od stvarnog "approve".
Backend trenutno ne razlikuje ta dva slučaja u samom `verify_genome()`
povratnom objektu.

**Ispravan fallback (predlog, NIJE implementiran, čeka odluku):**
`verify_genome()` bi trebalo da broji koliko od 5 podprovera je uspešno
IZVRŠENO (bez obzira na rezultat), ne samo koliko je flagova vratilo, i
vrati dodatno polje npr. `"provera_izvrsena_broj": N` (od mogućih 5). Ako
je taj broj 0, `odluka` ne bi trebalo da bude `"approve"` nego novo stanje
— npr. `"verifikacija_neuspesna"` — koje frontend prikazuje eksplicitno
("Verifikacija nije mogla da se izvrši za ovaj Genome"), ne kao "✓ nema
upozorenja".

**Zašto NIJE popravljeno sada:** ovo je backend/arhitektonska izmena
(nov status u `odluka` enum-u, promena ugovora `verify_genome()`
povratne vrednosti, frontend mora znati za treće stanje) — van obima UX
runde koja je bila u toku kad je nađeno. Takođe nema dokaza DA se ovo
ikad realno desilo (nijedan zabeležen slučaj gde su sve 4 provere pale
istovremeno) — po Rule A (Evidence Matrix) ne prolazi prag za hitnu
popravku, ali po founderovoj eksplicitnoj odluci OSTAJE praćen jer je
princip pogrešan, ne čeka da postane hitan.

**Status:** OTVOREN, praćen, ne blokira trenutni rad. Sledeći put kad se
`genome_validator.py` menja iz bilo kog drugog razloga, ovo je prirodna
prilika da se reši u istom prolazu.

**Verovatnoća/uticaj ako se desi:** Niska verovatnoća (zahteva
istovremen kvar 5 nezavisnih provera), ali visok uticaj po poverenje ako
se desi — korisnik bi video "✓ Nema upozorenja" tačno u trenutku kad
sistem najmanje zna šta se dešava. Ovo je tip rizika koji, kad se
materijalizuje, ne izgleda kao bug — izgleda kao lažno uveravanje.

Veza: [[project_case_genome]], [[project_ux_audit_2026-07-19]]
