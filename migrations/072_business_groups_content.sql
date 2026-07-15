-- ============================================================================
-- Vindex AI — Migracija 072: Business Groups — prodajni sadržaj kartica
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor, posle 071.
--
-- Kontekst: 071 je dala grupisanje (koja funkcija ide u koju od 7 poslovnih
-- celina). Ova migracija dodaje SADRŽAJ kartica za Pricing Modal Nivo 1 —
-- naslov, snažnu rečenicu (tagline), opis, poslovnu vrednost (rezultat) i
-- "Najveću vrednost ostvaruju" listu — svaki tekst prošao je kroz više
-- iteracija sa founderom (bez marketinških klišea: AI powered/revolucija/
-- ušteda vremena/produktivnost/inovativno... namerno izbegnuto).
--
-- description kolona (iz 071) se ovde AŽURIRA finalnim tekstom — 071 je
-- prvobitno imala jednu kratku rečenicu, ovde postaje puni "kratak opis"
-- (25-40 reči) po founderovom finalnom spec-u.
-- ============================================================================

ALTER TABLE public.business_groups
    ADD COLUMN IF NOT EXISTS tagline TEXT,
    ADD COLUMN IF NOT EXISTS value_statement TEXT,
    ADD COLUMN IF NOT EXISTS best_for TEXT[];

COMMENT ON COLUMN public.business_groups.tagline IS
    'Snažna rečenica (max 14 reči) — opisuje REZULTAT, ne funkcije. Prikazano ispod naziva na Pricing Modal kartici.';
COMMENT ON COLUMN public.business_groups.description IS
    'Kratak opis (25-40 reči) — objašnjava kako advokat radi drugačije sa ovom grupom funkcija, ne tehnologiju.';
COMMENT ON COLUMN public.business_groups.value_statement IS
    'Poslovna vrednost — jedna rečenica, prikazana sa "Rezultat:" prefiksom u UI-ju (prefiks nije u samom tekstu).';
COMMENT ON COLUMN public.business_groups.best_for IS
    'Lista kratkih fraza (tipova korisnika/slučajeva) — prikazano pod "Najveću vrednost ostvaruju" u UI-ju. NIKAD "Idealno za" (landing-page jezik, founder eksplicitno odbio).';

UPDATE public.business_groups SET
    display_name = 'Pravna analiza',
    tagline = 'Svaki pravni odgovor je proverljiv, dosledan i spreman za profesionalnu upotrebu.',
    description = 'Svaki odgovor povezan je sa relevantnim propisima, sudskom praksom i obrazloženjem, tako da se može koristiti u radu sa klijentom ili kao osnova za izradu podneska.',
    value_statement = 'konzistentan pravni stav kancelarije, bez obzira ko od advokata odgovara klijentu.',
    best_for = ARRAY['Samostalni advokati', 'Advokatske kancelarije', 'Pravni timovi kompanija']
WHERE key = 'ai_pravna_analiza';

UPDATE public.business_groups SET
    tagline = 'Najvažnije odluke donose se nakon simulacije mogućih ishoda, a ne na osnovu pretpostavki.',
    description = 'Pre ključnog poteza — pregovora, tužbe, ročišta — advokat testira više scenarija i vidi moguće ishode, umesto da se oslanja isključivo na iskustvo i pretpostavku o postupanju suda.',
    value_statement = 'strateške odluke zasnovane na proveri, ne na pretpostavci.',
    best_for = ARRAY['Parnični postupci', 'Arbitraže', 'Složeni privredni sporovi']
WHERE key = 'strategija_predmeta';

UPDATE public.business_groups SET
    tagline = 'Sve informacije koje određuju tok predmeta dostupne su u jedinstvenom pregledu predmeta.',
    description = 'Advokat u svakom trenutku zna gde predmet stoji — koji rok ističe, koji dokaz nedostaje, kakav je istorijat odluka — bez potrebe da ponovo prelazi celu dokumentaciju pre svakog sastanka ili ročišta.',
    value_statement = 'nijedan rok, dokaz ili rizik ne ostaje neprimećen.',
    best_for = ARRAY['Litigacioni timovi', 'Predmeti visoke složenosti', 'Advokati sa velikim brojem aktivnih predmeta']
WHERE key = 'inteligencija_predmeta';

UPDATE public.business_groups SET
    display_name = 'Dokumenti i dokazi',
    tagline = 'Svaki dokument izlazi iz kancelarije po istom profesionalnom standardu.',
    description = 'Nacrti podnesaka, poređenje verzija dokumenata i analiza dokaza više ne počinju od praznog lista. Svaki dokument nastaje uz strukturisanu podršku, a svaki dokaz dobija jasan kontekst pre nego što postane deo pravne argumentacije.',
    value_statement = 'dosledna dokumentacija kancelarije, bez obzira ko je sastavlja.',
    best_for = ARRAY['Advokati sa velikim obimom podnesaka', 'Predmeti sa obimnom dokumentacijom', 'Timovi koji rade sa dokaznim materijalom']
WHERE key = 'dokumenti_automatizacija';

UPDATE public.business_groups SET
    tagline = 'Iskustvo kancelarije postaje trajna prednost.',
    description = 'Presedani, interni stavovi i ranije doneseni zaključci se čuvaju i povezuju kroz vreme, tako da se odluka iz jednog predmeta pronalazi i koristi u sledećem, umesto da zavisi od sećanja pojedinog advokata.',
    value_statement = 'institucionalno znanje kancelarije se ne gubi kada se promeni tim.',
    best_for = ARRAY['Kancelarije sa više advokata', 'Kancelarije u fazi rasta tima', 'Kancelarije koje žele dosledan pravni stav kroz godine']
WHERE key = 'znanje_kancelarije';

UPDATE public.business_groups SET
    tagline = 'Kancelarija se vodi na osnovu podataka, ne na osnovu utiska.',
    description = 'Svakodnevni rad kancelarije prati se kroz jedinstven operativni pregled koji povezuje klijente, predmete, rokove, finansije i interne procese. Ključne informacije dostupne su pre nego što postanu operativni problem.',
    value_statement = 'poslovanje kancelarije postaje predvidljivo, merljivo i pod kontrolom.',
    best_for = ARRAY['Kancelarije sa više klijenata i predmeta', 'Partneri odgovorni za poslovanje kancelarije', 'Timovi koji upravljaju rokovima i naplatom']
WHERE key = 'upravljanje_kancelarijom';

UPDATE public.business_groups SET
    display_name = 'Digitalna imovina i usklađenost',
    tagline = 'Digitalna imovina zahteva isti nivo pravne sigurnosti kao i tradicionalna finansijska imovina.',
    description = 'Platforma objedinjuje proveru porekla sredstava, procenu rizika novčanika i izveštavanje po CARF, DAC8 i MiCA standardu — u jedinstvenom dosijeu spremnom za regulatora ili revizora.',
    value_statement = 'dokumentovana usklađenost spremna za regulatora, u svakom trenutku.',
    best_for = ARRAY['Banke', 'Finansijske institucije', 'Compliance timovi', 'Advokatske kancelarije', 'CASP pružaoci usluga']
WHERE key = 'digitalna_imovina';
