"""Original-preservation integrity, SDK serialization and side-effect regressions."""
import asyncio
import base64
from email import policy
from email.parser import BytesParser
import hashlib
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace
from fastapi import HTTPException

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import pytest

from tests.test_release_storage_sdk_semantics import Wire, application, upload
from routers.smart_intake import _encrypt
from security.crypto import _get_field_key
import httpx
from storage3 import SyncStorageClient
from tests.test_release_storage_sdk_semantics import BUCKET
import api

@pytest.fixture
def anyio_backend():return 'asyncio'

@pytest.fixture(autouse=True)
def rate_reset():
    from shared.rate import reset_limiter_state
    reset_limiter_state();yield;reset_limiter_state()

class EncryptedWire(Wire):
    def __init__(self):
        super().__init__();self.uploaded=[]
    def __call__(self,request):
        if request.method=='POST':
            # storage3 uses multipart/form-data even when the supplied file is bytes.
            # Inspect only the actual file part, not the MIME envelope.
            message=BytesParser(policy=policy.default).parsebytes(
                ('Content-Type: '+request.headers['content-type']+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+request.read())
            assert message.is_multipart()
            files=[p.get_payload(decode=True) for p in message.iter_parts()
                   if p.get_param('name',header='content-disposition')=='file']
            assert len(files)==1
            self.uploaded.extend(files)
        return super().__call__(request)

@pytest.mark.anyio
async def test_exact_original_roundtrip_uses_existing_encryption_before_native_sdk():
    raw=b'SYNTHETIC identical content'
    wire=EncryptedWire()
    with application(wire) as state:
        # Use the existing real local encryption implementation with the launcher's
        # synthetic key; neither encrypt nor the actual storage3 serialization is mocked.
        with patch('routers.smart_intake._encrypt',side_effect=_encrypt) as encrypt:
            r=await upload()
    assert r.status_code==200 and r.json()['original_preserved'] is True
    encrypt.assert_called_once_with(raw)
    assert len(wire.uploaded)==1 and wire.calls==['POST']
    encrypted=wire.uploaded[0]
    assert encrypted!=raw and raw not in encrypted
    envelope=base64.urlsafe_b64decode(encrypted)
    recovered=AESGCM(_get_field_key()).decrypt(envelope[:12],envelope[12:],None)
    assert recovered==raw
    assert hashlib.sha256(recovered).digest()==hashlib.sha256(raw).digest()
    assert state.rows[0]['storage_path']==wire.keys[0]

@pytest.mark.anyio
async def test_encryption_failure_prevents_native_storage_and_all_downstream():
    wire=EncryptedWire()
    with application(wire) as state:
        with patch('routers.smart_intake._encrypt',side_effect=ValueError('synthetic encryption failure')):
            r=await upload()
    assert r.status_code==503 and 'synthetic encryption failure' not in r.text
    assert wire.uploaded==[] and wire.keys==[]
    assert not any(method=='POST' for method in wire.calls)
    assert state.rows==[]
    state.extract.assert_not_called();state.ingest.assert_not_called()
    state.consume.assert_not_awaited();state.oai.assert_not_called()

@pytest.mark.parametrize('path', ['synthetic/предмет/član 1+%.pdf', 'synthetic/案子/потврда.pdf'])
def test_native_sdk_unicode_path_and_full_key_contract(path):
    wire=Wire()
    with httpx.Client(transport=httpx.MockTransport(wire)) as http:
        client=SyncStorageClient('http://127.0.0.1:9/storage/v1/',headers={},http_client=http)
        ack=client.from_(BUCKET).upload(path,b'SYNTHETIC encrypted bytes')
    assert ack.path==path
    assert ack.full_path==BUCKET+'/'+path and ack.fullPath==ack.full_path
    assert wire.keys==[path] and wire.calls==['POST']

@pytest.mark.anyio
async def test_unicode_filename_preserves_original_and_normalizes_only_suffix():
    wire=EncryptedWire()
    raw=b'SYNTHETIC unicode filename content'
    name='Mišljenje–测验.PDF'
    with application(wire) as state:
        with patch('routers.smart_intake._encrypt',side_effect=_encrypt):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app),base_url='http://127.0.0.1') as client:
                response=await client.post('/api/predmeti/pred-1/upload',headers={'Authorization':'Bearer synthetic'},
                    files={'file':(name,raw,'application/pdf')})
    assert response.status_code==200 and response.json()['filename']==name
    assert len(state.rows)==1 and state.rows[0]['naziv_fajla']==name
    assert state.rows[0]['storage_path']==wire.keys[0]
    assert wire.keys[0].startswith('synthetic-user/pred-1/') and wire.keys[0].endswith('.pdf')
    encoded=base64.urlsafe_b64decode(wire.uploaded[0])
    assert AESGCM(_get_field_key()).decrypt(encoded[:12],encoded[12:],None)==raw

@pytest.mark.anyio
@pytest.mark.parametrize('outcome',['error','bad_json','empty','error_200','null','blank','wrong','wrong_type','timeout'])
async def test_unconfirmed_original_has_zero_chunk_task_audit_or_cleanup_job(outcome):
    wire=Wire(outcome,'error_return')
    with application(wire) as state:
        with patch('uploaded_doc.chunker.chunk_document') as chunk, \
             patch('services.event_bus.emit_durable',new=AsyncMock()) as task, \
             patch('shared.audit_immutable.log_action',new=AsyncMock()) as audit, \
             patch('uploaded_doc.cleanup.cleanup_expired') as expired:
            response=await upload()
    assert response.status_code==503
    assert response.json()['detail']=='Interna greška servera. Pokušajte ponovo.'
    assert state.rows==[]
    state.extract.assert_not_called();chunk.assert_not_called();state.ingest.assert_not_called()
    state.consume.assert_not_awaited();state.oai.assert_not_called()
    task.assert_not_called();audit.assert_not_called();expired.assert_not_called()
    assert wire.removes==wire.keys and len(wire.keys)==1

@pytest.mark.anyio
async def test_valid_ack_precedes_one_document_and_one_charge_with_business_events():
    order=[]
    class OrderedWire(Wire):
        def __call__(self,request):
            order.append('storage-'+request.method)
            response=super().__call__(request)
            if request.method=='POST':order.append('storage-response')
            return response
    wire=OrderedWire()
    with application(wire) as state:
        def extract(*args):
            order.append('ocr');assert 'storage-response' in order
            return ('SYNTHETIC source only.',False,False,None,None)
        def chunk(*args,**kwargs):
            order.append('chunk');return SimpleNamespace(total_chunks=1)
        def ingest(*args,**kwargs):
            order.append('index');assert state.rows==[];return 1
        async def event(*args,**kwargs):
            assert len(state.rows)==1;order.append('event')
        async def consume(*args,**kwargs):
            assert len(state.rows)==1;order.append('charge')
        state.extract.side_effect=extract;state.ingest.side_effect=ingest
        state.consume.side_effect=consume
        with patch('uploaded_doc.chunker.chunk_document',side_effect=chunk) as chunk_call, \
             patch('services.event_bus.emit_durable',new=AsyncMock(side_effect=event)) as task, \
             patch('shared.audit_immutable.log_action',new=AsyncMock()) as audit, \
             patch('uploaded_doc.cleanup.cleanup_expired'):
            response=await upload()
            await asyncio.sleep(0)  # drain scheduled audit coroutine, not a race proof
    assert response.status_code==200 and response.json()['original_preserved'] is True
    assert order.index('storage-response')<order.index('ocr')<order.index('chunk')<order.index('index')<order.index('charge')
    assert len(state.rows)==1 and len(wire.keys)==1 and wire.removes==[]
    chunk_call.assert_called_once();state.ingest.assert_called_once();state.consume.assert_awaited_once()
    assert task.await_count==2
    assert {c.args[0] if c.args else c.kwargs['action'] for c in audit.call_args_list}=={'dokument_upload','dokument_ai_analiza_complete'}

@pytest.mark.anyio
@pytest.mark.parametrize('cleanup',['ok','error','error_return'])
async def test_downstream_failure_cleanup_cannot_falsely_report_deleted(cleanup,caplog):
    caplog.set_level('INFO',logger='vindex.api')
    wire=Wire('ok',cleanup)
    with application(wire) as state:
        state.extract.side_effect=HTTPException(422,'Synthetic downstream failure')
        response=await upload()
    assert response.status_code==422 and response.json()['detail']=='Synthetic downstream failure'
    assert state.rows==[] and wire.removes==wire.keys and len(wire.keys)==1
    state.ingest.assert_not_called();state.consume.assert_not_awaited();state.oai.assert_not_called()
    if cleanup!='ok':
        assert wire.blobs
        assert 'obrisan originalni fajl' not in caplog.text
        assert any(r.levelname=='WARNING' and 'cleanup' in r.message.lower() for r in caplog.records)
    else:assert not wire.blobs
