import sqlite3
from contextlib import closing
from datetime import date, timedelta
import pandas as pd
import plotly.express as px
import streamlit as st
from events import FIELDS,fetch_events,assurance

def render(sec,actions,DATA,OUT,label,chart,table,download,metric_row):
    st.caption('Five-year historical event register, plus provider-reported future dates. Market pricing history is unchanged.')
    db=OUT/'corporate_events.db'
    if st.button('Retrieve / refresh extended corporate actions',type='primary') or not db.exists():
        with st.spinner('Retrieving corporate actions from Yahoo Finance and configured Alpaca API…'):
            raw=DATA/'raw'; raw.mkdir(parents=True,exist_ok=True)
            rows,status=fetch_events(sec.security_id.tolist(),raw)
            if not any(x[2]=='Retrieved' for x in status) and db.exists():
                st.warning('No provider succeeded. Keeping the previous event snapshot.'); st.dataframe(pd.DataFrame(status,columns=['Provider','Scope','Status','Observations']),hide_index=True)
            else:
                with closing(sqlite3.connect(db,timeout=30)) as con:
                    pd.DataFrame(assurance(rows),columns=FIELDS+['verified_by','assurance']).to_sql('events',con,if_exists='replace',index=False)
                    pd.DataFrame(status,columns=['Provider','Scope','Status','Observations']).to_sql('coverage',con,if_exists='replace',index=False)
    with closing(sqlite3.connect(db)) as con:
        df=pd.read_sql_query('SELECT * FROM events',con); coverage=pd.read_sql_query('SELECT * FROM coverage',con)
    st.subheader('Source coverage'); table(coverage)
    st.caption('Alpaca access and history depend on account permissions. A successful request does not guarantee complete historical coverage. SEC filings can be reviewed separately in Institutional holdings.')
    if df.empty: st.info('No extended events retrieved. Check provider coverage above and refresh.'); return
    df['event_date']=pd.to_datetime(df.event_date,errors='coerce'); df['Instrument']=df.security_id.map(label)
    years=st.selectbox('Historical period',['3 months','1 year','3 years','5 years'],index=3)
    days={'3 months':92,'1 year':366,'3 years':1098,'5 years':1830}[years]
    sel=st.multiselect('Company / fund',sec.security_id.tolist(),format_func=label)
    types=st.multiselect('Event categories',sorted(df.event_type.unique()))
    scope=st.radio('Event dates',['Historical','Future reported dates','All'],horizontal=True)
    today=pd.Timestamp(date.today()); view=df[df.event_date>=today-pd.Timedelta(days=days)].copy()
    if scope=='Historical': view=view[view.event_date<=today]
    elif scope=='Future reported dates': view=view[view.event_date>today]
    if sel: view=view[view.security_id.isin(sel)]
    if types: view=view[view.event_type.isin(types)]
    unique=view.drop_duplicates(['security_id','event_type','event_date','amount','unit'])
    metric_row([('Distinct event observations',len(unique)),('Cash dividends',sum(unique.event_type=='Cash dividend')),('Stock splits',sum(unique.event_type=='Stock split')),('Other events',sum(~unique.event_type.isin(['Cash dividend','Stock split'])))])
    st.caption('Counts consolidate identical observations, not guaranteed unique economic events. Future dates do not establish confirmed or completed status.')
    if not view.empty:
        chart(px.scatter(unique,x='event_date',y='Instrument',color='event_type',hover_data=['amount','unit','source','date_basis'],labels={'event_date':'Reported event date','event_type':'Event category'},title='Corporate action timeline'))
        counts=unique.groupby('event_type').size().reset_index(name='Events'); chart(px.bar(counts,x='Events',y='event_type',orientation='h',labels={'event_type':'Event category'},title='Event category breakdown'))
    else: st.info('No events reported for this selection. This does not imply that all possible event categories were checked.')
    st.subheader('Event register | provider evidence')
    view['Business impact']=view.event_type.map({'Cash dividend':'Potential cash entitlement','Capital gains distribution':'Potential cash distribution','Stock split':'Potential share quantity change'}).fillna('Review event terms')
    columns=['Instrument','event_type','event_date','date_basis','announcement_date','record_date','payment_date','amount','unit','source','verified_by','assurance','provider_status','Business impact']
    table(view[columns].rename(columns={'event_type':'Event','event_date':'Event date','date_basis':'Date basis','announcement_date':'Announcement date','record_date':'Record date','payment_date':'Payment date','amount':'Reported amount / ratio','unit':'Unit','source':'Provider','verified_by':'Verified by','assurance':'Assurance','provider_status':'Provider status'})); download(view,'extended_corporate_actions')
    st.caption('Blank fields were not supplied. Matching observations require same instrument, comparable event type, date, unit and amount. No holdings are adjusted automatically; entitlement requires actual holdings on the relevant date.')
    with st.expander('Event terms and original provider evidence'):
        table(view[['Instrument','source','source_id','process_date','details']]); st.markdown('[Alpaca corporate actions reference](https://docs.alpaca.markets/us/v1.1/reference/corporateactions-1)')
