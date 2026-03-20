# Database Migration Strategy

## Current State

MediaVortex uses a manual migration approach in `Repositories/DatabaseManager.py`:
- `RunMigrations()` contains sequential `ALTER TABLE` statements with existence checks
- Each migration checks `information_schema.columns` before applying changes
- No version tracking — relies on idempotent column-existence checks
- No rollback capability
- Works but doesn't scale as the schema grows

## Recommended Approach: Alembic

[Alembic](https://alembic.sqlalchemy.org/) is SQLAlchemy's database migration tool. It works with raw SQL (no ORM required), making it compatible with MediaVortex's existing `psycopg2` stack.

### Why Alembic

| Feature | Current (`RunMigrations`) | Alembic |
|---------|---------------------------|---------|
| Version tracking | None | Migration history table |
| Rollback | Not supported | `downgrade()` per migration |
| Migration files | Inline in DatabaseManager.py | Individual versioned files |
| Ordering | Manual (code order) | Dependency chain |
| Team collaboration | Merge conflicts in one file | Separate files per migration |
| Auto-generation | N/A | Can diff models vs database |
| Raw SQL support | Yes | Yes (`op.execute()`) |

### Setup

```bash
# Install Alembic
pip install alembic

# Initialize in project root
alembic init Migrations
```

This creates:
```
Migrations/
    env.py          # Migration environment configuration
    script.py.mako  # Template for new migrations
    versions/       # Individual migration files
alembic.ini         # Alembic configuration
```

### Configuration

Edit `alembic.ini` to use the MediaVortex database:

```ini
[alembic]
script_location = Migrations
sqlalchemy.url = postgresql://mediavortex:mediavortex@localhost:5432/mediavortex
```

Or configure `Migrations/env.py` to read from environment variables (matching existing `DatabaseService` config):

```python
import os

def GetDatabaseUrl():
    Host = os.environ.get("MEDIAVORTEX_DB_HOST", "localhost")
    Port = os.environ.get("MEDIAVORTEX_DB_PORT", "5432")
    DbName = os.environ.get("MEDIAVORTEX_DB_NAME", "mediavortex")
    User = os.environ.get("MEDIAVORTEX_DB_USER", "mediavortex")
    Password = os.environ.get("MEDIAVORTEX_DB_PASSWORD", "mediavortex")
    return f"postgresql://{User}:{Password}@{Host}:{Port}/{DbName}"
```

### Migration File Conventions

Follow PascalCase naming to match the project style:

```bash
# Create a new migration
alembic revision -m "AddAudioCodecToMediaFiles"
```

This generates a file like `Migrations/versions/abc123_AddAudioCodecToMediaFiles.py`:

```python
"""AddAudioCodecToMediaFiles

Revision ID: abc123
Revises: def456
Create Date: 2026-03-14 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# Revision identifiers
revision = 'abc123'
down_revision = 'def456'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE MediaFiles ADD COLUMN AudioCodec TEXT")
    op.execute("ALTER TABLE MediaFiles ADD COLUMN SubtitleFormats TEXT")


def downgrade():
    op.execute("ALTER TABLE MediaFiles DROP COLUMN IF EXISTS SubtitleFormats")
    op.execute("ALTER TABLE MediaFiles DROP COLUMN IF EXISTS AudioCodec")
```

### Workflow

1. **Create migration**: `alembic revision -m "DescriptiveName"`
2. **Write SQL**: Edit the generated file's `upgrade()` and `downgrade()` functions
3. **Review**: Check the migration file before applying
4. **Apply**: `alembic upgrade head`
5. **Verify**: Run `py Scripts/UpdateDatabaseSchema.py` to refresh docs
6. **Commit**: Add the migration file to git

### Common Commands

```bash
# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Rollback to specific revision
alembic downgrade abc123

# Show current revision
alembic current

# Show migration history
alembic history

# Show pending migrations
alembic heads
```

### Integration with Existing Code

The transition from `RunMigrations()` to Alembic should be gradual:

1. **Phase 1 (Now)**: Install Alembic, create initial migration that stamps the current schema as the baseline
   ```bash
   alembic stamp head  # Mark current schema as up-to-date
   ```

2. **Phase 2**: Write all new migrations as Alembic files instead of adding to `RunMigrations()`

3. **Phase 3**: Once all environments are running Alembic, remove the old `RunMigrations()` checks

The `RunMigrations()` method can coexist with Alembic during the transition — its existence checks are idempotent, so running both won't cause conflicts.

### Startup Integration

To auto-apply migrations on startup (matching current `RunMigrations()` behavior), add to the service startup:

```python
import subprocess

def ApplyMigrations():
    """Run pending Alembic migrations."""
    Result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True, text=True
    )
    if Result.returncode != 0:
        LoggingService.LogError(
            f"Migration failed: {Result.stderr}",
            "StartupService", "ApplyMigrations"
        )
        raise RuntimeError("Database migration failed")
    LoggingService.LogInfo(
        "Database migrations applied successfully",
        "StartupService", "ApplyMigrations"
    )
```

### Adding Foreign Keys

The database currently has some foreign keys (from the SQLite migration) but is missing several. Alembic makes it straightforward to add them:

```python
def upgrade():
    op.execute("""
        ALTER TABLE TranscodeQueue
        ADD CONSTRAINT fk_TranscodeQueue_TranscodeAttemptId
        FOREIGN KEY (TranscodeAttemptId) REFERENCES TranscodeAttempts(Id)
    """)

def downgrade():
    op.execute("""
        ALTER TABLE TranscodeQueue
        DROP CONSTRAINT IF EXISTS fk_TranscodeQueue_TranscodeAttemptId
    """)
```
