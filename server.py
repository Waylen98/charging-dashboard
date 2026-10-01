"""Dynamic charging journal; all writes require validated Cloudflare Access."""
import argparse, hashlib, json, os, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import generate
from record_store import RecordStore, StoreError
from github_sync import sync

class AccessVerifier:
    def __init__(self,issuer,audience,email=None):
        import jwt
        self.jwt=jwt;self.issuer=issuer.rstrip('/');self.audience=audience;self.email=email;self.lock=threading.Lock()
        if not audience or not self.issuer.startswith('https://') or not self.issuer.endswith('.cloudflareaccess.com'): raise ValueError('Cloudflare Access issuer and audience required')
        self.keys=jwt.PyJWKClient(self.issuer+'/cdn-cgi/access/certs',cache_keys=True,timeout=10)
    def __call__(self,token):
        if not token: return False
        try:
            with self.lock: key=self.keys.get_signing_key_from_jwt(token).key
            claims=self.jwt.decode(token,key,algorithms=['RS256'],audience=self.audience,issuer=self.issuer,options={'require':['exp','iat','iss','aud']},leeway=10)
            return bool(claims.get('email')) and (not self.email or claims['email'].casefold()==self.email.casefold())
        except Exception: return False

def payload(store):
    records,excluded=generate.load_records(store.path)
    data={'version':'3.0.0','records':records,'excluded':excluded,'live':True}
    data['revision']=hashlib.sha256(generate.safe_json(data).encode()).hexdigest()[:16]
    return data

def make_server(store,code_dir,origin,verify,port=43140,preview=False):
    code_dir=Path(code_dir)
    class Handler(BaseHTTPRequestHandler):
        server_version='ChargingJournal'
        def setup(self):
            super().setup();self.connection.settimeout(20)
        def log_message(self,*args): pass
        def send(self,status,data,content_type='application/json; charset=utf-8',etag=None):
            if not isinstance(data,bytes): data=json.dumps(data,ensure_ascii=False,allow_nan=False).encode()
            self.send_response(status);self.send_header('Content-Type',content_type)
            self.send_header('Cache-Control','no-store' if status!=304 else 'no-cache')
            self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY')
            self.send_header('Referrer-Policy','strict-origin-when-cross-origin')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if etag: self.send_header('ETag',etag)
            self.send_header('Content-Length',str(len(data)));self.end_headers()
            if data: self.wfile.write(data)
        def authorized(self):
            if preview: return True
            return verify(self.headers.get('Cf-Access-Jwt-Assertion',''))
        def do_GET(self):
            path=urlsplit(self.path).path
            try:
                if path.startswith('/admin'):
                    if not self.authorized(): self.send(401,{'error':'LOGIN_REQUIRED','message':'请登录后录入。'});return
                    if path=='/admin/api/session': self.send(200,{'authenticated':True,'preview':preview});return
                    if path in ('/admin','/admin/'):
                        page=(code_dir/'admin.html').read_text(encoding='utf-8').replace('<!-- INLINE_STYLE -->','<style>'+(code_dir/'dashboard.css').read_text(encoding='utf-8')+'</style>').replace('<!-- INLINE_APP -->','<script>'+(code_dir/'admin.js').read_text(encoding='utf-8')+'</script>')
                        self.send(200,page.encode(),'text/html; charset=utf-8');return
                if path=='/api/records':
                    data=payload(store);etag='"'+data['revision']+'"'
                    if self.headers.get('If-None-Match')==etag: self.send(304,b'',etag=etag)
                    else: self.send(200,data,etag=etag)
                elif path=='/api/health': self.send(200,{'status':'ok','version':'3.0.0'})
                elif path=='/':
                    records,excluded=generate.load_records(store.path)
                    self.send(200,generate.render(records,excluded=excluded).encode(),'text/html; charset=utf-8')
                else: self.send(404,{'error':'NOT_FOUND'})
            except (ValueError,OSError) as error:
                self.send(503,{'error':'READ_FAILED','message':'记录暂时无法读取，请稍后重试。'})
        def do_POST(self):
            if urlsplit(self.path).path!='/admin/api/records': self.send(404,{'error':'NOT_FOUND'});return
            if not self.authorized(): self.send(401,{'error':'LOGIN_REQUIRED','message':'登录已过期，请重新登录后保存。'});return
            if self.headers.get('Origin')!=origin or self.headers.get('X-Charging-Request')!='manual-entry':
                self.send(403,{'error':'ORIGIN_REJECTED','message':'请从充电网页录入。'});return
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':
                self.send(415,{'error':'JSON_REQUIRED'});return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if length<=0 or length>8192: self.send(413,{'error':'BODY_LIMIT'});return
                record=json.loads(self.rfile.read(length))
                key=self.headers.get('Idempotency-Key','')
                if not key: raise StoreError('MISSING_REQUEST_ID','请求标识缺失，请刷新录入页。')
                result=store.add(record,request_id=key)
                result['revision']=payload(store)['revision']
                self.send(201 if result['action']=='added' else 200,result)
            except StoreError as error: self.send(error.status,{'error':error.code,'message':str(error)})
            except (ValueError,UnicodeError): self.send(400,{'error':'INVALID_JSON','message':'记录格式不正确。'})
            except OSError: self.send(503,{'error':'SAVE_FAILED','message':'未能确认保存，请保持表单并重试。'})
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.daemon_threads=True
    return server

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',default=os.environ.get('CHARGING_DATA_DIR','/srv/charging'))
    parser.add_argument('--port',type=int,default=int(os.environ.get('CHARGING_PORT','43140')))
    parser.add_argument('--preview',action='store_true')
    args=parser.parse_args();store=RecordStore(args.data_dir)
    if args.preview:
        if not (store.directory/'.preview-mode').exists() or store.directory.resolve()==Path('/srv/charging'): raise SystemExit('Preview requires isolated marked data directory')
        verifier=lambda token:False
        origin=f'http://127.0.0.1:{args.port}'
    else:
        verifier=AccessVerifier(os.environ.get('CHARGING_ACCESS_ISSUER',''),os.environ.get('CHARGING_ACCESS_AUD',''),os.environ.get('CHARGING_OWNER_EMAIL'))
        origin=os.environ.get('CHARGING_ORIGIN','https://charging.waylenlifeos.dpdns.org')
        def backup_loop():
            while True:
                try: sync(store)
                except Exception: print('Charging backup pending; retrying later',flush=True)
                time.sleep(30)
        threading.Thread(target=backup_loop,daemon=True).start()
    server=make_server(store,Path(__file__).resolve().parent,origin,verifier,args.port,args.preview)
    print(f'Charging journal 3.0.0 on 127.0.0.1:{args.port}',flush=True)
    server.serve_forever()
if __name__=='__main__': main()
