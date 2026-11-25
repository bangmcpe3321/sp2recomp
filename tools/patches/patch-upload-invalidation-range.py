#!/usr/bin/env python3
"""Limit upload-cache invalidation searches using the largest copied range in this submit."""
from pathlib import Path
import argparse,os
CHANGES=[
 (b'#include <array>\n',b'#include <algorithm> // PATCH-UPLOAD-INVALIDATION-RANGE\n#include <array>\n'),
 (b'uint64_t g_saved = 0, g_copied = 0;',b'''uint64_t g_saved = 0, g_copied = 0;
uint64_t g_largest_copy = 0; // PATCH-UPLOAD-INVALIDATION-RANGE: conservative until submit reset
uint64_t g_invalidate_calls = 0, g_invalidate_visits = 0;'''),
 (b'    g_copies[p] = {size, padded, u};',b'''    g_copies[p] = {size, padded, u};
    g_largest_copy = std::max(g_largest_copy, size); // PATCH-UPLOAD-INVALIDATION-RANGE'''),
 (b'void dedup_reset() { g_copies.clear(), g_generation++; }',b'void dedup_reset() { g_copies.clear(), g_generation++; g_largest_copy=0; } // PATCH-UPLOAD-INVALIDATION-RANGE'),
 (b'''void dedup_invalidate(const uint8_t* p, uint64_t size) {
    // Entries starting before p may still reach into it: look back over the few that can.
    auto it = g_copies.lower_bound(p + size);
    while (it != g_copies.begin()) {
        --it;
        if (it->first + it->second.size <= p) {
            if (p - it->first > (64ll << 20)) break;  // nothing larger than 64 MB is copied
            continue;
        }
        if (Front& f = front_of(it->first); f.p == it->first) f.generation = 0;
        it = g_copies.erase(it);
    }
}''',b'''void dedup_invalidate(const uint8_t* p, uint64_t size) {
    // PATCH-UPLOAD-INVALIDATION-RANGE: an entry starting more than the largest
    // cached copy before p cannot overlap. The bound only grows during a submit.
    if(!p || !size || g_copies.empty())return;
    const uintptr_t begin=reinterpret_cast<uintptr_t>(p);
    const uintptr_t first=begin>g_largest_copy ? begin-g_largest_copy : 0;
    const bool overflow=size>UINTPTR_MAX-begin;
    auto last=overflow ? g_copies.end() : g_copies.lower_bound(reinterpret_cast<const uint8_t*>(begin+size));
    auto it=g_copies.lower_bound(reinterpret_cast<const uint8_t*>(first));
    ++g_invalidate_calls;
    while(it!=last) {
        ++g_invalidate_visits;
        const uintptr_t address=reinterpret_cast<uintptr_t>(it->first);
        if(address<begin && it->second.size<=begin-address) {++it;continue;}
        if(Front& f=front_of(it->first);f.p==it->first)f.generation=0;
        it=g_copies.erase(it);
    }
}'''),
 (b'    g_copied = g_saved = 0;',b'''    if(g_invalidate_calls && std::getenv("NX_RENDER_STATS"))
        log("nvn: upload invalidation: %llu updates, %llu cached ranges examined", (unsigned long long)g_invalidate_calls, (unsigned long long)g_invalidate_visits);
    g_invalidate_calls=g_invalidate_visits=0; // PATCH-UPLOAD-INVALIDATION-RANGE
    g_copied = g_saved = 0;'''),
]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(os.environ.get('SP2PORT',str(Path.home()/'sp2port'))));p.add_argument('--restore',action='store_true');p.add_argument('--check',action='store_true');a=p.parse_args()
 path=a.root/'runtime/src/nvn/nvn_dedup.cpp';data=path.read_bytes()
 for old,new in CHANGES:
  if data.count(new)==1:data=data.replace(new,old if a.restore else new,1)
  elif data.count(old)==1:data=data.replace(old,old if a.restore else new,1)
  else:raise SystemExit('Upload invalidation anchor mismatch; no files changed')
 if a.check:print('Preflight passed');return
 path.write_bytes(data);print('Restored' if a.restore else 'Applied; rebuild nvn_dedup.cpp')
if __name__=='__main__':main()
