#!/usr/bin/env python3
"""Fetch the matching official native libretro core for a console, separately from our bundle."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import platform
import struct
import sys
import urllib.request
import zipfile

from systems import PROFILES

ROOT = Path(__file__).resolve().parent
def target(system=None, machine=None):
    system = platform.system() if system is None else system
    machine = (platform.machine() if machine is None else machine).lower()
    if system == 'Darwin':
        if machine in ('arm64', 'aarch64'):
            return 'arm64', 0x0100000C
        raise ValueError('Native macOS installation requires Apple Silicon and an ARM64 Python. Intel/Rosetta macOS Python is not supported by this installer.')
    if system != 'Linux':
        raise ValueError('Automatic installation supports Linux x86-64/ARM64 and Apple Silicon macOS.')
    if machine in ('x86_64', 'amd64'):
        return 'x86_64', 62
    if machine in ('aarch64', 'arm64'):
        return 'aarch64', 183
    raise ValueError(f'Automatic core installation does not support Linux {machine}. Supply a matching libretro core with --core.')


def validate(data, expected):
    if len(data) >= 64 and data[:6] == b'\x7fELF\x02\x01':
        actual = struct.unpack_from('<H', data, 18)[0]
    elif len(data) >= 32 and data[:4] == b'\xcf\xfa\xed\xfe':
        actual = struct.unpack_from('<I', data, 4)[0]
    else:
        raise ValueError('Expected a 64-bit little-endian ELF or Mach-O core')
    if actual != expected:
        raise ValueError(f'Core CPU architecture mismatch (binary CPU ID {actual}, expected {expected})')


SOURCES = {
    'pcsx_rearmed': ('PCSX ReARMed', 'https://github.com/libretro/pcsx_rearmed', 'GPL-2.0-or-later'),
    'pcsx2': ('PCSX2 (ParaLLEl PS2)', 'https://github.com/libretro/ps2', 'GPL-3.0-or-later'),
    'play': ('Play!', 'https://github.com/jpd002/Play-', 'BSD-2-Clause'),
}


def core_filename(system=None, core='pcsx_rearmed'):
    return core + '_libretro' + ('.dylib' if (system or platform.system()) == 'Darwin' else '.so')


def main(argv=()):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--console', choices=sorted(PROFILES), default='ps1')
    profile = PROFILES[parser.parse_args(argv).console]
    title, source, license = SOURCES[profile.core]
    try:
        system = platform.system()
        architecture, machine = target(system)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    if system not in profile.platforms:
        raise SystemExit(f'The {profile.key} profile ({title}) is not supported on {system} yet.')
    filename = core_filename(system, profile.core)
    family = 'apple/osx' if system == 'Darwin' else 'linux'
    url = f'https://buildbot.libretro.com/nightly/{family}/{architecture}/latest/{filename}.zip'
    print(f'Host platform: {"macOS" if system == "Darwin" else system} {architecture}')
    directory = ROOT / 'runtime/cores'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    if path.exists():
        try:
            validate(path.read_bytes(), machine)
        except ValueError:
            print('Existing core is incompatible or corrupt; downloading the matching core before replacing it.')
        else:
            print(f'Keeping existing core: {path}')
            return
    with urllib.request.urlopen(url, timeout=60) as response:
        archive = response.read(32*1024*1024+1)
    if len(archive) > 32*1024*1024:
        raise SystemExit('Core archive exceeds the download limit')
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        data = bundle.read(filename)
    try:
        validate(data, machine)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_bytes(data)
    temporary.replace(path)
    record = dict(url=url, system=system, architecture=architecture, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                  source=source, license=license)
    records = directory/'download.json'
    try:
        downloads = json.loads(records.read_text())
    except (OSError, ValueError):
        downloads = {}
    if 'url' in downloads:  # one-core record from earlier versions
        downloads = {'pcsx_rearmed': downloads}
    downloads[profile.core] = record
    records.write_text(json.dumps(downloads, indent=2)+'\n')
    print(f'Installed {title} ({len(data):,} bytes). Core hash recorded in runtime/cores/download.json.')


if __name__ == '__main__':
    main(sys.argv[1:])
