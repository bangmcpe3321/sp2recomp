#!/usr/bin/env python3
"""Check XAudio2 setup/submission results and reclaim rejected audio blocks."""
import argparse,os
from pathlib import Path
OLD_OPEN=b'''    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (FAILED(XAudio2Create(&g_xa, 0, XAUDIO2_DEFAULT_PROCESSOR))) return false;
    IXAudio2MasteringVoice* master = nullptr;
    if (FAILED(g_xa->CreateMasteringVoice(&master))) return false;
'''
NEW_OPEN=b'''    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    HRESULT result=XAudio2Create(&g_xa, 0, XAUDIO2_DEFAULT_PROCESSOR);
    if (FAILED(result)) { log("audio: XAudio2Create failed: 0x%08x", unsigned(result)); return false; }
    IXAudio2MasteringVoice* master = nullptr;
    result=g_xa->CreateMasteringVoice(&master);
    if (FAILED(result)) { log("audio: CreateMasteringVoice failed: 0x%08x", unsigned(result)); g_xa->Release(); g_xa=nullptr; return false; }
'''
OLD_START=b'''    if (FAILED(g_xa->CreateSourceVoice(&g_voice, &wf, 0, 2.0f, &g_callback))) return false;
    g_voice->Start();
    return true;
'''
NEW_START=b'''    result=g_xa->CreateSourceVoice(&g_voice, &wf, 0, 2.0f, &g_callback);
    if (SUCCEEDED(result)) result=g_voice->Start();
    if (FAILED(result)) {
        log("audio: XAudio2 source setup failed: 0x%08x", unsigned(result));
        if(g_voice)g_voice->DestroyVoice(); g_voice=nullptr; master->DestroyVoice(); g_xa->Release(); g_xa=nullptr; return false;
    }
    log("audio: XAudio2 output ready (48000 Hz, stereo PCM16)");
    return true;
'''
OLD_SUBMIT=b'''    g_voice->SubmitSourceBuffer(&xb);
    return true;
'''
NEW_SUBMIT=b'''    HRESULT result=g_voice->SubmitSourceBuffer(&xb);
    if(FAILED(result)) {
        g_queued--; delete p;
        log("audio: SubmitSourceBuffer failed: 0x%08x", unsigned(result));
        return false;
    }
    return true;
'''
SITES={
 'runtime/src/platform_win.cpp':[(OLD_OPEN,NEW_OPEN),(OLD_START,NEW_START),(OLD_SUBMIT,NEW_SUBMIT),
 (b'    if (!g_voice) return false;\n',b'    if (!g_voice || !data || !bytes || bytes%4 || bytes>XAUDIO2_MAX_BUFFER_BYTES) return false; // PATCH-SP2-AUDIO-OUTPUT\n'),
 (b'    void STDMETHODCALLTYPE OnVoiceError(void*, HRESULT) noexcept override {}\n',b'    void STDMETHODCALLTYPE OnVoiceError(void*, HRESULT result) noexcept override { log("audio: XAudio2 voice error: 0x%08x", unsigned(result)); } // PATCH-SP2-AUDIO-OUTPUT\n')],
 'runtime/src/hle_audio.cpp':[(b'    for (int h : o.held) plat::audio_submit(o.blocks[h], sizeof pcm, o.blocks[h]);\n',b'    for (int h : o.held) if (!plat::audio_submit(o.blocks[h], sizeof pcm, o.blocks[h])) o.free.push_back(h); // PATCH-SP2-AUDIO-OUTPUT\n')],
}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(os.environ.get('SP2PORT',str(Path.home()/'sp2port'))));p.add_argument('--restore',action='store_true');p.add_argument('--check',action='store_true');a=p.parse_args();changes=[]
 for relative,sites in SITES.items():
  path=a.root/relative;data=path.read_bytes()
  for old,new in sites:
   if data.count(new)==1:data=data.replace(new,old if a.restore else new,1)
   elif data.count(old)==1:data=data.replace(old,old if a.restore else new,1)
   else:raise SystemExit('Audio output anchor mismatch; no files changed: '+relative)
  changes.append((path,data))
 if a.check:print('Preflight passed');return
 for path,data in changes:path.write_bytes(data)
 print('Restored' if a.restore else 'Applied; rebuild platform_win.cpp and hle_audio.cpp')
if __name__=='__main__':main()
