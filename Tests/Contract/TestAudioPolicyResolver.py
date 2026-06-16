import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.AudioPolicyResolver import AudioPolicyResolver


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C9
class _FakeRepository:
    """Captures (Scope, ScopeKey) lookups and returns a per-scope row from a fixture dict."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C9
    def __init__(self, Fixture):
        self.Fixture = Fixture
        self.Calls = []

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C9
    def Get(self, Scope, ScopeKey):
        self.Calls.append((Scope, ScopeKey))
        return self.Fixture.get((Scope, ScopeKey))


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C9
class _MediaFile:
    """Stub MediaFile with Id, StorageRootId, RelativePath."""
    def __init__(self, Id, StorageRootId, RelativePath):
        self.Id = Id
        self.StorageRootId = StorageRootId
        self.RelativePath = RelativePath


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C9
class TestAudioPolicyResolver(unittest.TestCase):
    """C9: most-specific row wins across item > folder > library > global."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C9
    def test_global_when_no_other_rows(self):
        Repo = _FakeRepository({('global', None): {'Scope': 'global', 'Marker': 'G'}})
        Resolver = AudioPolicyResolver(Repository=Repo)
        Mf = _MediaFile(Id=42, StorageRootId=1, RelativePath='Movies/Foo.mp4')
        Result = Resolver.GetEffectivePolicy(Mf)
        self.assertEqual(Result['Marker'], 'G')

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C9
    def test_library_overrides_global(self):
        Repo = _FakeRepository({
            ('library', '1'): {'Scope': 'library', 'Marker': 'L'},
            ('global', None): {'Scope': 'global', 'Marker': 'G'},
        })
        Resolver = AudioPolicyResolver(Repository=Repo)
        Mf = _MediaFile(Id=42, StorageRootId=1, RelativePath='Movies/Foo.mp4')
        Result = Resolver.GetEffectivePolicy(Mf)
        self.assertEqual(Result['Marker'], 'L')

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C9
    def test_folder_overrides_library_and_global(self):
        Repo = _FakeRepository({
            ('folder', 'Movies'): {'Scope': 'folder', 'Marker': 'F'},
            ('library', '1'): {'Scope': 'library', 'Marker': 'L'},
            ('global', None): {'Scope': 'global', 'Marker': 'G'},
        })
        Resolver = AudioPolicyResolver(Repository=Repo)
        Mf = _MediaFile(Id=42, StorageRootId=1, RelativePath='Movies/Foo.mp4')
        Result = Resolver.GetEffectivePolicy(Mf)
        self.assertEqual(Result['Marker'], 'F')

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C9
    def test_item_overrides_all(self):
        Repo = _FakeRepository({
            ('item', '42'): {'Scope': 'item', 'Marker': 'I'},
            ('folder', 'Movies'): {'Scope': 'folder', 'Marker': 'F'},
            ('library', '1'): {'Scope': 'library', 'Marker': 'L'},
            ('global', None): {'Scope': 'global', 'Marker': 'G'},
        })
        Resolver = AudioPolicyResolver(Repository=Repo)
        Mf = _MediaFile(Id=42, StorageRootId=1, RelativePath='Movies/Foo.mp4')
        Result = Resolver.GetEffectivePolicy(Mf)
        self.assertEqual(Result['Marker'], 'I')

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C9
    def test_walks_in_specificity_order(self):
        Repo = _FakeRepository({('global', None): {'Scope': 'global'}})
        Resolver = AudioPolicyResolver(Repository=Repo)
        Mf = _MediaFile(Id=42, StorageRootId=1, RelativePath='Movies/Foo.mp4')
        Resolver.GetEffectivePolicy(Mf)
        Scopes = [Call[0] for Call in Repo.Calls]
        self.assertEqual(Scopes, ['item', 'folder', 'library', 'global'])

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C9
    def test_handles_dict_mediafile(self):
        Repo = _FakeRepository({('item', '99'): {'Scope': 'item', 'Marker': 'I'}})
        Resolver = AudioPolicyResolver(Repository=Repo)
        Mf = {'Id': 99, 'StorageRootId': 5, 'RelativePath': 'TV/Show/ep.mkv'}
        Result = Resolver.GetEffectivePolicy(Mf)
        self.assertEqual(Result['Marker'], 'I')


if __name__ == '__main__':
    unittest.main()
