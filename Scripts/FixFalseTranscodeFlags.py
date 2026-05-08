"""One-time fix: unflag files falsely marked as TranscodedByMediaVortex.

Files whose codec is NOT av1 were never actually transcoded by MediaVortex
(all profiles use libsvtav1 → av1). This script sets TranscodedByMediaVortex
back to false and clears the corresponding TranscodeFiles.SuccessfullyTranscoded
so they become eligible for the transcode queue again.
"""

import os
import sys
import psycopg2

def Main():
    Host = os.environ.get('MEDIAVORTEX_DB_HOST', 'localhost')
    Conn = psycopg2.connect(host=Host, port=5432, database='mediavortex',
                            user='mediavortex', password='mediavortex')
    Cur = Conn.cursor()

    # 1. Fix MediaFiles
    Cur.execute("""
        UPDATE MediaFiles
        SET TranscodedByMediaVortex = false
        WHERE TranscodedByMediaVortex = true
          AND Codec NOT IN ('av1')
    """)
    MfCount = Cur.rowcount
    print(f"MediaFiles unflagged: {MfCount}")

    # 2. Fix TranscodeFiles for those same paths
    Cur.execute("""
        UPDATE TranscodeFiles
        SET SuccessfullyTranscoded = false
        WHERE SuccessfullyTranscoded = true
          AND FilePath IN (
              SELECT tf.FilePath
              FROM TranscodeFiles tf
              JOIN MediaFiles mf ON tf.MediaFileId = mf.Id
              WHERE mf.Codec NOT IN ('av1')
          )
    """)
    TfCount = Cur.rowcount
    print(f"TranscodeFiles unflagged: {TfCount}")

    Conn.commit()
    print("Committed.")
    Conn.close()

if __name__ == '__main__':
    Main()
