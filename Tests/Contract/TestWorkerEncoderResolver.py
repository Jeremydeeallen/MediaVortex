# see transcode-flow-canonical.C25
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
from unittest.mock import MagicMock

from Features.TranscodeJob.Worker.WorkerEncoderResolver import (
    WorkerEncoderResolver,
    WorkerEncoderResolverError,
    NVENC_OVERRIDES,
    QSV_OVERRIDES,
)


# directive: transcode-flow-canonical
def _MakeDb(Rows):
    Db = MagicMock()
    Db.ExecuteQuery.return_value = Rows
    return Db


# directive: transcode-flow-canonical
def test_nvenc_only_resolves_to_nvenc_family():
    Db = _MakeDb([{'nvenccapable': True, 'qsvcapable': False}])
    Resolver = WorkerEncoderResolver(Db=Db)
    Family, Overrides = Resolver.Resolve('dot-worker-1')
    assert Family == 'NVENC'
    assert Overrides['Codec'] == 'av1_nvenc'
    assert Overrides['UseNvidiaHardware'] == 1
    assert Overrides['UseIntelHardware'] == 0


# directive: transcode-flow-canonical
def test_qsv_only_resolves_to_qsv_family():
    Db = _MakeDb([{'nvenccapable': False, 'qsvcapable': True}])
    Resolver = WorkerEncoderResolver(Db=Db)
    Family, Overrides = Resolver.Resolve('wakko-worker-1')
    assert Family == 'QSV'
    assert Overrides['Codec'] == 'av1_qsv'
    assert Overrides['UseNvidiaHardware'] == 0
    assert Overrides['UseIntelHardware'] == 1


# directive: transcode-flow-canonical
def test_both_capable_prefers_nvenc():
    Db = _MakeDb([{'nvenccapable': True, 'qsvcapable': True}])
    Resolver = WorkerEncoderResolver(Db=Db)
    Family, Overrides = Resolver.Resolve('dual-capable-worker')
    assert Family == 'NVENC', "When both encoders are available, NVENC takes precedence per C25"
    assert Overrides['Codec'] == 'av1_nvenc'


# directive: transcode-flow-canonical
def test_no_encoder_capability_raises_fail_loud():
    Db = _MakeDb([{'nvenccapable': False, 'qsvcapable': False}])
    Resolver = WorkerEncoderResolver(Db=Db)
    with pytest.raises(WorkerEncoderResolverError) as ExcInfo:
        Resolver.Resolve('larry-worker-1')
    assert 'no encode capability' in str(ExcInfo.value)


# directive: transcode-flow-canonical
def test_missing_worker_row_raises_fail_loud():
    Db = _MakeDb([])
    Resolver = WorkerEncoderResolver(Db=Db)
    with pytest.raises(WorkerEncoderResolverError) as ExcInfo:
        Resolver.Resolve('phantom-worker')
    assert 'not found' in str(ExcInfo.value)


# directive: transcode-flow-canonical
def test_apply_overrides_mutates_settings_dict_and_returns_family():
    Db = _MakeDb([{'nvenccapable': True, 'qsvcapable': False}])
    Resolver = WorkerEncoderResolver(Db=Db)
    Settings = {'Codec': 'av1', 'UseNvidiaHardware': 0, 'ExistingKey': 'preserved'}
    Family = Resolver.ApplyOverrides('dot-worker-1', Settings)
    assert Family == 'NVENC'
    assert Settings['Codec'] == 'av1_nvenc'
    assert Settings['UseNvidiaHardware'] == 1
    assert Settings['ExistingKey'] == 'preserved', "Non-override keys must survive ApplyOverrides"


# directive: transcode-flow-canonical
def test_apply_overrides_qsv_worker_flips_hardware_flags():
    Db = _MakeDb([{'nvenccapable': False, 'qsvcapable': True}])
    Resolver = WorkerEncoderResolver(Db=Db)
    Settings = {'Codec': 'av1'}
    Family = Resolver.ApplyOverrides('wakko-worker-1', Settings)
    assert Family == 'QSV'
    assert Settings['UseIntelHardware'] == 1
    assert Settings['UseNvidiaHardware'] == 0


# directive: transcode-flow-canonical
def test_nvenc_overrides_carries_preset_tune_multipass_rc():
    assert NVENC_OVERRIDES['Preset'] == 7
    assert NVENC_OVERRIDES['Tune'] == 'hq'
    assert NVENC_OVERRIDES['Multipass'] == 'fullres'
    assert NVENC_OVERRIDES['RateControlMode'] == 'vbr'
    assert NVENC_OVERRIDES['SpatialAq'] == 1
    assert NVENC_OVERRIDES['TemporalAq'] == 1


# directive: transcode-flow-canonical
def test_qsv_overrides_carries_preset_and_icq_rc():
    assert QSV_OVERRIDES['Preset'] == 1
    assert QSV_OVERRIDES['RateControlMode'] == 'icq'


# directive: transcode-flow-canonical
def test_resolver_reads_db_fresh_per_call_no_cache():
    Db = _MakeDb([{'nvenccapable': True, 'qsvcapable': False}])
    Resolver = WorkerEncoderResolver(Db=Db)
    Resolver.Resolve('dot-worker-1')
    Resolver.Resolve('dot-worker-1')
    assert Db.ExecuteQuery.call_count == 2, "Resolver must not cache; db-authority requires fresh read per call"


# directive: transcode-flow-canonical
def test_apply_overrides_returns_copy_not_shared_reference():
    Db = _MakeDb([{'nvenccapable': True, 'qsvcapable': False}])
    Resolver = WorkerEncoderResolver(Db=Db)
    Settings1 = {}
    Settings2 = {}
    Resolver.ApplyOverrides('dot-worker-1', Settings1)
    Resolver.ApplyOverrides('dot-worker-1', Settings2)
    Settings1['Codec'] = 'mutated'
    assert Settings2['Codec'] == 'av1_nvenc', "Each ApplyOverrides call must write independent values, not aliases"


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
