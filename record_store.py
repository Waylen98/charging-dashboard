"""Atomic store shared by the web app and SSH receiver."""
import hashlib, json, math, os, re, tempfile, threading, uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

FIELDS=('date','station','kwh','amount','duration_min','start_soc','end_soc','mileage','coupon','order_id','platform','gun','start_time','stop_method')
TEXT={'station':200,'order_id':120,'platform':80,'gun':80,'start_time':80,'stop_method':120}
LIMITS={'kwh':(0,1000),'amount':(0,10000),'duration_min':(0,1440),'start_soc':(0,100),'end_soc':(0,100),'mileage':(0,1000000),'coupon':(0,10000)}
_locks={}; _guard=threading.Lock()
class StoreError(ValueError):
    def __init__(self,code,message,status=400):
        super().__init__(message); self.code=code; self.status=status
def normalize(raw):
    if not isinstance(raw,dict): raise StoreError('INVALID_RECORD','请提交一条充电记录。')
    out={}
    for key in FIELDS:
        value=raw.get(key)
        if value is None or value=='': continue
        if key in TEXT:
            if not isinstance(value,str) or len(value.strip())>TEXT[key] or any(ord(c)<32 for c in value): raise StoreError('INVALID_FIELD',f'{key} 格式或长度不正确。')
            if value.strip(): out[key]=value.strip()
        elif key=='date':
            try:
                if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value): raise ValueError()
                date.fromisoformat(value)
            except ValueError: raise StoreError('INVALID_DATE','请填写有效的充电日期。')
            out[key]=value
        else:
            try:
                if isinstance(value,bool): raise ValueError()
                num=float(value);low,high=LIMITS[key]
                if not math.isfinite(num) or not low<=num<=high or (key=='kwh' and num==0): raise ValueError()
            except (TypeError,ValueError): raise StoreError('INVALID_NUMBER',f'{key} 的数值不正确。')
            out[key]=int(num) if num.is_integer() else num
    if any(key not in out for key in ('date','station','kwh','amount')): raise StoreError('MISSING_FIELDS','日期、充电站、电量和实付金额为必填项。')
    if 'start_soc' in out and 'end_soc' in out and out['end_soc']<out['start_soc']: raise StoreError('INVALID_SOC','结束电量不能小于起始电量。')
    return out
def same(a,b):
    if a.get('order_id') and b.get('order_id'): return str(a['order_id'])==str(b['order_id'])
    return (a.get('date'),a.get('kwh'),a.get('amount'))==(b.get('date'),b.get('kwh'),b.get('amount'))

def matches(record,incoming):
    return same(record,incoming) or any(same(entry['before'],incoming) for entry in record.get('_history',[]))

def revision(record):
    return hashlib.sha256(json.dumps(record,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def request_hash(record):
    return hashlib.sha256(json.dumps(record,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def atomic_write(path,content):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.'+path.name+'-',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as stream: stream.write(content);stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
        if os.name!='nt':
            descriptor=os.open(path.parent,os.O_RDONLY)
            try: os.fsync(descriptor)
            finally: os.close(descriptor)
    finally:
        if os.path.exists(name): os.unlink(name)
class RecordStore:
    def __init__(self,directory):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True);self.path=self.directory/'charging_records.json'
        with _guard: self.thread_lock=_locks.setdefault(str(self.path.resolve()),threading.RLock())
    @contextmanager
    def locked(self):
        with self.thread_lock,open(self.directory/'.records.lock','a+b') as lock:
            if os.name=='nt':
                import msvcrt
                if lock.tell()==0: lock.write(b'0');lock.flush()
                lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_LOCK,1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
            try: yield
            finally:
                if os.name=='nt': lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
                else: fcntl.flock(lock.fileno(),fcntl.LOCK_UN)
    def read(self):
        if not self.path.exists(): return []
        value=json.loads(self.path.read_text(encoding='utf-8-sig'))
        if not isinstance(value,list): raise StoreError('STORE_CORRUPT','记录文件无法读取。',503)
        return value
    def write(self,records):
        if self.path.exists():
            stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]+'.json'
            atomic_write(self.directory/'backups'/'records'/stamp,self.path.read_text(encoding='utf-8-sig'))
        records.sort(key=lambda r:str(r.get('date','')) if isinstance(r,dict) else '')
        atomic_write(self.path,json.dumps(records,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    def add(self,raw,request_id=None,upsert=False):
        record=normalize(raw);digest=hashlib.sha256(json.dumps(record,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        if request_id is not None and not re.fullmatch(r'[a-zA-Z0-9-]{16,80}',request_id): raise StoreError('INVALID_REQUEST_ID','请求标识不正确。')
        with self.locked():
            records=self.read()
            previous=next((r for r in records if request_id and r.get('_request_id')==request_id),None)
            if previous:
                if previous.get('_request_hash')!=digest: raise StoreError('REQUEST_CHANGED','这次请求的内容发生变化，请重新保存。',409)
                return {'status':'ok','action':'no-change','date':record['date'],'records':len(records)}
            existing=next((r for r in records if isinstance(r,dict) and matches(r,record)),None)
            if existing is not None:
                if not upsert: raise StoreError('DUPLICATE_RECORD','已有相同日期、电量和金额或订单号的记录，请先在充电记录中核对。',409)
                # Re-uploaded screenshots may enrich a corrected record, but never undo
                # fields explicitly changed or cleared by the owner.
                protected=set(existing.get('_edited_fields',[]))
                updated={**existing,**{k:v for k,v in record.items() if k not in protected}}
                if updated==existing: return {'status':'ok','action':'no-change','date':record['date'],'records':len(records)}
                records[records.index(existing)]=updated;action='updated'
            else:
                record['_id']=uuid.uuid4().hex
                if request_id: record.update(_request_id=request_id,_request_hash=digest)
                records.append(record);action='added'
            self.write(records)
        return {'status':'ok','action':action,'date':record['date'],'records':len(records)}
    def import_missing(self,items):
        if not isinstance(items,list): raise StoreError('INVALID_IMPORT','备份记录格式不正确。')
        with self.locked():
            records=self.read();count=0
            for raw in items:
                if not isinstance(raw,dict): continue
                try: record=normalize(raw)
                except StoreError: continue
                if not any(isinstance(r,dict) and matches(r,record) for r in records):
                    for key in ('is_test','record_type'):
                        if key in raw: record[key]=raw[key]
                    record['_id']=uuid.uuid4().hex
                    records.append(record);count+=1
            if count: self.write(records)
            return count
    def export(self): return [{k:v for k,v in r.items() if not k.startswith('_')} for r in self.read()]
    def ensure_ids(self):
        with self.locked():
            records=self.read();ids=set();changed=False
            for row in records:
                if not isinstance(row,dict): continue
                identity=row.get('_id')
                if not isinstance(identity,str) or not re.fullmatch(r'[a-f0-9]{32}',identity) or identity in ids:
                    row['_id']=uuid.uuid4().hex;changed=True
                ids.add(row['_id'])
            if changed: self.write(records)
    def detail(self,identity):
        with self.locked():
            row=next((r for r in self.read() if isinstance(r,dict) and r.get('_id')==identity),None)
            if row is None: raise StoreError('NOT_FOUND','这条记录不存在，请返回账本刷新。',404)
            history=[{k:v for k,v in entry.items() if k not in ('request_id','request_hash')} for entry in row.get('_history',[])]
            return {'id':identity,'record':{k:row[k] for k in FIELDS if k in row},'version':revision(row),'history':history}
    def edit(self,identity,raw,expected_version,request_id):
        record=normalize(raw);digest=request_hash(record)
        if not isinstance(request_id,str) or not re.fullmatch(r'[a-zA-Z0-9-]{16,80}',request_id): raise StoreError('INVALID_REQUEST_ID','请求标识不正确。')
        with self.locked():
            records=self.read()
            existing=next((r for r in records if isinstance(r,dict) and r.get('_id')==identity),None)
            if existing is None: raise StoreError('NOT_FOUND','这条记录不存在，请返回账本刷新。',404)
            previous=next((entry for entry in existing.get('_history',[]) if entry.get('request_id')==request_id),None)
            if previous:
                if previous['request_hash']!=digest: raise StoreError('REQUEST_CHANGED','这次请求内容已变化，请重新保存。',409)
                return {'status':'ok','action':'no-change','date':existing['date'],'records':len(records)}
            if not isinstance(expected_version,str) or revision(existing)!=expected_version: raise StoreError('RECORD_CONFLICT','记录已在别处更新。草稿已保留，请载入最新记录后再更正。',409)
            if any(isinstance(row,dict) and row is not existing and matches(row,record) for row in records): raise StoreError('DUPLICATE_RECORD','更正结果与另一条记录重复，请先核对日期、电量、金额或订单号。',409)
            before={k:existing[k] for k in FIELDS if k in existing}
            changed=[k for k in FIELDS if before.get(k)!=record.get(k)]
            if not changed: return {'status':'ok','action':'no-change','date':existing['date'],'records':len(records)}
            entry={'at':datetime.now(timezone.utc).isoformat(),'before':before,'after':record,'changed':changed,'request_id':request_id,'request_hash':digest}
            updated={k:v for k,v in existing.items() if k not in FIELDS}
            updated.update(record)
            updated['_history']=[*existing.get('_history',[]),entry]
            updated['_edited_fields']=sorted(set(existing.get('_edited_fields',[]))|set(changed))
            records[records.index(existing)]=updated
            self.write(records)
        return {'status':'ok','action':'updated','date':record['date'],'records':len(records)}
