import sqlite3

conn = sqlite3.connect('app/database/mexc_data.db')
timestamps = [r[0] for r in conn.execute('SELECT timestamp FROM candles ORDER BY timestamp ASC').fetchall()]

intervals = []
for i in range(1, len(timestamps)):
    diff = timestamps[i] - timestamps[i-1]
    if diff > 60000:
        intervals.append((diff, timestamps[i-1], timestamps[i]))

print(f'Total gaps: {len(intervals)}')
for g in intervals[:20]:
    print(f'Gap of {g[0]/60000} mins starting at {g[1]}')
