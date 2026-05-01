import tempfile
import unittest
from pathlib import Path

from scripts.python.remind_overlay_task_drift import _canonical_bytes


class CanonicalBytesTests(unittest.TestCase):
    def test_canonical_bytes_normalizes_crcrlf_to_lf(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            sample = Path(td) / "sample.json"
            sample.write_bytes(b"{\r\r\n\"k\":1\r\r\n}\r")
            self.assertEqual(b"{\n\n\"k\":1\n\n}\n", _canonical_bytes(sample))


if __name__ == "__main__":
    unittest.main()
