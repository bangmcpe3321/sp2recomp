#!/usr/bin/env python3
"""Avoid repeated descriptor-image tree lookups within a presented frame."""
import argparse
import os
from pathlib import Path

OLD = '''    static std::map<StorageKey, HeldImage> held;
    static uint64_t last_frame = UINT64_MAX;'''
NEW = '''    static std::map<StorageKey, HeldImage> held;
    // PATCH-IMAGE-HELD-FRONT: map nodes stay stable until frame retirement.
    // Clear these non-owning pointers before erasing any node below.
    struct HeldHit { StorageKey key{}; HeldImage* entry = nullptr; };
    static HeldHit hits[512];
    static uint64_t last_frame = UINT64_MAX;'''
PRUNE = '''    if (frame != last_frame) {
        std::map<uint64_t, uint64_t> latest_write;'''
PRUNE_NEW = '''    if (frame != last_frame) {
        for (auto& hit : hits) hit.entry = nullptr;
        std::map<uint64_t, uint64_t> latest_write;'''
LOOKUP = '''    if (auto it = held.find(key); it != held.end()) {
        it->second.used = frame;
        return it->second.image.get();
    }
    GpuImage* image = image_of_impl(guest);
    if (image && t->image) held.emplace(key, HeldImage{std::move(t->image), frame});
    return image;'''
LOOKUP_NEW = '''    uint64_t hash = key.memory ^ (key.memory >> 17) ^ uint64_t(key.format) * 0x9e3779b1u ^
                    uint64_t(key.width) * 31 ^ uint64_t(key.height) * 65537 ^
                    uint64_t(key.depth) * 257 ^ uint64_t(key.levels) * 17 ^
                    uint64_t(key.target) * 7 ^ uint64_t(key.samples) * 3 ^ key.swizzle;
    HeldHit& hit = hits[(hash ^ (hash >> 9)) & 511];
    if (hit.entry && !(key < hit.key) && !(hit.key < key)) {
        hit.entry->used = frame;
        return hit.entry->image.get();
    }
    if (auto it = held.find(key); it != held.end()) {
        hit = {key, &it->second};
        it->second.used = frame;
        return it->second.image.get();
    }
    GpuImage* image = image_of_impl(guest);
    if (image && t->image) {
        auto [it, inserted] = held.emplace(key, HeldImage{std::move(t->image), frame});
        hit = {key, &it->second};
    }
    return image;'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path(os.environ.get('SP2PORT', str(Path.home() / 'sp2port'))))
    p.add_argument('--check', action='store_true')
    p.add_argument('--restore', action='store_true')
    a = p.parse_args()
    path = a.root / 'runtime/src/nvn/nvn_image.cpp'
    data = path.read_text()
    for old, new in [(OLD, NEW), (PRUNE, PRUNE_NEW), (LOOKUP, LOOKUP_NEW)]:
        if data.count(new) == 1:
            data = data.replace(new, old if a.restore else new, 1)
        elif data.count(old) == 1:
            data = data.replace(old, old if a.restore else new, 1)
        else:
            raise SystemExit('Descriptor-image cache anchor mismatch; no files changed')
    if a.check:
        print('Preflight passed')
        return
    path.write_text(data)
    print('Restored' if a.restore else 'Applied; rebuild nvn_image.cpp')


if __name__ == '__main__':
    main()
