import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: compliance-symmetry
SNAPSHOT_PATH = r'C:\tmp\compliance_symmetry_e2e_snapshot.json'


# directive: compliance-symmetry
def _Current(DB, Mid):
    Rows = DB.ExecuteQuery(
        "SELECT Codec, AudioCodec, AudioBitrateKbps, VideoBitrateKbps, "
        "ResolutionCategory, ContainerFormat, SizeMB, AudioComplete, "
        "VideoCompliant, ContainerCompliant, AudioCompliant, "
        "VideoCompliantReason, ContainerCompliantReason, AudioCompliantReason, "
        "WorkBucket, IsCompliant FROM MediaFiles WHERE Id = %s", (Mid,))
    return Rows[0] if Rows else None


# directive: compliance-symmetry
def _LastAttempt(DB, Mid):
    Rows = DB.ExecuteQuery(
        "SELECT Disposition, DispositionReason, FileReplaced, ErrorMessage, "
        "WorkerName, AttemptDate FROM TranscodeAttempts WHERE MediaFileId = %s "
        "AND AttemptDate > NOW() - INTERVAL '120 minutes' ORDER BY Id DESC LIMIT 1",
        (Mid,))
    return Rows[0] if Rows else None


# directive: compliance-symmetry
def _Fmt(B, A, Key):
    BVal = B.get(Key)
    AVal = A.get(Key.lower())
    if BVal == AVal:
        return f"{BVal}"
    return f"{BVal} -> {AVal}"


# directive: compliance-symmetry
def _Outcome(B, A, Att):
    Disp = (Att.get('disposition') or '')
    Reason = (Att.get('dispositionreason') or '')
    Replaced = bool(Att.get('filereplaced'))
    BucketBefore = B.get('work_bucket')
    BucketAfter = A.get('workbucket')
    CompliantBefore = bool(B.get('is_compliant'))
    CompliantAfter = A.get('iscompliant') is True

    if CompliantAfter and not CompliantBefore:
        return 'COMPLIANT'
    if Disp == 'Replace' and not Replaced:
        return 'awaiting_replace'
    if Disp == 'Pending' and Reason == 'AwaitingVmaf':
        return 'awaiting_VMAF'
    if Disp == 'NoReplace':
        return f'NoReplace:{Reason}'
    if Disp == 'Reject':
        return f'Reject:{Reason}'
    if Disp == 'Replace' and Replaced and not CompliantAfter:
        return 'replaced_but_still_noncompliant'
    return Disp or 'pending'


# directive: compliance-symmetry
def Run():
    with open(SNAPSHOT_PATH) as F:
        Snap = json.load(F)
    DB = DatabaseService()

    for Mode in ('audiofix', 'remux', 'transcode'):
        print(f"\n===== {Mode.upper()} =====")
        Hdr = f"{'Id':<7} {'V':<14} {'C':<14} {'A':<14} {'Codec':<14} {'Container':<24} {'Bucket':<26} {'Outcome'}"
        print(Hdr)
        print('-' * len(Hdr))
        Compliant = 0
        AwaitingReplace = 0
        AwaitingVmaf = 0
        Failed = 0
        for B in Snap[Mode]:
            Mid = B['id']
            A = _Current(DB, Mid)
            if A is None:
                print(f"{Mid:<7} (deleted)")
                continue
            Att = _LastAttempt(DB, Mid) or {}
            Vstr = f"{B['video_compliant']} -> {A['videocompliant']}"
            Cstr = f"{B['container_compliant']} -> {A['containercompliant']}"
            Astr = f"{B['audio_compliant']} -> {A['audiocompliant']}"
            CodecStr = _Fmt(B, A, 'codec')
            ContStr = _Fmt(B, A, 'container_format')[:23]
            BucketStr = f"{B['work_bucket']} -> {A['workbucket']}"
            Outcome = _Outcome(B, A, Att)
            print(f"{Mid:<7} {Vstr:<14} {Cstr:<14} {Astr:<14} {CodecStr:<14} {ContStr:<24} {BucketStr:<26} {Outcome}")
            if A.get('iscompliant') is True:
                Compliant += 1
            elif Outcome == 'awaiting_replace':
                AwaitingReplace += 1
            elif Outcome == 'awaiting_VMAF':
                AwaitingVmaf += 1
            else:
                Failed += 1
        print(f"\nSummary: {Compliant} compliant | {AwaitingReplace} awaiting file-replace | {AwaitingVmaf} awaiting VMAF | {Failed} failed")


if __name__ == '__main__':
    Run()
