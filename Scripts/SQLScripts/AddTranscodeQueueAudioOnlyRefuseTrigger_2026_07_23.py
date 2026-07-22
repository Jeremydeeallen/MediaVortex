import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


# directive: transcode-flow-canonical -- C34
def Main() -> int:
    Db = DatabaseService()
    FunctionSql = (
        "CREATE OR REPLACE FUNCTION _RefuseAudioOnlyContainerOnTranscodeQueue() "
        "RETURNS TRIGGER AS $$ "
        "DECLARE "
        "    AudioOnly BOOLEAN; "
        "    SourceContainer TEXT; "
        "    SourceFileName TEXT; "
        "BEGIN "
        "    IF NEW.MediaFileId IS NULL THEN "
        "        RETURN NEW; "
        "    END IF; "
        "    SELECT LOWER(COALESCE(ContainerFormat, '')) IN "
        "           ('mp3','flac','ogg','wav','aac','opus','dsf','dff','ape','wma'), "
        "           ContainerFormat, FileName "
        "      INTO AudioOnly, SourceContainer, SourceFileName "
        "      FROM MediaFiles WHERE Id = NEW.MediaFileId; "
        "    IF AudioOnly THEN "
        "        RAISE EXCEPTION 'TranscodeQueue refuses MediaFileId %% (%%): audio-only ContainerFormat %%', "
        "            NEW.MediaFileId, SourceFileName, SourceContainer; "
        "    END IF; "
        "    RETURN NEW; "
        "END; "
        "$$ LANGUAGE plpgsql;"
    )
    TriggerSql = (
        "CREATE TRIGGER TranscodeQueueAudioOnlyRefuse "
        "    BEFORE INSERT ON TranscodeQueue "
        "    FOR EACH ROW "
        "    EXECUTE FUNCTION _RefuseAudioOnlyContainerOnTranscodeQueue();"
    )
    Db.ExecuteNonQuery(FunctionSql)
    Db.ExecuteNonQuery("DROP TRIGGER IF EXISTS TranscodeQueueAudioOnlyRefuse ON TranscodeQueue")
    Db.ExecuteNonQuery(TriggerSql)
    print("[C34] Trigger TranscodeQueueAudioOnlyRefuse installed")
    return 0


if __name__ == '__main__':
    sys.exit(Main())
