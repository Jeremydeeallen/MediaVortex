import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: compliance-symmetry
SNAPSHOT_PATH = r'C:\tmp\compliance_symmetry_e2e_snapshot.json'


# directive: compliance-symmetry
def _CurrentMediaFile(DB, Mid: int):
    Rows = DB.ExecuteQuery(
        "SELECT Id, Codec, AudioCodec, AudioBitrateKbps, VideoBitrateKbps, "
        "Resolution, ResolutionCategory, ContainerFormat, SizeMB, "
        "VideoCompliant, ContainerCompliant, AudioCompliant, "
        "VideoCompliantReason, ContainerCompliantReason, AudioCompliantReason, "
        "WorkBucket, IsCompliant, AudioComplete "
        "FROM MediaFiles WHERE Id = %s",
        (Mid,),
    )
    return Rows[0] if Rows else None


# directive: compliance-symmetry
def _QueueState(DB, QueueId: int, MediaFileId: int):
    QRows = DB.ExecuteQuery("SELECT Status FROM TranscodeQueue WHERE Id = %s", (QueueId,))
    QStatus = QRows[0]['status'] if QRows else 'gone'
    ARows = DB.ExecuteQuery(
        "SELECT Id, Disposition, DispositionReason, FileReplaced, Success, AttemptDate "
        "FROM TranscodeAttempts WHERE MediaFileId = %s ORDER BY Id DESC LIMIT 1",
        (MediaFileId,),
    )
    if not ARows:
        return {'status': QStatus, 'disposition': '', 'dispositionreason': '', 'filereplaced': None}
    A = ARows[0]
    return {'status': QStatus, 'disposition': A.get('disposition') or '',
            'dispositionreason': A.get('dispositionreason') or '',
            'filereplaced': A.get('filereplaced'), 'success': A.get('success'),
            'attempt_date': A.get('attemptdate')}


# directive: compliance-symmetry
def _Diff(Before, After):
    Cells = []
    for K in ('codec', 'audio_codec', 'audio_bitrate_kbps', 'video_bitrate_kbps',
              'container_format', 'size_mb', 'video_compliant', 'container_compliant',
              'audio_compliant', 'work_bucket', 'is_compliant', 'audio_complete'):
        Bv = Before.get(K)
        Av = After.get(K.replace('audio_bitrate_kbps', 'audiobitratekbps')
                       .replace('video_bitrate_kbps', 'videobitratekbps')
                       .replace('audio_codec', 'audiocodec')
                       .replace('container_format', 'containerformat')
                       .replace('size_mb', 'sizemb')
                       .replace('video_compliant', 'videocompliant')
                       .replace('container_compliant', 'containercompliant')
                       .replace('audio_compliant', 'audiocompliant')
                       .replace('work_bucket', 'workbucket')
                       .replace('is_compliant', 'iscompliant')
                       .replace('audio_complete', 'audiocomplete'))
        Cells.append((K, Bv, Av, '!=' if Bv != Av else '='))
    return Cells


# directive: compliance-symmetry
def Run():
    with open(SNAPSHOT_PATH, 'r', encoding='utf-8') as F:
        Snap = json.load(F)
    DB = DatabaseService()

    TotalDone = 0
    TotalPending = 0
    for Mode in ('audiofix', 'remux', 'transcode'):
        print(f"\n===== {Mode.upper()} =====")
        print(f"{'Id':<7} {'Status':<10} {'Disp':<14} {'V':<6} {'C':<6} {'A':<6} {'Bucket':<14} {'Compliant':<10}")
        for B in Snap[Mode]:
            Mid = B['id']
            Qs = _QueueState(DB, B['queue_id'], Mid)
            A = _CurrentMediaFile(DB, Mid)
            if Qs is None:
                Status = 'gone'
            else:
                Status = Qs.get('status') or Qs.get('Status') or '?'
                Disp = Qs.get('disposition') or Qs.get('Disposition') or ''
            if A is None:
                print(f"{Mid:<7} (mediafile missing)")
                continue
            VBefore = B['video_compliant']
            VAfter = A['videocompliant']
            CBefore = B['container_compliant']
            CAfter = A['containercompliant']
            ABefore = B['audio_compliant']
            AAfter = A['audiocompliant']
            VStr = f"{VBefore}->{VAfter}"
            CStr = f"{CBefore}->{CAfter}"
            AStr = f"{ABefore}->{AAfter}"
            BucketStr = f"{B['work_bucket']}->{A['workbucket']}"
            CompStr = f"{B['is_compliant']}->{A['iscompliant']}"
            DispStr = (Qs.get('disposition') or Qs.get('Disposition') or '') if Qs else ''
            DispStr = (DispStr or '')[:13]
            print(f"{Mid:<7} {Status:<10} {DispStr:<14} {VStr:<6} {CStr:<6} {AStr:<6} {BucketStr:<14} {CompStr:<10}")
            if Status in ('Completed', 'Failed') or A.get('workbucket') is None:
                TotalDone += 1
            else:
                TotalPending += 1

    print(f"\nTotal: {TotalDone} done / {TotalPending} still in flight (of 29 snapshot members).")


if __name__ == '__main__':
    Run()
