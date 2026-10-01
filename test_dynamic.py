import base64, concurrent.futures, json, tempfile, threading, time, unittest, urllib.error, uuid
from http.client import HTTPConnection
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from record_store import RecordStore, StoreError
from server import AccessVerifier, make_server
from github_sync import sync

ROW={'date':'2026-09-20','station':'充电站 A','kwh':40,'amount':24}
class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=RecordStore(self.tmp.name)
        self.store.path.write_text(json.dumps([ROW]),encoding='utf-8')
    def tearDown(self): self.tmp.cleanup()
    def test_retry_duplicate_and_changed_request(self):
        row={**ROW,'date':'2026-09-21'};key=str(uuid.uuid4())
        self.assertEqual(self.store.add(row,key)['action'],'added')
        self.assertEqual(self.store.add(row,key)['action'],'no-change')
        with self.assertRaises(StoreError) as ctx: self.store.add({**row,'amount':25},key)
        self.assertEqual(ctx.exception.code,'REQUEST_CHANGED')
        with self.assertRaises(StoreError) as ctx: self.store.add(row,str(uuid.uuid4()))
        self.assertEqual(ctx.exception.code,'DUPLICATE_RECORD')
        self.assertEqual(len(self.store.read()),2)
        self.assertEqual(len(list((self.store.directory/'backups'/'records').glob('*.json'))),1)
    def test_upload_enriches_without_erasing_manual_metadata(self):
        row={**ROW,'date':'2026-09-21'};key=str(uuid.uuid4());self.store.add(row,key)
        self.store.add({**row,'order_id':'order-42','start_soc':20,'end_soc':90},upsert=True)
        latest=self.store.read()[1]
        self.assertEqual(latest['_request_id'],key);self.assertEqual(latest['end_soc'],90)
        self.store.add(row,upsert=True);self.assertEqual(self.store.read()[1]['order_id'],'order-42')
        self.assertEqual(self.store.add(row,key)['action'],'no-change')
    def test_different_known_orders_are_independent(self):
        self.store.add({**ROW,'order_id':'first'},upsert=True)
        self.store.add({**ROW,'order_id':'second'},upsert=True)
        self.assertEqual(len(self.store.read()),2)
    def test_validation_rejects_bad_numbers_dates_and_soc(self):
        for change in [{'kwh':float('nan')},{'amount':-1},{'kwh':True},{'date':'2026-02-30'},{'station':''},{'start_soc':80,'end_soc':20},{'amount':10001}]:
            with self.subTest(change=change),self.assertRaises(StoreError): self.store.add({**ROW,**change})
        self.assertEqual(self.store.read(),[ROW])
    def test_concurrent_writers_do_not_lose_rows(self):
        def add(i): return RecordStore(self.tmp.name).add({**ROW,'amount':i+30},str(uuid.uuid4()))
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool: list(pool.map(add,range(20)))
        self.assertEqual(len(self.store.read()),21)
    def test_failed_atomic_write_keeps_canonical_file(self):
        before=self.store.path.read_bytes()
        with patch('record_store.os.replace',side_effect=OSError('disk full')),self.assertRaises(OSError):
            self.store.add({**ROW,'date':'2026-09-22'},str(uuid.uuid4()))
        self.assertEqual(self.store.path.read_bytes(),before)
    def test_import_stale_snapshot_preserves_new_rows_and_hidden_metadata(self):
        self.store.add({**ROW,'date':'2026-09-22'},str(uuid.uuid4()))
        self.assertEqual(self.store.import_missing([ROW]),0);self.assertEqual(len(self.store.read()),2)
        self.assertFalse(any(k.startswith('_') for r in self.store.export() for k in r))
    def test_github_conflict_reimports_new_remote_record_and_retries(self):
        (self.store.directory/'.github_token').write_text('test-only-token')
        self.store.add({**ROW,'date':'2026-09-21'},str(uuid.uuid4()))
        remote=[ROW];calls=[]
        class Response:
            def __init__(self,value): self.value=value
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self): return json.dumps(self.value).encode()
        def request(req,timeout):
            nonlocal remote
            calls.append(req.method)
            if req.method=='GET': return Response({'content':base64.b64encode(json.dumps(remote).encode()).decode(),'sha':'mock-sha'})
            if calls.count('PUT')==1:
                remote=[ROW,{**ROW,'date':'2026-09-23'}]
                raise urllib.error.HTTPError(req.full_url,409,'conflict',{},None)
            body=json.loads(req.data)
            remote=json.loads(base64.b64decode(body['content']))
            return Response({'commit':{'sha':'saved'}})
        with patch('github_sync.urllib.request.urlopen',side_effect=request): self.assertEqual(sync(self.store)['backup'],'synced')
        self.assertEqual(len(remote),3);self.assertEqual(len(self.store.read()),3)

class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=RecordStore(self.tmp.name)
        self.store.path.write_text(json.dumps([ROW]),encoding='utf-8')
        self.server=make_server(self.store,Path(__file__).parent,'https://charging.example',lambda token:token=='signed-test',0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.headers={'Cf-Access-Jwt-Assertion':'signed-test','Origin':'https://charging.example','Content-Type':'application/json','X-Charging-Request':'manual-entry','Idempotency-Key':str(uuid.uuid4())}
    def tearDown(self): self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def call(self,method,path,body=None,headers=None):
        client=HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        client.request(method,path,json.dumps(body).encode() if body is not None else None,headers or {})
        response=client.getresponse();value=response.read();result=(response.status,dict(response.getheaders()),value);client.close();return result
    def test_public_payload_etag_and_private_endpoints(self):
        status,headers,body=self.call('GET','/api/records');self.assertEqual(status,200)
        self.assertEqual(len(json.loads(body)['records']),1)
        self.assertNotIn('_request_id',body.decode());self.assertNotIn('order_id',body.decode())
        self.assertEqual(self.call('GET','/api/records',headers={'If-None-Match':headers['ETag']})[0],304)
        self.assertEqual(self.call('GET','/')[0],200)
        for path in ['/admin','/admin/','/admin/api/session']:
            self.assertEqual(self.call('GET',path)[0],401)
        self.assertEqual(self.call('GET','/admin/',headers=self.headers)[0],200)
    def test_post_auth_origin_validation_and_idempotency(self):
        row={**ROW,'date':'2026-09-22'}
        self.assertEqual(self.call('POST','/admin/api/records',row)[0],401)
        for change in [{'Origin':'https://evil.example'},{'X-Charging-Request':''}]:
            self.assertEqual(self.call('POST','/admin/api/records',row,{**self.headers,**change})[0],403)
        self.assertEqual(self.call('POST','/admin/api/records',{**row,'kwh':-1},self.headers)[0],400)
        self.assertEqual(self.call('POST','/admin/api/records',row,self.headers)[0],201)
        self.assertEqual(self.call('POST','/admin/api/records',row,self.headers)[0],200)
        status,headers,body=self.call('GET','/api/records');self.assertEqual(len(json.loads(body)['records']),2)

class JWTTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import jwt
            from cryptography.hazmat.primitives.asymmetric import rsa
        except ImportError: raise unittest.SkipTest('Production JWT dependencies installed in server venv')
        cls.jwt=jwt;cls.private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    def test_signed_tokens_require_right_issuer_audience_owner_and_expiry(self):
        verifier=AccessVerifier('https://team.cloudflareaccess.com','charging-aud','owner@example.com')
        claims={'iss':verifier.issuer,'aud':['charging-aud'],'email':'owner@example.com','exp':int(time.time())+300,'iat':int(time.time())}
        with patch.object(verifier.keys,'get_signing_key_from_jwt',return_value=SimpleNamespace(key=self.private.public_key())):
            def signed(values,key=None): return self.jwt.encode(values,key or self.private,algorithm='RS256')
            self.assertTrue(verifier(signed(claims)))
            for change in [{'aud':['other-app']},{'iss':'https://evil.example'},{'email':'other@example.com'},{'exp':int(time.time())-100}]:
                self.assertFalse(verifier(signed({**claims,**change})))
            missing={k:v for k,v in claims.items() if k!='exp'}
            self.assertFalse(verifier(signed(missing)));self.assertFalse(verifier(''));self.assertFalse(verifier('forged'))
            from cryptography.hazmat.primitives.asymmetric import rsa
            wrong=rsa.generate_private_key(public_exponent=65537,key_size=2048)
            self.assertFalse(verifier(signed(claims,wrong)))
if __name__=='__main__': unittest.main()
