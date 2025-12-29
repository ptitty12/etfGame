# app.py
import streamlit as st
import pandas as pd
import yfinance as yf
import sqlite3
from datetime import datetime
import plotly.express as px
import numpy as np

# Page config
st.set_page_config(
    page_title="Stock Portfolio Game",
    page_icon="📈",
    layout="wide"
)

# Add refresh button in the sidebar
if st.sidebar.button('🔄 Refresh Data'):
    st.cache_data.clear()
    st.rerun()
import os



import os
import time

DB_PATH = os.environ.get("ETF_DB_PATH", "/data/portfolios.db")
DB_PATH = "data/portfolios.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    #foo
    conn.row_factory = sqlite3.Row
    return conn




# Create tables if they don't exist
def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS positions (
            Player TEXT,
            Ticker TEXT,
            selfSub REAL,
            etfPercent REAL,
            entryPrice REAL,
            Shares REAL,
            entryValue REAL
        )
    ''')
    conn.commit()
    conn.close()


init_db()


import time

@st.cache_data(ttl=3600)
def fetch_all_stock_data(symbols):
    """
    1) Download daily OHLCV data for all symbols at once.
    2) If 'Open' is missing for a symbol on a given date, fill that day's
       OHLC with the prior day's 'Close' and set 'Volume' to 0.
    3) Return a DataFrame with just the 'Close' columns, index=Date, columns=Symbols.
    """
    max_retries = 3
    start_date = '2024-01-01'
    data = None

    for attempt in range(max_retries):
        try:
            tmp = yf.download(
                tickers=symbols,
                start=start_date,
                interval='1d',
                group_by='ticker',
                auto_adjust=True
            )
            
            # For each symbol and each date, if 'Open' is NaN, fill OHLC from previous day's Close
            for symbol in symbols:
                if symbol not in tmp.columns.levels[0]:
                    continue  # Symbol entirely missing in returned data
                for idx in tmp.index:
                    if pd.isna(tmp.loc[idx, (symbol, 'Open')]):
                        current_pos = tmp.index.get_loc(idx)
                        if current_pos > 0:  # There's a prior day to copy from
                            prior_idx = tmp.index[current_pos - 1]
                            prior_close = tmp.loc[prior_idx, (symbol, 'Close')]
                            tmp.loc[idx, (symbol, 'Open')] = prior_close
                            tmp.loc[idx, (symbol, 'High')] = prior_close
                            tmp.loc[idx, (symbol, 'Low')] = prior_close
                            tmp.loc[idx, (symbol, 'Close')] = prior_close
                            tmp.loc[idx, (symbol, 'Volume')] = 0

            data = tmp
            break  # Successfully downloaded and processed
        except Exception as e:
            print(f"Attempt {attempt + 1} failed for {symbols}: {e}")
            time.sleep(2)

    if data is not None and not data.empty:
        # Extract just the "Close" columns, which creates a 2D DataFrame
        # with date as index and each symbol as its own column.
        close_data = data.xs('Close', axis=1, level=1)
        close_data = close_data.round(2)
        return close_data
    else:
        # If we never got data or it's empty, return an empty DataFrame
        return pd.DataFrame()




def build_portfolio_dataframe(stock_data, positions):
    """Build a single DataFrame with current portfolio details."""
    if stock_data.empty:
        return pd.DataFrame()

    portfolio_data = []
    for pos in positions:
        symbol = pos['Ticker']
        if symbol in stock_data.columns:
            shares = pos['Shares']
            entry_price = pos['entryPrice']
            current_price = stock_data[symbol].iloc[-1]
            current_value = shares * current_price
            dollar_return = current_value - pos['entryValue']

            portfolio_data.append({
                'Player': pos['Player'],
                'Stock': symbol,
                'Entry Price': entry_price,
                'Shares': shares,
                'Current Price': current_price,
                'Current Value ($)': current_value,
                'Dollar Amount Return': dollar_return
            })

    return pd.DataFrame(portfolio_data)


def calculate_historical_dollar_returns(stock_data, positions):
    """Calculate aggregated historical dollar values for each player."""
    stock_data.index = pd.to_datetime(stock_data.index)  # Ensure index is pandas.Timestamp

    historical_data = []
    for pos in positions:
        symbol = pos['Ticker']
        shares = pos['Shares']

        if symbol in stock_data.columns:
            stock_prices = stock_data[symbol]
            for date, price in stock_prices.items():
                current_value = shares * price
                dollar_return = current_value - pos['entryValue']
                historical_data.append({
                    'Date': date,
                    'Player': pos['Player'],
                    'Dollar Value': current_value,
                    'Dollar Return': dollar_return
                })

    historical_df = pd.DataFrame(historical_data)
    aggregated_df = historical_df.groupby(['Date', 'Player'], as_index=False).sum()
    return aggregated_df


# Get positions from database
conn = get_db_connection()
positions = conn.execute('SELECT * FROM positions').fetchall()
conn.close()

if positions:
    all_symbols = list(set(pos['Ticker'] for pos in positions))

    with st.spinner('Fetching market data...'):
        stock_data = fetch_all_stock_data(all_symbols)

    if not stock_data.empty:
        portfolio_df = build_portfolio_dataframe(stock_data, positions)
        historical_df = calculate_historical_dollar_returns(stock_data, positions)

        tab1, tab2, tab3 = st.tabs(["📊 Leaderboard", "🔍 Portfolio Details", "📈 Performance Charts"])

        with tab1:
            st.header("Current Rankings")
            leaderboard = (
                portfolio_df.groupby('Player', as_index=False)
                .agg({'Dollar Amount Return': 'sum'})
                .sort_values('Dollar Amount Return', ascending=False)
            )
            for i, row in leaderboard.iterrows():
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"**{row['Player']}**")  # Removed the {i + 1}.
                with col2:
                    st.markdown(f"<h3 style='text-align: right'>${row['Dollar Amount Return']:.2f}</h3>",
                                unsafe_allow_html=True)
                st.divider()
            st.subheader("Historical Dollar Returns Over Time")
            if not historical_df.empty:
                fig_line = px.line(
                    historical_df,
                    x='Date',
                    y='Dollar Value',
                    color='Player',
                    labels={'Date': 'Date'}
                )
                fig_line.update_yaxes(showticklabels=False,visible=False)
                fig_line.update_traces(mode='lines')
                st.plotly_chart(fig_line, use_container_width=True)

        with tab2:
            st.header("Portfolio Details")
            for player in portfolio_df['Player'].unique():
                st.subheader(player)
                player_portfolio = portfolio_df[portfolio_df['Player'] == player]
                desired_columns = [
                                        'Stock',
                                        'Entry Price',
                                        'Current Price',
                                        'Shares',
                                        'Current Value ($)',
                                        'Dollar Amount Return'
                                    ]
                player_portfolio = player_portfolio[desired_columns]
                player_portfolio[' '] = np.where(player_portfolio['Dollar Amount Return'] > 0, '💸','📉' )
                #st.dataframe(player_portfolio.reset_index(drop=True))
                st.dataframe(player_portfolio.reset_index(drop=True), hide_index=True)



        with tab3:
            st.header("Portfolio Returns")



            st.subheader("Total Dollar Returns by Stock")
            fig_bar = px.bar(
                portfolio_df,
                x='Player',
                y='Dollar Amount Return',
                labels={'Player': 'Player', 'Dollar Amount Return': 'Dollar Return'},
                color='Dollar Amount Return',
                color_continuous_scale=[[0, 'red'], [0.5, 'red'], [0.5, 'green'], [1, 'green']],
                hover_data={
                    'Stock': True,
                    'Dollar Amount Return': ':.2f'
                }
            )

            # Update the color scale midpoint
            fig_bar.update_coloraxes(cmid=0)

            # Add thicker borders and text labels
            fig_bar.update_traces(
                textposition='inside',
                text=portfolio_df['Stock'],
                marker_line_width=2,
                marker_line_color='black'
            )

            st.plotly_chart(fig_bar, use_container_width=True)
else:
    st.warning("No positions found in the database. Please add some positions first.")

# Schema for reference
if st.sidebar.checkbox("Show Database Schema"):
    st.sidebar.code("""
    CREATE TABLE IF NOT EXISTS positions (
        Player TEXT,
        Ticker TEXT,
        selfSub REAL,
        etfPercent REAL,
        entryPrice REAL,
        Shares REAL,
        entryValue REAL
    );
    """)
