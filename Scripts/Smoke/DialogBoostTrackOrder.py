import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Features.AudioNormalization.AudioFilterEmitter import AudioFilterEmitter


class FakeMediaFile:
    Id = 999999
    AudioChannels = 2
    AudioStreamLanguageDetectionsJson = None
    SourceIntegratedLufs = -22.5
    SourceLoudnessRangeLU = 8.0
    SourceTruePeakDbtp = -1.0
    SourceIntegratedThresholdLufs = -32.0


class FakePolicy:
    LanguageDefault = 'eng'
    EnableSpeechLanguageDetection = False


def RunCase(Label, EmitBoost):
    Emitter = AudioFilterEmitter()
    Streams = [{'index': 0, 'tags': {'language': 'eng'}, 'disposition': {'default': 1}, 'codec_name': 'aac', 'channels': 2}]
    Blocks = Emitter.EmitTracks(
        MediaFile=FakeMediaFile(),
        Policy=FakePolicy(),
        AudioStreams=Streams,
        DemucsPremixPath='/tmp/fake_premix.wav' if EmitBoost else None,
        VocalsRmsDbfs=-25.0 if EmitBoost else None,
        PremixMeasuredI=-16.0, PremixMeasuredLra=7.0, PremixMeasuredTp=-1.5, PremixMeasuredThresh=-30.0,
    )
    print(f"\n=== {Label} ({len(Blocks)} tracks) ===")
    for I, B in enumerate(Blocks):
        Dispo = ' '.join(B.DispositionArgs)
        Meta = ' '.join(B.MetadataArgs)
        print(f"  Output Track {I}: Label={B.Label}  Language={B.Language}  Strategy={B.Strategy}")
        print(f"    MapArgs={B.MapArgs}")
        print(f"    Disposition={Dispo}")


if __name__ == '__main__':
    RunCase("1-track case (no Boost)", EmitBoost=False)
    RunCase("2-track case (Boost + Original)", EmitBoost=True)
