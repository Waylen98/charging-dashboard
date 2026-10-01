#!/usr/bin/env python3
"""Existing SSH forced command, now sharing the live data store."""
import json,os,sys
from record_store import RecordStore,StoreError
from github_sync import sync

def main():
    store=RecordStore(os.environ.get('CHARGING_DATA_DIR','/srv/charging'))
    try:
        result=store.add(json.load(sys.stdin),upsert=True)
    except (StoreError,ValueError) as error:
        print(json.dumps({'status':'error','message':str(error)},ensure_ascii=False));return 1
    try: result.update(sync(store))
    except Exception: result['backup']='pending'
    result['live']='https://charging.waylenlifeos.dpdns.org'
    print(json.dumps(result,ensure_ascii=False));return 0
if __name__=='__main__': sys.exit(main())
