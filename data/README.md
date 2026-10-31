# Data

`data/raw/` holds one CSV per ticker with columns `date,adj_close`. It is gitignored on purpose: market data vendors restrict redistribution.

Get the data on your own computer:

```
make data
```

If the script fails (the data library changes now and then), download each ticker manually from Yahoo Finance: open the ticker's page, go to Historical Data, pick the full range, download the CSV, then keep only the Date and Adj Close columns, rename them to `date` and `adj_close`, and save as `data/raw/<TICKER>.csv`.

Default tickers: SPY, EFA, EEM, AGG, TLT, GLD, VNQ.
