from Core.Database.DatabaseService import DatabaseService


SELECT_ALL_COLUMNS = (
    "Id, Scope, ScopeKey, Enabled, "
    "TargetIntegratedLufs, TargetTruePeakDbtp, TargetLra, LoudnessTolerance, "
    "EmitTracks, UngainablePolicy, LanguageKeepPolicy, "
    "KeepCommentaryTracks, EnableSpeechLanguageDetection, AudioDelayMs, LastUpdated"
)


GET_BY_SCOPE_KEY_SQL = (
    "SELECT " + SELECT_ALL_COLUMNS + " "
    "FROM AudioNormalizationConfig "
    "WHERE Scope = %s AND ScopeKey IS NOT DISTINCT FROM %s"
)


LIST_BY_SCOPE_SQL = (
    "SELECT " + SELECT_ALL_COLUMNS + " "
    "FROM AudioNormalizationConfig "
    "WHERE Scope = %s "
    "ORDER BY ScopeKey NULLS FIRST"
)


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C9
class AudioNormalizationConfigRepository:
    """Read-only access to AudioNormalizationConfig; fresh DB call per read per db-is-authority.md."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C9
    def Get(self, Scope, ScopeKey):
        """Return the single config row for (Scope, ScopeKey) or None."""
        Rows = DatabaseService().ExecuteQuery(GET_BY_SCOPE_KEY_SQL, (Scope, ScopeKey))
        return Rows[0] if Rows else None

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C9
    def ListByScope(self, Scope):
        """Return every config row at the given scope; empty list when none."""
        return DatabaseService().ExecuteQuery(LIST_BY_SCOPE_SQL, (Scope,))
