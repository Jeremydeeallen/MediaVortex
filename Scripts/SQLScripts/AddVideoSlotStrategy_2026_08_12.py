# directive: videoslotstrategy-persisted | # see post-transcode-disposition.C42
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


# directive: videoslotstrategy-persisted
def Main():
    Db = DatabaseService()
    Db.ExecuteNonQuery(
        "ALTER TABLE TranscodeAttempts "
        "ADD COLUMN IF NOT EXISTS VideoSlotStrategy TEXT"
    )
    Rows = Db.ExecuteQuery(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'transcodeattempts' AND column_name = 'videoslotstrategy'"
    )
    if Rows:
        print("Applied. TranscodeAttempts.VideoSlotStrategy column present.")
    else:
        raise RuntimeError("VideoSlotStrategy column not present after ALTER")


if __name__ == '__main__':
    Main()
