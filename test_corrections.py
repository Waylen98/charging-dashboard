import concurrent.futures,json,tempfile,threading,unittest,uuid
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch
from record_store import RecordStore,StoreError
from server import make_server
from github_sync import sync
from test_dynamic import ROW

class Corrections(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=RecordStore(self.tmp.name)
        self.store.path.write_text(json.dumps([{**ROW,'order_id':'old-order','gun':'gun-1','custom':'preserve'}]),encoding='utf-8')
        self.store.ensure_ids();self.identity=self.store.read()[0]['_id']
    def tearDown(self):self.tmp.cleanup()
    def edit(self,changes,request=None,version=None):
        detail=self.store.detail(self.identity)
        return self.store.edit(self.identity,{**detail['record'],**changes},version or detail['version'],request or str(uuid.uuid4()))
    def test_ids_preserve_legacy_data_and_survive_reopen(self):
        before=self.store.path.read_bytes();self.store.ensure_ids()
        self.assertEqual(self.store.path.read_bytes(),before)
        self.assertEqual(RecordStore(self.tmp.name).detail(self.identity)['record']['gun'],'gun-1')
        self.assertEqual(self.store.export()[0]['custom'],'preserve')
    def test_correction_is_atomic_retry_safe_and_preserves_optional_metadata(self):
        old=self.store.detail(self.identity);request=str(uuid.uuid4());body={**old['record'],'amount':26,'order_id':''}
        self.assertEqual(self.store.edit(self.identity,body,old['version'],request)['action'],'updated')
        self.assertEqual(self.store.edit(self.identity,body,old['version'],request)['action'],'no-change')
        new=self.store.detail(self.identity)
        self.assertEqual(len(new['history']),1);self.assertEqual(new['history'][0]['before']['amount'],24)
        self.assertEqual(new['history'][0]['after']['amount'],26);self.assertNotIn('order_id',new['record'])
        self.assertEqual(new['record']['gun'],'gun-1');self.assertEqual(self.store.read()[0]['custom'],'preserve')
        self.assertNotIn('request_id',new['history'][0]);self.assertNotIn('_history',self.store.export()[0])
        with self.assertRaises(StoreError) as error:self.store.edit(self.identity,{**body,'amount':27},old['version'],request)
        self.assertEqual(error.exception.code,'REQUEST_CHANGED')
    def test_stale_duplicate_and_failed_writes_preserve_history(self):
        old=self.store.detail(self.identity);self.edit({'amount':26})
        with self.assertRaises(StoreError) as error:self.edit({'amount':28},version=old['version'])
        self.assertEqual(error.exception.code,'RECORD_CONFLICT')
        self.store.add({**ROW,'date':'2026-09-22','amount':28})
        with self.assertRaises(StoreError) as error:self.edit({'date':'2026-09-22','amount':28,'order_id':''})
        self.assertEqual(error.exception.code,'DUPLICATE_RECORD')
        before=self.store.path.read_bytes()
        with patch('record_store.os.replace',side_effect=OSError('disk full')),self.assertRaises(OSError):self.edit({'amount':29})
        self.assertEqual(self.store.path.read_bytes(),before)
    def test_stale_import_and_reuploaded_screenshot_do_not_undo_correction(self):
        old=self.store.export();self.edit({'amount':26,'date':'2026-09-21','order_id':''})
        self.assertEqual(self.store.import_missing(old),0)
        self.store.add({**old[0],'coupon':2},upsert=True)
        data=self.store.detail(self.identity)
        self.assertEqual(data['record']['amount'],26);self.assertEqual(data['record']['date'],'2026-09-21')
        self.assertNotIn('order_id',data['record']);self.assertEqual(data['record']['coupon'],2)
        self.assertEqual(len(self.store.read()),1)
    def test_concurrent_corrections_conflict_instead_of_overwriting(self):
        old=self.store.detail(self.identity)
        def save(amount):
            try:return self.store.edit(self.identity,{**old['record'],'amount':amount},old['version'],str(uuid.uuid4()))['action']
            except StoreError as error:return error.code
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(save,range(30,36)))
        self.assertEqual(results.count('updated'),1);self.assertEqual(results.count('RECORD_CONFLICT'),5)
        self.assertEqual(len(self.store.detail(self.identity)['history']),1)
    def test_github_backup_replaces_old_version_without_reimporting_it(self):
        import base64
        old=self.store.export();self.edit({'date':'2026-09-21','amount':26,'order_id':''})
        (self.store.directory/'.github_token').write_text('test-only-token')
        calls=[]
        class Response:
            def __init__(self,value):self.value=value
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return json.dumps(self.value).encode()
        def request(req,timeout):
            if req.method=='GET':return Response({'sha':'old','content':base64.b64encode(json.dumps(old).encode()).decode()})
            body=json.loads(base64.b64decode(json.loads(req.data)['content']));calls.append(body)
            return Response({'commit':{'sha':'new'}})
        with patch('github_sync.urllib.request.urlopen',side_effect=request):self.assertEqual(sync(self.store)['backup'],'synced')
        self.assertEqual(len(calls[0]),1);self.assertEqual(calls[0][0]['amount'],26)
        self.assertFalse(any(key.startswith('_') for key in calls[0][0]))
    def test_http_edit_and_history_require_owner_and_same_origin(self):
        server=make_server(self.store,Path(__file__).parent,'https://charging.example',lambda token:token=='signed-test',0)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        route='/admin/api/records/'+self.identity
        def call(method,body=None,headers=None):
            client=HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            client.request(method,route,json.dumps(body).encode() if body is not None else None,headers or {})
            response=client.getresponse();value=response.read();client.close();return response.status,json.loads(value)
        headers={'Cf-Access-Jwt-Assertion':'signed-test','Origin':'https://charging.example','Content-Type':'application/json','X-Charging-Request':'manual-entry','Idempotency-Key':str(uuid.uuid4())}
        try:
            self.assertEqual(call('GET')[0],401)
            status,detail=call('GET',headers=headers);self.assertEqual(status,200)
            body={'record':{**detail['record'],'amount':26},'version':detail['version']}
            self.assertEqual(call('POST',body)[0],401)
            self.assertEqual(call('POST',body,{**headers,'Origin':'https://evil.example'})[0],403)
            self.assertEqual(call('POST',body,headers)[0],200)
            self.assertEqual(len(call('GET',headers=headers)[1]['history']),1)
        finally:server.shutdown();server.server_close();worker.join()

if __name__=='__main__':unittest.main()
