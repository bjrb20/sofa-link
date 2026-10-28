import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

import fetch_core
from fetch_core import target, validate, core_filename


def elf(machine):
    header = bytearray(64)
    header[:6] = b'\x7fELF\x02\x01'
    struct.pack_into('<H', header, 18, machine)
    return header


def macho(cpu):
    header = bytearray(32)
    header[:4] = b'\xcf\xfa\xed\xfe'
    struct.pack_into('<I', header, 4, cpu)
    return header


class InstallerTests(unittest.TestCase):
    def test_wrong_architecture_replaced_and_correct_core_reused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root/'runtime/cores/pcsx_rearmed_libretro.so'
            path.parent.mkdir(parents=True)
            path.write_bytes(elf(62))
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, 'w') as bundle:
                bundle.writestr('pcsx_rearmed_libretro.so', elf(183))
            with patch.object(fetch_core, 'ROOT', root), patch('platform.system', return_value='Linux'), \
                    patch('platform.machine', return_value='aarch64'), \
                    patch('urllib.request.urlopen', return_value=io.BytesIO(archive.getvalue())) as download:
                fetch_core.main()
                self.assertIn('/linux/aarch64/', download.call_args.args[0])
                self.assertEqual(path.read_bytes(), elf(183))
                self.assertEqual(json.loads(path.with_name('download.json').read_text())['pcsx_rearmed']['architecture'], 'aarch64')
                download.reset_mock()
                fetch_core.main()
                download.assert_not_called()

    def test_failed_download_keeps_previous_core(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root/'runtime/cores/pcsx_rearmed_libretro.so'
            path.parent.mkdir(parents=True)
            path.write_bytes(elf(62))
            with patch.object(fetch_core, 'ROOT', root), patch('platform.system', return_value='Linux'), \
                    patch('platform.machine', return_value='aarch64'), \
                    patch('urllib.request.urlopen', side_effect=urllib.error.URLError('offline')):
                with self.assertRaises(urllib.error.URLError):
                    fetch_core.main()
            self.assertEqual(path.read_bytes(), elf(62))

    def test_host_detection(self):
        self.assertEqual(target('Linux', 'aarch64'), ('aarch64', 183))
        self.assertEqual(target('Linux', 'arm64'), ('aarch64', 183))
        self.assertEqual(target('Linux', 'x86_64'), ('x86_64', 62))
        self.assertEqual(target('Linux', 'AMD64'), ('x86_64', 62))
        self.assertEqual(target('Darwin', 'arm64'), ('arm64', 0x0100000C))
        self.assertEqual(core_filename('Darwin'), 'pcsx_rearmed_libretro.dylib')
        self.assertEqual(core_filename('Linux'), 'pcsx_rearmed_libretro.so')
        for system, machine in [('Darwin', 'x86_64'), ('Windows', 'arm64'), ('Linux', 'armv7l')]:
            with self.assertRaises(ValueError):
                target(system, machine)

    def test_rejects_incompatible_download_or_existing_core(self):
        validate(elf(183), 183)
        validate(elf(62), 62)
        validate(macho(0x0100000C), 0x0100000C)
        for data, machine in [(elf(62), 183), (elf(183), 62), (b'not an ELF', 183), (elf(0), 183)]:
            with self.assertRaises(ValueError):
                validate(data, machine)

    def test_macos_uses_arm64_dylib_download(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, 'w') as bundle:
                bundle.writestr('pcsx_rearmed_libretro.dylib', macho(0x0100000C))
            with patch.object(fetch_core, 'ROOT', root), patch('platform.system', return_value='Darwin'), \
                    patch('platform.machine', return_value='arm64'), \
                    patch('urllib.request.urlopen', return_value=io.BytesIO(archive.getvalue())) as download:
                fetch_core.main()
                self.assertIn('/apple/osx/arm64/latest/pcsx_rearmed_libretro.dylib.zip', download.call_args.args[0])
                self.assertEqual((root/'runtime/cores/pcsx_rearmed_libretro.dylib').read_bytes(), macho(0x0100000C))
            with self.assertRaises(ValueError):
                validate(elf(183), 0x0100000C)
            with self.assertRaises(ValueError):
                validate(macho(0x0100000C), 183)

    def test_ps2_core_sits_beside_the_ps1_core(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root/'runtime/cores'
            directory.mkdir(parents=True)
            (directory/'pcsx_rearmed_libretro.so').write_bytes(elf(62))
            (directory/'download.json').write_text(json.dumps(dict(url='old', architecture='x86_64')))
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, 'w') as bundle:
                bundle.writestr('pcsx2_libretro.so', elf(62))
            with patch.object(fetch_core, 'ROOT', root), patch('platform.system', return_value='Linux'), \
                    patch('platform.machine', return_value='x86_64'), \
                    patch('urllib.request.urlopen', return_value=io.BytesIO(archive.getvalue())) as download:
                fetch_core.main(['--console', 'ps2'])
                self.assertIn('/linux/x86_64/latest/pcsx2_libretro.so.zip', download.call_args.args[0])
            self.assertEqual((directory/'pcsx2_libretro.so').read_bytes(), elf(62))
            self.assertEqual((directory/'pcsx_rearmed_libretro.so').read_bytes(), elf(62))
            records = json.loads((directory/'download.json').read_text())
            self.assertEqual(records['pcsx_rearmed']['url'], 'old')
            self.assertEqual(records['pcsx2']['license'], 'GPL-3.0-or-later')
        self.assertEqual(core_filename('Darwin', 'pcsx2'), 'pcsx2_libretro.dylib')

    def test_opengl_only_ps2_core_is_refused_on_macos(self):
        with patch('platform.system', return_value='Darwin'), patch('platform.machine', return_value='arm64'), \
                patch('urllib.request.urlopen') as download:
            with self.assertRaises(SystemExit):
                fetch_core.main(['--console', 'ps2-play'])
            download.assert_not_called()


if __name__ == '__main__':
    unittest.main()
