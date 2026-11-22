"""Persistent operational controls, independent of replaceable market snapshots."""
import sqlite3, json, os, time, hashlib
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import requests
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parent
DB=ROOT/'output'/'operations.db'
def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def connect():
    DB.parent.mkdir(exist_ok=True)
    c=sqlite3.connect(DB,timeout=30)
    c.executescript('''CREATE TABLE IF NOT EXISTS runs (run_id INTEGER PRIMARY KEY, timestamp TEXT, status TEXT, as_of TEXT, checks INTEGER, failed_checks INTEGER, quality_pct REAL, raw_prices INTEGER, mastered_prices INTEGER, dual_source INTEGER, detail TEXT);
    CREATE TABLE IF NOT EXISTS cases (case_id TEXT PRIMARY KEY, rule TEXT, security_id TEXT, as_of TEXT, severity TEXT, detail TEXT, status TEXT, owner TEXT, note TEXT, first_seen TEXT, last_seen TEXT, present INTEGER);
    CREATE TABLE IF NOT EXISTS audit (timestamp TEXT, case_id TEXT, status TEXT, owner TEXT, note TEXT);''')
    return c

def record(summary=None, errors=(), failure=None):
    s=summary or {}; stamp=now()
    with closing(connect()) as c, c:
        c.execute('INSERT INTO runs(timestamp,status,as_of,checks,failed_checks,quality_pct,raw_prices,mastered_prices,dual_source,detail) VALUES(?,?,?,?,?,?,?,?,?,?)',(stamp,'Failed' if failure else 'Published',s.get('as_of'),s.get('checks'),s.get('failed_checks'),s.get('quality_pct'),s.get('raw_prices'),s.get('mastered_prices'),s.get('dual_source_approved_prices'),failure or ''))
        if failure: return
        c.execute('UPDATE cases SET present=0')
        for rule,sid,day,severity,detail in errors:
            key=hashlib.sha256(json.dumps([rule,sid,day,detail]).encode()).hexdigest()[:20]
            c.execute('''INSERT INTO cases VALUES(?,?,?,?,?,?,?,?,?,?,?,1) ON CONFLICT(case_id) DO UPDATE SET last_seen=excluded.last_seen,present=1,status=CASE WHEN cases.status='Resolved' THEN 'Reopened' ELSE cases.status END''',(key,rule,sid,day,severity,detail,'Open','','',stamp,stamp))

def update_case(key,status,owner,note):
    if not owner.strip() or not note.strip(): raise ValueError('Owner and investigation note are required.')
    if status not in ('Open','In review','Resolved'): raise ValueError('Invalid workflow status')
    with closing(connect()) as c,c:
        row=c.execute('SELECT present FROM cases WHERE case_id=?',(key,)).fetchone()
        if not row: raise ValueError('Case not found')
        if status=='Resolved' and row[0]: raise ValueError('Exception still present in latest snapshot. Correct source and refresh before resolving.')
        c.execute('UPDATE cases SET status=?,owner=?,note=? WHERE case_id=?',(status,owner,note,key))
        c.execute('INSERT INTO audit VALUES(?,?,?,?,?)',(now(),key,status,owner,note))

def fetch_13f(cik,contact):
    if not contact or '@' not in contact: raise ValueError('Enter your contact email for SEC fair-access identification.')
    cik=str(int(cik)); headers={'User-Agent':f'InvestData360 research {contact}','Accept-Encoding':'gzip, deflate'}
    def get(url):
        time.sleep(.2); r=requests.get(url,headers=headers,timeout=45); r.raise_for_status(); return r
    sub=get(f'https://data.sec.gov/submissions/CIK{int(cik):010d}.json').json(); recent=sub['filings']['recent']
    i=next((i for i,f in enumerate(recent['form']) if f=='13F-HR'),None)
    if i is None: raise ValueError('No recent original 13F-HR filing found.')
    acc=recent['accessionNumber'][i]; base=f'https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace("-", "")}/'
    files=get(base+'index.json').json()['directory']['item']; rows=[]; source=None
    for file in files:
        name=file['name']
        if not name.lower().endswith('.xml'): continue
        root=ET.fromstring(get(base+name).content)
        for node in root.iter(): node.tag=node.tag.split('}')[-1]
        for node in root.findall('.//infoTable'):
            def val(path): return node.findtext(path,default='').strip()
            rows.append({'Issuer':val('nameOfIssuer'),'Class':val('titleOfClass'),'CUSIP':val('cusip'),'Reported value (USD)':int(val('value')),'Quantity':int(val('shrsOrPrnAmt/sshPrnamt')),'Quantity type':val('shrsOrPrnAmt/sshPrnamtType'),'Put/Call':val('putCall')})
        if rows: source=base+name; break
    if not rows: raise ValueError('No XML holdings information table found.')
    result={'manager':sub['name'],'report_date':recent['reportDate'][i],'filing_date':recent['filingDate'][i],'accession':acc,'source':source,'rows':rows,'retrieved':now(),'amendments':sum(f=='13F-HR/A' and d==recent['reportDate'][i] for f,d in zip(recent['form'],recent['reportDate']))}
    out=ROOT/'output'; out.mkdir(exist_ok=True); (out/f'13f_{cik}.json').write_text(json.dumps(result),encoding='utf-8'); return result

def publish_cloud(account,user,password,warehouse,database,schema):
    import snowflake.connector
    from snowflake.connector.pandas_tools import write_pandas
    import pandas as pd
    # Unique versioned tables avoid destructive overwrite; no existing tables dropped.
    suffix=datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
    names=[]
    with closing(sqlite3.connect(ROOT/'output'/'investment.db')) as local:
        local.execute('BEGIN')
        frames={n:pd.read_sql_query('SELECT * FROM '+n,local) for n in ('securities','prices_master','corporate_actions','exceptions')}
    with closing(snowflake.connector.connect(account=account,user=user,password=password,warehouse=warehouse,database=database,schema=schema)) as conn:
        for n,df in frames.items():
            name=n.upper()+'_'+suffix; df.columns=[x.upper() for x in df.columns]
            success,_,count,_=write_pandas(conn,df,name,auto_create_table=True)
            if not success or count!=len(df): raise RuntimeError(f'Upload incomplete: {name}')
            names.append(name)
    return names
