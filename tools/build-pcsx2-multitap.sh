#!/usr/bin/env bash
# Build the PCSX2 libretro core with patches/pcsx2-multitap.patch, so that a
# PS2 room seats four players. The official build reads two pads only.
# Output: runtime/cores/pcsx2_multitap_libretro.dylib (.so on Linux).
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
root=$PWD
commit=c31b36783e61f8c42d04ed7af147820a29439e6c  # libretro/ps2, the patch applies here
source=runtime/build/ps2
tools=runtime/build/tools
jobs=${JOBS:-$(( $(getconf _NPROCESSORS_ONLN) / 2 ))}

if [[ ! -d $source/.git ]]; then
  git clone --filter=blob:none https://github.com/libretro/ps2.git "$source"
fi
git -C "$source" fetch --quiet origin "$commit"
git -C "$source" checkout --quiet --force "$commit"
git -C "$source" apply "$root/patches/pcsx2-multitap.patch"

if [[ ! -x $tools/bin/cmake ]]; then
  "$root/.venv/bin/python" -m venv "$tools"
  "$tools/bin/python" -m pip install --quiet cmake ninja
fi
export PATH=$root/$tools/bin:$PATH
flags=(-DCMAKE_BUILD_TYPE=Release -DUSE_VULKAN=OFF)
[[ $(uname) == Darwin ]] && flags+=(-DCMAKE_OSX_ARCHITECTURES=arm64)
# Low priority: a host on this machine can keep running during the build.
nice -n 19 cmake -S "$source" -B "$source/build" -G Ninja "${flags[@]}"
nice -n 19 ninja -C "$source/build" -j "$jobs"

suffix=$([[ $(uname) == Darwin ]] && echo dylib || echo so)
built=$(find "$source/build" -name "pcsx2_libretro.$suffix" -type f | head -1)
[[ -n $built ]] || { echo "The build made no pcsx2_libretro.$suffix" >&2; exit 1; }
cp "$built" "runtime/cores/pcsx2_multitap_libretro.$suffix"
echo "Built runtime/cores/pcsx2_multitap_libretro.$suffix"
