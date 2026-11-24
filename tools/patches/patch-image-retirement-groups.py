#!/usr/bin/env python3
"""Retire held descriptor images by their existing contiguous storage groups."""
import argparse,os
from pathlib import Path

OLD='''        std::map<uint64_t, uint64_t> latest_write;
        for (const auto& entry : held)
            latest_write[entry.first.memory] = std::max(latest_write[entry.first.memory], entry.second.image->rendered_at);
        for (auto it = held.begin(); it != held.end();) {
            if (cached_image_expired(*it->second.image, it->second.used, frame, latest_write[it->first.memory])) {
                retire_image(std::move(it->second.image));
                it = held.erase(it);
            } else {
                ++it;
            }
        }'''
NEW='''        // PATCH-IMAGE-RETIREMENT-GROUPS: StorageKey orders memory first. Compute
        // each address's latest write before erasing that contiguous group; avoid
        // allocating a second map of every backing address once per frame.
        for (auto first = held.begin(); first != held.end();) {
            const uint64_t memory = first->first.memory;
            uint64_t latest_write = 0;
            auto last = first;
            while (last != held.end() && last->first.memory == memory) {
                latest_write = std::max(latest_write, last->second.image->rendered_at);
                ++last;
            }
            while (first != last) {
                if (cached_image_expired(*first->second.image, first->second.used, frame, latest_write)) {
                    retire_image(std::move(first->second.image));
                    first = held.erase(first);
                } else {
                    ++first;
                }
            }
        }'''

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path(os.environ.get('SP2PORT',str(Path.home()/'sp2port'))))
    p.add_argument('--check',action='store_true');p.add_argument('--restore',action='store_true');a=p.parse_args()
    path=a.root/'runtime/src/nvn/nvn_image.cpp';data=path.read_bytes()
    matches=[]
    for newline in [b'\n',b'\r\n']:
        old=OLD.encode().replace(b'\n',newline);new=NEW.encode().replace(b'\n',newline)
        if data.count(new)==1:matches.append((new,old if a.restore else new))
        elif data.count(old)==1:matches.append((old,old if a.restore else new))
    if len(matches)!=1:raise SystemExit('Image retirement anchor mismatch; no files changed')
    before,after=matches[0];data=data.replace(before,after,1)
    if a.check:print('Preflight passed');return
    path.write_bytes(data);print('Restored' if a.restore else 'Applied; rebuild nvn_image.cpp')
if __name__=='__main__':main()
