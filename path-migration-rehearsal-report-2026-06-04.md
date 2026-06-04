# Path Migration Rehearsal Report

**Generated:** 2026-06-04 18:53:17 UTC
**Runtime:** 1.56s
**StorageRoots loaded:** 3

## Per-(table, column) summary

| Source | Total | NULL | Parsed | NoPrefix | ValidationReject | Unexpected | CaseDrift | ContentDrift | FailureRate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MediaFiles.FilePath | 50089 | 0 | 50089 | 0 | 0 | 0 | 0 | 0 | 0.0000% |
| MediaFilesArchive.FilePath | 22860 | 0 | 22860 | 0 | 0 | 0 | 49 | 5 | 0.0000% |
| TranscodeQueue.FilePath | 862 | 0 | 862 | 0 | 0 | 0 | 0 | 0 | 0.0000% |
| TranscodeAttempts.FilePath | 26717 | 1656 | 25061 | 0 | 0 | 0 | 0 | 0 | 0.0000% |
| ShowSettings.ShowFolder | 6 | 0 | 6 | 0 | 0 | 0 | 0 | 0 | 0.0000% |
| TemporaryFilePaths.OriginalPath | 281 | 0 | 281 | 0 | 0 | 0 | 0 | 0 | 0.0000% |
| TemporaryFilePaths.LocalSourcePath | 281 | 0 | 281 | 0 | 0 | 0 | 0 | 0 | 0.0000% |
| TemporaryFilePaths.LocalOutputPath | 281 | 0 | 281 | 0 | 0 | 0 | 0 | 0 | 0.0000% |
| **TOTAL** | **101377** | -- | -- | -- | -- | -- | **49** | **5** | **0.0000%** |

## Verdict

- Overall parse-failure rate: **0.0000%** (target < 0.1%)
- Content drift: **5** (target 0 -- legacy and typed pair represent different files)
- Case-only drift: **49** (informational -- expected per D2/D10; scanner canonicalizes case at ingest, FromLegacyString preserves legacy case)
- Verdict: **INVESTIGATE**

## Failure samples

### MediaFilesArchive.FilePath

**cross_check_drift_content** (5 samples):

- id=54894: `'Z:\\Videos\\couple\\Strippers4K.25.10.10.Ronnie.Violet.Ronnies.Try.Out.XXX.2160p.MP4-WRB.mp4'`
  - reparsed: (3, 'Videos/couple/Strippers4K.25.10.10.Ronnie.Violet.Ronnies.Try.Out.XXX.2160p.MP4-WRB.mp4')
  - stored:   (3, 'Videos/couple/Strippers4K.25.10.10.Ronnie.Violet.Ronnies.Try.Out.XXX.720p.MP4-WRB.42.mp4')
- id=54969: `'Z:\\Videos\\couple\\PussyPatrol.25.10.28.Luxe.La.Fox.XXX.2160p.MP4-WRB.mp4'`
  - reparsed: (3, 'Videos/couple/PussyPatrol.25.10.28.Luxe.La.Fox.XXX.2160p.MP4-WRB.mp4')
  - stored:   (3, 'Videos/couple/PussyPatrol.25.10.28.Luxe.La.Fox.XXX.720p.MP4-WRB.42.mp4')
- id=58925: `'T:\\IT - Welcome to Derry\\Season 1\\IT - Welcome to Derry - S01E02 - The Thing in the Dark WEBDL-2160p.mkv'`
  - reparsed: (1, 'IT - Welcome to Derry/Season 1/IT - Welcome to Derry - S01E02 - The Thing in the Dark WEBDL-2160p.mkv')
  - stored:   (1, 'IT - Welcome to Derry/Season 1/IT - Welcome to Derry - S01E02 - The Thing in the Dark WEBDL-2160p.mp4')
- id=54969: `'Z:\\Videos\\couple\\PussyPatrol.25.10.28.Luxe.La.Fox.XXX.2160p.MP4-WRB.mp4'`
  - reparsed: (3, 'Videos/couple/PussyPatrol.25.10.28.Luxe.La.Fox.XXX.2160p.MP4-WRB.mp4')
  - stored:   (3, 'Videos/couple/PussyPatrol.25.10.28.Luxe.La.Fox.XXX.720p.MP4-WRB.42.mp4')
- id=54894: `'Z:\\Videos\\couple\\Strippers4K.25.10.10.Ronnie.Violet.Ronnies.Try.Out.XXX.2160p.MP4-WRB.mp4'`
  - reparsed: (3, 'Videos/couple/Strippers4K.25.10.10.Ronnie.Violet.Ronnies.Try.Out.XXX.2160p.MP4-WRB.mp4')
  - stored:   (3, 'Videos/couple/Strippers4K.25.10.10.Ronnie.Violet.Ronnies.Try.Out.XXX.720p.MP4-WRB.42.mp4')

**cross_check_drift_case_only** (10 samples):

- id=43490: `'Z:\\videos\\Couple\\SeeHimFuck.25.08.16.Eden.V.And.Jade.Green.XXX.1080p.MP4-FETiSH.mp4'`
  - reparsed: (3, 'videos/Couple/SeeHimFuck.25.08.16.Eden.V.And.Jade.Green.XXX.1080p.MP4-FETiSH.mp4')
  - stored:   (3, 'Videos/Couple/SeeHimFuck.25.08.16.Eden.V.And.Jade.Green.XXX.1080p.MP4-FETiSH.mp4')
- id=43615: `'Z:\\videos\\Couple\\HussiePass.25.08.22.Lola.Cheeks.Wild.BBC.Stretch.With.Damion.Dayski.XXX.1080p.MP4-WRB.mp4'`
  - reparsed: (3, 'videos/Couple/HussiePass.25.08.22.Lola.Cheeks.Wild.BBC.Stretch.With.Damion.Dayski.XXX.1080p.MP4-WRB.mp4')
  - stored:   (3, 'Videos/Couple/HussiePass.25.08.22.Lola.Cheeks.Wild.BBC.Stretch.With.Damion.Dayski.XXX.1080p.MP4-WRB.mp4')
- id=43837: `'Z:\\videos\\Couple\\SexMex.25.08.30.Andrea.Castro.XXX.2160p.MP4-WRB.mp4'`
  - reparsed: (3, 'videos/Couple/SexMex.25.08.30.Andrea.Castro.XXX.2160p.MP4-WRB.mp4')
  - stored:   (3, 'Videos/Couple/SexMex.25.08.30.Andrea.Castro.XXX.2160p.MP4-WRB.mp4')
- id=51099: `'Z:\\videos\\Couple\\MommysBoy.25.10.01.Diana.Grace.Bring.In.Your.Little.Toy.Too.XXX.2160p.MP4-VSEX.mp4'`
  - reparsed: (3, 'videos/Couple/MommysBoy.25.10.01.Diana.Grace.Bring.In.Your.Little.Toy.Too.XXX.2160p.MP4-VSEX.mp4')
  - stored:   (3, 'Videos/Couple/MommysBoy.25.10.01.Diana.Grace.Bring.In.Your.Little.Toy.Too.XXX.2160p.MP4-VSEX.mp4')
- id=43732: `'Z:\\videos\\Couple\\DigitalPlayground.25.09.15.Yhivi.Deadly.Vows.Episode.2.XXX.1080p.MP4-WRB.mp4'`
  - reparsed: (3, 'videos/Couple/DigitalPlayground.25.09.15.Yhivi.Deadly.Vows.Episode.2.XXX.1080p.MP4-WRB.mp4')
  - stored:   (3, 'Videos/Couple/DigitalPlayground.25.09.15.Yhivi.Deadly.Vows.Episode.2.XXX.1080p.MP4-WRB.mp4')
- id=51116: `'Z:\\videos\\Couple\\cuteHardcoreHoliday.25.10.01.Leya.Desantis.XXX.2160p.MP4-VSEX.mp4'`
  - reparsed: (3, 'videos/Couple/cuteHardcoreHoliday.25.10.01.Leya.Desantis.XXX.2160p.MP4-VSEX.mp4')
  - stored:   (3, 'Videos/Couple/cuteHardcoreHoliday.25.10.01.Leya.Desantis.XXX.2160p.MP4-VSEX.mp4')
- id=43414: `'Z:\\videos\\Couple\\FreakMobMedia.25.08.22.Vivian.Taylor.Got.A.Huge.Butt.XXX.1080p.MP4-WRB.mp4'`
  - reparsed: (3, 'videos/Couple/FreakMobMedia.25.08.22.Vivian.Taylor.Got.A.Huge.Butt.XXX.1080p.MP4-WRB.mp4')
  - stored:   (3, 'Videos/Couple/FreakMobMedia.25.08.22.Vivian.Taylor.Got.A.Huge.Butt.XXX.1080p.MP4-WRB.mp4')
- id=51104: `'Z:\\videos\\Couple\\NickMarxx.E94.Violet.Starr.XXX.2160p.MP4-NBQ.mp4'`
  - reparsed: (3, 'videos/Couple/NickMarxx.E94.Violet.Starr.XXX.2160p.MP4-NBQ.mp4')
  - stored:   (3, 'Videos/Couple/NickMarxx.E94.Violet.Starr.XXX.2160p.MP4-NBQ.mp4')
- id=53729: `'Z:\\videos\\Anal\\PornMegaLoad.25.10.17.Lizzie.Bakery.Hardcore.41704.XXX.2160p.MP4-WRB.mp4'`
  - reparsed: (3, 'videos/Anal/PornMegaLoad.25.10.17.Lizzie.Bakery.Hardcore.41704.XXX.2160p.MP4-WRB.mp4')
  - stored:   (3, 'Videos/Anal/PornMegaLoad.25.10.17.Lizzie.Bakery.Hardcore.41704.XXX.2160p.MP4-WRB.mp4')
- id=53729: `'Z:\\videos\\Anal\\PornMegaLoad.25.10.17.Lizzie.Bakery.Hardcore.41704.XXX.2160p.MP4-WRB.mp4'`
  - reparsed: (3, 'videos/Anal/PornMegaLoad.25.10.17.Lizzie.Bakery.Hardcore.41704.XXX.2160p.MP4-WRB.mp4')
  - stored:   (3, 'Videos/Anal/PornMegaLoad.25.10.17.Lizzie.Bakery.Hardcore.41704.XXX.2160p.MP4-WRB.mp4')

## StorageRoots used

- Id=2  Prefix=`M:\`
- Id=3  Prefix=`Z:\`
- Id=1  Prefix=`T:\`
