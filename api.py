from fastapi import FastAPI, HTTPException
import sqlite3
from contextlib import closing
from pipeline import OUT, run
app=FastAPI(title='InvestData 360')
def query(sql,params=()):
    if not (OUT/'investment.db').exists(): raise HTTPException(503,'Execute pipeline.py first')
    with closing(sqlite3.connect(OUT/'investment.db',timeout=30)) as con:
        con.row_factory=sqlite3.Row
        return [dict(r) for r in con.execute(sql,params)]
@app.get('/securities')
def securities(): return query('SELECT * FROM securities')
@app.get('/prices/{security_id}')
def prices(security_id:str): return query('SELECT * FROM prices_master WHERE security_id=? ORDER BY price_date',(security_id,))
@app.get('/exceptions')
def exceptions(): return query('SELECT * FROM exceptions')
