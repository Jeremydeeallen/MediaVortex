import dataclasses
import unittest
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity


# directive: work-transcode-unified
class TestSeriesIdentityVO(unittest.TestCase):
    """Value object: equality by value, immutability, URL-encodable composite key."""

    # directive: work-transcode-unified
    def test_equality_by_value(self):
        # see work-bucket.C2
        A = SeriesIdentity(StorageRootId=3, RelativePath='House')
        B = SeriesIdentity(StorageRootId=3, RelativePath='House')
        self.assertEqual(A, B)
        self.assertEqual(hash(A), hash(B))

    # directive: work-transcode-unified
    def test_inequality_by_storage_root(self):
        # see work-bucket.C2
        A = SeriesIdentity(StorageRootId=3, RelativePath='House')
        B = SeriesIdentity(StorageRootId=4, RelativePath='House')
        self.assertNotEqual(A, B)

    # directive: work-transcode-unified
    def test_inequality_by_relative_path(self):
        # see work-bucket.C2
        A = SeriesIdentity(StorageRootId=3, RelativePath='House')
        B = SeriesIdentity(StorageRootId=3, RelativePath='Breaking Bad')
        self.assertNotEqual(A, B)

    # directive: work-transcode-unified
    def test_immutability(self):
        # see work-bucket.C2
        A = SeriesIdentity(StorageRootId=3, RelativePath='House')
        with self.assertRaises(dataclasses.FrozenInstanceError):
            A.StorageRootId = 4

    # directive: work-transcode-unified
    def test_composite_key_roundtrip(self):
        # see work-bucket.C2
        A = SeriesIdentity(StorageRootId=3, RelativePath='Breaking Bad')
        Key = A.ToCompositeKey()
        self.assertEqual(Key, '3:Breaking Bad')
        B = SeriesIdentity.FromCompositeKey(Key)
        self.assertEqual(A, B)

    # directive: work-transcode-unified
    def test_composite_key_roundtrip_with_colons_in_relativepath(self):
        # see work-bucket.C2
        A = SeriesIdentity(StorageRootId=3, RelativePath='Star Trek: Strange New Worlds')
        Key = A.ToCompositeKey()
        self.assertEqual(Key, '3:Star Trek: Strange New Worlds')
        B = SeriesIdentity.FromCompositeKey(Key)
        self.assertEqual(A, B)


if __name__ == '__main__':
    unittest.main()
