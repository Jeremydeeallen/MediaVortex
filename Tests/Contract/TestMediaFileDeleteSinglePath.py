# see probe-worker-decoupled.C11 -- MediaFiles delete has ONE path: MediaFilesRepository.DeleteMediaFile. FK ON DELETE SET NULL preserves attempt history.
import os
import re
import unittest


ProjectRoot = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
ProductionDirs = ['Features', 'Workers', 'WorkerService', 'WebService', 'Repositories', 'Core']


def _WalkPy(Root):
    for Dp, _Dn, Fn in os.walk(Root):
        if '__pycache__' in Dp or os.sep + 'venv' + os.sep in Dp:
            continue
        for F in Fn:
            if F.endswith('.py'):
                yield os.path.join(Dp, F)


class TestMediaFileDeleteSinglePath(unittest.TestCase):

    def test_no_deletemediafilecascade_references(self):
        Hits = []
        Rx = re.compile(r'DeleteMediaFileCascade')
        for Dir in ProductionDirs:
            Root = os.path.join(ProjectRoot, Dir)
            if not os.path.isdir(Root):
                continue
            for Path in _WalkPy(Root):
                with open(Path, 'r', encoding='utf-8', errors='ignore') as Fh:
                    for I, Line in enumerate(Fh, 1):
                        if Rx.search(Line):
                            Hits.append(f"{Path}:{I}: {Line.rstrip()}")
        self.assertEqual(Hits, [], "DeleteMediaFileCascade is retired -- use DeleteMediaFile; FK SET NULL preserves attempts.\n" + "\n".join(Hits))

    def test_mediafileid_fk_is_set_null(self):
        from Core.Database.DatabaseService import DatabaseService
        Rows = DatabaseService().ExecuteQuery(
            "SELECT conname, confdeltype FROM pg_constraint "
            "WHERE contype='f' AND conrelid::regclass::text IN ('transcodeattempts','transcodefiles') "
            "AND confrelid::regclass::text='mediafiles'"
        )
        self.assertEqual(len(Rows), 2, f"Expected 2 FK constraints, got {len(Rows)}: {Rows}")
        for R in Rows:
            self.assertEqual(R['confdeltype'], 'n', f"FK {R['conname']} must be ON DELETE SET NULL (confdeltype='n'), got {R['confdeltype']!r}")


if __name__ == '__main__':
    unittest.main()
