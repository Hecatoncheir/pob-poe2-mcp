"""Проверки выбора платформы и обязательных нативных библиотек."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pob_poe2_mcp.errors import EngineError
from pob_poe2_mcp.native_runtime import check_native_runtime, lua_library


class NativeRuntime(unittest.TestCase):
    def test_windows_uses_original_pob_library(self):
        with patch('sys.platform', 'win32'):
            self.assertEqual(lua_library(Path('runtime')), str(Path('runtime/lua51.dll')))

    def test_unix_bundle_is_selected_for_each_platform(self):
        for platform, name in [('linux', 'libluajit-5.1.so.2'), ('darwin', 'libluajit-5.1.dylib')]:
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / name).touch()
                (root / 'lua-utf8.so').touch()
                with patch('sys.platform', platform), patch.dict(os.environ, {'POB_MCP_NATIVE_DIR': temporary}, clear=True):
                    self.assertEqual(check_native_runtime(Path('runtime')), str(root / name))

    def test_missing_utf8_module_is_an_actionable_error(self):
        with tempfile.TemporaryDirectory() as temporary, patch('sys.platform', 'linux'):
            with patch.dict(os.environ, {'POB_MCP_NATIVE_DIR': temporary, 'POB_MCP_LUA_LIBRARY': str(Path(temporary) / 'lua.so')}, clear=True):
                with self.assertRaises(EngineError) as error:
                    check_native_runtime(Path('runtime'))
                self.assertEqual(error.exception.code, 'LUA_UTF8_NOT_FOUND')
