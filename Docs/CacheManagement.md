# Cache Management for MediaVortex

## Problem: Python Bytecode Caching with Database Schema Changes

MediaVortex uses Python bytecode caching (`.pyc` files) which can cause issues when database schema changes are made. The cached bytecode may contain references to old database columns or methods that no longer exist.

### Symptoms
- `AttributeError: 'ModelName' object has no attribute 'ColumnName'`
- Database operations failing after schema changes
- Code changes not taking effect until cache is cleared

### Root Cause
Python automatically creates `.pyc` files in `__pycache__` directories to speed up module loading. When database schema changes are made:
1. Database schema is updated
2. Code is updated to match new schema
3. But cached bytecode still contains old references
4. Application crashes when trying to access removed attributes

## Solution: Automatic Cache Management

### 1. Automatic Cache Clearing
The main application (`MediaVortex.py`) now automatically:
- Disables bytecode caching for critical modules
- Clears existing cache on startup
- Prevents future caching issues

### 2. Manual Cache Clearing
If you encounter caching issues, run:
```bash
py clear_cache.py
```

### 3. Critical Modules
These modules are automatically cleared on startup:
- `Repositories/` - Database access layer
- `Models/` - Data models
- `Services/` - Business logic layer

## Best Practices

### During Development
1. **After database schema changes**: Always restart the application
2. **After model changes**: Run `py clear_cache.py` if issues persist
3. **Before deployment**: Clear cache to ensure fresh code

### Production Deployment
1. The application automatically clears cache on startup
2. No manual intervention required
3. Fresh code execution guaranteed

## Technical Details

### Cache Disabling
```python
import sys
sys.dont_write_bytecode = True
```

### Cache Clearing
```python
import shutil
shutil.rmtree("module/__pycache__")
```

### Performance Impact
- Minimal performance impact for MediaVortex use case
- Safety benefits far outweigh performance cost
- Prevents silent failures and deployment issues

## Troubleshooting

### If Cache Issues Persist
1. Stop the application completely
2. Run `py clear_cache.py`
3. Restart the application
4. Check for any remaining `__pycache__` directories

### Manual Cache Clearing
```bash
# Windows PowerShell
Remove-Item -Path "Repositories\__pycache__" -Recurse -Force
Remove-Item -Path "Models\__pycache__" -Recurse -Force
Remove-Item -Path "Services\__pycache__" -Recurse -Force

# Or use the script
py clear_cache.py
```

## Prevention

The automatic cache management in `MediaVortex.py` prevents this issue by:
1. Disabling bytecode caching for critical modules
2. Clearing existing cache on every startup
3. Ensuring fresh code execution after schema changes

This ensures that database schema changes are immediately reflected in the running application without manual intervention.
