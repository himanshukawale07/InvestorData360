import json
import sqlite3
from contextlib import closing
import plotly.graph_objects as go
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
from pipeline import run, OUT, DATA
from assurance import comparison as build_comparison, PROVIDERS

st.set_page_config(page_title='InvestData 360 | Operations', page_icon='📊', layout='wide')
st.markdown('''<style>
[data-testid="stSidebar"] {background:#eaf0f6;}
[data-testid="stMetric"] {border:1px solid #8394a544;border-radius:12px;padding:16px;}
.block-container {padding-top:2rem;max-width:1500px;} h1,h2,h3 {letter-spacing:-.025em;}
</style>''', unsafe_allow_html=True)
st.sidebar.title('InvestData 360')
st.sidebar.caption('INVESTMENT DATA OPERATIONS')
page=st.sidebar.radio('Workspace',['Overview','Market intelligence','Security master','Price reconciliation','Data quality','Corporate actions','Portfolio','Reports & lineage','Risk & coverage','Institutional holdings','Quality history','Exception workbench','Integrations & scheduling'])
refresh=st.sidebar.button('Refresh market data',use_container_width=True)
ready=all((OUT/n).exists() for n in ['investment.db','summary.json','daily_report.html'])
if refresh or not ready:
    try:
        with st.spinner('Retrieving actual market data and running controls…'):
            run()
        st.sidebar.success('Refresh completed')
    except Exception as exc:
        st.error(f'Refresh failed: {exc}')
        if not ready:
            st.stop()
        st.warning('Showing the available published database; refresh did not complete. Exports or source files may need a subsequent successful refresh.')
try:
    s=json.loads((OUT/'summary.json').read_text())
    with closing(sqlite3.connect(OUT/'investment.db',timeout=30)) as con:
        con.execute('BEGIN')
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='run_summary'").fetchone():
            s=json.loads(con.execute('SELECT payload FROM run_summary').fetchone()[0])
        tables={name:pd.read_sql_query('SELECT * FROM '+name,con) for name in ['securities','prices_raw','prices_master','exceptions','corporate_actions','portfolio_valuation']}
        tables['validation_results']=pd.read_sql_query('SELECT * FROM validation_results',con) if con.execute("SELECT 1 FROM sqlite_master WHERE name='validation_results'").fetchone() else pd.DataFrame(columns=['rule','security_id','as_of','passed'])
except Exception as exc:
    st.error(f'Unable to load database: {exc}. Refresh market data to rebuild it.')
    st.stop()
sec= tables['securities']; raw=tables['prices_raw']; prices=tables['prices_master']; errors=tables['exceptions']; actions=tables['corporate_actions']; holdings=tables['portfolio_valuation']
manifest_path=DATA/'raw'/'manifest.json'
manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
source_names={'Vendor A':'Yahoo Finance','Vendor B':'Alpha Vantage','Vendor C':'Twelve Data','Vendor D':'Alpaca SIP'}
for frame in [raw,prices]:
    frame['source']=frame['vendor'].map(source_names).fillna(frame['vendor'])
    frame['price_date']=pd.to_datetime(frame['price_date'],errors='coerce')
    frame.sort_values(['security_id','price_date'],inplace=True)
names=dict(zip(sec.security_id,sec.name))
def label(t): return f'{names.get(t,t)} ({t})'
colors=['#2878b5','#0f9d90','#e6a23c','#7869bc','#df6b57','#64748b','#55a5d9']
def chart(fig):
    for trace in fig.data:
        if trace.name in names: trace.name=label(trace.name)
        for axis in ('x','y','text'):
            values=getattr(trace,axis,None)
            if values is not None and not isinstance(values,str):
                try: setattr(trace,axis,[label(v) if isinstance(v,str) and v in names else v for v in values])
                except (ValueError,TypeError): pass
    fig.update_layout(template='plotly_white',margin=dict(l=12,r=12,t=35,b=12),legend_title_text='',font=dict(size=13),height=370,hovermode='closest',paper_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig,use_container_width=True)
def table(df):
    df=df.copy()
    for col in ("security_id","Ticker","Security"):
        if col in df: df[col]=df[col].map(lambda x:label(x) if x in names else x)
    st.dataframe(df,use_container_width=True,hide_index=True)
def download(df,name):
    st.download_button('Export '+name,df.to_csv(index=False).encode(),name+'.csv','text/csv',key='export_'+name)
def metric_row(items):
    for col,(label,value) in zip(st.columns(len(items)),items):
        col.metric(label,value)
def count_chart(df,col,label):
    if df.empty:
        st.info('No records in this selection.')
    else:
        counts=df.groupby(col).size().reset_index(name='Count').sort_values('Count')
        chart(px.bar(counts,x='Count',y=col,orientation='h',color_discrete_sequence=[colors[0]],labels={col:label}))
st.sidebar.divider()
st.sidebar.caption('Daily historical data • USD')
st.sidebar.caption('Equity = company shares · ETF = exchange-traded fund')
st.sidebar.caption('As of '+str(s['as_of']))
st.sidebar.caption('Alpha Vantage '+('configured' if manifest.get('alpha_enabled') else 'not configured'))
st.title('Investment Operations Control Centre' if page=='Overview' else page)
st.caption('InvestData 360  /  Investment operations  /  Data as of '+str(s['as_of']))
if s['provider_failures']:
    st.warning(f"{s['provider_failures']} provider retrieval failures were recorded. Review Data quality before using the outputs.")
if s['dual_source_approved_prices']==0:
    st.sidebar.warning('One price source verified. Independent comparison not established.')
    if page in ['Overview','Price reconciliation','Data quality','Integrations & scheduling']:
        st.caption('Data assurance: prices are checked for validity, but not independently confirmed by a second provider. Connect additional providers under Integrations & scheduling.')
if page=='Overview':
    metric_row([('Securities',s['securities']),('Approved prices',f"{s['mastered_prices']:,}"),('Check pass rate',f"{s['quality_pct']:.2f}%"),('Failed checks',s['failed_checks'])])
    a,b=st.columns([2,1])
    with a:
        st.subheader('Market performance | indexed to 100')
        p=prices.dropna(subset=['price']).copy()
        if not p.empty:
            p['Index']=100*p['price']/p.groupby('security_id')['price'].transform('first')
            chart(px.line(p,x='price_date',y='Index',color='security_id',color_discrete_sequence=colors,labels={'price_date':'Trading date','security_id':'Security'}))
            st.caption('Price-only performance; not total return. Each series begins at 100.')
    with b:
        st.subheader('Data assurance')
        if errors.empty:
            st.success('No failed checks in the latest refresh.')
        else:
            count_chart(errors,'severity','Severity')
        st.metric('Independently confirmed prices',s['dual_source_approved_prices'])
        st.caption('A passing internal check is not the same as independent verification.')
    a,b=st.columns(2)
    with a:
        st.subheader('Source observations')
        count_chart(raw,'source','Provider')
    with b:
        st.subheader('Asset universe')
        if not sec.empty:
            counts=sec.groupby('asset_class').size().reset_index(name='Count')
            chart(px.pie(counts,names='asset_class',values='Count',hole=.6,color_discrete_sequence=colors))
    st.subheader('Market snapshot')
    snapshot=[]
    for symbol,p in prices.groupby('security_id'):
        p=p.sort_values('price_date'); last=p.iloc[-1]; ret=p.price.pct_change().dropna()
        snapshot.append({'Ticker':symbol,'Instrument':names.get(symbol,symbol),'Latest date':last.price_date.date(),'Close (USD)':last.price,'Last session (%)':100*ret.iloc[-1] if len(ret) else None,'Period change (%)':100*(last.price/p.price.iloc[0]-1),'Approved sessions':len(p),'Source':last.source})
    snap=pd.DataFrame(snapshot)
    if not snap.empty:
        st.dataframe(snap,use_container_width=True,hide_index=True,column_config={'Close (USD)':st.column_config.NumberColumn(format='$%.2f'),'Last session (%)':st.column_config.NumberColumn(format='%.2f%%'),'Period change (%)':st.column_config.NumberColumn(format='%.2f%%')})
        chart(px.bar(snap.sort_values('Period change (%)'),x='Period change (%)',y='Ticker',orientation='h',color='Period change (%)',color_continuous_scale='RdYlGn',color_continuous_midpoint=0))
    st.subheader('Latest price assurance')
    latest_date=pd.to_datetime(s['as_of'])
    result=build_comparison(raw,prices,sec.security_id,[latest_date])
    result['Company / Fund']=result.security_id.map(label)
    verified=result['Assurance status'].str.endswith('-source verified')
    metric_row([('Multi-source verified',int(verified.sum())),('Single-source approvals',int(result['Assurance status'].eq('Single-source approval').sum())),('Not approved / review',int((~verified & ~result['Assurance status'].eq('Single-source approval')).sum()))])
    st.caption(f'Trading date: {latest_date.date()} • USD. Primary provider supplies the approved price; Verified by lists other eligible providers that agree within tolerance.')
    main=['Company / Fund','Approved close (USD)','Primary pricing provider','Verified by','Valid sources','Assurance status']
    config={'Approved close (USD)':st.column_config.NumberColumn(format='$%.2f'),'Company / Fund':st.column_config.TextColumn(width='large'),'Spread (%)':st.column_config.NumberColumn(format='%.4f')}
    st.dataframe(result[main],use_container_width=True,hide_index=True,column_config=config)
    with st.expander('Provider price evidence and approval reasons',expanded=False):
        detail=['Company / Fund']+PROVIDERS+['Spread (%)','Contributing sources','Approval reason']
        st.dataframe(result[detail],use_container_width=True,hide_index=True,column_config={**config,**{p:st.column_config.NumberColumn(format='$%.2f') for p in PROVIDERS}})
        st.caption('Blank price = unavailable or ineligible observation. Spread = (highest − lowest) / lowest × 100. One source cannot independently verify a price.')
    download(result,'latest_price_assurance')

elif page=='Market intelligence':
    ticker=st.selectbox('Security',sec.security_id.tolist(),format_func=label)
    p=prices[prices.security_id==ticker].copy()
    if p.empty:
        st.warning('No approved prices for this security.')
    else:
        p['Daily return (%)']=p.price.pct_change()*100
        p['20-day average']=p.price.rolling(20).mean()
        metric_row([('Latest close',f'${p.price.iloc[-1]:,.2f}'),('Period high (close)',f'${p.price.max():,.2f}'),('Period low (close)',f'${p.price.min():,.2f}'),('Observations',len(p))])
        chart(px.line(p,x='price_date',y=['price','20-day average'],labels={'price_date':'Trading date','value':'USD','variable':'Series'},color_discrete_sequence=colors))
        chart(px.bar(p,x='price_date',y='Daily return (%)',color_discrete_sequence=[colors[1]]))
        table(p); download(p,'market_prices')
elif page=='Security master':
    q=st.text_input('Search by ticker, name, asset class or currency')
    filtered=sec[sec.astype(str).apply(lambda c:c.str.contains(q,case=False,regex=False)).any(axis=1)]
    metric_row([('Configured instruments',len(sec)),('Equities',int((sec.asset_class=='Equity').sum())),('ETFs',int((sec.asset_class=='ETF').sum()))])
    table(filtered); download(filtered,'security_master')
    st.caption('Instrument metadata is a configured reference universe; prices and actions are sourced externally.')
elif page=='Price reconciliation':
    metric_row([('Raw observations',len(raw)),('Approved observations',len(prices)),('Dual-source approvals',s['dual_source_approved_prices'])])
    ticker=st.selectbox('Security',sec.security_id.tolist(),format_func=label)
    r=raw[raw.security_id==ticker]
    if not r.empty:
        chart(px.line(r,x='price_date',y='price',color='source',markers=True,color_discrete_sequence=colors,labels={'price':'Close (USD)','price_date':'Trading date'}))
        comparison=build_comparison(r,prices[prices.security_id==ticker],[ticker],sorted(r.price_date.dropna().unique()))
        comparison['Trading date']=comparison.price_date.dt.date
        st.subheader('Historical reconciliation decisions')
        main=['Trading date','Approved close (USD)','Primary pricing provider','Verified by','Valid sources','Spread (%)','Assurance status']
        st.dataframe(comparison[main].sort_values('Trading date',ascending=False),use_container_width=True,hide_index=True,column_config={'Approved close (USD)':st.column_config.NumberColumn(format='$%.2f'),'Spread (%)':st.column_config.NumberColumn(format='%.4f')})
        with st.expander('Detailed provider observations and reasons'):
            table(comparison[['Trading date']+PROVIDERS+['Contributing sources','Approval reason']])
        download(comparison,'vendor_comparison')
    st.caption('Source priority: Yahoo Finance, Alpha Vantage, Twelve Data, Alpaca SIP. Only eligible observations contribute. Spread above 2% blocks approval; one eligible source is not independently verified.')
elif page=='Data quality':
    st.caption('Understand which controls ran, what passed and which issues need investigation.')
    metric_row([('Checks executed',f"{s['checks']:,}"),('Pass rate',f"{s['quality_pct']:.2f}%"),('Failed checks',s['failed_checks']),('Provider failures',s['provider_failures'])])
    if errors.empty:
        st.success('All executed checks passed. No exceptions require investigation in this snapshot.')
    else:
        st.warning(f"{len(errors)} failed control observations require review.")
    st.subheader('Control performance')
    audit=tables['validation_results']
    if not audit.empty:
        controls=audit.groupby('rule').passed.agg(['count','sum']).reset_index().rename(columns={'rule':'Control','count':'Executed','sum':'Passed'})
        controls['Failed']=controls.Executed-controls.Passed
        controls['Pass rate (%)']=100*controls.Passed/controls.Executed
        chart(px.bar(controls.sort_values('Executed'),x=['Passed','Failed'],y='Control',orientation='h',color_discrete_map={'Passed':'#168574','Failed':'#c94e42'},labels={'value':'Number of checks','variable':'Outcome'}))
        table(controls.round(2)); download(controls,'control_performance')
    else:
        st.info('Refresh once to record detailed pass counts for each control.')
    st.subheader('What the controls mean')
    table(pd.DataFrame([('Security identity','Checks that instruments exist in the security master'),('Price validity','Checks for positive, finite closing prices'),('Duplicate prices','Checks for repeated provider observations'),('Price coverage','Checks for approved prices across observed trading dates'),('Vendor agreement','Compares two valid provider prices when both are available'),('Corporate actions','Checks security identity and positive event factor')],columns=['Control','Business purpose']))
    if s['dual_source_approved_prices']==0:
        st.warning('Independent price verification is not established. The pass rate covers executed checks only.')
    if not errors.empty:
        st.subheader('Issues requiring review')
        rules=st.multiselect('Filter control',sorted(errors.rule.dropna().unique().tolist()))
        severities=st.multiselect('Filter severity',sorted(errors.severity.dropna().unique().tolist()))
        filtered=errors.copy()
        if rules: filtered=filtered[filtered.rule.isin(rules)]
        if severities: filtered=filtered[filtered.severity.isin(severities)]
        table(filtered); download(filtered,'exceptions')
    st.caption('Use Exception workbench to assign and investigate detected issues.')
elif page=='Corporate actions':
    from corporate_page import render
    render(sec,actions,DATA,OUT,label,chart,table,download,metric_row)
elif page=='Portfolio':
    st.caption('Enter actual holdings to value at the latest approved market date. No holdings are invented.')
    with st.form('holdings_form'):
        portfolio=st.text_input('Portfolio name','My portfolio')
        inputs=st.data_editor(pd.DataFrame({'Security':sec.security_id.tolist(),'Instrument':sec.name.tolist(),'Quantity':[0.0]*len(sec)}),disabled=['Security','Instrument'],column_config={'Quantity':st.column_config.NumberColumn(min_value=0.0,step=1.0)},hide_index=True,use_container_width=True)
        submit=st.form_submit_button('Calculate valuation')
    if submit:
        chosen=inputs[inputs.Quantity>0].rename(columns={'Security':'security_id','Quantity':'quantity'})
        latest=prices[prices.price_date==pd.Timestamp(s['as_of'])][['security_id','price']]
        result=chosen.merge(latest,on='security_id',how='left'); result['portfolio']=portfolio; result['market_value']=result.quantity*result.price
        st.session_state['interactive_holdings']=result
    view=st.session_state.get('interactive_holdings',holdings)
    if view.empty:
        st.info('No user holdings supplied. Enter quantities above to explore valuation.')
    else:
        metric_row([('Priced value',f"${view.market_value.sum():,.2f}"),('Priced positions',f"{view.price.notna().sum()}/{len(view)}")])
        priced=view.dropna(subset=['market_value'])
        if not priced.empty: chart(px.bar(priced,x='security_id',y='market_value',color_discrete_sequence=colors,labels={'market_value':'Market value (USD)'}))
        table(view); download(view,'portfolio_valuation')
    st.caption('Interactive valuations are session-only; the automated report uses holdings_input.csv. Unpriced positions are excluded; not official NAV.')
elif page=='Risk & coverage':
    st.caption('Historical price-based diagnostics, not investment advice or total-return estimates.')
    wide=prices.pivot(index='price_date',columns='security_id',values='price').sort_index()
    returns=wide.pct_change(fill_method=None)
    metric_row([('Observed sessions',len(wide)),('Expected security-days',len(wide)*len(sec)),('Approved security-days',len(prices)),('Observed coverage',f'{100*len(prices)/max(1,len(wide)*len(sec)):.2f}%')])
    st.subheader('Risk measures by instrument')
    risk=[]
    for ticker in wide:
        p=wide[ticker].dropna(); r=returns[ticker].dropna()
        if len(p):
            risk.append({'Ticker':ticker,'Annualised volatility (%)':r.std()*np.sqrt(252)*100 if len(r)>1 else None,'Maximum drawdown (%)':100*(p/p.cummax()-1).min(),'Daily observations':len(r),'Worst daily change (%)':100*r.min() if len(r) else None})
    risk=pd.DataFrame(risk); table(risk); download(risk,'risk_metrics')
    if not risk.empty:
        chart(px.scatter(risk,x='Annualised volatility (%)',y='Maximum drawdown (%)',text='Ticker',hover_name='Ticker',color_discrete_sequence=[colors[0]]))
    st.subheader('Daily price-return correlation')
    if len(returns)>2:
        corr=returns.corr(min_periods=5)
        chart(go.Figure(go.Heatmap(z=corr.values,x=corr.columns.tolist(),y=corr.index.tolist(),zmin=-1,zmax=1,colorscale='RdBu',reversescale=True,hoverongaps=False)))
    st.subheader('Approved pricing coverage by trading date')
    coverage=wide.reindex(columns=sec.security_id.tolist()).notna().astype(int)
    if not coverage.empty:
        chart(go.Figure(go.Heatmap(z=coverage.T.values,x=coverage.index.strftime('%Y-%m-%d').tolist(),y=coverage.columns.tolist(),zmin=0,zmax=1,colorscale=[[0,'#dc6b65'],[1,'#159a80']],showscale=False,hovertemplate='%{y} | %{x} | approved: %{z}<extra></extra>')))
    st.caption('Coverage uses observed dates, not an independent exchange calendar. Volatility assumes 252 sessions per year; missing returns are excluded.')
elif page=='Reports & lineage':
    st.subheader('Daily control report')
    st.download_button('Download HTML report',(OUT/'daily_report.html').read_bytes(),'daily_report.html','text/html')
    st.subheader('Data lineage')
    st.markdown('Financial data providers → raw files → validation → mastered SQL tables → dashboard & report')
    st.json(manifest)
    for name,df in [('raw_prices',raw),('approved_prices',prices),('exceptions',errors)]: download(df,name)

else:
    from enterprise_pages import render
    render(page,chart,table,metric_row,download,raw,prices,s)
