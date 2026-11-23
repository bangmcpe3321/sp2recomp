"""Exercise the shader-miss updater with isolated fake translator and validator tools (Linux/WSL)."""
from pathlib import Path
import hashlib
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'tools/wsl/wsl-translate-shaders.sh'

with tempfile.TemporaryDirectory(prefix='sp2 shader workflow ') as temporary:
    root = Path(temporary)
    misses, cache, sdk, scratch = (root / n for n in ('misses', 'cache', 'sdk', 'scratch'))
    for directory in (misses, cache, sdk, scratch):
        directory.mkdir()
    harness = root / 'harness.dll'
    harness.write_text('fake harness marker')
    dotnet = sdk / 'dotnet'
    dotnet.write_text('''#!/usr/bin/env python3
from pathlib import Path
import csv, os, sys
args=sys.argv
src=Path(args[args.index('--batch')+1]);out=Path(args[args.index('--out')+1]);out.mkdir()
with (out/'results.tsv').open('w',newline='') as f:
 w=csv.writer(f,delimiter='\\t',lineterminator='\\n');w.writerow(['hash','status','resources','spv_bytes'])
 for code in sorted(src.glob('code_*.bin')):
  h=code.stem[5:];data=b'INVALID' if os.environ.get('FAKE_INVALID')==h else b'VALID shader'
  (out/(h+'.spv')).write_bytes(data);w.writerow([h,'ok','cb1=s0b20',len(data)])
''')
    dotnet.chmod(0o755)
    validator = root / 'spirv-val'
    validator.write_text('''#!/usr/bin/env python3
from pathlib import Path
import sys
assert sys.argv[1:3]==['--target-env','vulkan1.2']
raise SystemExit(0 if Path(sys.argv[3]).read_bytes().startswith(b'VALID') else 1)
''')
    validator.chmod(0o755)
    env = dict(os.environ, DOTNET_SDK=str(sdk), SPIRV_HARNESS=str(harness),
               SPIRV_VAL=str(validator), TMPDIR=str(scratch))

    def pair(data):
        h = hashlib.sha1(data).hexdigest()[:16]
        (misses / f'code_{h}.bin').write_bytes(data)
        (misses / f'ctrl_{h}.bin').write_bytes(b'control')
        return h

    def run(ok=True, **extra):
        p = subprocess.run(['bash', str(SCRIPT), str(misses), str(cache)],
                           env=dict(env, **extra), capture_output=True, text=True)
        assert (p.returncode == 0) == ok, (p.stdout, p.stderr)
        assert not list(scratch.iterdir()), 'temporary run directories leaked'
        return p

    old_hash = pair(b'existing shader')
    (cache / f'{old_hash}.spv').write_bytes(b'VALID old cache')
    previous = b'hash\tstatus\tresources\tspv_bytes\n' + f'{old_hash}\tok\tcb3=s0b22\t15\n'.encode()
    (cache / 'results.tsv').write_bytes(previous)
    new_hash = pair(b'new shader')
    run()
    assert (cache / f'{old_hash}.spv').read_bytes() == b'VALID old cache'
    metadata = (cache / 'results.tsv').read_bytes()
    assert metadata.startswith(previous) and metadata.count(new_hash.encode()) == 1
    snapshot = {p.name: p.read_bytes() for p in cache.iterdir()}
    run()
    assert snapshot == {p.name: p.read_bytes() for p in cache.iterdir()}, 'repeated run changed cache'

    invalid = pair(b'invalid shader')
    run(ok=False, FAKE_INVALID=invalid)
    assert snapshot == {p.name: p.read_bytes() for p in cache.iterdir()}, 'invalid output changed cache'
    (misses / f'ctrl_{invalid}.bin').unlink()
    run(ok=False)
    assert snapshot == {p.name: p.read_bytes() for p in cache.iterdir()}, 'missing pair changed cache'
    (misses / f'code_{invalid}.bin').write_bytes(b'wrong filename hash')
    (misses / f'ctrl_{invalid}.bin').write_bytes(b'control')
    run(ok=False)
    assert snapshot == {p.name: p.read_bytes() for p in cache.iterdir()}, 'hash mismatch changed cache'
    (misses / f'code_{invalid}.bin').unlink()
    (misses / f'ctrl_{invalid}.bin').unlink()
    another = pair(b'another shader')
    (cache / 'results.tsv').write_bytes(b'hash\tstatus\tresources\n')
    run(ok=False)
    assert not (cache / f'{another}.spv').exists(), 'metadata mismatch staged a shader'
    assert (cache / 'results.tsv').read_bytes() == b'hash\tstatus\tresources\n'

print('PASS isolated shader workflow: validated additions, preserved cache/metadata, idempotence, invalid-output and input refusals, temporary cleanup')
