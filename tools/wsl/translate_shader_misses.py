#!/usr/bin/env python3
"""Private shader-cache updates for wsl-translate-shaders.sh (no game files shipped)."""
import csv
import fcntl
import hashlib
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def executable(value):
    found = shutil.which(value)
    if not found:
        raise RuntimeError(f'Executable not found: {value}')
    return found


def validator_path(path, validator):
    # A Windows SDK executable needs Windows paths even when invoked from WSL.
    if validator.lower().endswith('.exe') and sys.platform != 'win32':
        return subprocess.check_output(['wslpath', '-w', str(path)], text=True).strip()
    return str(path)


def records(raw):
    text = raw.decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text), delimiter='\t')
    if not reader.fieldnames or not {'hash', 'status', 'resources', 'spv_bytes'} <= set(reader.fieldnames):
        raise RuntimeError('Missing required columns in results.tsv')
    return reader.fieldnames, list(reader)


def main():
    misses, cache, run = (Path(p).resolve() for p in sys.argv[1:])
    if not misses.is_dir():
        raise RuntimeError(f'No shader-miss directory: {misses}')
    pending = []
    for code in sorted(misses.glob('code_*.bin')):
        shader_hash = code.stem.removeprefix('code_')
        if not re.fullmatch('[0-9a-f]{16}', shader_hash):
            raise RuntimeError(f'Unexpected shader filename: {code.name}')
        if (cache / f'{shader_hash}.spv').exists():
            continue  # Existing cache entries are never replaced by this workflow.
        control = misses / f'ctrl_{shader_hash}.bin'
        if not control.is_file():
            raise RuntimeError(f'Missing control pair: {control}')
        if not hashlib.sha1(code.read_bytes()).hexdigest().startswith(shader_hash):
            raise RuntimeError(f'Code hash does not match filename: {code}')
        pending.append((shader_hash, code, control))
    if not pending:
        print('No missing stages to translate; existing cache preserved.')
        return

    dotnet = executable(str(Path(os.environ.get('DOTNET_SDK', str(Path.home() / 'dotnet-sdk'))) / 'dotnet'))
    port = Path(os.environ.get('SP2PORT', str(Path.home() / 'sp2port'))).resolve()
    harness = Path(os.environ.get('SPIRV_HARNESS', str(port / 'private/build/spirv_harness/bin/Release/net10.0/spirv_harness.dll'))).resolve()
    if not harness.is_file():
        raise RuntimeError(f'No translation harness: {harness} (build tools/maxwell/spirv_harness)')
    validator = executable(os.environ.get('SPIRV_VAL') or shutil.which('spirv-val') or shutil.which('spirv-val.exe') or 'spirv-val')
    target = 'vulkan1.2'
    inputs, output = run / 'inputs', run / 'output'
    inputs.mkdir()
    for shader_hash, code, control in pending:
        shutil.copyfile(code, inputs / code.name)
        shutil.copyfile(control, inputs / control.name)
    environment = os.environ.copy()
    environment.update(DOTNET_SYSTEM_GLOBALIZATION_INVARIANT='1', DOTNET_CLI_TELEMETRY_OPTOUT='1')
    # Harness validation defaults to a machine-specific path; perform required validation below,
    # including WSL-to-Windows path conversion when SPIRV_VAL selects a Windows SDK executable.
    subprocess.run([dotnet, str(harness), '--batch', str(inputs), '--out', str(output),
                    '--jobs', '4', '--no-val'], env=environment, check=True)
    header, translated = records((output / 'results.tsv').read_bytes())
    by_hash = {}
    for row in translated:
        shader_hash = row['hash']
        if shader_hash in by_hash:
            raise RuntimeError(f'Duplicate translation record: {shader_hash}')
        by_hash[shader_hash] = row
    if set(by_hash) != {h for h, _, _ in pending}:
        raise RuntimeError('Translation records do not match requested missing stages')
    for shader_hash, _, _ in pending:
        row = by_hash[shader_hash]
        path = output / f'{shader_hash}.spv'
        if row['status'] not in ('ok', 'ok-retry') or not path.is_file():
            raise RuntimeError(f'Translation failed for {shader_hash}: {row["status"]}')
        if path.stat().st_size != int(row['spv_bytes']):
            raise RuntimeError(f'SPIR-V length differs from translation record: {shader_hash}')
        subprocess.run([validator, '--target-env', target, validator_path(path, validator)], check=True)

    cache.mkdir(parents=True, exist_ok=True)
    # Serialize this tool's writers, recheck concurrent additions, and preserve prior TSV bytes.
    with (cache / '.translation.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        metadata = cache / 'results.tsv'
        previous = metadata.read_bytes() if metadata.exists() else b''
        if previous:
            old_header, _ = records(previous)
            if old_header != header:
                raise RuntimeError('Cache metadata columns differ from the harness; no files staged')
        additions = []
        for shader_hash, _, _ in pending:
            destination = cache / f'{shader_hash}.spv'
            if destination.exists():
                continue
            # Link an already complete temporary file without overwriting a concurrent entry.
            fd, temporary = tempfile.mkstemp(prefix='.shader-', suffix='.tmp', dir=cache)
            try:
                with os.fdopen(fd, 'wb') as target_file:
                    target_file.write((output / destination.name).read_bytes())
                    target_file.flush()
                    os.fsync(target_file.fileno())
                try:
                    os.link(temporary, destination)
                except FileExistsError:
                    continue
                additions.append(by_hash[shader_hash])
            finally:
                Path(temporary).unlink(missing_ok=True)
        if additions:
            stream = io.StringIO(newline='')
            writer = csv.DictWriter(stream, fieldnames=header, delimiter='\t', lineterminator='\n')
            if not previous:
                writer.writeheader()
            writer.writerows(additions)
            updated = previous + (b'\n' if previous and not previous.endswith(b'\n') else b'') + stream.getvalue().encode()
            fd, temporary = tempfile.mkstemp(prefix='.results-', suffix='.tmp', dir=cache)
            try:
                with os.fdopen(fd, 'wb') as target_file:
                    target_file.write(updated)
                    target_file.flush()
                    os.fsync(target_file.fileno())
                os.replace(temporary, metadata)
            finally:
                Path(temporary).unlink(missing_ok=True)
    print(f'Validated {len(pending)} stages for {target}; added {len(additions)} new cache entries.')
    print('Restart the game to load the new stages and resource records.')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'Shader translation stopped: {error}')
