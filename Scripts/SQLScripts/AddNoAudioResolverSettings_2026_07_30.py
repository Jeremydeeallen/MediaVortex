import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


SETTING_SQL = (
    "INSERT INTO SystemSettings (SettingKey, SettingValue, DataType, Description) "
    "VALUES (%s, %s, %s, %s) ON CONFLICT (SettingKey) DO NOTHING"
)


# directive: language-worker-progress-invariant
def Main():
    Db = DatabaseService()
    Db.ExecuteNonQuery(SETTING_SQL, (
        'SonarrUrl', '', 'string',
        'Base URL of Sonarr instance (e.g. http://10.0.0.137:8989/sonarr). NoAudioResolver reads to regrab TV files with no audio streams.',
    ))
    Db.ExecuteNonQuery(SETTING_SQL, (
        'SonarrApiKey', '', 'string',
        'Sonarr API key. NoAudioResolver authenticates with this to delete episodefiles + trigger EpisodeSearch.',
    ))
    Db.ExecuteNonQuery(SETTING_SQL, (
        'RadarrUrl', '', 'string',
        'Base URL of Radarr instance (e.g. http://10.0.0.137:7878/radarr). NoAudioResolver reads to regrab movie files with no audio streams.',
    ))
    Db.ExecuteNonQuery(SETTING_SQL, (
        'RadarrApiKey', '', 'string',
        'Radarr API key. NoAudioResolver authenticates with this to delete moviefiles + trigger MoviesSearch.',
    ))
    print("NoAudioResolver settings present: SonarrUrl, SonarrApiKey, RadarrUrl, RadarrApiKey.")
    return 0


if __name__ == '__main__':
    raise SystemExit(Main())
