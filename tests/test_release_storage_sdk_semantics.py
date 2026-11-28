"""RC ASGI -> real pinned storage3 -> MockTransport. NO provider/real DB proof."""
import asyncio
from contextlib import contextmanager
import json
import os
from threading import Barrier, Lock
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest
from storage3 import SyncStorageClient
os.environ.setdefault('FOUNDER_EMAILS', 'founder@example.invalid')
import api
from tests.test_intake_original_file_storage import _supa_upload_succeeds, _fake_user, _fake_permission_dependency, _fake_openai_client

BUCKET='intake-dokumenti'

@pytest.fixture
def anyio_backend():return 'asyncio'

@pytest.fixture(autouse=True)
def rate_reset():
    from shared.rate import reset_limiter_state
    reset_limiter_state();yield;reset_limiter_state()

class Wire:
    def __init__(self, outcome='ok', cleanup='ok', barrier=None):
        self.outcome=outcome;self.cleanup=cleanup;self.barrier=barrier
        self.calls=[];self.keys=[];self.removes=[];self.blobs=set();self.lock=Lock()
    def __call__(self,r):
        with self.lock:self.calls.append(r.method)
        if r.method=='POST':
            key=r.url.path.split('/object/'+BUCKET+'/',1)[1]
            with self.lock:self.keys.append(key)
            if self.barrier:self.barrier.wait(timeout=4)
            if self.outcome=='timeout':
                self.blobs.add(key)  # simulated accepted write, lost response
                raise httpx.ReadTimeout('SYNTHETIC_PRIVATE_ERROR',request=r)
            if self.outcome=='error':return httpx.Response(400,json={'statusCode':400,'error':'SyntheticError','message':'SYNTHETIC_PRIVATE_ERROR'})
            if self.outcome=='bad_json':return httpx.Response(200,text='invalid-json')
            if self.outcome=='empty':return httpx.Response(200,json={})
            if self.outcome=='error_200':return httpx.Response(200,json={'error':'SYNTHETIC_PRIVATE_ERROR'})
            if self.outcome=='null':return httpx.Response(200,json={'Key':None})
            if self.outcome=='blank':return httpx.Response(200,json={'Key':''})
            if self.outcome=='wrong':return httpx.Response(200,json={'Key':BUCKET+'/different-owner/other.pdf'})
            if self.outcome=='wrong_type':return httpx.Response(200,json={'Key':[]})
            self.blobs.add(key)
            return httpx.Response(200,json={'Key':BUCKET+'/'+key,'Id':'synthetic-object-id'})
        if r.method=='DELETE':
            keys=json.loads(r.content)['prefixes'];self.removes.extend(keys)
            if self.cleanup=='error_return':return httpx.Response(200,json={'error':'synthetic cleanup failure'})
            if self.cleanup=='error':return httpx.Response(500,json={'statusCode':500,'error':'SyntheticError','message':'synthetic cleanup failure'})
            for key in keys:self.blobs.discard(key)
            return httpx.Response(200,json=[{'name':key} for key in keys])
        raise AssertionError('Unexpected Storage network method: '+r.method)

@contextmanager
def application(wire, raw_return=False):
    rows=[];supa=_supa_upload_succeeds(inserted_rows=rows)
    client=httpx.Client(transport=httpx.MockTransport(wire),base_url='http://127.0.0.1:9')
    storage=SyncStorageClient('http://127.0.0.1:9/storage/v1',headers={'Authorization':'Bearer synthetic'},http_client=client)
    supa.storage=storage
    if raw_return:
        # Explicitly a MOCKED SDK/wrapper return; native upload does not return a dict.
        storage=MagicMock();storage.from_.return_value.upload.return_value={'error':'synthetic wrapper error'};supa.storage=storage
    oai=_fake_openai_client()
    try:
        with patch('api._require_auth',return_value=_fake_user('synthetic-user','user@example.invalid')), \
             patch('api._get_supa',return_value=supa), \
             patch('api.PermissionService.require',return_value=_fake_permission_dependency), \
             patch('shared.kancelarija_utils.get_kancelarija_id',new=AsyncMock(return_value=None)), \
             patch('routers.smart_intake._encrypt',return_value=b'ENCRYPTED-SYNTHETIC'), \
             patch('uploaded_doc.extractor.extract',return_value=('SYNTHETIC source only.',False,False,None,None)) as extract, \
             patch('uploaded_doc.chunker.chunk_document',return_value=SimpleNamespace(total_chunks=1)), \
             patch('uploaded_doc.ingest.ingest_session',return_value=1) as ingest, \
             patch('openai.OpenAI',new=oai), \
             patch('api.UsageService.consume',new=AsyncMock()) as consume:
            yield SimpleNamespace(rows=rows,extract=extract,ingest=ingest,consume=consume,oai=oai)
    finally:client.close()

async def upload():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app),base_url='http://127.0.0.1') as c:
        return await c.post('/api/predmeti/pred-1/upload',headers={'Authorization':'Bearer synthetic'},
                            files={'file':('synthetic.pdf',b'SYNTHETIC identical content','application/pdf')})

@pytest.mark.anyio
async def test_valid_sdk_ack_positive():
    wire=Wire()
    with application(wire) as state:r=await upload()
    assert r.status_code==200,r.text
    assert r.json()['original_preserved'] is True
    assert len(state.rows)==1 and state.rows[0]['storage_path']==wire.keys[0]
    assert state.extract.call_count==state.ingest.call_count==1
    assert wire.calls==['POST']  # no invented read-back/HEAD requirement

@pytest.mark.anyio
@pytest.mark.parametrize('outcome',['error','bad_json','empty','error_200','null','blank','wrong','wrong_type'])
async def test_unconfirmed_sdk_ack_stops_before_downstream(outcome):
    wire=Wire(outcome)
    with application(wire) as state:r=await upload()
    assert r.status_code==503,r.text
    assert r.json()['detail']=='Interna greška servera. Pokušajte ponovo.'
    assert 'SYNTHETIC_PRIVATE_ERROR' not in r.text
    assert state.rows==[]
    state.extract.assert_not_called();state.ingest.assert_not_called();state.consume.assert_not_awaited();state.oai.assert_not_called()
    assert wire.removes==wire.keys

@pytest.mark.anyio
@pytest.mark.parametrize('cleanup',['ok','error','error_return'])
async def test_ambiguous_upload_timeout_preserves_failure_despite_cleanup(cleanup, caplog):
    # UI fixture modules disable logging globally during full-suite collection.
    # caplog.set_level restores capture for this assertion and undoes it afterward.
    caplog.set_level('WARNING',logger='vindex.api')
    wire=Wire('timeout',cleanup)
    with application(wire) as state:r=await upload()
    assert r.status_code==503 and state.rows==[]
    state.extract.assert_not_called();state.ingest.assert_not_called();state.consume.assert_not_awaited()
    assert wire.removes==wire.keys
    if cleanup=='error_return':
        assert 'cleanup returned an unconfirmed response' in caplog.text
    if cleanup!='ok':assert wire.blobs  # no false claim that orphan was removed
    else:assert not wire.blobs  # simulated transport state only

@pytest.mark.anyio
async def test_mock_nonthrow_error_return_stops_before_downstream():
    wire=Wire()
    with application(wire,raw_return=True) as state:r=await upload()
    assert r.status_code==503 and state.rows==[]
    state.extract.assert_not_called();state.ingest.assert_not_called();state.consume.assert_not_awaited()

@pytest.mark.anyio
async def test_same_content_new_occurrence_uses_new_key_after_uncertain_cleanup():
    wire=Wire('timeout','error_return')
    with application(wire) as state:
        first=await upload();wire.outcome='ok';second=await upload()
    assert first.status_code==503 and second.status_code==200
    assert len(wire.keys)==2 and len(set(wire.keys))==2
    assert wire.removes==[wire.keys[0]] and len(state.rows)==1
    assert state.rows[0]['storage_path']==wire.keys[1]

@pytest.mark.anyio
async def test_overlapping_uploads_have_disjoint_cleanup_keys():
    wire=Wire('timeout','error_return',Barrier(2))
    with application(wire) as state:responses=await asyncio.gather(upload(),upload())
    assert [r.status_code for r in responses]==[503,503]
    assert len(set(wire.keys))==2 and sorted(wire.keys)==sorted(wire.removes)
    assert state.rows==[];state.extract.assert_not_called();state.ingest.assert_not_called()
