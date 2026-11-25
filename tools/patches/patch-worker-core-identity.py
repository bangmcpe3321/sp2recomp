#!/usr/bin/env python3
"""Honor worker affinity and report the kernel's guest core in nn::os HLE."""
import argparse, os
from pathlib import Path

REPLACEMENTS = [
    (b'uint64_t g_next_thread_id = 1;', b'std::atomic<uint64_t> g_next_thread_id{1}; // PATCH-WORKER-CORE-IDENTITY'),
    (b'ctx = kernel_alloc(0x40, 8);', b'ctx = kernel_alloc(0x200, 8); // PATCH-WORKER-CORE-IDENTITY: SDK ThreadType handle field'),
    (b'        st<int32_t>(ctx + 0x10, 0);', b'''        KThread* current = self_thread();
        st<int32_t>(ctx + 0x10, current ? std::max(current->core, 0) : 0);
        st<uint32_t>(ctx + 0x1b8, current ? current->handle : 0xffff8000u); // PATCH-WORKER-CORE-IDENTITY'''),
    (b'void get_current_core_number(CPU& c) { c.x[0] = uint32_t(ld<int32_t>(thread_ctx() + 0x10)); }', b'''void get_current_core_number(CPU& c) {
    // PATCH-WORKER-CORE-IDENTITY: gsys scratch cursors are indexed by this guest core.
    KThread* current = self_thread();
    c.x[0] = current ? uint32_t(std::max(current->core, 0)) : 0;
    static thread_local bool reported = false;
    if (!reported) {
        reported = true;
        log("workers: thread %llx reports guest core %u", current ? (unsigned long long)current->id : 0ull, unsigned(c.x[0]));
    }
}'''),
    (b'void set_thread_core_mask(CPU& c) { c.x[0] = 0; }  // always accept', b'''void set_thread_core_mask(CPU& c) {
    // PATCH-WORKER-CORE-IDENTITY: the US 1.0.0 SDK reads ThreadType.handle at +0x1b8.
    // Synthetic current-thread tokens expose that same field; real SDK objects already have it.
    uint32_t handle = c.x[0] ? ld<uint32_t>(c.x[0] + 0x1b8) : 0;
    int32_t ideal = int32_t(c.x[1]);
    uint64_t mask = c.x[2];
    c.x[0] = nx::set_thread_core_mask(handle, ideal, mask);
    log("workers: affinity handle %x ideal %d mask %llx result %x", handle, int(ideal), (unsigned long long)mask, unsigned(c.x[0]));
}'''),
]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path(os.environ.get('SP2PORT', str(Path.home() / 'sp2port'))))
    p.add_argument('--restore', action='store_true')
    p.add_argument('--check', action='store_true')
    a = p.parse_args()
    path = a.root / 'runtime/src/hle_os.cpp'
    data = path.read_bytes()
    sdk = (a.root / 'gen/sdk/code_011.cpp').read_bytes()
    if b'c.x[1] + 0x1b8ull; c.x[0] = uint32_t(nx::ld<uint32_t>(a));' not in sdk:
        raise SystemExit('Unsupported SDK thread handle layout; no files changed')
    for old, new in REPLACEMENTS:
        if data.count(new) == 1:
            data = data.replace(new, old if a.restore else new, 1)
        elif data.count(old) == 1:
            data = data.replace(old, old if a.restore else new, 1)
        else:
            raise SystemExit('Worker core anchor mismatch; no files changed')
    if a.check:
        print('Preflight passed'); return
    path.write_bytes(data)
    print('Restored' if a.restore else 'Applied; rebuild hle_os.cpp')

if __name__ == '__main__': main()
