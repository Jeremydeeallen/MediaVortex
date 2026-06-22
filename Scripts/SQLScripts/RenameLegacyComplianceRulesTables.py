import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: compliance-symmetry
LEGACY_TABLES = [
    ('videocompliancerules', 'videocompliancerules_old_2026_06_22'),
    ('containercompliancerules', 'containercompliancerules_old_2026_06_22'),
]


# directive: compliance-symmetry
def TableExists(DB, Name):
    Rows = DB.ExecuteQuery(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = %s",
        (Name,),
    )
    return bool(Rows)


# directive: compliance-symmetry
def Run():
    DB = DatabaseService()

    for OldName, NewName in LEGACY_TABLES:
        if TableExists(DB, NewName):
            print(f"{NewName} already exists; skipping.")
            continue
        if not TableExists(DB, OldName):
            print(f"{OldName} does not exist; nothing to rename.")
            continue
        print(f"Renaming {OldName} -> {NewName} ...")
        DB.ExecuteNonQuery(f"ALTER TABLE {OldName} RENAME TO {NewName}")
        print("  done.")

    print("Post-migration state:")
    for OldName, NewName in LEGACY_TABLES:
        old_present = TableExists(DB, OldName)
        new_present = TableExists(DB, NewName)
        print(f"  {OldName}: present={old_present}; {NewName}: present={new_present}")


if __name__ == '__main__':
    Run()
