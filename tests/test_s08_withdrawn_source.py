"""S08: real HTTP routes, synthetic tenant-filtered database; no production IO."""
import pytest

from shared import rokovi
from tests.ns005_harness import pripremi, ocisti, zaglavlje
from tests.test_ns2b_c_odbijen_rok_ostaje_odbijen import _baza, _odluke_reda


@pytest.fixture
def env(monkeypatch):
    import shared.audit_immutable as audit
    real_log = audit.log_action
    data = _baza()
    data['predmet_hronologija'][0].update(
        akter=rokovi.AKTER_GENOME, dokument_id=None, dokument_naziv='source.pdf')
    data['predmet_dokumenti'] = []
    rokovi._resetuj_sondu()
    client, db = pripremi(monkeypatch, data)
    monkeypatch.setattr(audit, 'log_action', real_log)
    yield client, db
    rokovi._resetuj_sondu()
    ocisti()


def post(client, who='A', rid='r-1'):
    return client.post(f'/api/rokovi/{rid}/potvrdi', json={}, headers=zaglavlje(who))


def test_withdrawn_direct_post_repeated_no_write(env):
    client, db = env
    for _ in range(2):
        response = post(client)
        assert response.status_code == 409, response.text
        assert _odluke_reda(db, 'r-1') == []


def test_required_source_read_failure(env):
    client, db = env
    db.greske['predmet_dokumenti'] = RuntimeError('source read unavailable')
    assert post(client).status_code == 503
    assert _odluke_reda(db, 'r-1') == []


@pytest.mark.parametrize('deleted', ['doc-1', 'unrelated'])
def test_actual_deletion_with_same_name_documents(env, deleted):
    client, db = env
    row = db.tabele['predmet_hronologija'][0]
    row['dokument_id'] = 'doc-1'
    db.tabele['predmet_dokumenti'] = [
        dict(id=i, user_id='uid-A', predmet_id='pred-A-1', naziv_fajla=n)
        for i, n in [('doc-1', 'source.pdf'), ('doc-2', 'source.pdf'), ('unrelated', 'other.pdf')]]
    db.table('predmet_dokumenti').delete().eq('id', deleted).execute()
    if deleted == 'doc-1':
        row['dokument_id'] = None  # explicit emulation of production FK
    assert post(client).status_code == 200
    assert _odluke_reda(db, 'r-1') == ['rok_potvrdjen']


@pytest.mark.parametrize('source_id,name,actor,docs', [
    ('doc-2', 'source.pdf', rokovi.AKTER_GENOME, ['source.pdf']),
    (None, 'source.pdf', rokovi.AKTER_GENOME, ['source.pdf']),
    (None, None, rokovi.AKTER_GENOME, []),
    (None, 'source.pdf', 'Smart Intake', []),
])
def test_unknown_duplicate_name_and_unrelated_deletion(env, source_id, name, actor, docs):
    client, db = env
    # Two documents can share a name: after deletion of one, the remaining name
    # cannot prove which source disappeared. A live ID also survives unrelated deletion.
    db.tabele['predmet_hronologija'][0].update(
        dokument_id=source_id, dokument_naziv=name, akter=actor)
    db.tabele['predmet_dokumenti'] = [
        dict(id='doc-2', user_id='uid-A', predmet_id='pred-A-1', naziv_fajla=n) for n in docs]
    assert post(client).status_code == 200
    assert _odluke_reda(db, 'r-1') == ['rok_potvrdjen']
    assert post(client).json()['odluka_zabelezena'] is False


def test_ab_authorization_and_document_scope(env):
    client, db = env
    db.tabele['predmet_dokumenti'] = [
        dict(id='b', user_id='uid-B', predmet_id='pred-A-1', naziv_fajla='source.pdf'),
        dict(id='other', user_id='uid-A', predmet_id='other-case', naziv_fajla='source.pdf')]
    assert post(client, 'B').status_code == 404
    assert post(client, 'A', 'r-B').status_code == 404
    assert post(client).status_code == 409
    assert db.tabele['audit_immutable'] == []


def test_confirmed_review_semantics_preserved(env, monkeypatch):
    import routers.rok_odluka as route
    client, db = env
    db.table('audit_immutable').insert(dict(action='rok_potvrdjen', resource_type='rok',
        resource_id='r-1', user_id='uid-A', entry_hash='a' * 64)).execute()
    monkeypatch.setattr(route, 'izvor_uklonjen_posle_potvrde', lambda rows: {'r-1'})
    db.greske['predmet_dokumenti'] = RuntimeError('must not check first-confirmation source')
    assert post(client).status_code == 200
    assert _odluke_reda(db, 'r-1') == ['rok_potvrdjen', 'rok_potvrdjen']


@pytest.mark.parametrize("code,status", [("P0801", 200), ("P0802", 409), ("42501", 503)])
def test_database_fence_response(env, monkeypatch, code, status):
    import shared.audit_immutable as audit
    from postgrest.exceptions import APIError

    client, db = env
    row = db.tabele['predmet_hronologija'][0]
    row['dokument_id'] = 'doc-1'

    def reject_insert(*args):
        if code == "P0801":
            db.table('audit_immutable').insert(dict(action='rok_potvrdjen', resource_type='rok',
                resource_id='r-1', user_id='uid-A')).execute()
        raise APIError({"code": code, "message": "database guard outcome"})

    monkeypatch.setattr(audit, '_build_and_insert', reject_insert)
    response = post(client)
    assert response.status_code == status, response.text
    if code == "P0801":
        assert response.json()['odluka_zabelezena'] is False
        assert response.json()['stanje_odluke'] == 'CONFIRMED'
    assert len(_odluke_reda(db, 'r-1')) == int(code == "P0801")
