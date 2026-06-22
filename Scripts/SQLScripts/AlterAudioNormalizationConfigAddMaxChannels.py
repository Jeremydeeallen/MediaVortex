import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: compliance-symmetry
def Run():
    DB = DatabaseService()

    DB.ExecuteNonQuery("ALTER TABLE AudioNormalizationConfig ADD COLUMN IF NOT EXISTS MaxAudioChannels INT NOT NULL DEFAULT 2")

    Rows = DB.ExecuteQuery(
        "SELECT column_name, data_type, column_default FROM information_schema.columns "
        "WHERE table_name = 'audionormalizationconfig' AND column_name = 'maxaudiochannels'"
    )
    if Rows:
        R = Rows[0]
        print(f"AudioNormalizationConfig.MaxAudioChannels present: {R['data_type']} default={R['column_default']}")
    else:
        print("ERROR: AudioNormalizationConfig.MaxAudioChannels NOT present")


if __name__ == '__main__':
    Run()
