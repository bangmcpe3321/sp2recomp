#!/usr/bin/env python3
"""Keep controller and mouse gyro sampling on one clock and avoid fallback during packet gaps."""
import argparse,os
from pathlib import Path

CHANGES={
 'runtime/src/controller_motion.h':[
  (b'    void publish() {',b'    void publish(uint64_t timestamp_ns) { // PATCH-GYRO-STREAM-CONTINUITY'),
  (b'        MouseGyroSample s;s.sampling_number=++serial_;',b'''        // Same monotonic 5 ms numbering as MouseGyro. Focus/reconnect must not
        // restart at 1 after sead has consumed a much larger mouse sample number.
        MouseGyroSample s;s.sampling_number=timestamp_ns/tick_ns+1;
        serial_=s.sampling_number; // PATCH-GYRO-STREAM-CONTINUITY'''),
  (b'    void reset() { *this=ControllerMotion{}; }',b'''    void reset() { *this=ControllerMotion{}; }
    void pause() { // PATCH-GYRO-STREAM-CONTINUITY: retain orientation and learned bias across focus changes.
        if(started_&&!calibrated_)calibrated_=true;
        started_=false;count_=head_=0;last_=next_=0;
        for(double& v:pending_)v=0;
        for(double& v:previous_)v=0;
        cal_count_=0;cal_start_=0;for(double& v:cal_sum_)v=0;
    }'''),
  (b'const bool stationary=speed<.1&&',b'const bool stationary=speed<.02&& // PATCH-GYRO-STREAM-CONTINUITY: deliberate gentle aiming is movement\n                '),
  (b'if(cal_count_||speed>=.1)calibrated_=true;',b'if(cal_count_||speed>=.02)calibrated_=true; // PATCH-GYRO-STREAM-CONTINUITY'),
  (b'std::copy(raw,raw+3,previous_);publish();return;',b'std::copy(raw,raw+3,previous_);publish(timestamp_ns);return; // PATCH-GYRO-STREAM-CONTINUITY'),
  (b'if(cursor==next_) {publish();next_+=tick_ns;}',b'if(cursor==next_) {publish(next_);next_+=tick_ns;} // PATCH-GYRO-STREAM-CONTINUITY'),
 ],
 'runtime/src/switch_pro_win.h':[
  (b'inline unsigned read_switch_pro_motion(',b'''inline bool switch_pro_motion_selected() { // PATCH-GYRO-STREAM-CONTINUITY
    auto& s=switch_pro_detail::state(); std::lock_guard<std::mutex> lock(s.mutex);
    return s.connected && s.gyro;
}
inline unsigned read_switch_pro_motion('''),
  (b's.focused=focused; s.motion.reset(); s.last_gyro_ns=0;',b's.focused=focused; s.motion.pause(); s.last_gyro_ns=0; // PATCH-GYRO-STREAM-CONTINUITY\n        '),
 ],
 'runtime/src/platform_win.cpp':[
  (b'bool read_mouse_gyro(unsigned sensor, MouseGyroSample& sample) {',b'''bool read_mouse_gyro(unsigned sensor, MouseGyroSample& sample) {
    if(!g_window || GetForegroundWindow()!=g_window)return false; // PATCH-GYRO-STREAM-CONTINUITY'''),
  (b'unsigned read_mouse_gyro_states(unsigned sensor,MouseGyroSample* samples,unsigned capacity) {',b'''unsigned read_mouse_gyro_states(unsigned sensor,MouseGyroSample* samples,unsigned capacity) {
    if(!g_window || GetForegroundWindow()!=g_window)return 0; // PATCH-GYRO-STREAM-CONTINUITY'''),
  (b'''    if (!g_mouse_capture.load() && g_window && GetForegroundWindow()==g_window &&
        read_switch_pro_motion(sensor,&sample,1)) return true;''',b'''    if (!g_mouse_capture.load() && g_window && GetForegroundWindow()==g_window &&
        switch_pro_motion_selected()) return read_switch_pro_motion(sensor,&sample,1)>0; // PATCH-GYRO-STREAM-CONTINUITY'''),
  (b'''    if (!g_mouse_capture.load() && g_window && GetForegroundWindow()==g_window) {
        const unsigned count=read_switch_pro_motion(sensor,samples,capacity);
        if (count) return count;
    }''',b'''    if (!g_mouse_capture.load() && g_window && GetForegroundWindow()==g_window &&
        switch_pro_motion_selected()) return read_switch_pro_motion(sensor,samples,capacity); // PATCH-GYRO-STREAM-CONTINUITY'''),
 ],
 'runtime/src/hle_hid.cpp':[
  (b'''        if(n) {
            for(unsigned i=0;i<n;i++)store_mouse_gyro_state(out+0x60ull*i,samples[i]);
            c.x[0]=n;return;
        }''',b'''        // PATCH-GYRO-STREAM-CONTINUITY: no sensor data means no new samples.
        // Fabricated fallback samples can jump sead's last-sampling counter.
        for(unsigned i=0;i<n;i++)store_mouse_gyro_state(out+0x60ull*i,samples[i]);
        c.x[0]=n;return;'''),
 ]
}

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--root',type=Path,default=Path(os.environ.get('SP2PORT',str(Path.home()/'sp2port'))))
 p.add_argument('--restore',action='store_true');p.add_argument('--check',action='store_true');a=p.parse_args()
 updated={}
 for relative,replacements in CHANGES.items():
  path=a.root/relative;data=path.read_bytes()
  for old,new in replacements:
   if data.count(new)==1:data=data.replace(new,old if a.restore else new,1)
   elif data.count(old)==1:data=data.replace(old,old if a.restore else new,1)
   else:raise SystemExit('Gyro continuity anchor mismatch in '+relative+'; no files changed')
  updated[path]=data
 if a.check:print('Preflight passed');return
 for path,data in updated.items():path.write_bytes(data)
 print('Restored' if a.restore else 'Applied; rebuild platform_win.cpp and hle_hid.cpp')

if __name__=='__main__':main()
