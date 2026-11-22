import os, sys, subprocess, json
from pathlib import Path
from contextlib import closing
import pandas as pd
import plotly.express as px
import streamlit as st
import operations as op

def render(page,chart,table,metric_row,download,raw,prices,s):
    if page=='Institutional holdings':
        st.subheader('Public institutional disclosures | SEC Form 13F')
        st.caption('Quarter-end disclosed positions, not current holdings or a complete portfolio. Values are as filed in USD for modern filings. Original filings only; amendments are flagged, not merged.')
        manager=st.selectbox('Reporting manager', ['Berkshire Hathaway (0001067983)','Custom SEC filer'])
        cik='1067983' if manager.startswith('Berkshire') else st.text_input('SEC Central Index Key (CIK)')
        contact=st.text_input('Contact email for SEC fair access',value=os.getenv('SEC_CONTACT_EMAIL',''))
        if st.button('Retrieve latest original 13F filing'):
            try:
                with st.spinner('Retrieving official SEC filing and holdings XML…'): op.fetch_13f(cik,contact)
            except Exception as exc: st.error(f'SEC retrieval failed: {exc}')
        cache=op.ROOT/'output'/f'13f_{int(cik)}.json' if cik.isdigit() else None
        if cache and cache.exists():
            result=json.loads(cache.read_text()); df=pd.DataFrame(result['rows']); total=df['Reported value (USD)'].sum()
            metric_row([('Reporting date',result['report_date']),('Filing date',result['filing_date']),('Reported lines',len(df)),('Reported line value',f'${total:,.0f}')]); st.write(result['manager']); st.markdown(f"[Official filing XML]({result['source']})")
            if result['amendments']: st.warning('Amendments exist for this reporting period. Original filing results may be superseded.')
            top=df.groupby('Issuer',as_index=False)['Reported value (USD)'].sum().nlargest(15,'Reported value (USD)').sort_values('Reported value (USD)'); chart(px.bar(top,x='Reported value (USD)',y='Issuer',orientation='h',title='Largest disclosed issuer exposures'))
            q=st.text_input('Search issuer or CUSIP'); table(df[df.Issuer.str.contains(q,case=False,regex=False)|df.CUSIP.str.contains(q,case=False,regex=False)]); download(df,'institutional_holdings')
        else: st.info('No SEC filing loaded. Enter contact email and retrieve the filing; no mock fallback.')
    elif page=='Quality history':
        with closing(op.connect()) as c: df=pd.read_sql_query('SELECT * FROM runs ORDER BY run_id',c)
        if df.empty: st.info('History begins on the next refresh.'); return
        ok=df[df.status=='Published']; metric_row([('Refresh attempts',len(df)),('Published',len(ok)),('Failed',len(df)-len(ok))]);
        if len(ok)==1: st.caption('One successful refresh recorded. A trend becomes meaningful after additional refreshes.')
        if not ok.empty:
            chart(px.line(ok,x='run_id',y='quality_pct',markers=True,title='Validation pass rate by refresh',hover_data=['timestamp','checks','as_of'])); chart(px.line(ok,x='run_id',y=['failed_checks','dual_source'],markers=True,title='Failed checks and dual-source approvals'))
        table(df); download(df,'refresh_history')
    elif page=='Exception workbench':
        with closing(op.connect()) as c:
            df=pd.read_sql_query('SELECT * FROM cases ORDER BY last_seen DESC',c); audit=pd.read_sql_query('SELECT * FROM audit ORDER BY timestamp DESC',c)
        metric_row([('Tracked cases',len(df)),('Currently detected',int(df.present.sum())),('Resolved',int((df.status=='Resolved').sum()))]);
        if df.empty:
            st.success('No exception cases recorded. There is currently nothing to assign or resolve.')
            st.caption('Cases are created automatically when a validation control fails. A successful refresh with no failures will not create cases.')
            st.subheader('How an issue is handled')
            st.table(pd.DataFrame([('1. Detect','A failed control creates a case'),('2. Assign','An analyst accepts ownership'),('3. Investigate','Record evidence and corrective action'),('4. Revalidate','Refresh the source data'),('5. Resolve','Close only after the issue is absent')],columns=['Stage','Action']))
            return
        statuses=st.multiselect('Workflow status',sorted(df.status.unique())); view=df[df.status.isin(statuses)] if statuses else df; table(view); download(view,'exception_cases')
        key=st.selectbox('Select case',df.case_id.tolist(),format_func=lambda k: f"{df.set_index('case_id').loc[k,'rule']} | {df.set_index('case_id').loc[k,'security_id']} | {k[:8]}")
        with st.form('case_update'):
            owner=st.text_input('Assigned analyst'); status=st.selectbox('Update status',['Open','In review','Resolved']); note=st.text_area('Investigation / resolution evidence'); submit=st.form_submit_button('Save case update')
        if submit:
            try: op.update_case(key,status,owner,note); st.rerun()
            except ValueError as exc: st.error(str(exc))
        st.caption('A case cannot be resolved while the latest refresh still detects it. Cases and audit records persist separately from market snapshots.'); st.subheader('Audit trail'); table(audit)
    else:
        st.subheader('1. Connect financial data providers')
        st.caption('Each configured provider is queried during refresh. Missing observations are never fabricated.')
        metric_row([(name,int((raw.vendor==code).sum())) for code,name in [('Vendor A','Yahoo Finance'),('Vendor B','Alpha Vantage'),('Vendor C','Twelve Data'),('Vendor D','Alpaca SIP')]])
        st.metric('Multi-source approved records',s.get('dual_source_approved_prices',0))
        st.markdown('[Alpha Vantage API key](https://www.alphavantage.co/support/#api-key) · [Twelve Data](https://twelvedata.com/) · [Alpaca](https://alpaca.markets/)')
        with st.form('provider_keys'):
            key=st.text_input('Alpha Vantage API key',type='password')
            twelve=st.text_input('Twelve Data API key',type='password')
            alpaca=st.text_input('Alpaca API key ID',type='password')
            secret=st.text_input('Alpaca API secret',type='password')
            submit=st.form_submit_button('Activate configured feeds for this session')
        if submit:
            if bool(alpaca.strip())!=bool(secret.strip()): st.error('Enter both Alpaca credentials.')
            else:
                for env,value in [('ALPHA_VANTAGE_API_KEY',key),('TWELVE_DATA_API_KEY',twelve),('APCA_API_KEY_ID',alpaca),('APCA_API_SECRET_KEY',secret)]:
                    if value.strip(): os.environ[env]=value.strip()
                st.success('Credentials configured in this process. Click Refresh market data to retrieve observations.')
        st.caption('Alpaca requests the consolidated SIP historical feed, not single-exchange IEX; access depends on your account. Keys are not saved by this form.')
        st.divider(); st.subheader('2. Optional cloud data warehouse'); st.caption('Optional connector; install requirements-cloud.txt first. Upload creates versioned tables in your selected database and schema; costs may apply. No connection without credentials.')
        with st.form('snowflake'):
            account=st.text_input('Account identifier'); user=st.text_input('Username'); password=st.text_input('Password',type='password'); warehouse=st.text_input('Warehouse'); database=st.text_input('Database'); schema=st.text_input('Schema'); submit=st.form_submit_button('Publish curated snapshot')
        if submit:
            try:
                with st.spinner('Publishing to Snowflake…'): names=op.publish_cloud(account,user,password,warehouse,database,schema)
                st.success('Published: '+', '.join(names))
            except Exception as exc: st.error('Cloud publication failed: '+type(exc).__name__+'. Check connector installation, credentials and privileges.')
        st.divider(); st.subheader('3. Schedule automatic daily refresh'); st.caption('Register a daily local-time Windows task using the current Python executable. Computer must be running; task runs under your account. Configure the API key as a user environment variable for scheduled runs.')
        when=st.time_input('Daily refresh time',value=__import__('datetime').time(8,0))
        if st.button('Register or update daily task'):
            try:
                if os.name!='nt': raise RuntimeError('Windows only')
                action=f'"{sys.executable}" "{op.ROOT / "pipeline.py"}"'
                r=subprocess.run(['schtasks','/Create','/TN','InvestData360Daily','/TR',action,'/SC','DAILY','/ST',when.strftime('%H:%M'),'/F'],capture_output=True,text=True,check=True); st.success(r.stdout)
            except Exception as exc: st.error(f'Task registration failed: {exc}')
        if st.button('Check scheduled task'):
            if os.name=='nt':
                r=subprocess.run(['schtasks','/Query','/TN','InvestData360Daily','/V','/FO','LIST'],capture_output=True,text=True); st.code(r.stdout or r.stderr)
            else: st.info('Windows only')
