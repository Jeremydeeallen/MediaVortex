from typing import Any, Dict

from Features.TranscodeJob.Emit.EncoderArgsStrategies.IEncoderArgsStrategy import IEncoderArgsStrategy


class SvtAv1EncoderArgsStrategy(IEncoderArgsStrategy):
    """Emit libsvtav1 CRF/preset args; owns film-grain emission (NVENC + QSV no-op for film-grain)."""

    def AddCodecParameters(self, CommandParts: list, CodecParameters: list, ProfileSettings: Dict[str, Any]) -> None:
        ParamLookup = {}
        for Param in CodecParameters:
            ParamLookup[Param['ParameterName']] = Param

        Quality = ProfileSettings.get('Quality')
        if Quality is not None and Quality != '' and Quality != 'None':
            if 'crf' in ParamLookup:
                CommandParts.extend(['-crf', str(Quality)])

        Preset = ProfileSettings.get('Preset')
        if Preset is not None and Preset != '' and Preset != 'None':
            if 'preset' in ParamLookup:
                CommandParts.extend(['-preset', str(Preset)])

    def AddFilmGrainParameter(self, CommandParts: list, CodecParameters: list, ProfileSettings: Dict[str, Any]) -> None:
        ParamLookup = {}
        for Param in CodecParameters:
            ParamLookup[Param['ParameterName']] = Param

        if 'film-grain' in ParamLookup:
            FilmGrain = ProfileSettings.get('FilmGrain')
            if FilmGrain is not None and FilmGrain != '' and FilmGrain != 'None' and FilmGrain > 0:
                CommandParts.extend(['-svtav1-params', f'film-grain={FilmGrain}'])
