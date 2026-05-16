"""Was the INSERT itself the failure? Pull any exception logs immediately
after the 'Insert attempt parameters' lines."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from Core.Database.DatabaseService import DatabaseService

Db = DatabaseService()

# Each 'Insert attempt parameters' line is followed within ~50ms by either
# a successful insert or an exception. Pull the next log entry after each.
Rows = Db.ExecuteQuery(
    "SELECT Id, Timestamp, LogLevel, FunctionName, ExceptionType, ExceptionMessage, Message "
    "FROM Logs WHERE Timestamp > NOW() - INTERVAL %s "
    "ORDER BY Timestamp ASC, Id ASC",
    ('15 minutes',)
)
for R in Rows:
    if not R['Message']:
        continue
    Msg = R['Message']
    # Print exceptions, failed jobs, attempt insert lines, and anything between
    if ('attempt' in Msg.lower() or 'exception' in Msg.lower() or
        'failed' in Msg.lower() or R.get('LogLevel') == 'ERROR' or
        R.get('ExceptionType')):
        print(f"[{R['Timestamp']}] [{R['LogLevel']}] {R['FunctionName']}")
        if R.get('ExceptionType'):
            print(f"  EXC: {R['ExceptionType']}: {R.get('ExceptionMessage','')[:300]}")
        print(f"  MSG: {Msg[:300]}")
        print()
