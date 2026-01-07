import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
import sqlite3
import os

# Initialize Selenium WebDriver
options = webdriver.ChromeOptions()
options.add_argument('--verbose')
options.add_argument('--headless')
options.add_argument('--disable-gpu')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')

driver = webdriver.Chrome(options=options)

def get_earnings_for_symbol(symbol, limit):

    today_date = datetime.now().date().strftime("%Y-%m-%d")

    url = f"https://finance.yahoo.com/calendar/earnings?day={today_date}&symbol={symbol}&offset=0&size={limit}"
    print(url)

    driver.get(url)
    driver.implicitly_wait(5)  # Wait for page to load

    page_content = driver.page_source
    soup = BeautifulSoup(page_content, 'html.parser')

    table = soup.find('table', {'class': 'bd'})

    if table:
        headers = [header.text for header in table.find_all('th')]
        rows = []
        for row in table.find_all('tr')[1:]:  # Skip header row
            rows.append([cell.text for cell in row.find_all('td')])

        headers = [h.strip() for h in headers]
        df = pd.DataFrame(rows, columns=headers)

        return df

    else:
        print("Earnings table not found")
        return None

def get_past_earnings_dates(symbol, limit=20, years=5):
    init_db()
    
    # Check cache first
    cached = get_cached_earnings(symbol)
    if cached:
        return cached
    
    # Fetch from API
    df = get_earnings_for_symbol(symbol, limit)
    driver.close()
    
    # Extract date and determine if before/after market
    df['date'] = pd.to_datetime(df['Earnings Date'].str.split(' at ').str[0])
    df['timing'] = df['Earnings Date'].str.contains('PM', na=False).map({True: 'after', False: 'before'})
    
    # Filter past dates and get top results
    past_df = df[df['date'] < pd.Timestamp.now()].nlargest(years * 4, 'date')
    
    # Return list of tuples (date, timing)
    results = [(row['date'].date(), row['timing']) for _, row in past_df.iterrows()]
    
    # Save to cache
    if results:
        save_earnings(symbol, results)
    
    return results


def init_db():
    conn = sqlite3.connect('earnings.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS earnings
                 (ticker TEXT, earnings_date DATE, earnings_time TEXT, fetched_at TIMESTAMP, 
                  PRIMARY KEY (ticker, earnings_date))''')
    conn.commit()
    conn.close()

def get_cached_earnings(ticker):
    conn = sqlite3.connect('earnings.db')
    c = conn.cursor()
    three_months_ago = (datetime.now() - timedelta(days=90)).isoformat()
    c.execute('''SELECT earnings_date, earnings_time FROM earnings 
                 WHERE ticker = ? AND fetched_at > ?
                 ORDER BY earnings_date DESC''', 
              (ticker, three_months_ago))
    results = [(datetime.strptime(row[0], '%Y-%m-%d').date(), row[1]) for row in c.fetchall()]
    conn.close()
    return results if results else None

def save_earnings(ticker, dates_with_times):
    conn = sqlite3.connect('earnings.db')
    c = conn.cursor()
    now = datetime.now().isoformat()
    for date, time in dates_with_times:
        c.execute('''INSERT OR REPLACE INTO earnings VALUES (?, ?, ?, ?)''',
                  (ticker, str(date), time, now))
    conn.commit()
    conn.close()



