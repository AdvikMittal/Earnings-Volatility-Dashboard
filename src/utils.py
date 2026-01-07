from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from dotenv import dotenv_values
from datetime import datetime, timedelta
import requests
import sqlite3
import json

config = dotenv_values("C:\\dev\\keys\\new_alpaca_keys.txt")
alpaca_key, alpaca_sec = config['key'], config['sec']
mdata_token = config['mdata_token']
stock_client = StockHistoricalDataClient(alpaca_key, alpaca_sec)

def get_stock_price_at_945(ticker, date):
    """Get stock price at 9:45 AM EST using 15-min bar close"""
    start_time = f"{date.strftime('%Y-%m-%d')}T09:30:00-05:00"
    end_time = f"{date.strftime('%Y-%m-%d')}T10:00:00-05:00"
    
    req = StockBarsRequest(
        symbol_or_symbols=ticker,
        start=start_time,
        end=end_time,
        timeframe=TimeFrame(15, TimeFrameUnit('Min'))
    )
    
    bars = stock_client.get_stock_bars(req)
    data = bars.model_dump()['data']
    
    if ticker in data and len(data[ticker]) > 0:
        return data[ticker][0]['close']
    return None

def get_historical_options_chain(ticker, start_date, from_date, to_date):
    init_options_db()
    
    # Check cache first
    cached = get_cached_options_chain(ticker, start_date, from_date, to_date)
    if cached:
        return cached
    
    url = f"https://api.marketdata.app/v1/options/chain/{ticker}/?date={start_date}&from={from_date}&to={to_date}"
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {mdata_token}'
    }
    response = requests.get(url, headers=headers)
    
    if 'optionSymbol' in response.json():
        symbols = response.json()['optionSymbol']
        save_options_chain(ticker, start_date, from_date, to_date, symbols)
        return symbols
    return response.json()


def init_options_db():
    conn = sqlite3.connect('earnings.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS options_chain
                 (ticker TEXT, start_date DATE, from_date DATE, to_date DATE, 
                  symbols TEXT, fetched_at TIMESTAMP,
                  PRIMARY KEY (ticker, start_date, from_date, to_date))''')
    conn.commit()
    conn.close()

def get_cached_options_chain(ticker, start_date, from_date, to_date):
    conn = sqlite3.connect('earnings.db')
    c = conn.cursor()
    one_month_ago = (datetime.now() - timedelta(days=30)).isoformat()
    c.execute('''SELECT symbols FROM options_chain 
                 WHERE ticker = ? AND start_date = ? AND from_date = ? AND to_date = ? AND fetched_at > ?''',
              (ticker, start_date, from_date, to_date, one_month_ago))
    result = c.fetchone()
    conn.close()
    return json.loads(result[0]) if result else None

def save_options_chain(ticker, start_date, from_date, to_date, symbols):
    conn = sqlite3.connect('earnings.db')
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO options_chain VALUES (?, ?, ?, ?, ?, ?)''',
              (ticker, start_date, from_date, to_date, json.dumps(symbols), datetime.now().isoformat()))
    conn.commit()
    conn.close()

