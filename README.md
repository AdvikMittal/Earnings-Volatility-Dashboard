# Earnings Straddle Dashboard

A Streamlit dashboard for analyzing options straddle performance around earnings announcements.

## Overview

This tool tracks how options straddles (buying both a call and put at the same strike) perform before and after earnings releases. It fetches historical earnings dates, retrieves options pricing data, and visualizes the straddle value changes over time.

## How It Works

1. **Earnings Data**: Scrapes Yahoo Finance for past earnings dates and timing (before/after market)
2. **Options Data**: Uses Alpaca API to fetch 15-minute bar data for ATM call and put options
3. **Caching**: Stores earnings dates in SQLite to reduce API calls
4. **Visualization**: Plots call, put, and straddle prices with earnings date marked

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure Alpaca API keys in `C:\dev\keys\new_alpaca_keys.txt`:
```
key=YOUR_API_KEY
sec=YOUR_SECRET_KEY
```

3. Run the app:
```bash
streamlit run src/app.py
```

## Usage

1. Enter a stock ticker (e.g., NVDA)
2. Set lookback days (before earnings) and lookahead days (after earnings)
3. Click "Fetch Data" to analyze straddle performance
4. View interactive charts showing price movements and metrics
5. Enable Debug Mode in sidebar for detailed logging
