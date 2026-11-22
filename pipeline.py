import sqlite3, csv, json, html, math
from contextlib import closing
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict
BASE=Path(__file__).resolve().parent
DATA=BASE/'data'; OUT=BASE/'output'

def _run():
    DATA.mkdir(exist_ok=True); OUT.mkdir(exist_ok=True)
    from feeds import fetch
    today,securities,prices,positions,actions,issues=fetch(DATA)
    tables={'securities':(['security_id','asset_class','currency','name'],securities),'prices_raw':(['security_id','price_date','vendor','price'],prices),'positions':(['portfolio','security_id','as_of','quantity'],positions),'corporate_actions':(['action_id','security_id','action_type','effective_date','factor'],actions)}
    db=OUT/'investment.db'; con=sqlite3.connect(':memory:')
    try:
        schemas={'securities':'security_id TEXT PRIMARY KEY, asset_class TEXT, currency TEXT, name TEXT','prices_raw':'security_id TEXT, price_date TEXT, vendor TEXT, price REAL','positions':'portfolio TEXT, security_id TEXT, as_of TEXT, quantity INTEGER','corporate_actions':'action_id TEXT, security_id TEXT, action_type TEXT, effective_date TEXT, factor REAL'}
        for t,(cols,rows) in tables.items():
            with (DATA/f'{t}.csv').open('w',newline='') as f: w=csv.writer(f); w.writerow(cols); w.writerows(rows)
            con.execute(f'CREATE TABLE {t} ({schemas[t]})'); con.executemany(f'INSERT INTO {t} VALUES ({",".join("?" for _ in cols)})',rows)
        con.executescript('CREATE TABLE exceptions (id INTEGER PRIMARY KEY, rule TEXT, security_id TEXT, as_of TEXT, severity TEXT, detail TEXT, status TEXT); CREATE TABLE prices_master (security_id TEXT, price_date TEXT, price REAL, vendor TEXT, PRIMARY KEY(security_id,price_date));')
        con.execute("CREATE TABLE validation_results (rule TEXT, security_id TEXT, as_of TEXT, passed INTEGER)")
        ids={s[0] for s in securities}; grouped=defaultdict(lambda:defaultdict(list)); checks=0; failed=0; verified=0
        def check(ok,rule,sid,day,detail,severity='High'):
            nonlocal checks,failed
            checks+=1
            con.execute("INSERT INTO validation_results VALUES (?,?,?,?)",(rule,sid,day,int(bool(ok))))
            if not ok:
                failed+=1; con.execute('INSERT INTO exceptions(rule,security_id,as_of,severity,detail,status) VALUES(?,?,?,?,?,?)',(rule,sid,day,severity,detail,'Open'))
            return ok
        for sid,day,v,p in prices:
            valid_id=check(sid in ids,'Unknown identifier',sid,day,v)
            valid_p=check(p is not None and math.isfinite(p) and p>0,'Missing or invalid price',sid,day,f'{v}: {p}')
            if valid_id and valid_p: grouped[(sid,day)][v].append(p)
        for (sid,day),vendors in sorted(grouped.items()):
            candidates={}
            for v,vals in vendors.items():
                if check(len(vals)==1,'Duplicate vendor price',sid,day,f'{v}: {vals}'): candidates[v]=vals[0]
            if len(candidates)>=2:
                low=min(candidates.values()); high=max(candidates.values())
                if not check((high-low)/low<=.02,'Vendor price divergence',sid,day,str(candidates)): continue
                verified+=1
            if candidates:
                v=next(v for v in ('Vendor A','Vendor B','Vendor C','Vendor D') if v in candidates)
                con.execute('INSERT INTO prices_master VALUES (?,?,?,?)',(sid,day,candidates[v],v))
        # Observed trading dates only; no weekend false positives. Missing entire market days need a calendar extension.
        observed_dates=sorted({d for _,d,_,_ in prices})
        for sid in sorted(ids):
            for day in observed_dates:
                present=con.execute('SELECT 1 FROM prices_master WHERE security_id=? AND price_date=?',(sid,day)).fetchone()
                check(bool(present),'Missing approved price',sid,day,'No eligible mastered price')
        for sid,source,detail in issues:
            check(False,'Provider retrieval failure',sid,today.isoformat(),f'{source}: {detail}')
        for aid,sid,typ,day,factor in actions:
            check(sid in ids,'Unknown corporate action security',sid,day,aid); check(factor>0,'Invalid corporate action factor',sid,day,aid)
        for portfolio,sid,day,q in positions:
            check(sid in ids and q>=0,'Invalid long-only position',sid,day,portfolio)
        con.executescript('''CREATE VIEW portfolio_valuation AS SELECT p.portfolio,p.security_id,p.as_of,p.quantity,m.price,p.quantity*m.price AS market_value FROM positions p LEFT JOIN prices_master m ON p.security_id=m.security_id AND p.as_of=m.price_date;''')
        con.commit()
        summary={'as_of':today.isoformat(),'securities':len(ids),'raw_prices':len(prices),'mastered_prices':con.execute('SELECT count(*) FROM prices_master').fetchone()[0],'checks':checks,'failed_checks':failed,'provider_failures':len(issues),'dual_source_approved_prices':verified,'quality_pct':round(100*(checks-failed)/checks,2) if checks else 0,'priced_positions':con.execute('SELECT count(price) FROM portfolio_valuation').fetchone()[0],'total_positions':len(positions),'priced_market_value':round(con.execute('SELECT coalesce(sum(market_value),0) FROM portfolio_valuation').fetchone()[0],2)}
        con.execute('CREATE TABLE run_summary (payload TEXT NOT NULL)')
        con.execute('INSERT INTO run_summary VALUES (?)',(json.dumps(summary),))
        con.commit()
        with closing(sqlite3.connect(db,timeout=30)) as destination:
            destination.execute('PRAGMA busy_timeout=30000')
            con.backup(destination)
        (OUT/'summary.json').write_text(json.dumps(summary,indent=2))
        for table in ['securities','prices_master','positions','corporate_actions','exceptions','portfolio_valuation']:
            cur=con.execute(f'SELECT * FROM {table}')
            with (OUT/f'{table}.csv').open('w',newline='') as f: w=csv.writer(f); w.writerow([d[0] for d in cur.description]); w.writerows(cur)
        rows=con.execute('SELECT rule,count(*) FROM exceptions GROUP BY rule ORDER BY count(*) DESC').fetchall()
        report=f'<html><meta charset="utf-8"><title>InvestData 360</title><style>body{{font:16px Arial;max-width:900px;margin:50px auto;color:#18324c}}table{{border-collapse:collapse;width:100%}}td,th{{padding:12px;border-bottom:1px solid #ddd;text-align:left}}h1{{color:#125b83}}</style><h1>InvestData 360 | Daily control report</h1><p>Actual API-derived market prices • {today} • USD • user-supplied holdings • simplified valuation excludes bond quotation conventions and corporate action adjustments.</p><h2>Control summary</h2><table>'+''.join(f'<tr><th>{html.escape(k.replace("_"," ").title())}</th><td>{v:,}</td></tr>' if isinstance(v,(int,float)) else f'<tr><th>{k}</th><td>{v}</td></tr>' for k,v in summary.items())+'</table><h2>Exception breakdown</h2><table>'+''.join(f'<tr><td>{html.escape(k)}</td><td>{v}</td></tr>' for k,v in rows)+'</table><p>Unpriced holdings are excluded from the priced market value. All exceptions require review; corporate actions are validated but not applied.</p></html>'
        (OUT/'daily_report.html').write_text(report); print(json.dumps(summary,indent=2))
        from operations import record
        record(summary,con.execute('SELECT rule,security_id,as_of,severity,detail FROM exceptions').fetchall())
        return summary
    finally:
        con.close()
def run():
    import operations
    from contextlib import closing
    OUT.mkdir(exist_ok=True)
    # Separate lock DB serializes scheduled and UI refresh jobs across processes.
    with closing(sqlite3.connect(OUT/'refresh_lock.db',timeout=1)) as lock:
        lock.execute('BEGIN IMMEDIATE')
        try: return _run()
        except Exception as exc:
            operations.record(failure=type(exc).__name__)
            raise
        finally: lock.rollback()
if __name__=='__main__': run()
