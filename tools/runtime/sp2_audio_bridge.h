// Included inside hle_audio.cpp's anonymous namespace, after the renderer helpers.
// PATCH-SP2-NATIVE-AUDIO: retain the SDK's own config serialization and status updates.
struct Sp2AudioState {
    std::mutex lock;
    bool started=false;
    uint32_t rate=48000,samples=240,buffers=0;
    nx::sp2::audio::Renderer renderer;
    Sp2AudioState():renderer([](uint64_t address,size_t size)->const uint8_t* {
        if(!address || size>32*1024*1024 || address+size<address)return nullptr;
        uint64_t end=address+size;
        for(uint64_t pos=address;pos<end;) {
            VmInfo info=vm_query(pos);
            if(!(info.perm&1) || info.addr+info.size<=pos)return nullptr;
            pos=std::min(end,info.addr+info.size);
        }
        return reinterpret_cast<const uint8_t*>(address);
    },[](uint64_t address,size_t size)->uint8_t* {
        if(!address || size>32*1024*1024 || address+size<address)return nullptr;
        uint64_t end=address+size;
        for(uint64_t pos=address;pos<end;){VmInfo info=vm_query(pos);if(!(info.perm&2)||info.addr+info.size<=pos)return nullptr;pos=std::min(end,info.addr+info.size);}
        return reinterpret_cast<uint8_t*>(address);
    }){}
};
std::mutex g_sp2_audio_handles_lock,g_sp2_audio_update;
std::map<uint64_t,std::shared_ptr<Sp2AudioState>> g_sp2_audio_handles;
std::shared_ptr<Sp2AudioState> sp2_audio_handle(uint64_t handle) {
    std::lock_guard lk(g_sp2_audio_handles_lock);
    auto found=g_sp2_audio_handles.find(handle);
    return found==g_sp2_audio_handles.end()?nullptr:found->second;
}
bool sp2_audio_enabled() {
    static const bool enabled=std::strcmp(nx::game::kInfo.id,"sp2")==0 && [] {
        const char* value=std::getenv("NX_AUDIO_STUB_RENDERER");return !value||std::strcmp(value,"1")!=0;
    }();
    return enabled;
}
void sp2_audio_noop(CPU& c){c.x[0]=0;}
void sp2_audio_rate(CPU& c){auto s=sp2_audio_handle(c.x[0]);if(s&&c.x[1])st<uint32_t>(c.x[1],s->rate);c.x[0]=0;}
void sp2_audio_samples(CPU& c){auto s=sp2_audio_handle(c.x[0]);if(s&&c.x[1])st<uint32_t>(c.x[1],s->samples);c.x[0]=0;}
void sp2_audio_buffers(CPU& c){auto s=sp2_audio_handle(c.x[0]);if(s&&c.x[1])st<uint32_t>(c.x[1],s->buffers);c.x[0]=0;}
void sp2_audio_state(CPU& c){auto s=sp2_audio_handle(c.x[0]);if(s&&c.x[1]){std::lock_guard lk(s->lock);st<uint32_t>(c.x[1],s->started?0:1);}c.x[0]=0;}
void sp2_audio_start(CPU& c){auto s=sp2_audio_handle(c.x[0]);if(s){std::lock_guard lk(s->lock);s->started=true;}c.x[0]=0;}
void sp2_audio_stop(CPU& c){auto s=sp2_audio_handle(c.x[0]);if(s){std::lock_guard lk(s->lock);s->started=false;}c.x[0]=0;}
void sp2_audio_close(CPU& c){std::lock_guard lk(g_sp2_audio_handles_lock);g_sp2_audio_handles.erase(c.x[0]);c.x[0]=0;}

void sp2_audio_request(CPU& c) {
    auto state=sp2_audio_handle(c.x[0]);
    if(!state){c.x[0]=0x5299;return;}
    uint64_t output=ld<uint64_t>(c.x[1]),capacity=ld<uint64_t>(c.x[1]+8);
    uint64_t input=ld<uint64_t>(c.x[3]),size=ld<uint64_t>(c.x[3]+8);
    if(!input||!output||size<0x40||size>8*1024*1024||capacity>8*1024*1024){c.x[0]=0x5299;return;}
    try {
        std::lock_guard lk(state->lock);
        auto packet=std::span<const uint8_t>(reinterpret_cast<const uint8_t*>(input),size_t(size));
        auto result=state->renderer.update(packet,state->started);
        if(result.size()>capacity){c.x[0]=0x5299;return;}
        std::memset(reinterpret_cast<void*>(output),0,size_t(capacity));
        std::memcpy(reinterpret_cast<void*>(output),result.data(),result.size());
        {
            std::lock_guard lk(g_render.lock);
            for(unsigned i=0;i<480;i++)g_render.mix[i]=state->renderer.pcm[i];
            g_render.mixed=state->started;
        }
        render_submit();
        uint64_t frame=state->renderer.frames;
        if(frame==1 || frame%2000==0) {
            log("SP2 audio: frame %llu, packet %llu -> %zu bytes, voices %llu (PCM16 %llu, ADPCM %llu), splitter voices %llu, effects %llu",
                (unsigned long long)frame,(unsigned long long)size,result.size(),(unsigned long long)state->renderer.activeVoices,
                (unsigned long long)state->renderer.formats[2],(unsigned long long)state->renderer.formats[6],
                (unsigned long long)state->renderer.splitterVoices,(unsigned long long)state->renderer.unsupportedEffects);
            log("SP2 audio: auxiliary send %llu, return %llu, underflows %llu",(unsigned long long)state->renderer.auxSent,(unsigned long long)state->renderer.auxReturned,(unsigned long long)state->renderer.auxUnderflows);
        }
        static const char* dump=std::getenv("NX_AUDIO_PACKET_DUMP");static bool dumped=false;
        if(dump&&!dumped&&state->renderer.activeVoices){if(FILE* file=std::fopen(dump,"wb")){std::fwrite(packet.data(),1,packet.size(),file);std::fclose(file);dumped=true;}}
        c.x[0]=0;
    } catch(const std::exception& error){log("SP2 audio: rejected update: %s",error.what());c.x[0]=0x5299;}
}
void sp2_audio_open(CPU& c) {
    auto state=std::make_shared<Sp2AudioState>();
    state->rate=ld<uint32_t>(c.x[2]);state->samples=ld<uint32_t>(c.x[2]+4);state->buffers=ld<uint32_t>(c.x[2]+8);
    if(state->rate!=48000||state->samples!=240){log("SP2 audio: unsupported renderer %u Hz / %u samples",state->rate,state->samples);c.x[0]=0x5299;return;}
    uint64_t object=kernel_alloc(0x1000),vtable=kernel_alloc(0x1000);
    for(unsigned i=0;i<0x100;i+=8)st<uint64_t>(vtable+i,hle_address_or("__sp2_audio_noop",sp2_audio_noop));
    for(auto entry : {std::pair{0x20u,"__sp2_audio_rate"}, {0x28u,"__sp2_audio_samples"}, {0x30u,"__sp2_audio_buffers"}, {0x38u,"__sp2_audio_state"}, {0x40u,"__sp2_audio_request"}})st<uint64_t>(vtable+entry.first,hle_address(entry.second));
    st<uint64_t>(object,vtable);st<uint64_t>(c.x[0],object);
    {std::lock_guard lk(g_sp2_audio_handles_lock);g_sp2_audio_handles[object]=state;}
    if(c.x[1]) {
        auto read=std::make_shared<KEvent>(),write=std::make_shared<KEvent>();read->state=write->state=g_audio_frame;
        CPU event=c;event.x[0]=c.x[1];event.x[1]=handle_add(read);event.x[2]=1;event.x[3]=handle_add(write);event.x[4]=1;event.x[5]=1;
        call(event,find_symbol("_ZN2nn2os17AttachSystemEventEPNS0_15SystemEventTypeEjbjbNS0_14EventClearModeE"));
    }
    static std::once_flag once;std::call_once(once,[&]{start_render_thread(c);});
    log("SP2 audio: native renderer opened, %u Hz, %u samples, %u mix buffers",state->rate,state->samples,state->buffers);c.x[0]=0;
}
