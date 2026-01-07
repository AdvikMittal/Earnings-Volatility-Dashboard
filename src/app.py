import streamlit as st
import plotly.graph_objects as go
import get_earnings_dates
import get_options
from datetime import datetime, timedelta
import logging
import traceback
import pandas as pd
import sqlite3
import os
import tempfile

st.set_page_config(page_title="Earnings Straddle Dashboard", layout="wide")

# Setup logging to file
log_file = os.path.join(tempfile.gettempdir(), 'earnings_dashboard.log')
if 'log_initialized' not in st.session_state:
    open(log_file, 'w').close()
    st.session_state.log_initialized = True

handler = logging.FileHandler(log_file, mode='a')
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger = logging.getLogger('app_logger')
logger.handlers.clear()
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)
logger.propagate = False

# Initialize database
def init_performance_db():
    conn = sqlite3.connect('earnings.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS pre_earnings_performance
                 (ticker TEXT, earnings_date DATE, lookback_days INTEGER, pre_earnings_change REAL, 
                  logged_at TIMESTAMP, PRIMARY KEY (ticker, earnings_date, lookback_days))''')
    c.execute('''CREATE TABLE IF NOT EXISTS post_earnings_performance
                 (ticker TEXT, earnings_date DATE, lookahead_days INTEGER, post_earnings_change REAL, 
                  logged_at TIMESTAMP, PRIMARY KEY (ticker, earnings_date, lookahead_days))''')
    conn.commit()
    conn.close()

def log_pre_earnings(ticker, earnings_date, lookback_days, pre_earnings_change):
    conn = sqlite3.connect('earnings.db')
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO pre_earnings_performance VALUES (?, ?, ?, ?, ?)''',
              (ticker, str(earnings_date), lookback_days, pre_earnings_change, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def log_post_earnings(ticker, earnings_date, lookahead_days, post_earnings_change):
    conn = sqlite3.connect('earnings.db')
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO post_earnings_performance VALUES (?, ?, ?, ?, ?)''',
              (ticker, str(earnings_date), lookahead_days, post_earnings_change, datetime.now().isoformat()))
    conn.commit()
    conn.close()

init_performance_db()


st.title("Earnings Straddle Performance Dashboard")
st.markdown("Analyze straddle performance around earnings dates")

# Sidebar inputs
with st.sidebar:
    st.header("Configuration")
    ticker = st.text_input("Stock Symbol", value="NVDA").upper()
    lookback = st.number_input("Days Before Earnings", min_value=1, max_value=10, value=5)
    lookahead = st.number_input("Days After Earnings", min_value=1, max_value=10, value=2)
    
    fetch_button = st.button("Fetch Data", type="primary")

# Tabs
tab1, tab2 = st.tabs(["Dashboard", "Logs"])

with tab1:
    if fetch_button:
        if not ticker:
            st.error("Please enter a stock symbol")
            logger.error("No ticker symbol provided")
        else:
            with st.spinner(f"Fetching earnings dates for {ticker}..."):
                try:
                    logger.info(f"Fetching earnings dates for {ticker}")
                    dates = get_earnings_dates.get_past_earnings_dates(ticker)
                    
                    if not dates:
                        st.error("No earnings dates found")
                        logger.error(f"No earnings dates found for {ticker}")
                        st.stop()
                    
                    # Filter dates to the past 1 year
                    cutoff_date = datetime.today().date() - timedelta(days=366)
                    filtered_dates = [(d, t) for d, t in dates if d > cutoff_date]
                    earning_dates_str = ',  '.join([str(d) for d, _ in filtered_dates])
                    
                    if not filtered_dates:
                        st.error("No earnings dates found in the past one year")
                        logger.error("No earnings dates after cutoff")
                        st.stop()
                    
                    st.success(f"Found {len(filtered_dates)} earnings dates in the past 1 year: {earning_dates_str}")
                    logger.info(f"Processing {len(filtered_dates)} earnings dates")
                
                except Exception as e:
                    st.error(f"Error fetching earnings dates: {str(e)}")
                    logger.error(f"Error fetching earnings dates: {str(e)}")
                    logger.debug(traceback.format_exc())
                    st.stop()
            
            # Process each earnings date
            for idx, (earnings_date, earnings_time) in enumerate(filtered_dates):
                with st.spinner(f"Fetching options data for {earnings_date}..."):
                    try:
                        logger.info(f"Processing earnings date {idx+1}/{len(filtered_dates)}: {earnings_date}")
                        df, symbols = get_options.get_options_data(ticker, earnings_date, lookback, lookahead)
                    
                        if df is None or df.empty:
                            st.warning(f"No options data found for {earnings_date}")
                            logger.warning(f"No options data for {earnings_date}")
                            continue
                        
                        logger.info(f"Successfully fetched {len(df)} data points")
                        
                        # Convert timestamps to EST and drop rows with missing data
                        df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_convert('US/Eastern')
                        df = df.dropna(subset=['call_close', 'put_close', 'straddle'])
                        logger.info(f"After filtering: {len(df)} valid data points")
                        
                        # Create numerical index and format timestamp labels
                        df = df.reset_index(drop=True)
                        df['timestamp_label'] = df['timestamp'].dt.strftime('%m/%d %H:%M')
                        
                        # Find earnings index based on timing (before = 9:30, after = 16:00)
                        earnings_hour = 9 if earnings_time == 'before' else 16
                        earnings_minute = 30 if earnings_time == 'before' else 0
                        
                        earnings_datetime = pd.Timestamp(datetime.combine(earnings_date, datetime.min.time()).replace(hour=earnings_hour, minute=earnings_minute)).tz_localize('US/Eastern')
                        earnings_idx = (df['timestamp'] - earnings_datetime).abs().idxmin()
                        
                        # Get strike and expiry from symbols
                        if symbols:
                            call_symbol = symbols[0]
                            strike = int(call_symbol[-8:]) / 1000
                            expiry_str = call_symbol[len(ticker):len(ticker)+6]
                            expiry_date = datetime.strptime(expiry_str, '%y%m%d').strftime('%Y-%m-%d')
                        else:
                            strike = 'N/A'
                            expiry_date = 'N/A'
                        
                        # Display earnings info
                        st.info(f"Earnings: {earnings_date} ({earnings_time} market) | Strike: ${strike} | Expiry: {expiry_date}")
                        
                        # Create interactive chart
                        fig = go.Figure()
                        
                        # Add call trace (faint green)
                        fig.add_trace(go.Scatter(
                            x=df.index,
                            y=df['call_close'],
                            mode='lines',
                            name='Call',
                            line=dict(color='rgba(0, 255, 0, 0.3)', width=1.5),
                            text=df['timestamp_label'],
                            hovertemplate='%{text}<br>Call: $%{y:.2f}<extra></extra>'
                        ))
                        
                        # Add put trace (faint red)
                        fig.add_trace(go.Scatter(
                            x=df.index,
                            y=df['put_close'],
                            mode='lines',
                            name='Put',
                            line=dict(color='rgba(255, 0, 0, 0.3)', width=1.5),
                            text=df['timestamp_label'],
                            hovertemplate='%{text}<br>Put: $%{y:.2f}<extra></extra>'
                        ))
                        
                        # Add straddle trace (solid blue)
                        fig.add_trace(go.Scatter(
                            x=df.index,
                            y=df['straddle'],
                            mode='lines',
                            name='Straddle',
                            line=dict(color='#1f77b4', width=2),
                            text=df['timestamp_label'],
                            hovertemplate='%{text}<br>Straddle: $%{y:.2f}<extra></extra>'
                        ))
                        
                        # Add earnings date vertical line
                        fig.add_shape(
                            type="line",
                            x0=earnings_idx, x1=earnings_idx,
                            y0=0, y1=1,
                            yref="paper",
                            line=dict(color="red", width=2, dash="dash")
                        )
                        fig.add_annotation(
                            x=earnings_idx,
                            y=1,
                            yref="paper",
                            text="Earnings",
                            showarrow=False,
                            yshift=10
                        )
                        
                        # Configure x-axis with timestamp labels
                        tick_indices = list(range(0, len(df), max(1, len(df)//10)))
                        tick_labels = [df.loc[i, 'timestamp_label'] for i in tick_indices]
                        
                        fig.update_layout(
                            title=f"{ticker} ${strike} - {earnings_date}",
                            xaxis_title="Date/Time (EST)",
                            yaxis_title="Price ($)",
                            hovermode='closest',
                            height=500,
                            template="plotly_white",
                            xaxis=dict(
                                tickmode='array',
                                tickvals=tick_indices,
                                ticktext=tick_labels
                            )
                        )
                        
                        st.plotly_chart(fig, use_container_width=True)
                        
                        # Display metrics
                        initial_straddle = df['straddle'].iloc[0]
                        pre_earnings_straddle = df['straddle'].iloc[earnings_idx - 1]
                        final_straddle = df['straddle'].iloc[-1]
                        
                        pre_earnings_change = ((pre_earnings_straddle - initial_straddle) / initial_straddle) * 100
                        post_earnings_change = ((final_straddle - pre_earnings_straddle) / pre_earnings_straddle) * 100
                        
                        col1, col2, col3, col4 = st.columns(4)
                        
                        with col1:
                            st.metric("Initial Straddle", f"${initial_straddle:.2f}")
                        with col2:
                            st.metric("Pre-Earnings", f"${pre_earnings_straddle:.2f}", delta=f"{pre_earnings_change:.2f}%")
                        with col3:
                            st.metric("Post-Earnings", f"${final_straddle:.2f}", delta=f"{post_earnings_change:.2f}%")
                        with col4:
                            total_change = ((final_straddle - initial_straddle) / initial_straddle) * 100
                            st.metric("Total Change", f"{total_change:.2f}%")
                        
                        # Log performance to database
                        log_pre_earnings(ticker, earnings_date, lookback, pre_earnings_change)
                        log_post_earnings(ticker, earnings_date, lookahead, post_earnings_change)
                        
                        st.divider()
                        
                    except Exception as e:
                        st.error(f"Error for {earnings_date}: {str(e)}")
                        logger.error(f"Error for {earnings_date}: {str(e)}")
                        logger.debug(traceback.format_exc())
                        continue
    else:
        st.info("Enter parameters in the sidebar and click 'Fetch Data' to begin")

with tab2:
    debug_mode = st.toggle("Show Debug Logs", value=False)
    
    st.markdown("""
    <style>
        .logs-display {
            background-color: #000000;
            color: #fafafa;
            padding: 15px;
            border-radius: 5px;
            font-family: monospace;
            font-size: 12px;
            white-space: pre-wrap;
            max-height: 600px;
            overflow-y: auto;
        }
    </style>
    """, unsafe_allow_html=True)
    
    if os.path.exists(log_file):
        with open(log_file, 'r') as f:
            log_content = f.read()
        if log_content:
            if not debug_mode:
                filtered_lines = [line for line in log_content.split('\n') if '- DEBUG -' not in line]
                log_content = '\n'.join(filtered_lines)
            st.markdown(f'<div class="logs-display">{log_content}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="logs-display">No logs yet. Click \'Fetch Data\' to see logs.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="logs-display">No logs yet. Click \'Fetch Data\' to see logs.</div>', unsafe_allow_html=True)
