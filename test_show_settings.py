import sys
sys.path.insert(0, r'C:\Code\Automation\MediaVortex')
from Features.ShowSettings.ShowSettingsRepository import ShowSettingsRepository

repo = ShowSettingsRepository()
shows = repo.GetShowsWithStats('T:')
print(f'Found {len(shows)} shows')
print('First 5:')
for s in shows[:5]:
    print(f"  {s['ShowName']}: {s['FileCount']} files, {s['TotalGB']}GB, res={s['CommonResolution']}, codec={s['CommonCodec']}, target={s['TargetResolution']}")
