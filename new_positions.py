import sqlite3
import pandas as pd

# Read the Excel file
excel_file = 'db_entries.xlsx'
df = pd.read_excel(excel_file)

# Ensure correct data types (optional)
df['Player'] = df['Player'].astype(str)
df['Ticker'] = df['Ticker'].astype(str)
df['selfSub'] = df['selfSub'].astype(float)
df['etfPercent'] = df['etfPercent'].astype(float)
df['entryPrice'] = df['entryPrice'].astype(float)
df['Shares'] = df['Shares'].astype(float)
df['entryValue'] = df['entryValue'].astype(float)

# Connect to the database
conn = sqlite3.connect('portfolios.db')
cursor = conn.cursor()

# Drop the table if it exists
cursor.execute("DROP TABLE IF EXISTS positions")

# Recreate the table with the correct schema
cursor.execute("""
CREATE TABLE positions (
    Player TEXT,
    Ticker TEXT,
    selfSub REAL,
    etfPercent REAL,
    entryPrice REAL,
    Shares REAL,
    entryValue REAL
)
""")

# Insert the data from the DataFrame into the database
for _, row in df.iterrows():
    cursor.execute("""
    INSERT INTO positions (Player, Ticker, selfSub, etfPercent, entryPrice, Shares, entryValue)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (row['Player'], row['Ticker'], row['selfSub'], row['etfPercent'], row['entryPrice'], row['Shares'], row['entryValue']))

# Commit and close
conn.commit()
conn.close()

print("Data from db_enteries.xlsx has been successfully loaded into the database.")
