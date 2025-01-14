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

# Add refresh button in the sidebar
if st.sidebar.button('🔄 Refresh Data'):
    st.cache_data.clear()
    st.rerun()


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


@st.cache_data(ttl=3600)
def fetch_all_stock_data(symbols):
    """Fetch historical data for all symbols with retries for missing data."""
    max_retries = 3
    start_date = '2024-01-01'
    all_data = pd.DataFrame()

    for attempt in range(max_retries):
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

            all_data = pd.concat([all_data, close_data], axis=1)

            # Find missing symbols
            fetched_symbols = all_data.columns.tolist()
            missing_symbols = [symbol for symbol in symbols if symbol not in fetched_symbols]

            if not missing_symbols:
                return all_data.round(2)  # Return if no missing data

            symbols = missing_symbols  # Retry only for missing symbols

            print(f"Retrying for missing symbols: {missing_symbols}")

        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {str(e)}")
            continue
    print(all_data)
    return all_data.round(2)  # Return whatever data was fetched


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
        portfolio_df['Dollar Amount Return'] = portfolio_df['Dollar Amount Return'].round(2)

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
                    st.write(f"**{i + 1}. {row['Player']}**")
                with col2:
                    st.markdown(f"<h3 style='text-align: right'>${row['Dollar Amount Return']:.2f}</h3>",
                                unsafe_allow_html=True)
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
            colors = ['red' if x < 0 else 'green' for x in portfolio_df['Dollar Amount Return']]

            fig_bar = px.bar(
                portfolio_df,
                x='Player',
                y='Dollar Amount Return',
                title='Total Dollar Returns by Player',
                labels={'Player': 'Player', 'Dollar Amount Return': 'Dollar Return'},
                hover_data=['Ticker'],  # Add Ticker to tooltip
                custom_data=['Ticker']  # Include Ticker in custom data
            )
            fig_bar.update_traces(marker_color=colors)
            fig_bar.update_traces(
                hovertemplate="<br>".join([
                    "Player: %{x}",
                    "Dollar Return: $%{y:,.2f}",
                    "Ticker: %{customdata[0]}",
                    "<extra></extra>"
                ])
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
