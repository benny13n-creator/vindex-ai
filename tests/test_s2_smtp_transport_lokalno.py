# -*- coding: utf-8 -*-
"""S2-D — transportna granica podsetnika kroz STVARAN `_smtp_send` (smtplib, STARTTLS, AUTH) prema lokalnom SMTP
serveru za hvatanje poruka na 127.0.0.1. Nijedna poruka ne napušta računar; primaoci su `@example.invalid`.

Meri: šta se broji kao `poslato` (SMTP je prihvatio poruku — NE prijem u sanduče), šta kao `neisporuceno`
(rezervisano, ishod nepoznat ili neuspešan, bez automatskog ponavljanja) i da odbijen primalac jednog korisnika ne
gasi podsetnik drugog."""
import asyncio
import datetime as _dt
import socket
import ssl
import threading
from unittest.mock import patch

import pytest

from tests import test_b10_reminder_claim as b10
from tests.test_g2_podsetnici_raspored import _Dan, _baza, _dan, u_vreme
from tests.test_n4_podsetnici import _rok


def _sertifikat(tmp_path):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    kljuc = ec.generate_private_key(ec.SECP256R1())
    ime = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    sada = _dt.datetime.now(_dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(ime).issuer_name(ime).public_key(kljuc.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(sada - _dt.timedelta(days=1))
            .not_valid_after(sada + _dt.timedelta(days=1)).sign(kljuc, hashes.SHA256()))
    c, k = tmp_path / "c.pem", tmp_path / "k.pem"
    c.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    k.write_bytes(kljuc.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
    return str(c), str(k)


class LokalniSmtp:
    """Minimalan SMTP server: EHLO, STARTTLS, AUTH PLAIN/LOGIN, MAIL, RCPT, DATA, QUIT. `odbij_rcpt` — adrese za
    koje RCPT dobija 550; `auth_pada` — 535; `posle_data` — 'ok' | '421' | 'prekid' (veza zatvorena bez odgovora)."""

    def __init__(self, cert, kljuc, odbij_rcpt=(), auth_pada=False, posle_data="ok"):
        self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ctx.load_cert_chain(cert, kljuc)
        self.odbij_rcpt, self.auth_pada, self.posle_data = set(odbij_rcpt), auth_pada, posle_data
        self.primljeno = []
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self._radi = True
        threading.Thread(target=self._petlja, daemon=True).start()

    def _petlja(self):
        while self._radi:
            try:
                veza, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._sesija, args=(veza,), daemon=True).start()

    def _sesija(self, veza):
        f = veza.makefile("rb")

        def salji(t):
            veza.sendall((t + "\r\n").encode())
        try:
            salji("220 localhost ESMTP test")
            od, za, tls = None, [], False
            while True:
                red = f.readline()
                if not red:
                    return
                k = red.decode("utf-8", "replace").strip()
                gk = k.upper()
                if gk.startswith("EHLO") or gk.startswith("HELO"):
                    veza.sendall(b"250-localhost\r\n" + (b"250-AUTH PLAIN LOGIN\r\n" if tls else b"250-STARTTLS\r\n")
                                 + b"250 OK\r\n")
                elif gk == "STARTTLS":
                    salji("220 Ready")
                    veza = self.ctx.wrap_socket(veza, server_side=True)
                    f, tls = veza.makefile("rb"), True
                elif gk.startswith("AUTH"):
                    if gk.startswith("AUTH LOGIN") and len(k.split()) == 2:
                        salji("334 VXNlcm5hbWU6"); f.readline(); salji("334 UGFzc3dvcmQ6"); f.readline()
                    salji("535 5.7.8 Authentication failed" if self.auth_pada else "235 OK")
                elif gk.startswith("MAIL FROM"):
                    od, za = k, []
                    salji("250 OK")
                elif gk.startswith("RCPT TO"):
                    adr = k.split(":", 1)[1].strip().strip("<>")
                    if adr in self.odbij_rcpt:
                        salji("550 5.1.1 User unknown")
                    else:
                        za.append(adr)
                        salji("250 OK")
                elif gk == "DATA":
                    salji("354 End data with <CR><LF>.<CR><LF>")
                    telo = b""
                    while True:
                        r = f.readline()
                        if r in (b".\r\n", b"") :
                            break
                        telo += r
                    if self.posle_data == "prekid":
                        veza.close()
                        return
                    if self.posle_data == "554":
                        salji("554 5.7.1 Poruka odbijena")
                        continue
                    if self.posle_data == "421":
                        salji("421 4.4.2 Timeout — veza se zatvara")
                        veza.close()
                        return
                    self.primljeno.append({"od": od, "za": list(za), "telo": telo})
                    salji("250 OK queued")
                elif gk == "QUIT":
                    salji("221 Bye")
                    veza.close()
                    return
                else:
                    salji("250 OK")
        except (OSError, ssl.SSLError):
            return

    def zatvori(self):
        self._radi = False
        self.sock.close()


def _pokreni_stvarno(b, server):
    import routers.email_notif as en
    from shared.rate import limiter
    limiter.reset()
    _Dan.pomak = 0
    with u_vreme(_Dan.today()), patch.object(en, "_get_supa", return_value=b), \
         patch.object(en, "_SMTP_HOST", "127.0.0.1"), patch.object(en, "_SMTP_PORT", server.port), \
         patch.object(en, "_SMTP_USER", "test-korisnik"), patch.object(en, "_SMTP_PASS", "test-lozinka"), \
         patch.object(en, "_FROM_ADDR", "podsetnik@example.invalid"), \
         patch.object(en, "_potvrdjeni_ids", lambda ids: set(ids)):
        return asyncio.run(en.posalji_podsetnike(b10._request(), user={"user_id": "cron", "email": ""}))


@pytest.fixture
def cert(tmp_path):
    return _sertifikat(tmp_path)


def _dva_korisnika():
    b = _baza([_rok("r1", _dan(1))])
    b.tabele["korisnik_email_notif"].append({"user_id": "u-2", "aktivan": True, "dan_1": True, "dan_3": False, "dan_7": False})
    b.tabele["profiles"].append({"id": "u-2", "email": "nepostoji@example.invalid"})
    b.tabele["predmeti"].append({"id": "p-9", "user_id": "u-2", "status": "aktivan"})
    b.tabele["predmet_hronologija"].append(dict(_rok("r9", _dan(1)), user_id="u-2", predmet_id="p-9"))
    return b


def test_smtp_prihvata_poslato_i_poruka_ide_samo_vlasniku(cert):
    s = LokalniSmtp(*cert)
    try:
        b = _baza([_rok("r1", _dan(1))])
        rez = _pokreni_stvarno(b, s)
    finally:
        s.zatvori()
    assert rez == {"poslato": 1, "greske": 0, "preskoceno": 0, "neisporuceno": 0, "kasni": 0}
    assert len(s.primljeno) == 1 and s.primljeno[0]["za"] == [b10.MAIL]
    import email
    poruka = email.message_from_bytes(s.primljeno[0]["telo"])
    html = next(d for d in poruka.walk() if d.get_content_type() == "text/html").get_payload(decode=True).decode()
    assert poruka["To"] == b10.MAIL and "Rok za žalbu" in html and _dan(1) in html


def test_odbijen_primalac_jednog_korisnika_ne_gasi_drugog_i_ponavlja_se_ograniceno(cert):
    """RCPT 550 je odbijanje PRE sadržaja: poruka sigurno nije predata (D4) → `neuspeh`, greska, ponavlja se najviše
    _MAX_POKUSAJA puta; drugi korisnik dobija svoju poruku."""
    import routers.email_notif as en
    s = LokalniSmtp(*cert, odbij_rcpt={"nepostoji@example.invalid"})
    try:
        b = _dva_korisnika()
        rez = _pokreni_stvarno(b, s)
        assert rez["poslato"] == 1 and rez["greske"] == 1 and rez["neisporuceno"] == 0, rez
        assert [m["za"] for m in s.primljeno] == [[b10.MAIL]]
        drugi = next(r for r in b.log if r["user_id"] == "u-2")
        assert (drugi["stanje"], drugi["pokusaja"]) == ("neuspeh", 1)
        for _ in range(5):                                                  # ponovljena slanja istog dana
            _pokreni_stvarno(b, s)
    finally:
        s.zatvori()
    assert (drugi["stanje"], drugi["pokusaja"]) == ("neuspeh", en._MAX_POKUSAJA)   # ograničeno, ne beskonačno
    assert [m["za"] for m in s.primljeno] == [[b10.MAIL]]                   # prvi korisnik nije dobio duplikat


def test_pad_prijave_na_smtp_nije_predato_pa_ponovno_slanje_isporucuje_jednom(cert):
    """F6: pogrešna lozinka (535) je ranije trošila rezervaciju kao „neisporuceno“ — podsetnik tog dana izgubljen."""
    s = LokalniSmtp(*cert, auth_pada=True)
    b = _baza([_rok("r1", _dan(1))])
    try:
        rez = _pokreni_stvarno(b, s)
        assert rez["poslato"] == 0 and rez["greske"] == 1 and rez["neisporuceno"] == 0 and s.primljeno == []
        assert [(r["stanje"], r["pokusaja"]) for r in b.log] == [("neuspeh", 1)]
        s.auth_pada = False                                                  # lozinka ispravljena
        rez2 = _pokreni_stvarno(b, s)
        rez3 = _pokreni_stvarno(b, s)
    finally:
        s.zatvori()
    assert rez2["poslato"] == 1 and rez3["poslato"] == 0 and len(s.primljeno) == 1
    assert [(r["stanje"], r["pokusaja"]) for r in b.log] == [("poslato", 2)]


def test_421_posle_sadrzaja_je_izricito_neprihvatanje_i_ponavlja_se(cert):
    """Server je ODGOVORIO 421 na kraj sadržaja: poruku nije prihvatio (RFC 5321) → `neuspeh`, ponavlja se."""
    s = LokalniSmtp(*cert, posle_data="421")
    b = _baza([_rok("r1", _dan(1))])
    try:
        rez = _pokreni_stvarno(b, s)
        assert rez["greske"] == 1 and rez["neisporuceno"] == 0 and s.primljeno == []
        s.posle_data = "ok"
        rez2 = _pokreni_stvarno(b, s)
    finally:
        s.zatvori()
    assert rez2["poslato"] == 1 and len(s.primljeno) == 1


def test_prekid_veze_posle_sadrzaja_je_nepoznat_ishod_i_ne_ponavlja_se(cert):
    """Veza pukla posle predaje sadržaja, bez odgovora: poruka je MOŽDA isporučena → `nepoznato`, bez ponavljanja."""
    s = LokalniSmtp(*cert, posle_data="prekid")
    b = _baza([_rok("r1", _dan(1))])
    try:
        rez = _pokreni_stvarno(b, s)
        assert rez["poslato"] == 0 and rez["neisporuceno"] == 1 and rez["greske"] == 0, rez
        s.posle_data = "ok"
        rez2 = _pokreni_stvarno(b, s)
    finally:
        s.zatvori()
    assert rez2["poslato"] == 0 and s.primljeno == [] and [r["stanje"] for r in b.log] == ["nepoznato"]


def test_554_posle_sadrzaja_je_trajno_odbijeno_bez_ponavljanja(cert):
    s = LokalniSmtp(*cert, posle_data="554")
    b = _baza([_rok("r1", _dan(1))])
    try:
        rez = _pokreni_stvarno(b, s)
        s.posle_data = "ok"
        rez2 = _pokreni_stvarno(b, s)
    finally:
        s.zatvori()
    assert rez["greske"] == 1 and rez["poslato"] == 0 and rez2["poslato"] == 0 and s.primljeno == []
    assert [r["stanje"] for r in b.log] == ["odbijeno"]


def test_server_nedostupan_nije_predato_ponavlja_se(cert):
    s = LokalniSmtp(*cert)
    s.zatvori()                                                              # port više ne prima veze
    b = _baza([_rok("r1", _dan(1))])
    rez = _pokreni_stvarno(b, s)
    assert rez["poslato"] == 0 and rez["greske"] == 1 and rez["neisporuceno"] == 0
    assert [(r["stanje"], r["pokusaja"]) for r in b.log] == [("neuspeh", 1)]
    s2 = LokalniSmtp(*cert)
    try:
        b2 = b
        import routers.email_notif as en
        rez2 = _pokreni_stvarno(b2, s2)
    finally:
        s2.zatvori()
    assert rez2["poslato"] == 1 and len(s2.primljeno) == 1


def test_smtp_prihvatio_a_zapis_ishoda_pao_ne_ponavlja_se(cert):
    """Provajder je prihvatio (250), ali upis `poslato` nije uspeo: red ostaje `rezervisano` (nepoznat zapis) →
    greska je vidljiva, ponovno slanje NE šalje duplikat."""
    s = LokalniSmtp(*cert)
    b = _baza([_rok("r1", _dan(1))])
    try:
        b.update_puca = True
        rez = _pokreni_stvarno(b, s)
        b.update_puca = False
        rez2 = _pokreni_stvarno(b, s)
    finally:
        s.zatvori()
    assert rez["poslato"] == 1 and rez["greske"] == 1 and rez2["poslato"] == 0 and len(s.primljeno) == 1
    assert [r["stanje"] for r in b.log] == ["rezervisano"]
