# directive: bug-0094-activity-handler-decouple
import os
import re
import unittest


AntiPattern = re.compile(r"\.then\(Render|\.then\(Load[A-Z]|\.then\(Refresh")


def RepoRoot() -> str:
    Here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(Here, "..", ".."))


def EnumerateTemplates() -> list:
    TemplatesDir = os.path.join(RepoRoot(), "Templates")
    Out = []
    for Name in sorted(os.listdir(TemplatesDir)):
        if Name.endswith(".html"):
            Out.append(os.path.join(TemplatesDir, Name))
    return Out


class TestOperatorUIHandlersDecoupled(unittest.TestCase):
    def test_no_mutation_handler_couples_to_render_fn_name(self):
        Hits = []
        for Path in EnumerateTemplates():
            with open(Path, "r", encoding="utf-8") as Fh:
                for LineNo, Line in enumerate(Fh, start=1):
                    if AntiPattern.search(Line):
                        Hits.append(f"{os.path.relpath(Path, RepoRoot())}:{LineNo}: {Line.rstrip()}")
        self.assertEqual(
            Hits, [],
            "JS mutation handlers hard-coupled to render/refresh fn names -- see BUG-0094. "
            "Fix: dispatch a domain event or delete the callback and let SSE/poll refresh. "
            f"Hits:\n" + "\n".join(Hits)
        )


if __name__ == "__main__":
    unittest.main()
