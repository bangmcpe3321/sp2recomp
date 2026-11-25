// Splatoon 2's REV1-REV4 AudioRenderer wire protocol, implemented on the host.
// Packet sizes/offsets are verified against this game's SDK pack/unpack routines.
#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <functional>
#include <map>
#include <span>
#include <stdexcept>
#include <vector>

namespace nx::sp2::audio {
template<class T> inline T get(std::span<const uint8_t> data, size_t offset) {
    if (offset > data.size() || sizeof(T) > data.size() - offset) throw std::runtime_error("Audio packet field out of bounds");
    T value; std::memcpy(&value, data.data() + offset, sizeof value); return value;
}
template<class T> inline void put(std::span<uint8_t> data, size_t offset, T value) {
    if (offset > data.size() || sizeof(T) > data.size() - offset) throw std::runtime_error("Audio output field out of bounds");
    std::memcpy(data.data() + offset, &value, sizeof value);
}
inline float gain(float value) { return std::isfinite(value) ? std::clamp(value, -16.0f, 16.0f) : 0.0f; }
using Memory = std::function<const uint8_t*(uint64_t, size_t)>;
using WritableMemory = std::function<uint8_t*(uint64_t, size_t)>;

struct Wave {
    std::vector<float> samples;
    uint32_t start = 0, end = 0, channels = 1;
    bool ready = false, loop = false, eos = false;
};
struct Voice {
    std::array<Wave,4> waves;
    uint32_t head = 0, consumed = 0;
    uint64_t played = 0;
    double position = 0;
    bool initialized = false, stopped = true;
    std::array<std::array<double,2>,12> filters{};
};
struct Sections {
    std::array<std::span<const uint8_t>,10> data;
    explicit Sections(std::span<const uint8_t> packet) {
        uint32_t revision = get<uint32_t>(packet,0);
        if ((revision & 0xffffff) != 0x564552 || (revision >> 24) < '1' || (revision >> 24) > '4') throw std::runtime_error("Unsupported audio protocol revision");
        uint32_t total = get<uint32_t>(packet,0x3c);
        if (total != packet.size() || total > 8*1024*1024) throw std::runtime_error("Invalid audio packet size");
        size_t offset = 0x40;
        for (unsigned field : {1u,2u,4u,3u,5u,9u,6u,7u,8u}) {
            size_t size = get<uint32_t>(packet,4*field);
            if (offset > packet.size() || size > packet.size()-offset) throw std::runtime_error("Invalid audio section size");
            data[field] = packet.subspan(offset,size); offset += size;
        }
        if (offset != total) throw std::runtime_error("Audio sections do not match total size");
        for (auto pair : {std::pair{2u,0x20u}, {3u,0x170u}, {4u,0x70u}, {5u,0xc0u}, {6u,0x930u}, {7u,0x140u}})
            if (data[pair.first].size()%pair.second) throw std::runtime_error("Invalid audio record stride");
        if (data[3].size()/0x170 > 1024 || data[6].size()/0x930 > 256) throw std::runtime_error("Audio configuration too large");
    }
};

class Renderer {
    std::vector<Voice> voices;
    std::vector<uint32_t> pools;
    std::map<uint32_t,std::vector<float>> mixes;
    uint32_t finalChannels = 2;
    Memory memory;
    WritableMemory writable;
    void effects(uint32_t mixId, std::span<const uint8_t> parameters) {
        auto& mix=mixes[mixId];size_t buffers=mix.size()/240;
        std::vector<std::span<const uint8_t>> list;
        for(size_t i=0;i<parameters.size()/0xc0;i++){auto e=parameters.subspan(i*0xc0,0xc0);if(get<uint8_t>(e,0)&&get<uint32_t>(e,4)==mixId)list.push_back(e);}
        std::stable_sort(list.begin(),list.end(),[](auto a,auto b){return get<int32_t>(a,0x18)<get<int32_t>(b,0x18);});
        for(auto e:list) {
            uint8_t type=get<uint8_t>(e,0);
            if(type==1 && get<uint8_t>(e,2)) {
                uint32_t count=std::min(get<uint32_t>(e,0xb0),24u);auto original=mix;
                for(uint32_t i=0;i<count;i++){unsigned input=get<uint8_t>(e,0x20+i),output=get<uint8_t>(e,0x38+i);if(input>=buffers||output>=buffers)continue;float volume=gain(get<float>(e,0x50+4*i));for(unsigned s=0;s<240;s++)mix[output*240+s]+=original[input*240+s]*volume;}
                continue;
            }
            if(type!=2){unsupportedEffects++;continue;}
            uint32_t count=std::min(get<uint32_t>(e,0x50),24u),capacity=get<uint32_t>(e,0x58);
            if(!count||capacity<count*240||capacity>1024*1024||!writable)continue;
            // Each direction stores an (info, samples) pair, as the SDK's auxiliary read/write calls load it.
            uint8_t* sendInfo=writable(get<uint64_t>(e,0x60),0x80),*returnInfo=writable(get<uint64_t>(e,0x70),0x80);
            uint8_t* sendData=writable(get<uint64_t>(e,0x68),size_t(capacity)*4);
            const uint8_t* returnData=memory(get<uint64_t>(e,0x78),size_t(capacity)*4);
            if(!sendInfo||!returnInfo||!sendData||!returnData)continue;
            auto si=std::span<uint8_t>(sendInfo,0x80),ri=std::span<uint8_t>(returnInfo,0x80);
            if(!get<uint8_t>(e,2)){
                put<uint32_t>(si,0x40,0);put<uint32_t>(si,0x44,0);put<uint32_t>(ri,0x40,0);put<uint32_t>(ri,0x44,0);
                auto original=mix;for(unsigned ch=0;ch<count;ch++){unsigned input=get<uint8_t>(e,0x20+ch),output=get<uint8_t>(e,0x38+ch);if(input<buffers&&output<buffers)std::copy_n(original.data()+input*240,240,mix.data()+output*240);}
                continue;
            }
            uint32_t size=count*240,write=get<uint32_t>(si,0x44)%capacity,read=get<uint32_t>(si,0)%capacity;
            uint32_t free=(read+capacity-write-1)%capacity;
            if(free>=size) {
                for(unsigned ch=0;ch<count;ch++){unsigned input=get<uint8_t>(e,0x20+ch);for(unsigned s=0;s<240;s++){float sample=input<buffers?mix[input*240+s]:0;int32_t value=int32_t(std::clamp<double>(sample,INT32_MIN,INT32_MAX));size_t index=(write+ch*240+s)%capacity;std::memcpy(sendData+index*4,&value,4);}}
                put<uint32_t>(si,0x44,(write+size)%capacity);auxSent+=size;
            }
            read=get<uint32_t>(ri,0x40)%capacity;write=get<uint32_t>(ri,0x44)%capacity;
            uint32_t available=(write+capacity-read)%capacity;
            bool returned=available>=size;
            for(unsigned ch=0;ch<count;ch++){unsigned output=get<uint8_t>(e,0x38+ch);if(output>=buffers)continue;for(unsigned s=0;s<240;s++){int32_t value=0;if(returned){size_t index=(read+ch*240+s)%capacity;std::memcpy(&value,returnData+index*4,4);}mix[output*240+s]=float(value);}}
            if(returned){put<uint32_t>(ri,0x40,(read+size)%capacity);put<uint32_t>(ri,0,(read+size)%capacity);auxReturned+=size;}else auxUnderflows++;
        }
    }
    static int16_t adpcm_sample(int nibble, unsigned scale, int16_t c0, int16_t c1, int16_t& h0, int16_t& h1) {
        int64_t sample = (int64_t(nibble)*(int64_t(1)<<scale)*2048 + int64_t(c0)*h0 + int64_t(c1)*h1 + 1024) >> 11;
        int16_t result = int16_t(std::clamp<int64_t>(sample,-32768,32767)); h1=h0; h0=result; return result;
    }
    Wave load_wave(std::span<const uint8_t> v, unsigned slot) {
        auto w=v.subspan(0x60+slot*0x38,0x38); Wave result;
        uint64_t address=get<uint64_t>(w,0), bytes=get<uint64_t>(w,8);
        int32_t start=get<int32_t>(w,0x10), end=get<int32_t>(w,0x14);
        result.channels=get<uint32_t>(v,0x18);
        if (!address || !bytes || bytes>32*1024*1024 || start<0 || end<=start || result.channels<1 || result.channels>6) return result;
        const uint8_t* source=memory(address,size_t(bytes)); if (!source) return result;
        uint8_t format=get<uint8_t>(v,0xb);
        uint64_t available = format==6 ? bytes/8*14 : bytes/(format==1 ? 1 : format==2 ? 2 : format==3 ? 3 : 4)/result.channels;
        if (format<1 || format>6 || uint64_t(end)>available || uint64_t(end)*result.channels>16*1024*1024 || (format==6 && result.channels!=1)) return result;
        result.samples.resize(size_t(end)*result.channels);
        if (format==6) {
            uint64_t extra=get<uint64_t>(v,0x48); const uint8_t* coefficients=memory(extra,32);
            if (!coefficients) return Wave{};
            int16_t h0=0,h1=0;
            uint64_t context=get<uint64_t>(w,0x20), contextSize=get<uint64_t>(w,0x28);
            unsigned begin=0;
            if (context && contextSize>=6) {
                if (const uint8_t* ctx=memory(context,6)) {
                    std::memcpy(&h0,ctx+2,2); std::memcpy(&h1,ctx+4,2); begin=unsigned(start);
                }
            }
            for (unsigned i=begin;i<unsigned(end);i++) {
                size_t block=size_t(i/14)*8; uint8_t header=source[block]; unsigned predictor=header>>4;
                if (predictor>=8) return Wave{};
                int16_t c0,c1; std::memcpy(&c0,coefficients+predictor*4,2); std::memcpy(&c1,coefficients+predictor*4+2,2);
                uint8_t packed=source[block+1+(i%14)/2]; int nibble=(i%2)==0 ? packed>>4 : packed&15;
                if (nibble>=8) nibble-=16;
                result.samples[i]=adpcm_sample(nibble,header&15,c0,c1,h0,h1);
            }
        } else {
            for (size_t i=0;i<result.samples.size();i++) {
                float sample=0;
                if (format==1) sample=float(int8_t(source[i]))*256;
                if (format==2) { int16_t x;std::memcpy(&x,source+2*i,2);sample=x; }
                if (format==3) { int32_t x=source[3*i]|source[3*i+1]<<8|source[3*i+2]<<16; if(x&0x800000)x|=~0xffffff;sample=float(x)/256; }
                if (format==4) { int32_t x;std::memcpy(&x,source+4*i,4);sample=float(double(x)/65536); }
                if (format==5) { float x;std::memcpy(&x,source+4*i,4);sample=std::isfinite(x)?std::clamp(x,-1.0f,1.0f)*32768:0; }
                result.samples[i]=sample;
            }
        }
        result.start=unsigned(start);result.end=unsigned(end);result.ready=true;result.loop=get<uint8_t>(w,0x18);result.eos=get<uint8_t>(w,0x19);
        return result;
    }
    float filter(Voice& state, unsigned channel, float sample, std::span<const uint8_t> v) {
        for (unsigned f=0;f<2;f++) {
            size_t offset=0x24+f*12;
            if (!get<uint8_t>(v,offset)) continue;
            auto& delay=state.filters[channel*2+f];
            double b0=get<int16_t>(v,offset+2)/16384.0, b1=get<int16_t>(v,offset+4)/16384.0, b2=get<int16_t>(v,offset+6)/16384.0;
            double a1=get<int16_t>(v,offset+8)/16384.0, a2=get<int16_t>(v,offset+10)/16384.0;
            double y=b0*sample+delay[0]; delay[0]=b1*sample+a1*y+delay[1];delay[1]=b2*sample+a2*y;
            if (!std::isfinite(y) || std::abs(y)>1e9) { delay={};y=0; }
            sample=float(y);
        }
        return sample;
    }
    void render_voice(Voice& state, std::span<const uint8_t> v, std::span<const uint8_t> channels) {
        uint32_t destination=get<uint32_t>(v,0x58);
        auto found=mixes.find(destination);
        if (found==mixes.end()) { if (get<uint32_t>(v,0x5c)!=0xffffffff) splitterVoices++; return; }
        uint32_t count=get<uint32_t>(v,0x18);if(count<1||count>6)return;
        float volume=gain(get<float>(v,0x20));
        double step=double(get<uint32_t>(v,0xc))*gain(get<float>(v,0x1c))/48000.0;
        if (step<=0 || step>16)return;
        auto& mix=found->second; size_t buffers=mix.size()/240;
        for (unsigned s=0;s<240;s++) {
            unsigned attempts=0;
            while (state.waves[state.head].ready && state.position>=state.waves[state.head].end && attempts++<4) {
                Wave& wave=state.waves[state.head];
                if (wave.loop) { state.position=wave.start+std::fmod(state.position-wave.end,double(wave.end-wave.start)); break; }
                state.position-=wave.end;wave.ready=false;state.consumed++;bool eos=wave.eos;state.head=(state.head+1)%4;
                if(eos){state.played=0;break;}
                if(state.waves[state.head].ready)state.position+=state.waves[state.head].start;
            }
            auto& wave=state.waves[state.head]; if(!wave.ready)break;
            size_t position=size_t(state.position);size_t next=position+1;
            if(next>=wave.end)next=wave.loop?wave.start:position;
            double fraction=state.position-position;
            for(unsigned ch=0;ch<count;ch++) {
                float sample=wave.samples[position*count+ch]+float(fraction)*(wave.samples[next*count+ch]-wave.samples[position*count+ch]);
                sample=filter(state,ch,sample,v)*volume;
                uint32_t resource=get<uint32_t>(v,0x140+ch*4);
                if(resource>=channels.size()/0x70)continue;
                auto row=channels.subspan(resource*0x70,0x70);
                for(size_t b=0;b<buffers && b<24;b++)mix[b*240+s]+=sample*gain(get<float>(row,4+4*b));
            }
            double previous=state.position;state.position+=step;state.played+=uint64_t(state.position)-uint64_t(previous);
        }
    }
public:
    uint64_t frames=0,activeVoices=0,splitterVoices=0,unsupportedEffects=0,auxSent=0,auxReturned=0,auxUnderflows=0;
    std::array<uint64_t,7> formats{};
    std::array<int32_t,480> pcm{};
    explicit Renderer(Memory read,WritableMemory write={}):memory(std::move(read)),writable(std::move(write)){}
    std::vector<uint8_t> update(std::span<const uint8_t> packet, bool started) {
        Sections sections(packet);auto& d=sections.data;
        size_t count=d[3].size()/0x170;voices.resize(count);pools.resize(d[2].size()/0x20,6);
        mixes.clear();
        for(size_t i=0;i<d[6].size()/0x930;i++) {
            auto m=d[6].subspan(i*0x930,0x930);
            if(!get<uint8_t>(m,0xc))continue;
            uint32_t id=get<uint32_t>(m,0x10),buffers=get<uint32_t>(m,8);
            if(buffers>24)throw std::runtime_error("Too many audio mix buffers");
            mixes[id].resize(buffers*240);
            if(id==0)finalChannels=buffers;
        }
        pcm.fill(0);activeVoices=splitterVoices=unsupportedEffects=0;formats.fill(0);
        for(size_t i=0;i<count;i++) {
            auto v=d[3].subspan(i*0x170,0x170);auto& state=voices[i];
            if(!get<uint8_t>(v,9)){state=Voice{};continue;}
            bool fresh=get<uint8_t>(v,8);
            if(fresh || !state.initialized){state=Voice{};state.initialized=true;state.head=uint16_t(get<int16_t>(v,0x40))%4;}
            uint8_t playState=get<uint8_t>(v,0xa);
            if(playState==1){if(!state.stopped){state.consumed+=uint32_t(std::count_if(state.waves.begin(),state.waves.end(),[](const Wave& w){return w.ready;}));for(auto& w:state.waves)w.ready=false;state.position=0;}state.stopped=true;}
            else state.stopped=false;
            for(unsigned slot=0;slot<4;slot++) {
                auto w=v.subspan(0x60+slot*0x38,0x38);
                if(!get<uint8_t>(w,0x1a) && get<uint64_t>(w,0) && get<uint64_t>(w,8)){
                    state.waves[slot]=load_wave(v,slot);
                    if(slot==state.head && state.position<state.waves[slot].start)state.position=state.waves[slot].start;
                }
            }
            if(started && playState==0){activeVoices++;uint8_t format=get<uint8_t>(v,0xb);if(format<formats.size())formats[format]++;render_voice(state,v,d[4]);}
        }
        // Route submixes before their destinations. Acyclic chains are the SDK's documented mix topology.
        std::map<uint32_t,std::span<const uint8_t>> configs;
        for(size_t i=0;i<d[6].size()/0x930;i++){auto m=d[6].subspan(i*0x930,0x930);if(get<uint8_t>(m,0xc))configs[get<uint32_t>(m,0x10)]=m;}
        std::map<uint32_t,unsigned> incoming;for(auto [id,m]:configs){uint32_t dst=get<uint32_t>(m,0x924);if(id!=0&&configs.count(dst))incoming[dst]++;}
        std::vector<uint32_t> ready;for(auto [id,m]:configs)if(!incoming[id])ready.push_back(id);
        for(size_t q=0;q<ready.size();q++) {
            uint32_t id=ready[q];auto m=configs[id];auto& source=mixes[id];
            if(started)effects(id,d[5]);
            float volume=gain(get<float>(m,0));for(float& sample:source)sample*=volume;
            uint32_t dst=get<uint32_t>(m,0x924);
            if(id==0||!mixes.count(dst))continue;
            auto& target=mixes[dst];
            for(size_t a=0;a<source.size()/240;a++)for(size_t b=0;b<target.size()/240;b++) {
                float scale=gain(get<float>(m,0x24+(a*24+b)*4));if(scale==0)continue;
                for(unsigned s=0;s<240;s++)target[b*240+s]+=source[a*240+s]*scale;
            }
            if(incoming[dst]&&!--incoming[dst])ready.push_back(dst);
        }
        if(auto final=mixes.find(0);final!=mixes.end()) {
            auto& mix=final->second;
            for(size_t i=0;i<d[7].size()/0x140;i++) {
                auto sink=d[7].subspan(i*0x140,0x140);if(get<uint8_t>(sink,0)!=1||!get<uint8_t>(sink,1))continue;
                uint32_t inputs=std::min(get<uint32_t>(sink,0x120),6u);if(!inputs)continue;
                auto sample=[&](unsigned channel,unsigned s){if(channel>=inputs)return 0.0f;uint8_t b=get<uint8_t>(sink,0x124+channel);return size_t(b)<mix.size()/240?mix[b*240+s]:0.0f;};
                for(unsigned s=0;s<240;s++) {
                    double left=sample(0,s),right=inputs>1?sample(1,s):left;
                    if(inputs>=6){left+=(sample(2,s)+sample(4,s))*0.707106781;right+=(sample(2,s)+sample(5,s))*0.707106781;}
                    pcm[2*s]+=int32_t(std::clamp(left,-32768.0,32767.0));pcm[2*s+1]+=int32_t(std::clamp(right,-32768.0,32767.0));
                }
            }
        }
        size_t effectCount=d[5].size()/0xc0,sinkCount=d[7].size()/0x140;
        size_t total=0x40+pools.size()*16+count*16+effectCount*16+sinkCount*32+16+0xb0;
        std::vector<uint8_t> output(total);auto out=std::span<uint8_t>(output);
        put(out,0,get<uint32_t>(packet,0));put(out,4,0xb0u);put(out,8,uint32_t(pools.size()*16));put(out,12,uint32_t(count*16));put(out,20,uint32_t(effectCount*16));put(out,28,uint32_t(sinkCount*32));put(out,32,16u);put(out,0x3c,uint32_t(total));
        size_t offset=0x40;
        for(size_t i=0;i<pools.size();i++){uint32_t request=get<uint32_t>(d[2],i*0x20+0x10);pools[i]=request==4?5:request==2?3:request;put(out,offset,pools[i]);offset+=16;}
        for(auto& state:voices){put(out,offset,state.played);put(out,offset+8,state.consumed);offset+=16;}
        for(size_t i=0;i<effectCount;i++){put<uint8_t>(out,offset,get<uint8_t>(d[5],i*0xc0)?1:0);offset+=16;}
        frames++;return output;
    }
};
} // namespace nx::sp2::audio
