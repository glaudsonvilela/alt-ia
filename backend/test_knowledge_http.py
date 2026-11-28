import unittest
from knowledge_http import byte_window


class RangeTest(unittest.TestCase):
    def test_pdfjs_ranges_and_suffix(self):
        for header, expected in [(None, (0,100)), ('bytes=0-9',(0,10)),
            ('bytes=90-',(90,100)), ('bytes=-20',(80,100)),
            ('bytes=90-200',(90,100)), ('bytes=-200',(0,100))]:
            self.assertEqual(byte_window(header,100),expected)

    def test_invalid_or_unsatisfiable_ranges(self):
        for header in ['bytes=100-', 'bytes=9-2', 'bytes=0-1,5-6', 'bytes=-0', 'bytes=abc-']:
            with self.assertRaises(ValueError):
                byte_window(header,100)
