#!/usr/bin/env python3
"""Connect this US 1.0.0 SDK's audio packets to the host renderer."""
import argparse
from pathlib import Path
import os
INCLUDE=b'#include <nx/game.h>\n#include "sp2_audio_renderer.h" // PATCH-SP2-NATIVE-AUDIO\n'
BRIDGE=b'#include "sp2_audio_bridge.h" // PATCH-SP2-NATIVE-AUDIO\n\n'
HOOKS={
    b'void OpenAudioRenderer(CPU& c) {\n':b'    if(sp2_audio_enabled()){sp2_audio_open(c);return;} // PATCH-SP2-NATIVE-AUDIO\n',
    b'void RequestUpdateAudioRenderer(CPU& c) {\n':b'    if(sp2_audio_handle(c.x[0])){std::lock_guard lk(g_sp2_audio_update);call(c,request_update_fn());return;} // PATCH-SP2-NATIVE-AUDIO\n',
    b'void StartAudioRenderer(CPU& c) {\n':b'    if(sp2_audio_handle(c.x[0])){sp2_audio_start(c);return;} // PATCH-SP2-NATIVE-AUDIO\n',
    b'void StopAudioRenderer(CPU& c) {\n':b'    if(sp2_audio_handle(c.x[0])){sp2_audio_stop(c);return;} // PATCH-SP2-NATIVE-AUDIO\n',
    b'void CloseAudioRenderer(CPU& c) {\n':b'    if(sp2_audio_handle(c.x[0])){sp2_audio_close(c);return;} // PATCH-SP2-NATIVE-AUDIO\n',
}
REGISTRATIONS=b'''namespace nx {
NX_HLE("__sp2_audio_rate", sp2_audio_rate);
NX_HLE("__sp2_audio_samples", sp2_audio_samples);
NX_HLE("__sp2_audio_buffers", sp2_audio_buffers);
NX_HLE("__sp2_audio_state", sp2_audio_state);
NX_HLE("__sp2_audio_request", sp2_audio_request);
}
// PATCH-SP2-NATIVE-AUDIO-END
'''
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(os.environ.get('SP2PORT',str(Path.home()/'sp2port'))));p.add_argument('--restore',action='store_true');p.add_argument('--check',action='store_true');a=p.parse_args()
    path=a.root/'runtime/src/hle_audio.cpp';data=path.read_bytes();applied=INCLUDE in data
    headers={name:(Path(__file__).resolve().parents[1]/'runtime'/name).read_bytes() for name in ('sp2_audio_renderer.h','sp2_audio_bridge.h')}
    if applied:
        legacy=REGISTRATIONS.replace(b'namespace nx {\n',b'').replace(b'}\n// PATCH-SP2-NATIVE-AUDIO-END',b'// PATCH-SP2-NATIVE-AUDIO-END')
        if legacy in data and REGISTRATIONS not in data:data=data.replace(legacy,REGISTRATIONS,1)
        if data.count(INCLUDE)!=1 or data.count(BRIDGE)!=1 or data.count(REGISTRATIONS)!=1:raise SystemExit('Partial audio patch; no files changed')
        data=data.replace(INCLUDE,b'',1).replace(BRIDGE,b'',1).replace(REGISTRATIONS,b'',1)
        for anchor,hook in HOOKS.items():
            if data.count(anchor+hook)!=1:raise SystemExit('Audio hook mismatch; no files changed')
            data=data.replace(anchor+hook,anchor,1)
    elif any(b'PATCH-SP2-NATIVE-AUDIO' in data for _ in [0]):raise SystemExit('Unknown audio patch; no files changed')
    if not a.restore:
        # Verify the precise wire-protocol API used by the bridge before installing it.
        table=(a.root/'gen/sdk/table.cpp').read_bytes()
        if b'"_ZN2nn5audio26RequestUpdateAudioRendererENS0_19AudioRendererHandleEPKNS0_19AudioRendererConfigE", 0x161c6c, 932,' not in table:raise SystemExit('Unsupported SDK packet serializer; no files changed')
        data=INCLUDE+data
        for anchor,hook in HOOKS.items():
            if data.count(anchor)!=1:raise SystemExit('Audio source anchor mismatch; no files changed')
            data=data.replace(anchor,(BRIDGE if anchor.startswith(b'void Open') else b'')+anchor+hook,1)
        data+=REGISTRATIONS
    if a.check:print('Can restore' if a.restore else 'Can apply/update');return
    path.write_bytes(data)
    for name,value in headers.items():
        target=a.root/'runtime/src'/name
        if a.restore:
            if target.exists():target.unlink()
        else:target.write_bytes(value)
    print('Restored' if a.restore else 'Applied; rebuild hle_audio.cpp and changed Windows output')
if __name__=='__main__':main()
