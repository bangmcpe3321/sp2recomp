#!/usr/bin/env python3
"""Report the SDK's font error when a cached SFNT pointer is null or the sentinel 1."""
import argparse,os
from pathlib import Path
FUNCTION=b'void sdk_001A2A1C(nx::CPU& NX_RESTRICT c) {\n'
OLD=b'''    { uint64_t a = c.x[8] + 0x38ull; c.x[8] = uint64_t(nx::ld<uint64_t>(a)); } // ldr x8, [x8, #0x38]
    { uint64_t a = c.x[8] + 0x30ull; auto v0 = nx::ld<uint64_t>(a + 0); auto v1 = nx::ld<uint64_t>(a + 8); c.x[10] = uint64_t(v0); c.x[9] = uint64_t(v1); } // ldp x10, x9, [x8, #0x30]
'''
NEW=OLD.splitlines(keepends=True)[0]+b'''    // PATCH-FSS-SFNT-NOT-READY: the shared font slot changed after scale_font_ttf checked it.
    // The observed unavailable sentinel is 1 (the load at +0x30 faulted at address 0x31).
    // Use check_sfnt's existing 0x130 error, including the font context status read by its caller.
    if (c.x[8] <= 1) {
        nx::st<uint32_t>(c.x[0] + 0x48ull, 0x130u);
        c.x[0] = 0x130u;
        goto L_1A2B00;
    }
'''+OLD.splitlines(keepends=True)[1]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(os.environ.get('SP2PORT',str(Path.home()/'sp2port'))));p.add_argument('--restore',action='store_true');p.add_argument('--check',action='store_true');a=p.parse_args()
 path=a.root/'gen/sdk/code_035.cpp';data=path.read_bytes();start=data.index(FUNCTION);end=data.index(b'\n}\n',start)+3;body=data[start:end]
 if body.count(NEW)==1:body=body.replace(NEW,OLD if a.restore else NEW,1)
 elif body.count(OLD)==1:body=body.replace(OLD,OLD if a.restore else NEW,1)
 else:raise SystemExit('SFNT anchor mismatch; no files changed')
 if a.check:print('Preflight passed');return
 path.write_bytes(data[:start]+body+data[end:]);print('Restored' if a.restore else 'Applied; rebuild SDK code_035.cpp')
if __name__=='__main__':main()
