import os
from typing import Any


class DebugService:
    """Centralized debugging service for MediaVortex."""
    
    _instance = None
    _debug_enabled = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DebugService, cls).__new__(cls)
            # Check environment variable for debug mode
            cls._debug_enabled = os.getenv('MEDIAVORTEX_DEBUG', 'false').lower() in ('true', '1', 'yes', 'on')
        return cls._instance
    
    @classmethod
    def IsDebugEnabled(cls) -> bool:
        """Check if debugging is enabled."""
        return cls._debug_enabled
    
    @classmethod
    def EnableDebug(cls):
        """Enable debugging."""
        cls._debug_enabled = True
    
    @classmethod
    def DisableDebug(cls):
        """Disable debugging."""
        cls._debug_enabled = False
    
    @classmethod
    def SetDebugMode(cls, enabled: bool):
        """Set debug mode on or off."""
        cls._debug_enabled = enabled
    
    @classmethod
    def Log(cls, message: str, *args, **kwargs):
        """Log a debug message if debugging is enabled."""
        if cls._debug_enabled:
            if args or kwargs:
                print(f"DEBUG: {message.format(*args, **kwargs)}")
            else:
                print(f"DEBUG: {message}")
    
    @classmethod
    def LogException(cls, message: str, exception: Exception):
        """Log an exception with full traceback if debugging is enabled."""
        if cls._debug_enabled:
            print(f"DEBUG: {message}")
            print(f"DEBUG: Exception: {str(exception)}")
            import traceback
            traceback.print_exc()
    
    @classmethod
    def LogData(cls, message: str, data: Any):
        """Log data if debugging is enabled."""
        if cls._debug_enabled:
            print(f"DEBUG: {message}")
            print(f"DEBUG: Data: {data}")
    
    @classmethod
    def LogFunctionEntry(cls, function_name: str, *args, **kwargs):
        """Log function entry with parameters if debugging is enabled."""
        if cls._debug_enabled:
            params = []
            if args:
                params.extend([str(arg) for arg in args])
            if kwargs:
                params.extend([f"{k}={v}" for k, v in kwargs.items()])
            param_str = ", ".join(params) if params else "no parameters"
            print(f"DEBUG: {function_name} called with {param_str}")
    
    @classmethod
    def LogFunctionExit(cls, function_name: str, result: Any = None):
        """Log function exit with result if debugging is enabled."""
        if cls._debug_enabled:
            if result is not None:
                print(f"DEBUG: {function_name} completed, result: {result}")
            else:
                print(f"DEBUG: {function_name} completed")
