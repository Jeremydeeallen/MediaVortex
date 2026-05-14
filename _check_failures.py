from Core.Database.DatabaseService import DatabaseService
DB = DatabaseService()

# Check for any failures with acompressor in the command
Rows = DB.ExecuteQuery("SELECT id, success, errormessage, ffpmpegcommand FROM TranscodeAttempts WHERE success = false AND ffpmpegcommand ILIKE '%%acompressor%%' ORDER BY id DESC LIMIT 5")
print(f"Failures with acompressor: {len(Rows)}")
for R in Rows:
    print(f"--- ID {R['id']} ---")
    print(f"Error: {R['errormessage']}")
    print(f"Command: {R['ffpmpegcommand']}")
    print()

# Check current setting
Rows2 = DB.ExecuteQuery("SELECT settingkey, settingvalue FROM SystemSettings WHERE settingkey IN ('AudioCompressionEnabled', 'AudioNormalizationEnabled') ORDER BY settingkey")
print("--- Current Settings ---")
for R in Rows2:
    print(f"{R['settingkey']}: {R['settingvalue']}")

# Check most recent attempts (success or fail) to see if compression is showing up
Rows3 = DB.ExecuteQuery("SELECT id, success, ffpmpegcommand FROM TranscodeAttempts WHERE ffpmpegcommand IS NOT NULL ORDER BY id DESC LIMIT 3")
print("\n--- Latest attempts with commands ---")
for R in Rows3:
    print(f"ID {R['id']} (success={R['success']}): {R['ffpmpegcommand']}")
    print()
