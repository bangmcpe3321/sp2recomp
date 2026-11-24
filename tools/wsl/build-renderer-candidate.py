#!/usr/bin/env python3
"""Build an isolated Windows renderer candidate, retaining all other linked objects."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path.home()/'sp2port')
    p.add_argument('--manifest', type=Path, help='Exact preceding build manifest with an objects list')
    p.add_argument('--objects', type=Path, help='Baseline object directory when no manifest is supplied')
    p.add_argument('--out', type=Path, required=True, help='New, empty output directory')
    p.add_argument('--jobs', type=int, choices=range(1, 9), default=2)
    p.add_argument('--optimization', choices=['O1', 'O2'], default='O2')
    a = p.parse_args()
    root = a.root.resolve()
    out = a.out.resolve()
    if out.exists():
        p.error('Output directory already exists; choose a fresh path')
    if a.manifest and a.objects:
        p.error('Choose --manifest or --objects')
    base = json.loads(a.manifest.read_text()) if a.manifest else {}
    objects = ([Path(x).resolve() for x in base['objects']] if a.manifest else
               sorted((a.objects or root/'obj-win').resolve().rglob('*.o')))
    if not objects or len(objects) != len(set(objects)) or not all(x.is_file() for x in objects):
        p.error('Missing, empty or duplicate baseline objects')
    before = {str(x): digest(x) for x in objects}
    if base.get('object_sha256') and before != base['object_sha256']:
        p.error('Baseline object hashes differ from manifest')
    sources = {}
    for obj in objects:
        if not obj.stem.startswith('nvn_'):
            continue
        if obj.stem in sources:
            p.error('Ambiguous renderer object name: '+obj.name)
        source = root/'runtime/src/nvn'/f'{obj.stem}.cpp'
        if not source.is_file():
            p.error('Missing renderer source: '+str(source))
        sources[obj.stem] = source
    if not sources:
        p.error('No renderer objects found')
    compiler = Path.home()/'llvm-mingw/bin/x86_64-w64-mingw32-clang++'
    if not compiler.is_file():
        p.error('LLVM-MinGW compiler not found: '+str(compiler))
    headers = {str(x.relative_to(root)): digest(x) for folder in ['runtime/src', 'runtime/include']
               for x in (root/folder).rglob('*.h')}
    out.mkdir(parents=True)

    def build(item):
        name, source = item
        output = out/f'{name}.o'
        args = [str(compiler), '-std=c++20', '-c', '-'+a.optimization, '-w',
                '-DVK_USE_PLATFORM_WIN32_KHR', '-D_WIN32_WINNT=0x0A00', '-DWINVER=0x0A00',
                '-I', 'runtime/include', '-I', 'runtime/src',
                '-I', str(Path.home()/'vkheaders/include'), str(source), '-o', str(output)]
        original = digest(source)
        with (out/f'{name}.log').open('w') as log:
            subprocess.run(args, cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True)
        if digest(source) != original:
            raise RuntimeError('Source changed during build: '+str(source))
        print('Built '+name, flush=True)
        return name, {'source_sha256': original, 'object_sha256': digest(output), 'command': args}

    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        changes = dict(pool.map(build, sources.items()))
    if before != {str(x): digest(x) for x in objects}:
        raise RuntimeError('Baseline objects changed during build; refusing to link')
    if any(digest(root/x) != value for x, value in headers.items()):
        raise RuntimeError('Headers changed during build; refusing to link')
    linked = [out/x.name if x.stem in changes else x for x in objects]
    exe = out/'sp2-renderer-performance.exe'
    command = [str(compiler), '-o', str(exe), *map(str, linked), '-lxaudio2_8', '-lxinput',
               '-ldbghelp', '-lole32', '-loleaut32', '-luuid', '-luser32', '-lgdi32', '-lshell32',
               '-lshlwapi', '-ladvapi32', '-lws2_32', '-lwinmm', '-lversion', '-static']
    with (out/'link.log').open('w') as log:
        subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True)
    result = {'baseline_sha256': base.get('candidate_sha256'), 'baseline_objects_sha256': before,
              'candidate_sha256': digest(exe), 'changed_units': changes, 'headers_sha256': headers,
              'objects': list(map(str, linked)), 'object_sha256': {str(x): digest(x) for x in linked},
              'link_command': command}
    (out/'manifest.json').write_text(json.dumps(result, indent=2)+'\n')
    print(f'DONE: {exe}\nSHA-256: {result["candidate_sha256"]}')


if __name__ == '__main__':
    main()
