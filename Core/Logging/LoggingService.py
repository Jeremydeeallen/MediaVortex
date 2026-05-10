import os
import traceback
from typing import Any, Optional
from datetime import datetime, timezone
from Core.Database.DatabaseService import DatabaseService


class LoggingService:
    """Centralized logging service for MediaVortex that logs to database.

    Verbosity flags are read at import time (class-attribute initialization)
    rather than inside `__new__`. Earlier versions read them in `__new__`,
    which only fires on `LoggingService()` instantiation -- but every callsite
    in the codebase uses the `@classmethod` form (`LoggingService.LogInfo(...)`)
    without instantiating, so the flags stayed at their `False` defaults and
    setting the env var had no effect on WorkerService.
    """

    _Instance = None
    _DebugEnabled = os.getenv('MEDIAVORTEX_DEBUG', 'false').lower() in ('true', '1', 'yes', 'on')
    _InfoEnabled = os.getenv('MEDIAVORTEX_LOG_INFO', 'false').lower() in ('true', '1', 'yes', 'on')
    DatabaseService = None

    def __new__(cls):
        if cls._Instance is None:
            cls._Instance = super(LoggingService, cls).__new__(cls)
            cls.DatabaseService = DatabaseService()
        return cls._Instance

    @classmethod
    def IsDebugEnabled(cls) -> bool:
        """Check if debugging is enabled."""
        return cls._DebugEnabled

    @classmethod
    def EnableDebug(cls):
        """Enable debugging."""
        cls._DebugEnabled = True

    @classmethod
    def DisableDebug(cls):
        """Disable debugging."""
        cls._DebugEnabled = False

    @classmethod
    def SetDebugMode(cls, Enabled: bool):
        """Set debug mode on or off."""
        cls._DebugEnabled = Enabled

    @classmethod
    def LogToDatabase(cls, LogLevel: str, Message: str, FunctionName: str = '', Component: str = 'System',
                     Operation: str = '', ExceptionType: str = None,
                     ExceptionMessage: str = None, StackTrace: str = None):
        """Log a message to the database."""
        try:
            # Ensure DatabaseService is initialized
            if cls.DatabaseService is None:
                cls.DatabaseService = DatabaseService()

            Query = """
            INSERT INTO Logs (Timestamp, LogLevel, FunctionName, Message, SourceFile,
                            SourceLine, SourceFunction, ExceptionType, ExceptionMessage,
                            StackTrace, Component, Operation, CreatedAt)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """

            Now = datetime.now(timezone.utc)
            Params = (
                Now,           # Timestamp
                LogLevel,      # LogLevel
                FunctionName,  # FunctionName
                Message,       # Message
                '',            # SourceFile
                0,             # SourceLine
                '',            # SourceFunction
                ExceptionType, # ExceptionType
                ExceptionMessage, # ExceptionMessage
                StackTrace,    # StackTrace
                Component,     # Component
                Operation,     # Operation
                Now            # CreatedAt
            )

            cls.DatabaseService.ExecuteNonQuery(Query, Params)

        except Exception as e:
            # Fallback to console if database logging fails
            print(f"ERROR: Failed to log to database: {str(e)}")
            print(f"Original message: {Message}")

    @classmethod
    def LogInfo(cls, Message: str, FunctionName: str = '', Component: str = 'System', Operation: str = ''):
        """Log an info message.

        DB write is unconditional -- the audit trail is a system invariant, not
        an operator preference. Terminal print is gated by `_InfoEnabled`
        (defaults off; `MEDIAVORTEX_LOG_INFO=true` makes it chatty).
        """
        cls.LogToDatabase('INFO', Message, FunctionName, Component, Operation)
        if cls._InfoEnabled:
            try:
                print(f"INFO: {Message}")
            except OSError:
                # stdout not available (e.g., service context) -- DB write already happened.
                pass

    @classmethod
    def LogError(cls, Message: str, FunctionName: str = '', Component: str = 'System', Operation: str = ''):
        """Log an error message."""
        try:
            print(f"ERROR: {Message}")
        except OSError:
            # Ignore OSError when stdout is not available (e.g., in service context)
            pass
        cls.LogToDatabase('ERROR', Message, FunctionName, Component, Operation)

    @classmethod
    def LogWarning(cls, Message: str, FunctionName: str = '', Component: str = 'System', Operation: str = ''):
        """Log a warning message."""
        try:
            print(f"WARNING: {Message}")
        except OSError:
            # Ignore OSError when stdout is not available (e.g., in service context)
            pass
        cls.LogToDatabase('WARNING', Message, FunctionName, Component, Operation)

    @classmethod
    def LogDebug(cls, Message: str, FunctionName: str = '', Component: str = 'System', Operation: str = ''):
        """Log a debug message if debugging is enabled."""
        if cls._DebugEnabled:
            try:
                print(f"DEBUG: {Message}")
            except OSError:
                # Ignore OSError when stdout is not available (e.g., in service context)
                pass
            cls.LogToDatabase('DEBUG', Message, FunctionName, Component, Operation)

    @classmethod
    def LogException(cls, Message: str, Exception: Exception, FunctionName: str = '', Component: str = 'System', Operation: str = ''):
        """Log an exception with full traceback."""
        ExceptionType = type(Exception).__name__
        ExceptionMessage = str(Exception)
        StackTrace = traceback.format_exc()

        ErrorMessage = f"{Message}: {ExceptionMessage}"
        print(f"EXCEPTION: {ErrorMessage}")
        print(StackTrace)

        cls.LogToDatabase('ERROR', ErrorMessage, FunctionName, Component, Operation,
                         ExceptionType, ExceptionMessage, StackTrace)

    @classmethod
    def LogFunctionEntry(cls, FunctionName: str, Component: str = 'System', *Args, **Kwargs):
        """Log function entry with parameters if debugging is enabled."""
        if cls._DebugEnabled:
            Params = []
            if Args:
                Params.extend([str(Arg) for Arg in Args])
            if Kwargs:
                Params.extend([f"{K}={V}" for K, V in Kwargs.items()])
            ParamStr = ", ".join(Params) if Params else "no parameters"
            Message = f"{FunctionName} called with {ParamStr}"
            print(f"DEBUG: {Message}")
            cls.LogToDatabase('DEBUG', Message, FunctionName, Component, FunctionName)

    @classmethod
    def LogFunctionExit(cls, FunctionName: str, Result: Any = None, Component: str = 'System'):
        """Log function exit with result if debugging is enabled."""
        if cls._DebugEnabled:
            if Result is not None:
                Message = f"{FunctionName} completed, result: {Result}"
            else:
                Message = f"{FunctionName} completed"
            print(f"DEBUG: {Message}")
            cls.LogToDatabase('DEBUG', Message, FunctionName, Component, FunctionName)

    @classmethod
    def LogData(cls, Message: str, Data: Any, FunctionName: str = '', Component: str = 'System', Operation: str = ''):
        """Log data if debugging is enabled."""
        if cls._DebugEnabled:
            FullMessage = f"{Message}: {Data}"
            print(f"DEBUG: {FullMessage}")
            cls.LogToDatabase('DEBUG', FullMessage, FunctionName, Component, Operation)

    # Backward compatibility methods
    @classmethod
    def Log(cls, Message: str, *Args, **Kwargs):
        """Log a debug message if debugging is enabled (backward compatibility)."""
        if Args or Kwargs:
            FormattedMessage = Message.format(*Args, **Kwargs)
        else:
            FormattedMessage = Message
        cls.LogDebug(FormattedMessage)
