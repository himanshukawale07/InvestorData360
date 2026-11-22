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

st.set_page_config(
    page_title='InvestData 360 | Operations',
    page_icon='📊',
    layout='wide',
    initial_sidebar_state='expanded',
)

# Explicit contrast rules prevent the navigation text from inheriting a white
# foreground when Streamlit Cloud or an existing theme uses a light sidebar.
st.markdown('''
<style>
:root { color-scheme: light; }
[data-testid="stSidebar"],
[data-testid="stSidebar"] > div {
    background-color: #EAF1F7 !important;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"],
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] [data-testid="stRadio"] label,
[data-testid="stSidebar"] [data-testid="stRadio"] label p,
[data-testid="stSidebar"] [role="radiogroup"] label,
[data-testid="stSidebar"] [role="radiogroup"] label p {
    color: #172B4D !important;
    -webkit-text-fill-color: #172B4D !important;
}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
[data-testid="stSidebar"] small {
    color: #566B83 !important;
    -webkit-text-fill-color: #566B83 !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
    background-color: #DCEAF2 !important;
    border-radius: 7px;
}
[data-testid="stSidebar"] .stButton button {
    background-color: #087E8B !important;
    border: 1px solid #087E8B !important;
    color: #FFFFFF !important;
    border-radius: 9px;
    font-weight: 650;
}
[data-testid="stSidebar"] .stButton button p,
[data-testid="stSidebar"] .stButton button span {
    color: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;
}
[data-testid="stSidebar"] .stButton button:hover {
    background-color: #066975 !important;
}
[data-testid="stSidebar"] hr { border-color: #C8D6E2 !important; }
[data-testid="stSidebar"] [data-testid="stAlert"] p,
[data-testid="stSidebar"] [data-testid="stAlert"] span {
    color: #172B4D !important;
    -webkit-text-fill-color: #172B4D !important;
}
[data-testid="stMetric"] {
    border: 1px solid #D8E1EB;
    border-radius: 12px;
    padding: 16px;
    background: #FFFFFF;
}
.block-container { padding-top: 2rem; max-width: 1500px; }
h1, h2, h3 { letter-spacing: -0.025em; }
</style>
''', unsafe_allow_html=True)
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
