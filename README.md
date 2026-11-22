# InvestData 360 — actual market data edition

US listed equities and ETFs, USD, daily closing prices (not real-time quotes). AAPL, MSFT, NVDA, AMZN, IBM, SPY, QQQ. No synthetic prices or holdings are generated. The symbol universe, names and asset classes are a manually curated configuration, not an authoritative security master.

## Windows PowerShell
```
python -m pip install -r requirements.txt
# Optional: enable independent second provider using your own free key
$env:ALPHA_VANTAGE_API_KEY = 'YOUR_KEY'
python -m streamlit run app.py
```
In a second terminal: `python -m uvicorn api:app --reload` and open http://127.0.0.1:8000/docs.

Enter your own holdings in data/holdings_input.csv, with portfolio,security_id,quantity columns. The file is intentionally empty. Quantities are assumed to be valid on the latest observed price date, USD, long-only. No official NAV, cash, FX or entitlement calculations. Do not add confidential holdings for a public demonstration.

## Sources
- Yahoo Finance via unofficial open-source yfinance library: https://ranaroussi.github.io/yfinance/reference/yfinance.price_history.html (Vendor A; verify provider usage terms).
- Alpha Vantage daily raw close: https://www.alphavantage.co/documentation/ (Vendor B; optional API key, quotas and availability apply).
- Raw responses and retrieval manifest: data/raw/. Never commit keys or redistribute restricted data. Alpaca is not connected; SEC holdings are available in the Ultimate edition.

## Quality controls
Positive prices, known identifiers, duplicate vendor observations, 2% cross-provider divergence, observed-session coverage, position validation and corporate-action validation. No invented exceptions are injected. Single-source prices are permitted when valid; they are not independently verified. The summary counts dual-source approved prices separately. Feed retrieval failures are logged; if no prices are retrieved, the pipeline fails instead of generating mock data. Current calendar day is excluded to reduce incomplete bars. Exchange-calendar checks, source timestamp alignment and split-adjustment reconciliation remain recommended extensions. Historical raw price conventions may vary across vendors; investigate differences rather than assuming errors. Corporate actions are recorded but not applied to positions. All reports describe a prototype, not a production-ready valuation system.

## Verification
Source syntax checked; live retrieval and dashboard/API runtime not verified in this environment. Generate output on a network-enabled computer. No previous synthetic outputs are included.

First dashboard launch automatically executes the ingestion pipeline if outputs are absent. Use **Refresh market data** in the sidebar for subsequent updates. Daily prices are not streaming quotes. The optional independent provider requires an API key.

## Enterprise edition changes
- No database file deletion on refresh. The pipeline builds a validated in-memory SQLite snapshot and publishes using SQLite backup; all read connections explicitly close. A failed fetch leaves the published database untouched.
- Added market snapshot, return ranking, annualised historical volatility, maximum drawdown, correlation and approved-price coverage heatmap.
- Risk diagnostics use daily closing prices, not total return; no mock production data. The offline test uses isolated temporary fixtures only.
- Run `python -m unittest test_refresh -v` to verify repeat refresh with an idle connection and preservation of the database after a simulated fetch failure.
- Start with `python -m streamlit run app.py`. Stop previous versions first. Alpha Vantage remains optional.

## Ultimate edition
Four new pages: Institutional holdings, Quality history, Exception workbench, Integrations & scheduling. Full company names accompany tickers in charts and selectors. SEC EDGAR retrieves original Form 13F disclosure XML for a chosen manager; enter a real contact email (no SEC key). Amendments are flagged and are not consolidated; disclosed quarter-end values are not current valuations or total assets under management. See https://www.sec.gov/search-filings/edgar-application-programming-interfaces. Data is fetched on request and cached locally. The holdings remain separate from personal portfolio positions.

Alpha Vantage key: configure in Integrations & scheduling, then press Refresh market data. For persistence across restarts and scheduled tasks, set a Windows user environment variable with `[Environment]::SetEnvironmentVariable('ALPHA_VANTAGE_API_KEY','YOUR_KEY','User')` and reopen the terminal. Free quota is limited; seven requests per complete run. Yahoo historical closes may differ in split conventions; review divergence rather than assuming a provider is wrong.

Operations database persists refresh success/failure history, analyst case assignment, notes and audit records separately from market snapshots. A detected exception cannot be marked resolved while present; recurrence reopens it. Absence may also reflect the rolling window; analysts must verify resolution evidence. Local analyst names are self-reported, not authenticated. Run history begins with this edition. Keep output/operations.db to retain it.

Snowflake: `python -m pip install -r requirements-cloud.txt` then enter credentials and warehouse/database/schema on the integration page. Explicit publication creates versioned tables and verifies row counts; a partial failure may leave versioned tables. No automatic cloud publication or paid account provided. Authentication and permissions depend on your account.

Daily Windows scheduling: register a local-time daily task in the integration page; the machine must be available, and the registered account must have network and folder access. It runs pipeline.py (market data and control reporting), not SEC retrieval or Snowflake upload. Refresh history tracks the result. To remove: `schtasks /Delete /TN InvestData360Daily /F`. A separate SQLite lock serializes concurrent refresh jobs.

Tests: `python -m unittest test_refresh test_operations -v`. Offline fixtures are temporary only. Live provider connectivity, Windows Task Scheduler, Snowflake and Streamlit UI have not been exercised in the build environment. No synthetic production data included.

## Clarity edition
The quality page now records individual passed and failed controls in the snapshot database and displays counts by control. Refresh once to populate this new table. Empty exception states explain the successful outcome. Corporate actions show dividend dates, amounts per share and instrument names, with split ratios separate. Provider assurance notices are contextual rather than repeated across every page. All existing integrations remain available. No production mock financial data is included.

## Multi-source pricing edition
Configure Alpha Vantage, Twelve Data and/or Alpaca SIP credentials on Integrations & scheduling, then refresh. All are optional; no fake fallback. Alpaca uses consolidated historical SIP, subject to account entitlement. Latest prices table shows all four providers on the same date, valid source count, spread, approved price and selected provider. Price spread is (maximum − minimum)/minimum; above 2% quarantines the record. Multiple feeds agreeing does not guarantee independent upstream exchange sources. Historical split adjustment conventions may differ, particularly around corporate actions; investigate discrepancies before use. API keys are session-process only; scheduled ingestion requires environment variables ALPHA_VANTAGE_API_KEY, TWELVE_DATA_API_KEY, APCA_API_KEY_ID and APCA_API_SECRET_KEY as applicable. Respect provider data licensing and limits. Offline tests: python -m unittest test_refresh test_operations test_multisource -v. Actual external API access has not been tested in this build environment.

## Assurance Edition
Overview and historical Price reconciliation now show the approved pricing provider, other verifying providers, eligible source count, assurance status and expandable evidence. A sole Alpha Vantage (or other) feed is a single-source approval, not independent verification. The existing source priority and 2% tolerance are unchanged. Run `python -m unittest test_refresh test_operations test_multisource test_assurance -v` for offline regression tests. Live API and Windows Streamlit execution must be verified locally.

## Extended corporate actions edition
Open Corporate actions after activating Alpaca credentials in Integrations & scheduling. On first visit the page fetches five years of Yahoo Finance action history and, when configured, Alpaca corporate actions using the documented v1 endpoint with pagination and 90-day processing-date windows. Click Retrieve / refresh extended corporate actions after changing credentials. This separate on-demand snapshot does not change the three-month pricing pipeline or its scheduled refresh; the original short-history action table remains in the core daily report and API. Coverage and errors are displayed per provider; blanks mean not reported. Historical coverage depends on API permissions and availability. Future reported dates are not proof of announcement or completion. Matching cash/split observations are conservatively compared by instrument, date, unit and amount; other event types are shown as provider evidence, not automatically reconciled. SEC filings remain a separate module; automatic filing-to-event matching and entitlement calculation are not implemented. No synthetic production events are inserted. Tests: python -m unittest test_events test_refresh test_operations test_multisource test_assurance -v
