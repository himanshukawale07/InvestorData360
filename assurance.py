import numpy as np
import pandas as pd

PROVIDERS=['Yahoo Finance','Alpha Vantage','Twelve Data','Alpaca SIP']

def comparison(raw, approved, universe, dates):
    keys=['security_id','price_date']
    index=pd.MultiIndex.from_product([list(universe),list(dates)],names=keys)
    valid=raw[raw.price.notna() & np.isfinite(raw.price) & (raw.price>0) & raw.source.isin(PROVIDERS)]
    valid=valid[~valid.duplicated(keys+['source'],keep=False)]
    wide=valid.pivot(index=keys,columns='source',values='price').reindex(index=index,columns=PROVIDERS)
    wide['Valid sources']=wide[PROVIDERS].count(axis=1)
    wide['Spread (%)']=100*(wide[PROVIDERS].max(axis=1)-wide[PROVIDERS].min(axis=1))/wide[PROVIDERS].min(axis=1)
    wide.loc[wide['Valid sources']<2,'Spread (%)']=np.nan
    master=approved.set_index(keys)
    wide['Approved close (USD)']=master.price
    wide['Primary pricing provider']=master.source.fillna('—')
    wide['Primary pricing provider']=wide['Primary pricing provider'].fillna('—')
    def describe(row):
        sources=[p for p in PROVIDERS if pd.notna(row[p])]
        primary=row['Primary pricing provider']
        if pd.isna(row['Approved close (USD)']):
            status='Discrepancy — review required' if len(sources)>=2 and row['Spread (%)']>2 else 'Price unavailable' if not sources else 'Not approved — review required'
            return pd.Series(['—',status,'No approved price published',', '.join(sources) or '—'])
        if primary not in sources or (len(sources)>=2 and row['Spread (%)']>2):
            return pd.Series(['—','Review source evidence','Published record does not match eligible observations',', '.join(sources) or '—'])
        others=[p for p in sources if p!=primary]
        return pd.Series([', '.join(others) or '—',f'{len(sources)}-source verified' if others else 'Single-source approval','Preferred eligible provider; agreement within 2% tolerance' if others else 'Only one eligible provider; no independent comparison',', '.join(sources)])
    wide[['Verified by','Assurance status','Approval reason','Contributing sources']]=wide.apply(describe,axis=1) if len(wide) else pd.DataFrame(index=wide.index,columns=range(4))
    return wide.reset_index()
