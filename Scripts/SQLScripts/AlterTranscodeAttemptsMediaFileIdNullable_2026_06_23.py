import os
import sys

ScriptDir = os.path.dirname(os.path.abspath(__file__))
RepoRoot = os.path.abspath(os.path.join(ScriptDir, '..', '..'))
if RepoRoot not in sys.path:
    sys.path.insert(0, RepoRoot)

from Core.Database.DatabaseService import DatabaseService


# directive: worker-runtime-state | # see transcoded-output-placement.C13
def Main():
    Db = DatabaseService()
    Before = Db.ExecuteQuery(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s",
        ('transcodeattempts', 'mediafileid'),
    )
    if not Before:
        print('ERROR: transcodeattempts.mediafileid column not found.')
        sys.exit(1)
    BeforeNullable = Before[0]['is_nullable']
    print(f'Before: transcodeattempts.mediafileid is_nullable={BeforeNullable}')
    if BeforeNullable == 'YES':
        print('No-op: column is already nullable; FK ON DELETE SET NULL can fire safely.')
        return
    Db.ExecuteNonQuery('ALTER TABLE transcodeattempts ALTER COLUMN mediafileid DROP NOT NULL', ())
    After = Db.ExecuteQuery(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s",
        ('transcodeattempts', 'mediafileid'),
    )
    AfterNullable = After[0]['is_nullable']
    print(f'After:  transcodeattempts.mediafileid is_nullable={AfterNullable}')
    if AfterNullable != 'YES':
        print('ERROR: ALTER did not take effect.')
        sys.exit(1)
    print('OK: NOT NULL dropped. FK ON DELETE SET NULL now consistent with column nullability.')


if __name__ == '__main__':
    Main()
