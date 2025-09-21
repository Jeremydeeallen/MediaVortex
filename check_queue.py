#!/usr/bin/env python3
import sqlite3

# Connect to database
conn = sqlite3.connect('Data/MediaVortex.db')
cursor = conn.cursor()

# Check current queue
cursor.execute('SELECT Id, FilePath, Status FROM TranscodeQueue WHERE Status = "Pending" ORDER BY Id DESC LIMIT 5')
results = cursor.fetchall()

print('Pending queue items:')
for r in results:
    print(f'  {r[0]}: {r[1]} - {r[2]}')

if not results:
    print('  No pending items in queue')

# Check if Manon.mkv is already in the database
cursor.execute('SELECT Id, FilePath, AssignedProfile FROM MediaFiles WHERE FilePath LIKE "%Manon%"')
manon_results = cursor.fetchall()

print('\nManon.mkv in MediaFiles:')
for r in manon_results:
    print(f'  {r[0]}: {r[1]} - Profile: {r[2]}')

conn.close()
