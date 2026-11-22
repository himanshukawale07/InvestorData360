"""Real corporate action observations; no synthetic fallback."""
import os, math, json
from datetime import date,timedelta
import requests

FIELDS=['security_id','event_type','event_date','date_basis','amount','unit','source','source_id','announcement_date','record_date','payment_date','process_date','provider_status','currency','details']
def number(x):
    try:
        n=float(x); return n if math.isfinite(n) and n>0 else None
    except (ValueError,TypeError): return None

def alpaca_rows(payload,symbols):
    out=[]
    groups=payload['corporate_actions']
    for kind, records in groups.items():
        for r in records or []:
            sid=next((r.get(k) for k in ('symbol','acquiree_symbol','old_symbol','parent_symbol','acquirer_symbol','new_symbol') if r.get(k) in symbols),None)
            if not sid: continue
            typ=kind.removesuffix('s').replace('_',' ').title()
            if kind=='cash_dividends': typ='Cash dividend'
            elif kind=='capital_gains_distributions': typ='Capital gains distribution'
            elif kind in ('forward_splits','reverse_splits'): typ='Stock split'
            basis=next((k for k in ('ex_date','effective_date','process_date') if r.get(k)),None)
            if not basis: continue
            amount=None; unit='See source details'; currency=r.get('currency') or 'USD'
            if kind in ('cash_dividends','capital_gains_distributions'): amount=number(r.get('rate')); unit=f'{currency} per share'
            elif kind in ('forward_splits','reverse_splits','unit_splits'):
                old=number(r.get('old_rate')); new=number(r.get('new_rate')); amount=new/old if old and new else None; unit='New shares per old share'
            out.append((sid,typ,r[basis],basis,amount,unit,'Alpaca',str(r.get('id','')),r.get('declaration_date') or r.get('announcement_date'),r.get('record_date'),r.get('payable_date'),r.get('process_date'),r.get('status'),currency,json.dumps(r,sort_keys=True)))
    return out

def fetch_events(symbols,raw,today=None):
    import yfinance as yf
    today=today or date.today(); start=today-timedelta(days=366*5); end=today+timedelta(days=90)
    rows=[]; statuses=[]
    for sid in symbols:
        try:
            h=yf.Ticker(sid).history(start=start.isoformat(),end=(today+timedelta(days=1)).isoformat(),interval='1d',auto_adjust=False,actions=True,raise_errors=True)
            if h.empty: raise ValueError('Empty history')
            h.to_csv(raw/f'{sid}_corporate_yahoo.csv')
            found=[]
            for dt,r in h.iterrows():
                for col,typ,unit in [('Dividends','Cash dividend','USD per share'),('Stock Splits','Stock split','New shares per old share'),('Capital Gains','Capital gains distribution','USD per share')]:
                    n=number(r.get(col)); d=dt.date().isoformat()
                    if n is not None: found.append((sid,typ,d,'ex_date' if col!='Stock Splits' else 'effective_date',n,unit,'Yahoo Finance',f'{sid}-{d}-{col}',None,None,None,None,None,'USD',''))
            rows.extend(found); statuses.append(('Yahoo Finance',sid,'Retrieved',len(found)))
        except Exception as e: statuses.append(('Yahoo Finance',sid,'Failed: '+type(e).__name__,0))
    key=os.getenv('APCA_API_KEY_ID','').strip(); secret=os.getenv('APCA_API_SECRET_KEY','').strip()
    if key and secret:
        try:
            found=[]; pages=[]; cursor=None; seen=set(); lo=start
            while lo<=end:
                hi=min(lo+timedelta(days=89),end); cursor=None; seen=set()
                while True:
                    params={'symbols':','.join(symbols),'start':lo.isoformat(),'end':hi.isoformat(),'limit':1000}
                    if cursor: params['page_token']=cursor
                    resp=requests.get('https://data.alpaca.markets/v1/corporate-actions',params=params,headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret},timeout=30)
                    if not resp.ok: raise ValueError(f'HTTP {resp.status_code}')
                    p=resp.json(); pages.append(p); found.extend(alpaca_rows(p,symbols)); cursor=p.get('next_page_token')
                    if not cursor: break
                    if cursor in seen: raise ValueError('Repeated page token')
                    seen.add(cursor)
                lo=hi+timedelta(days=1)
            (raw/'alpaca_corporate_actions.json').write_text(json.dumps(pages),encoding='utf-8')
            rows.extend(found); statuses.append(('Alpaca','All selected instruments','Retrieved',len(found)))
        except Exception as e: statuses.append(('Alpaca','All selected instruments','Failed: '+(str(e) if str(e).startswith('HTTP ') else type(e).__name__),0))
    else: statuses.append(('Alpaca','All selected instruments','Not configured',0))
    return list(dict.fromkeys(rows)),statuses

def assurance(rows):
    """Conservative match for comparable cash/split observations only."""
    result=[]
    for r in rows:
        peers=[x for x in rows if x[0:3]==r[0:3] and x[6]!=r[6] and x[4] is not None and r[4] is not None and x[5]==r[5] and x[3]!='process_date' and r[3]!='process_date'] if r[1] in ('Cash dividend','Stock split','Capital gains distribution') else []
        matches=[x for x in peers if math.isclose(x[4],r[4],rel_tol=1e-5,abs_tol=1e-6)]
        status='Review amount discrepancy' if peers and len(matches)!=len(peers) else 'Matching provider observation' if matches else 'Single-source observation'
        result.append((*r,', '.join(sorted({x[6] for x in matches})),status))
    return result
