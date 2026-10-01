"""GitHub remains a compatible backup/import channel."""
import base64,json,urllib.error,urllib.request
API='https://api.github.com/repos/Waylen98/charging-dashboard/contents/charging_records.json'
def sync(store):
    token_path=store.directory/'.github_token'
    if not token_path.exists(): return {'backup':'disabled'}
    token=token_path.read_text().strip()
    def api(method,payload=None):
        data=json.dumps(payload).encode() if payload is not None else None
        req=urllib.request.Request(API,data=data,method=method,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=20) as res: return json.load(res)
    for attempt in range(3):
        current=api('GET');remote=json.loads(base64.b64decode(current['content']))
        store.import_missing(remote);exported=store.export()
        if remote==exported: return {'backup':'synced'}
        body=json.dumps(exported,ensure_ascii=False,indent=2)+'\n'
        try:
            result=api('PUT',{'message':'Sync charging records from live journal','content':base64.b64encode(body.encode()).decode(),'sha':current['sha'],'branch':'main'})
            return {'backup':'synced','commit':result['commit']['sha']}
        except urllib.error.HTTPError as error:
            if error.code not in (409,422) or attempt==2: raise
    return {'backup':'pending'}
