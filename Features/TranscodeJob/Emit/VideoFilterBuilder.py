from typing import Any, Dict, Optional


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C8
class VideoFilterBuilder:
    """Composes yadif (when interlaced) and optional scale filter into the -vf string; pure value computation."""

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C8
    def Build(self, ProfileSettings: Dict[str, Any], ScaleFilter: Optional[str], IsInterlaced: bool = False) -> Optional[str]:
        """Return comma-joined filter chain, or None when no filters are needed."""
        Filters = []
        if IsInterlaced:
            Filters.append("yadif=1:1:1")
        if ScaleFilter:
            Filters.append(ScaleFilter)
        return ','.join(Filters) if Filters else None
