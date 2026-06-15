# see paged-query.C2 -- SRP: one class per file across Core/Querying/ tree

import ast
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


_QUERYING_ROOT = Path(__file__).resolve().parent.parent.parent / "Core" / "Querying"


# directive: paged-query-core | # see paged-query.C2
def _CountTopLevelClasses(FilePath: Path) -> int:
    Tree = ast.parse(FilePath.read_text(encoding="utf-8"))
    return sum(1 for Node in Tree.body if isinstance(Node, ast.ClassDef))


# directive: paged-query-core | # see paged-query.C2
def _IterPyFiles(Root: Path):
    for Entry in Root.rglob("*.py"):
        Name = Entry.name
        if Name == "__init__.py":
            continue
        yield Entry


# directive: paged-query-core | # see paged-query.C2
class TestOneClassPerFile(unittest.TestCase):
    # directive: paged-query-core | # see paged-query.C2
    def test_no_py_file_in_querying_tree_has_more_than_one_class(self):
        Offenders = []
        for FilePath in _IterPyFiles(_QUERYING_ROOT):
            ClassCount = _CountTopLevelClasses(FilePath)
            if ClassCount > 1:
                Rel = FilePath.relative_to(_QUERYING_ROOT.parent.parent)
                Offenders.append(f"{Rel} -> {ClassCount} classes")
        self.assertEqual(
            Offenders,
            [],
            f"SRP violation: files with multiple top-level classes: {Offenders}",
        )

    # directive: paged-query-core | # see paged-query.C2
    def test_every_named_class_lives_in_its_own_file(self):
        Expected = {
            "PagedQuery": "PagedQuery.py",
            "PagedQueryBuilder": "PagedQueryBuilder.py",
            "PagedQueryConfig": "PagedQueryConfig.py",
            "PagedQueryResult": "PagedQueryResult.py",
            "QuerySort": "QuerySort.py",
            "EqualsFilter": "Filters/EqualsFilter.py",
            "LikeFilter": "Filters/LikeFilter.py",
            "NotLikeFilter": "Filters/NotLikeFilter.py",
            "RangeFilter": "Filters/RangeFilter.py",
            "InListFilter": "Filters/InListFilter.py",
            "AndComposer": "Filters/AndComposer.py",
            "OrComposer": "Filters/OrComposer.py",
            "InvalidColumnError": "Exceptions/InvalidColumnError.py",
            "InvalidPageError": "Exceptions/InvalidPageError.py",
            "IQueryFilter": "Interfaces/IQueryFilter.py",
            "IQuerySort": "Interfaces/IQuerySort.py",
        }
        for ClassName, RelPath in Expected.items():
            FilePath = _QUERYING_ROOT / RelPath
            self.assertTrue(FilePath.exists(), f"Expected file {RelPath} does not exist")
            Tree = ast.parse(FilePath.read_text(encoding="utf-8"))
            Classes = [Node.name for Node in Tree.body if isinstance(Node, ast.ClassDef)]
            self.assertIn(ClassName, Classes, f"{RelPath} does not define class {ClassName}")
            self.assertEqual(
                len(Classes), 1,
                f"{RelPath} should contain exactly one class but contains: {Classes}",
            )

    # directive: paged-query-core | # see paged-query.C2
    def test_no_orphan_classes_in_querying_init_or_helpers(self):
        ForbiddenSpots = {
            _QUERYING_ROOT / "QueryFilter.py": "legacy flat module deleted",
            _QUERYING_ROOT / "Exceptions.py": "legacy flat module deleted",
        }
        for Spot, Reason in ForbiddenSpots.items():
            self.assertFalse(Spot.exists(), f"{Spot.relative_to(_QUERYING_ROOT.parent.parent)} must not exist ({Reason})")


if __name__ == "__main__":
    unittest.main()
