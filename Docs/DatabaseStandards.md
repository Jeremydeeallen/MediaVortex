# Database Standards

## FilePath Query Standards

### Rule: ALL FilePath equality comparisons MUST use case-insensitive matching

**Problem**: Windows file system is case-insensitive, but database stores FilePath with exact casing. This can create duplicate records when users enter paths with different casing (e.g., `Z:\videos\Couple\` vs `z:\videos\couple\`).

**Solution**: Use case-insensitive matching for all FilePath queries to ensure the same file is always found regardless of path casing.

### Standard Patterns

#### For exact matches:
```python
# CORRECT:
WHERE LOWER(FilePath) = LOWER(?)

# WRONG:
WHERE FilePath = ?
```

#### For LIKE patterns (prefix/suffix matching):
```python
# CORRECT:
WHERE LOWER(FilePath) LIKE LOWER(?)

# WRONG:
WHERE FilePath LIKE ?
```

### Applies To

- Any new methods that query by FilePath
- Any new tables that store file paths  
- Any ad-hoc queries in scripts or tools
- All existing FilePath queries (already implemented in DatabaseManager.py)

### Implementation Details

1. `LOWER(FilePath)` converts the database column value to lowercase
2. `LOWER(?)` converts the input parameter to lowercase
3. Comparison is now case-insensitive
4. Original FilePath values in database remain unchanged
5. No data migration required

### Performance Impact

- `LOWER()` function has negligible performance impact on small-medium databases
- Prevents duplicate records which improves overall system performance
- Case-insensitive matching is more robust and user-friendly

### Examples

#### MediaFiles Table Queries
```python
# GetMediaFileByPath - CORRECT
query = """
    SELECT * FROM MediaFiles 
    WHERE LOWER(FilePath) = LOWER(?)
"""

# DeleteMediaFileByPath - CORRECT  
query = "DELETE FROM MediaFiles WHERE LOWER(FilePath) = LOWER(?)"
```

#### TranscodeFiles Table Queries
```python
# GetTranscodeFileByFilePath - CORRECT
query = """
    SELECT * FROM TranscodeFiles 
    WHERE LOWER(FilePath) = LOWER(?)
"""

# UpdateTranscodeFileStatus - CORRECT
query = f"UPDATE TranscodeFiles SET {fields} WHERE LOWER(FilePath) = LOWER(?)"
```

### Root Folder Queries (Exception)

Root folder queries use `LIKE` for prefix matching and should remain unchanged:
```python
# CORRECT - No change needed for prefix matching
WHERE FilePath LIKE ? || '%'
```

### Testing

When implementing new FilePath queries:
1. Test with different casing: `Z:\test\file.mp4` vs `z:\TEST\file.mp4`
2. Verify only ONE record is found/updated, not multiple
3. Ensure existing functionality still works correctly

### Migration Notes

- All existing FilePath queries in `DatabaseManager.py` have been updated
- No data migration required - existing FilePath values remain unchanged
- Backward compatible - existing functionality preserved, just more robust
