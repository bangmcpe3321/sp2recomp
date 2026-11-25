#!/usr/bin/env python3
"""Bound snapshot image searches to the requested guest storage address."""
from pathlib import Path
import argparse, os

ANCHOR=b'std::map<StorageKey, std::weak_ptr<GpuImage>> g_live_images;\n'
HELPER=b'''
// PATCH-IMAGE-STORAGE-LOOKUP: StorageKey orders memory first. Avoid visiting every
// historical resolution and every expired weak entry for a single storage lookup.
static auto images_at_memory(uint64_t memory) {
    auto first = g_live_images.lower_bound(StorageKey{memory});
    auto last = memory == UINT64_MAX ? g_live_images.end() : g_live_images.lower_bound(StorageKey{memory + 1});
    return std::pair{first, last};
}
'''
OLD=b'        for (auto& e : g_live_images) {\n'
NEW=b'''        auto [first, last] = images_at_memory(t->memory); // PATCH-IMAGE-STORAGE-LOOKUP
        for (auto it = first; it != last; ++it) {
            auto& e = *it;
'''
REGIONS=[(b'    if (any_format && snapshot', b'    // PATCH-SNAPSHOT-SHARE-MEM:'),
         (b'    if (share_mem && share && snapshot', b'    if (own) return own;')]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path(os.environ.get('SP2PORT',str(Path.home()/'sp2port'))))
    p.add_argument('--restore',action='store_true');p.add_argument('--check',action='store_true');a=p.parse_args()
    path=a.root/'runtime/src/nvn/nvn_image.cpp';data=path.read_bytes()
    if data.count(ANCHOR)!=1:raise SystemExit('Image registry anchor mismatch; no files changed')
    if HELPER in data:data=data.replace(HELPER,b'',1)
    for start,end in REGIONS:
        i=data.index(start);j=data.index(end,i);body=data[i:j]
        if body.count(NEW)==1:body=body.replace(NEW,OLD if a.restore else NEW,1)
        elif body.count(OLD)==1:body=body.replace(OLD,OLD if a.restore else NEW,1)
        else:raise SystemExit('Storage lookup anchor mismatch; no files changed')
        data=data[:i]+body+data[j:]
    if not a.restore:data=data.replace(ANCHOR,ANCHOR+HELPER,1)
    if a.check:print('Preflight passed');return
    path.write_bytes(data);print('Restored' if a.restore else 'Applied; rebuild nvn_image.cpp')

if __name__=='__main__':main()
