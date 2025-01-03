# app.py
import streamlit as st
import pandas as pd
import yfinance as yf
import sqlite3
from datetime import datetime, date, timedelta
import plotly.express as px
import plotly.graph_objects as go

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

@st.cache_data(ttl=3600)  # Cache for 1 hour
def fetch_all_stock_data(symbols, start_date):
    """Fetch historical data for all symbols at once"""
    try:
        if isinstance(start_date, (date, datetime)):
            start_date = start_date.strftime('%Y-%m-%d')
        
        data = yf.download(
            tickers=symbols,
            start=start_date,
            interval='1d',
            group_by='ticker',
            auto_adjust=True
        )
        
        # Handle single vs multiple symbols
        if len(symbols) == 1:
            return pd.DataFrame({'Close': data['Close']})
        return data.xs('Close', axis=1, level=1)
            
    except Exception as e:
        st.error(f"Error fetching data: {str(e)}")
        return pd.DataFrame()

def calculate_returns(stock_data, positions):
    """Calculate returns for all portfolios using pre-fetched data"""
    player_positions = {}
    for pos in positions:
        if pos['player'] not in player_positions:
            player_positions[pos['player']] = {}
        player_positions[pos['player']][pos['symbol']] = {
            'allocation': pos['allocation'],
            'entry_price': pos['entry_price']
        }
    
    # Calculate returns for each player
    all_returns = []
    for player, pos_details in player_positions.items():
        player_returns = pd.Series(0.0, index=stock_data.index)
        for symbol, details in pos_details.items():
            if symbol in stock_data.columns:
                stock_returns = ((stock_data[symbol] - details['entry_price']) / 
                               details['entry_price']) * details['allocation'] * 100
                player_returns += stock_returns
        
        returns_df = pd.DataFrame({
            'player': player,
            'return_pct': player_returns
        })
        all_returns.append(returns_df)
    
    if not all_returns:
        return pd.DataFrame()
    
    combined_df = pd.concat(all_returns).reset_index()
    combined_df.rename(columns={'index': 'Date'}, inplace=True)
    return combined_df

def calculate_current_positions(stock_data, positions):
    """Calculate current portfolio details using pre-fetched data"""
    if stock_data.empty:
        return pd.DataFrame()
    
    current_prices = stock_data.iloc[-1]
    
    returns_data = []
    for pos in positions:
        if pos['symbol'] in current_prices.index:
            current_price = current_prices[pos['symbol']]
            return_pct = ((current_price - pos['entry_price']) / pos['entry_price']) * pos['allocation']
            returns_data.append({
                'player': pos['player'],
                'symbol': pos['symbol'],
                'allocation': pos['allocation'],
                'entry_price': pos['entry_price'],
                'current_price': current_price,
                'return_pct': return_pct * 100
            })
    
    return pd.DataFrame(returns_data)

# Sidebar controls
with st.sidebar:
    st.header("Controls")
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
    
    days_to_show = st.slider("Days to show", 7, 90, 30)

# Get positions from database
conn = get_db_connection()
positions = conn.execute('SELECT * FROM positions').fetchall()
conn.close()

if positions:
    # Get unique symbols and determine start date
    all_symbols = list(set(pos['symbol'] for pos in positions))
    start_date = date.today() - timedelta(days=days_to_show)
    
    # Fetch all stock data once
    with st.spinner('Fetching market data...'):
        stock_data = fetch_all_stock_data(all_symbols, start_date)
    
    if not stock_data.empty:
        # Calculate all metrics using the same stock data
        historical_df = calculate_returns(stock_data, positions)
        current_returns_df = calculate_current_positions(stock_data, positions)
        
        # Main content
        tab1, tab2, tab3 = st.tabs(["📊 Leaderboard", "🔍 Portfolio Details", "📈 Performance Charts"])

        with tab1:
            st.header("Current Rankings")
            
            if not current_returns_df.empty:
                # Calculate total returns per player
                leaderboard = current_returns_df.groupby('player')['return_pct'].sum().reset_index()
                leaderboard = leaderboard.sort_values('return_pct', ascending=False)
                
                # Create ranking table with formatting
                for i, row in leaderboard.iterrows():
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"**{i+1}. {row['player']}**")
                    with col2:
                        color = "green" if row['return_pct'] >= 0 else "red"
                        st.markdown(f"<h3 style='color: {color};text-align: right'>{row['return_pct']:.2f}%</h3>", 
                                  unsafe_allow_html=True)
                    st.divider()
                
                # Historical performance chart
                st.subheader("Performance Trends")
                if not historical_df.empty:
                    fig = px.line(historical_df, 
                                 x='Date', 
                                 y='return_pct',
                                 color='player',
                                 title='Portfolio Performance Over Time',
                                 labels={'Date': 'Date', 'return_pct': 'Return %'})
                    
                    fig.update_traces(mode='lines+markers')
                    fig.update_layout(
                        hovermode='x unified',
                        yaxis_title="Return %",
                        xaxis_title="Date"
                    )
                    st.plotly_chart(fig, use_container_width=True)

        with tab2:
            st.header("Portfolio Details")
            if not current_returns_df.empty:
                for player in current_returns_df['player'].unique():
                    st.subheader(player)
                    player_portfolio = current_returns_df[current_returns_df['player'] == player]
                    
                    for _, pos in player_portfolio.iterrows():
                        col1, col2, col3 = st.columns([2, 2, 1])
                        with col1:
                            st.write(f"**{pos['symbol']}** ({pos['allocation']*100:.0f}%)")
                        with col2:
                            st.write(f"${pos['entry_price']:.2f} → ${pos['current_price']:.2f}")
                        with col3:
                            color = "green" if pos['return_pct'] >= 0 else "red"
                            st.markdown(f"<p style='color: {color};text-align: right'>{pos['return_pct']:.2f}%</p>", 
                                      unsafe_allow_html=True)
                    st.divider()

        with tab3:
            st.header("Performance Charts")
            if not current_returns_df.empty:
                col1, col2 = st.columns(2)
                
                with col1:
                    # Total Returns Bar Chart
                    fig_returns = px.bar(leaderboard, 
                                       x='player', 
                                       y='return_pct',
                                       title='Total Returns by Player',
                                       labels={'player': 'Player', 'return_pct': 'Return %'},
                                       color='return_pct',
                                       color_continuous_scale=['red', 'green'])
                    st.plotly_chart(fig_returns, use_container_width=True)
                
                # Portfolio Composition Charts
                st.subheader("Portfolio Compositions")
                for player in current_returns_df['player'].unique():
                    player_portfolio = current_returns_df[current_returns_df['player'] == player]
                    
                    fig_composition = px.pie(player_portfolio, 
                                           values='allocation',
                                           names='symbol',
                                           title=f"{player}'s Portfolio Allocation")
                    st.plotly_chart(fig_composition, use_container_width=True)

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
