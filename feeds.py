import os, csv, math, json, time
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
import requests

SYMBOLS={'AAPL':'Apple Inc.','MSFT':'Microsoft Corporation','NVDA':'NVIDIA Corporation','AMZN':'Amazon.com Inc.','IBM':'International Business Machines','SPY':'SPDR S&P 500 ETF','QQQ':'Invesco QQQ Trust'}

def fetch(data):
    import yfinance as yf
    today=date.today(); prices=[]; actions=[]; issues=[]; securities=[]
    raw=data/'raw'; raw.mkdir(exist_ok=True)
    key=os.getenv('ALPHA_VANTAGE_API_KEY','').strip()
    twelve=os.getenv('TWELVE_DATA_API_KEY','').strip()
    alpaca=os.getenv('APCA_API_KEY_ID','').strip(); secret=os.getenv('APCA_API_SECRET_KEY','').strip()
    for sid,name in SYMBOLS.items():
        securities.append((sid,'ETF' if sid in ('SPY','QQQ') else 'Equity','USD',name))
        try:
            h=yf.Ticker(sid).history(period='3mo',interval='1d',auto_adjust=False,actions=True,raise_errors=True)
            if h.empty: raise ValueError('Empty price history')
            h.to_csv(raw/f'{sid}_yahoo.csv')
            for dt,r in h.iterrows():
                d=dt.date().isoformat()
                if dt.date()>=today or dt.date()<today-timedelta(days=90): continue
                p=float(r['Close']); prices.append((sid,d,'Vendor A',p if math.isfinite(p) else None))
                for col,typ in [('Dividends','DIVIDEND'),('Stock Splits','SPLIT')]:
                    f=float(r.get(col,0))
                    if math.isfinite(f) and f!=0: actions.append((f'{sid}-{d}-{typ}',sid,typ,d,f))
        except Exception as e: issues.append((sid,'Yahoo Finance',type(e).__name__))
        if key:
            try:
                response=requests.get('https://www.alphavantage.co/query',params={'function':'TIME_SERIES_DAILY','symbol':sid,'apikey':key},timeout=30); response.raise_for_status(); payload=response.json()
                (raw/f'{sid}_alpha.json').write_text(json.dumps(payload),encoding='utf-8')
                series=payload.get('Time Series (Daily)')
                if not series: raise ValueError('Empty or restricted API response')
                for d,r in series.items():
                    if (today-timedelta(days=90)).isoformat()<=d<today.isoformat():
                        p=float(r['4. close']); prices.append((sid,d,'Vendor B',p if math.isfinite(p) else None))
            except Exception as e: issues.append((sid,'Alpha Vantage',type(e).__name__))
            time.sleep(1)
        if twelve:
            try:
                response=requests.get('https://api.twelvedata.com/time_series',params={'symbol':sid,'interval':'1day','outputsize':100,'adjust':'splits','apikey':twelve},timeout=30); response.raise_for_status(); payload=response.json()
                series=payload.get('values'); meta=payload.get('meta',{})
                if not series or meta.get('currency')!='USD': raise ValueError('Missing USD history')
                (raw/f'{sid}_twelve.json').write_text(json.dumps(payload),encoding='utf-8')
                rows=[(sid,r['datetime'][:10],'Vendor C',float(r['close'])) for r in series if (today-timedelta(days=90)).isoformat()<=r['datetime'][:10]<today.isoformat()]
                if not rows: raise ValueError('No eligible dates')
                prices.extend(rows)
            except Exception as e: issues.append((sid,'Twelve Data',type(e).__name__))
        if alpaca and secret:
            try:
                params={'symbols':sid,'timeframe':'1Day','start':(today-timedelta(days=90)).isoformat(),'end':today.isoformat(),'adjustment':'split','feed':'sip','limit':1000,'currency':'USD'}
                response=requests.get('https://data.alpaca.markets/v2/stocks/bars',params=params,headers={'APCA-API-KEY-ID':alpaca,'APCA-API-SECRET-KEY':secret},timeout=30); response.raise_for_status(); payload=response.json()
                series=payload.get('bars',{}).get(sid,[])
                if not series: raise ValueError('Missing SIP bars')
                (raw/f'{sid}_alpaca.json').write_text(json.dumps(payload),encoding='utf-8')
                rows=[(sid,r['t'][:10],'Vendor D',float(r['c'])) for r in series if (today-timedelta(days=90)).isoformat()<=r['t'][:10]<today.isoformat()]
                if not rows: raise ValueError('No eligible dates')
                prices.extend(rows)
            except Exception as e: issues.append((sid,'Alpaca SIP',type(e).__name__))
    if not prices: raise RuntimeError('No actual market prices retrieved. Check network/provider access; no mock fallback.')
    asof=max(d for _,d,_,_ in prices); positions=[]
    with (data/'holdings_input.csv').open(newline='',encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            q=float(r['quantity']); sid=r['security_id'].strip().upper()
            if not math.isfinite(q) or q<0 or sid not in SYMBOLS: raise ValueError('Holdings must contain supported tickers and finite nonnegative quantities')
            positions.append((r['portfolio'],sid,asof,q))
    (raw/'manifest.json').write_text(json.dumps({'retrieved_utc':datetime.now(timezone.utc).isoformat(),'sources':{'Vendor A':'Yahoo Finance via yfinance','Vendor B':'Alpha Vantage (optional)','Vendor C':'Twelve Data','Vendor D':'Alpaca SIP'},'alpha_enabled':bool(key),'twelve_enabled':bool(twelve),'alpaca_enabled':bool(alpaca and secret),'issues':issues,'valuation_date':asof},indent=2))
    return date.fromisoformat(asof),securities,prices,positions,actions,issues
