"""Per-console system profiles: core, BIOS, controllers and default core options."""
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Profile:
    key: str
    name: str
    core: str  # libretro core basename on the official buildbot
    content: str  # --disc help text
    max_players: int
    default_players: int
    variables: dict = field(default_factory=dict)
    multitap: str = ''  # core option that selects the multitap, if the console has one
    multitaps: tuple = ()
    bios: str = ''  # directory inside runtime/system that must hold a BIOS dump
    bios_hint: str = ''
    bios_required: bool = False
    platforms: tuple = ('Linux', 'Darwin')
    pad: str = 'pad'
    analog: bool = False  # the pad has sticks; the page then sends them
    multitap_core: str = ''  # a core build that reads the multitap slots, when the usual one does not

    def options(self, multitap=None, overrides=()):
        """Core option values for this session, with KEY=VALUE overrides applied last."""
        values = {key: value.encode() for key, value in self.variables.items()}
        if self.multitap:
            values[self.multitap] = (multitap or self.multitaps[0]).encode()
        for override in overrides:
            key, _, value = override.partition('=')
            values[key] = value.encode()
        return values

    def missing_bios(self, system):
        """Return a message when the console's BIOS directory has no dump, else None."""
        if not self.bios:
            return None
        directory = Path(system)/self.bios
        if directory.is_dir() and any(p.is_file() and not p.name.startswith('.') for p in directory.iterdir()):
            return None
        return f'No {self.name} BIOS found in {directory}. {self.bios_hint}'


PROFILES = {profile.key: profile for profile in (
    Profile(
        key='ps1', name='PS1', core='pcsx_rearmed', pad='PS1 pad',
        content='Path to the original CUE with all referenced BIN tracks',
        max_players=4, default_players=4,
        variables={
            'pcsx_rearmed_frameskip_type': 'disabled',
            'pcsx_rearmed_neon_enhancement_enable': 'disabled',
            'pcsx_rearmed_dithering': 'enabled',
            'pcsx_rearmed_bios': 'auto',
        },
        multitap='pcsx_rearmed_multitap', multitaps=('port 1', 'disabled', 'port 2', 'ports 1 and 2'),
    ),
    # PCSX2 (the libretro "ParaLLEl PS2" build). It refuses to start without a
    # BIOS. The software renderer draws on the CPU and returns a plain
    # framebuffer, so it needs no GPU and runs on both host platforms.
    Profile(
        key='ps2', name='PS2', core='pcsx2', pad='PS2 pad', analog=True,
        content='Path to a PS2 disc image (ISO, CHD, CSO or CUE) or a homebrew ELF',
        max_players=4, default_players=2,
        variables={
            'pcsx2_renderer': 'Software (SW)',
            'pcsx2_fastboot': 'enabled',
        },
        # The official build reads two pads and has no multitap; tools/build-pcsx2-multitap.sh adds it.
        multitap='pcsx2_multitap', multitaps=('disabled', 'port 1', 'port 2', 'ports 1 and 2'),
        multitap_core='pcsx2_multitap',
        bios='pcsx2/bios', bios_required=True,
        bios_hint='Copy a dump of your own console BIOS there (for example SCPH-70012.bin).',
    ),
    # Play! boots homebrew ELFs without a BIOS (built-in HLE), but draws only
    # with OpenGL. The host gives it an offscreen EGL context, so Linux only.
    Profile(
        key='ps2-play', name='PS2', core='play', pad='PS2 pad', analog=True,
        content='Path to a homebrew PS2 ELF or a PS2 disc image',
        max_players=2, default_players=2,
        platforms=('Linux',),
    ),
)}
