import unittest
from Features.WorkBucket.Domain.BucketKey import BucketKey


# directive: work-transcode-unified
class TestBucketKeyVO(unittest.TestCase):

    # directive: work-transcode-unified
    def test_from_url_key_transcode(self):
        # see work-bucket.C1
        K = BucketKey.FromUrlKey('Transcode')
        self.assertIsNotNone(K)
        self.assertEqual(K.BucketName, 'Transcode')
        self.assertEqual(K.ProcessingMode, 'Transcode')

    # directive: work-transcode-unified
    def test_from_url_key_remux(self):
        # see work-bucket.C1
        K = BucketKey.FromUrlKey('Remux')
        self.assertIsNotNone(K)
        self.assertEqual(K.BucketName, 'Remux')
        self.assertEqual(K.ProcessingMode, 'Remux')

    # directive: work-transcode-unified
    def test_from_url_key_audio(self):
        # see work-bucket.C1
        K = BucketKey.FromUrlKey('Audio')
        self.assertIsNotNone(K)
        self.assertEqual(K.BucketName, 'AudioFix')
        self.assertEqual(K.ProcessingMode, 'AudioFix')

    # directive: work-transcode-unified
    def test_from_url_key_unknown(self):
        # see work-bucket.C1
        self.assertIsNone(BucketKey.FromUrlKey('NotABucket'))

    # directive: work-transcode-unified
    def test_labels_present(self):
        # see work-bucket.C1
        K = BucketKey.FromUrlKey('Transcode')
        self.assertEqual(K.Title, 'Transcode')
        self.assertTrue(K.Subtitle)
        self.assertTrue(K.Icon)


if __name__ == '__main__':
    unittest.main()
