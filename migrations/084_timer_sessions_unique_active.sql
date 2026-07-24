-- Migracija 084 — timer_sessions: UNIQUE(user_id) WHERE aktivan
-- Nightly repair (2026-07-24), Faza 1 item 4
--
-- Nalaz: routers/billing.py::timer_start radi "proveri pa upiši" u dva
-- odvojena koraka (SELECT ... WHERE aktivan=True, pa INSERT) bez
-- transakcione izolacije. Dva brza klika (ili dva otvorena taba) mogu oba
-- proći proveru pre nego što ijedan upis commit-uje, kreirajući DVA
-- istovremeno aktivna tajmera za istog korisnika -- tiho kvari naplaćene
-- sate. Ista klasa greške kao TOCTOU race u audit_immutable (v. migracija
-- 081, docs/security/AUDIT_CHAIN_INCIDENT_2026-07-24.md), isti dokazan
-- obrazac rešenja primenjen ovde: delimični unique indeks čini drugi
-- upis nemogućim na nivou baze, kod ga hvata i vraća čist 409 umesto
-- da dozvoli duplikat.

CREATE UNIQUE INDEX IF NOT EXISTS timer_sessions_one_active_per_user
    ON timer_sessions (user_id)
    WHERE aktivan = true;
