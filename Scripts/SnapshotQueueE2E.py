import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: compliance-symmetry
OUTPUT_PATH = r'C:\tmp\compliance_symmetry_e2e_snapshot.json'


# directive: compliance-symmetry
def _PickPerMode(DB, Mode: str, Limit: int):
    Rows = DB.ExecuteQuery(
        "SELECT tq.Id AS QueueId, tq.MediaFileId, tq.DateAdded "
        "FROM TranscodeQueue tq "
        "WHERE tq.ProcessingMode = %s AND tq.Status IN ('Pending','Running') "
        "ORDER BY tq.DateAdded ASC, tq.Id ASC LIMIT %s",
        (Mode, Limit),
    )
    return [(int(R['queueid']), int(R['mediafileid'])) for R in Rows]


# directive: compliance-symmetry
def _SnapshotMediaFile(DB, MediaFileId: int):
    Rows = DB.ExecuteQuery(
        "SELECT Id, FileName, AssignedProfile, "
        "Codec, AudioCodec, AudioBitrateKbps, VideoBitrateKbps, "
        "Resolution, ResolutionCategory, ContainerFormat, SizeMB, "
        "VideoCompliant, ContainerCompliant, AudioCompliant, "
        "VideoCompliantReason, ContainerCompliantReason, AudioCompliantReason, "
        "WorkBucket, IsCompliant, AudioComplete, AudioChannels "
        "FROM MediaFiles WHERE Id = %s",
        (MediaFileId,),
    )
    if not Rows:
        return None
    R = Rows[0]
    return {
        'id': int(R['id']),
        'filename': R['filename'],
        'assigned_profile': R['assignedprofile'],
        'codec': R['codec'],
        'audio_codec': R['audiocodec'],
        'audio_bitrate_kbps': R['audiobitratekbps'],
        'video_bitrate_kbps': R['videobitratekbps'],
        'resolution': R['resolution'],
        'resolution_category': R['resolutioncategory'],
        'container_format': R['containerformat'],
        'size_mb': float(R['sizemb']) if R['sizemb'] else None,
        'video_compliant': R['videocompliant'],
        'container_compliant': R['containercompliant'],
        'audio_compliant': R['audiocompliant'],
        'video_reason': R['videocompliantreason'],
        'container_reason': R['containercompliantreason'],
        'audio_reason': R['audiocompliantreason'],
        'work_bucket': R['workbucket'],
        'is_compliant': R['iscompliant'],
        'audio_complete': R['audiocomplete'],
        'audio_channels': R['audiochannels'],
    }


# directive: compliance-symmetry
def Run():
    DB = DatabaseService()
    Snapshot = {'audiofix': [], 'remux': [], 'transcode': []}
    for Mode, Key in (('AudioFix', 'audiofix'), ('Remux', 'remux'), ('Transcode', 'transcode')):
        Picks = _PickPerMode(DB, Mode, 10)
        for QueueId, MediaFileId in Picks:
            State = _SnapshotMediaFile(DB, MediaFileId)
            if State is None:
                continue
            State['queue_id'] = QueueId
            State['processing_mode'] = Mode
            Snapshot[Key].append(State)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as F:
        json.dump(Snapshot, F, indent=2, default=str)
    print(f"Snapshot written: {OUTPUT_PATH}")
    for Mode in ('audiofix', 'remux', 'transcode'):
        print(f"  {Mode}: {len(Snapshot[Mode])} files")


if __name__ == '__main__':
    Run()
