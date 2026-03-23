import sys
sys.path.insert(0, 'C:/Code/Automation/MediaVortex')
from Core.Database.DatabaseService import DatabaseService

DB = DatabaseService()
IDs = [1518901, 1518496, 1519249]
for LogId in IDs:
    Rows = DB.ExecuteQuery(f"SELECT Message, ExceptionMessage, StackTrace FROM Logs WHERE Id = {LogId}")
    for R in Rows:
        print(f"=== LOG ID {LogId} ===")
        print("MESSAGE:", R['message'])
        print("EXCEPTION:", R['exceptionmessage'])
        print("STACKTRACE:", R['stacktrace'])
        print()
