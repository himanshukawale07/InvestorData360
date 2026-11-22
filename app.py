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
        latest=prices.sort_values('price_date').dropna(subset=['price']).drop_duplicates('security_id', keep='last')[['security_id','price']]
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
    st.caption('Interactive valuations use each instrument’s latest available approved price and are session-only. The automated report uses optional holdings_input.csv; this is not official NAV.')
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
