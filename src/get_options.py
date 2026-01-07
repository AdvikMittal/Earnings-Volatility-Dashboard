from alpaca.data.timeframe import TimeFrameUnit
from alpaca.data.timeframe import TimeFrame
from alpaca.data.historical.option import OptionBarsRequest
from alpaca.data.historical.option import OptionHistoricalDataClient
import pandas as pd
import numpy as np
from dotenv import dotenv_values
from datetime import timedelta
import logging
import utils
import pandas_market_calendars as mcal

config = dotenv_values("C:\\dev\\keys\\new_alpaca_keys.txt")
key, sec = config['key'], config['sec']
option_client = OptionHistoricalDataClient(key, sec)

def get_options_data(ticker, earnings_date, lookback, lookahead):
    
    timeframe = TimeFrame(15, TimeFrameUnit('Min'))
    
    # Use market calendar for trading days
    nyse = mcal.get_calendar('NYSE')
    schedule = nyse.schedule(start_date=earnings_date - timedelta(days=lookback*2), end_date=earnings_date + timedelta(days=lookahead*2))
    trading_days = schedule.index.date
    
    earnings_idx = list(trading_days).index(earnings_date) if earnings_date in trading_days else 0
    start_date = trading_days[max(0, earnings_idx - lookback)]
    end_date = trading_days[min(len(trading_days) - 1, earnings_idx + lookahead)]
    
    start_time = f"{start_date.strftime('%Y-%m-%d')}T09:30:00-05:00"
    end_time = f"{end_date.strftime('%Y-%m-%d')}T16:00:00-05:00"
    
    symbols = find_symbol(ticker, earnings_date, start_date)
    if not symbols:
        logging.error(f"No valid options contracts found for {ticker} around {earnings_date}")
        return None, None

    req = OptionBarsRequest(symbol_or_symbols=symbols, 
                            start=start_time, 
                            end=end_time, 
                            limit=600, timeframe=timeframe)

    bars = option_client.get_option_bars(req)
    data = bars.model_dump()['data']
    
    call_df = pd.DataFrame([{'timestamp': bar['timestamp'], 'call_close': bar['close']} for bar in data[symbols[0]]])
    put_df = pd.DataFrame([{'timestamp': bar['timestamp'], 'put_close': bar['close']} for bar in data[symbols[1]]])
    
    df = pd.merge(call_df, put_df, on='timestamp', how='outer').sort_values('timestamp')
    df['date'] = pd.to_datetime(df['timestamp']).dt.date
    
    for col in ['call_close', 'put_close']:
        df[col] = df.groupby('date')[col].ffill().bfill()
    
    df['straddle'] = (df['call_close'] + df['put_close']).round(2)
    df[['call_close', 'put_close']] = df[['call_close', 'put_close']].round(2)
    df = df.drop(columns=['date'])
    return df, symbols

def find_symbol(ticker, earnings_date, start_date):
    """Find the call and put symbols for the closest strike to stock price at 9:45 AM"""
    # Get stock price at 9:45 AM on start_date
    stock_price = utils.get_stock_price_at_945(ticker, start_date)
    if not stock_price:
        logging.error(f"Could not find stock price for {ticker} on {start_date}")
        return None
    
    # Get options chain with expiries between 1 day and 1 week after earnings
    from_date = (earnings_date + timedelta(days=8)).strftime('%Y-%m-%d')
    to_date = (earnings_date + timedelta(days=15)).strftime('%Y-%m-%d')
    start_date_str = start_date.strftime('%Y-%m-%d')
    
    option_symbols = utils.get_historical_options_chain(ticker, start_date_str, from_date, to_date)
    if not option_symbols:
        logging.error(f"Could not find options chain for {ticker} from {from_date} to {to_date}")
        return None
    
    # Extract unique strikes from call options
    strikes = set()
    for symbol in option_symbols:
        if 'C' in symbol:
            # Extract strike from symbol
            strike_str = symbol[-8:]
            strike = int(strike_str) / 1000
            strikes.add(strike)
    
    # Find closest strike to stock price
    closest_strike = min(strikes, key=lambda x: abs(x - stock_price))
    
    # Find the symbols with this strike
    strike_str = f"{int(closest_strike * 1000):08d}"
    call_symbol = [s for s in option_symbols if 'C' + strike_str in s][0]
    put_symbol = [s for s in option_symbols if 'P' + strike_str in s][0]
    
    return [call_symbol, put_symbol]