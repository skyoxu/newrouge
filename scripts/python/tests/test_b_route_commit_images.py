"""Read-only frozen target classification on actual temporary Windows files."""
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest

import _b_route_codec as codec
import _planning_apply_journal as journal
from test_b_route_records import encoded


class FrozenTargetImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='nr27-images-', dir=os.environ.get('ADOPTION_TEST_TEMP'))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.before = b'{ "old": true }\r\n'
        self.target = {'path': 'ordinary/data.json', 'schema_version': 'synthetic.image.v1',
            'before_raw_digest': None, 'after_payload': {'complete': 'new value'},
            'after_raw_digest': codec.raw_digest(encoded({'complete': 'new value'})),
            'verification_mode': 'immutable_bytes'}
        self.path = self.root / self.target['path']

    def test_absent_before_after_unknown_and_unchanged_images(self):
        self.assertEqual('before', journal.classify_frozen_target(self.root, self.target)['state'])
        self.assertEqual([], list(self.root.iterdir()))
        self.path.parent.mkdir()
        self.path.write_bytes(self.before)
        self.target['before_raw_digest'] = codec.raw_digest(self.before)
        self.assertEqual('before', journal.classify_frozen_target(self.root, self.target)['state'])
        self.assertEqual(self.before, self.path.read_bytes())
        after = encoded(self.target['after_payload']); self.path.write_bytes(after)
        self.assertEqual('after', journal.classify_frozen_target(self.root, self.target)['state'])
        self.assertEqual(after, self.path.read_bytes())
        unknown = b'{"external":"preserve"}'; self.path.write_bytes(unknown)
        with self.assertRaises(codec.CodecError) as failure:
            journal.classify_frozen_target(self.root, self.target)
        self.assertEqual(codec.ReasonCode.CONFLICT, failure.exception.diagnostic.reason_code)
        self.assertEqual(codec.raw_digest(unknown), failure.exception.diagnostic.actual)
        self.assertEqual(self.target['path'], failure.exception.diagnostic.resume_ref)
        self.assertEqual(unknown, self.path.read_bytes())

    def test_tamper_unsafe_path_directory_and_hardlink_are_rejected(self):
        original = deepcopy(self.target)
        for name in ['../escape.json', 'CON', 'ordinary/../data.json']:
            target = dict(original, path=name)
            with self.subTest(path=name), self.assertRaises(codec.CodecError):
                journal.classify_frozen_target(self.root, target)
        changed = deepcopy(original); changed['after_payload']['complete'] = 'tampered'
        with self.assertRaises(codec.CodecError):
            journal.classify_frozen_target(self.root, changed)
        self.path.mkdir(parents=True)
        with self.assertRaises(codec.CodecError):
            journal.classify_frozen_target(self.root, original)
        self.path.rmdir(); self.path.write_bytes(encoded(original['after_payload']))
        alias = self.path.with_name('alias.json'); os.link(self.path, alias)
        with self.assertRaises(codec.CodecError) as failure:
            journal.classify_frozen_target(self.root, original)
        self.assertEqual(codec.ReasonCode.UNSAFE_PATH, failure.exception.diagnostic.reason_code)

    @unittest.skipUnless(os.name == 'nt', 'Windows file sharing evidence')
    def test_actual_occupied_windows_handle_blocks_read_without_modifying_bytes(self):
        import ctypes
        from ctypes import wintypes
        self.path.parent.mkdir(); raw = encoded(self.target['after_payload']); self.path.write_bytes(raw)
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        api.CreateFileW.restype = wintypes.HANDLE
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        api.CloseHandle.restype = wintypes.BOOL
        handle = api.CreateFileW(str(self.path), 0x80000000, 0, None, 3, 0x80, None)
        self.assertNotEqual(ctypes.c_void_p(-1).value, handle)
        try:
            with self.assertRaises(codec.CodecError) as failure:
                journal.classify_frozen_target(self.root, self.target)
            self.assertEqual(codec.ReasonCode.READ_ERROR, failure.exception.diagnostic.reason_code)
        finally:
            api.CloseHandle(handle)
        self.assertEqual(raw, self.path.read_bytes())
        self.assertEqual('after', journal.classify_frozen_target(self.root, self.target)['state'])
