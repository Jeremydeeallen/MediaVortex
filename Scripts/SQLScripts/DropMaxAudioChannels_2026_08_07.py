import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: bug-0087-followup-maxaudiochannels-delete
def Run():
    DB = DatabaseService()

    DB.ExecuteNonQuery("ALTER TABLE AudioNormalizationConfig DROP COLUMN IF EXISTS MaxAudioChannels")

    Rows = DB.ExecuteQuery(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'audionormalizationconfig' AND column_name = 'maxaudiochannels'"
    )
    if not Rows:
        print("AudioNormalizationConfig.MaxAudioChannels dropped (idempotent OK)")
    else:
        print("ERROR: AudioNormalizationConfig.MaxAudioChannels still present after drop")


if __name__ == '__main__':
    Run()
