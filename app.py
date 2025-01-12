# app.py
import streamlit as st
import pandas as pd
import yfinance as yf
import sqlite3
from datetime import datetime
import plotly.express as px

# Page config
st.set_page_config(
    page_title="Stock Portfolio Game",
    page_icon="📈",
    layout="wide"
)

# Database connection
def get_db_connection():
    conn = sqlite3.connect('portfolios.db')
    conn.row_factory = sqlite3.Row
    return conn

# Create tables if they don't exist
def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY,
            player TEXT NOT NULL,
            symbol TEXT NOT NULL,
            allocation REAL NOT NULL,
            entry_price REAL NOT NULL,
            entry_date DATE NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@st.cache_data(ttl=3600)
def fetch_all_stock_data(symbols):
    """Fetch historical data for all symbols."""
    max_retries = 3
    retry_count = 0
    start_date = '2024-01-01'

    while retry_count < max_retries:
        try:
            data = yf.download(
                tickers=symbols,
                start=start_date,
                interval='1d',
                group_by='ticker',
                auto_adjust=True
            )
            
            # Handle single vs multiple symbols
            if len(symbols) == 1:
                close_data = pd.DataFrame({'Close': data['Close']})
            else:
                close_data = data.xs('Close', axis=1, level=1)
            
            close_data = close_data.round(2)
            return close_data
        
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                print(f"Failed after {max_retries} attempts: {str(e)}")
                return pd.DataFrame()
            print(f"Retrying ({retry_count}/{max_retries})...")

def build_portfolio_dataframe(stock_data, positions):
    """Build a single DataFrame with current portfolio details."""
    if stock_data.empty:
        return pd.DataFrame()
    
    portfolio_data = []
    for pos in positions:
        symbol = pos['symbol']
        if symbol in stock_data.columns:
            entry_price = pos['entry_price']
            allocation = pos['allocation'] * 1000  # Convert allocation to dollar value
            shares_bought = allocation / entry_price  # Fractional shares
            current_price = stock_data[symbol].iloc[-1]
            current_value = shares_bought * current_price
            dollar_return = current_value - allocation
            
            portfolio_data.append({
                'Player': pos['player'],
                'Stock': symbol,
                'Entry Price': entry_price,
                'Allocation ($)': allocation,
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
        symbol = pos['symbol']
        entry_date = pd.to_datetime(pos['entry_date'])  # Ensure entry_date is pandas.Timestamp
        
        if symbol in stock_data.columns:
            # Handle missing entry_date by finding the nearest available date
            if entry_date not in stock_data.index:
                closest_index = stock_data.index.get_indexer([entry_date], method='nearest')[0]
                closest_date = stock_data.index[closest_index]
            else:
                closest_date = entry_date
            
            entry_price = stock_data.loc[closest_date, symbol]
            allocation = pos['allocation'] * 1000  # Initial allocation in dollars
            shares_bought = allocation / entry_price  # Fractional shares
            
            stock_prices = stock_data[symbol]
            for date, price in stock_prices.items():
                current_value = shares_bought * price
                dollar_return = current_value - allocation
                historical_data.append({
                    'Date': date,
                    'Player': pos['player'],
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
    all_symbols = list(set(pos['symbol'] for pos in positions))
    
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
                    st.write(f"**{i+1}. {row['Player']}**")
                with col2:
                    st.markdown(f"<h3 style='text-align: right'>${row['Dollar Amount Return']:.2f}</h3>", unsafe_allow_html=True)
                st.divider()

        with tab2:
            st.header("Portfolio Details")
            for player in portfolio_df['Player'].unique():
                st.subheader(player)
                player_portfolio = portfolio_df[portfolio_df['Player'] == player]
                st.dataframe(player_portfolio)

        with tab3:
            st.header("Performance Charts")
            
            st.subheader("Historical Dollar Returns Over Time")
            if not historical_df.empty:
                fig_line = px.line(
                    historical_df,
                    x='Date',
                    y='Dollar Value',
                    color='Player',
                    title='Historical Dollar Values Over Time',
                    labels={'Date': 'Date', 'Dollar Value': 'Total Portfolio Value ($)'}
                )
                fig_line.update_traces(mode='lines+markers')
                st.plotly_chart(fig_line, use_container_width=True)

            
            st.subheader("Total Dollar Returns by Player")
            fig_bar = px.bar(
                portfolio_df,
                x='Player',
                y='Dollar Amount Return',
                title='Total Dollar Returns by Player',
                labels={'Player': 'Player', 'Dollar Amount Return': 'Dollar Return'},
                color='Dollar Amount Return',
                color_continuous_scale=['red', 'green']
            )
            st.plotly_chart(fig_bar, use_container_width=True)
else:
    st.warning("No positions found in the database. Please add some positions first.")

# Schema for reference
if st.sidebar.checkbox("Show Database Schema"):
    st.sidebar.code("""
    CREATE TABLE positions (
        id INTEGER PRIMARY KEY,
        player TEXT NOT NULL,
        symbol TEXT NOT NULL,
        allocation REAL NOT NULL,
        entry_price REAL NOT NULL,
        entry_date DATE NOT NULL
    );
    """)
    
    st.sidebar.markdown("Example INSERT statement:")
    st.sidebar.code("""
    INSERT INTO positions 
    (player, symbol, allocation, entry_price, entry_date)
    VALUES 
    ('Player1', 'AAPL', 0.5, 180.5, '2024-01-10');
    """)
