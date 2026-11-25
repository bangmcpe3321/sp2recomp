#define VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>
#include <windows.h>
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <vector>
VkDevice device;
PFN_vkGetInstanceProcAddr gip;
PFN_vkGetDeviceProcAddr gdp;
PFN_vkAllocateMemory allocateMemory;
PFN_vkFreeMemory freeMemory;
uint64_t calls=0;
namespace nx::nvn {VkDevice vk_device(){return device;}}
namespace nx::vk {
VkResult p_vkAllocateMemory(VkDevice d,const VkMemoryAllocateInfo* ai,const VkAllocationCallbacks* cb,VkDeviceMemory* m){++calls;return allocateMemory(d,ai,cb,m);}
void p_vkFreeMemory(VkDevice d,VkDeviceMemory m,const VkAllocationCallbacks* cb){freeMemory(d,m,cb);}
}
#include <thread>
#include <cstring>
#include <cstdint>
void check(VkResult r){if(r!=VK_SUCCESS){std::printf("FAIL VkResult %d\n",int(r));std::exit(1);}}
int main(){
 auto dll=LoadLibraryA("vulkan-1.dll");if(!dll)return 1;
 gip=(PFN_vkGetInstanceProcAddr)GetProcAddress(dll,"vkGetInstanceProcAddr");
 auto createInstance=(PFN_vkCreateInstance)gip(nullptr,"vkCreateInstance");
 VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};app.pApplicationName="sp2 allocation benchmark";app.apiVersion=VK_API_VERSION_1_0;
 VkInstanceCreateInfo ici{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};ici.pApplicationInfo=&app;
 VkInstance instance;check(createInstance(&ici,nullptr,&instance));
 auto enumerate=(PFN_vkEnumeratePhysicalDevices)gip(instance,"vkEnumeratePhysicalDevices");
 auto properties=(PFN_vkGetPhysicalDeviceProperties)gip(instance,"vkGetPhysicalDeviceProperties");
 auto memoryProperties=(PFN_vkGetPhysicalDeviceMemoryProperties)gip(instance,"vkGetPhysicalDeviceMemoryProperties");
 auto queues=(PFN_vkGetPhysicalDeviceQueueFamilyProperties)gip(instance,"vkGetPhysicalDeviceQueueFamilyProperties");
 auto createDevice=(PFN_vkCreateDevice)gip(instance,"vkCreateDevice");
 uint32_t count=0;check(enumerate(instance,&count,nullptr));std::vector<VkPhysicalDevice> all(count);check(enumerate(instance,&count,all.data()));
 VkPhysicalDevice physical=all.at(0);VkPhysicalDeviceProperties props{};
 for(auto p:all){properties(p,&props);if(props.deviceType==VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU){physical=p;break;}}
 properties(physical,&props);std::printf("GPU: %s\n",props.deviceName);
 queues(physical,&count,nullptr);std::vector<VkQueueFamilyProperties> families(count);queues(physical,&count,families.data());
 uint32_t family=0;while(family<count && !(families[family].queueFlags & VK_QUEUE_GRAPHICS_BIT))++family;if(family==count)return 2;
 float priority=1;VkDeviceQueueCreateInfo qi{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};qi.queueFamilyIndex=family;qi.queueCount=1;qi.pQueuePriorities=&priority;
 VkDeviceCreateInfo dci{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};dci.queueCreateInfoCount=1;dci.pQueueCreateInfos=&qi;check(createDevice(physical,&dci,nullptr,&device));
 gdp=(PFN_vkGetDeviceProcAddr)gip(instance,"vkGetDeviceProcAddr");

#define FN(name) auto name=(PFN_vk##name)gdp(device,"vk"#name)
 FN(AllocateMemory);FN(FreeMemory);FN(CreateBuffer);FN(DestroyBuffer);FN(GetBufferMemoryRequirements);FN(BindBufferMemory);FN(MapMemory);FN(UnmapMemory);
 FN(CreateCommandPool);FN(DestroyCommandPool);FN(AllocateCommandBuffers);FN(ResetCommandPool);FN(BeginCommandBuffer);FN(EndCommandBuffer);
 FN(CmdPipelineBarrier);FN(CmdFillBuffer);FN(CmdCopyBuffer);FN(GetDeviceQueue);FN(QueueSubmit);FN(CreateFence);FN(DestroyFence);FN(ResetFences);FN(WaitForFences);
 VkQueue queue;GetDeviceQueue(device,family,0,&queue);
 VkPhysicalDeviceMemoryProperties mp;memoryProperties(physical,&mp);

 constexpr uint64_t bytes=2ull<<20;
 auto make_buffer=[&](){VkBufferCreateInfo ci{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};ci.size=bytes;ci.usage=VK_BUFFER_USAGE_TRANSFER_SRC_BIT|VK_BUFFER_USAGE_TRANSFER_DST_BIT;VkBuffer b;check(CreateBuffer(device,&ci,nullptr,&b));return b;};
 VkBuffer gpu=make_buffer();VkMemoryRequirements req;GetBufferMemoryRequirements(device,gpu,&req);
 uint32_t local=0;while(local<mp.memoryTypeCount && (!(req.memoryTypeBits&(1u<<local)) || !(mp.memoryTypes[local].propertyFlags&VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT)))++local;
 if(local==mp.memoryTypeCount)return 3;
 VkMemoryAllocateInfo ai{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};ai.allocationSize=req.size;ai.memoryTypeIndex=local;VkDeviceMemory gpuMemory;check(AllocateMemory(device,&ai,nullptr,&gpuMemory));check(BindBufferMemory(device,gpu,gpuMemory,0));
 VkCommandPoolCreateInfo pi{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};pi.queueFamilyIndex=family;VkCommandPool pool;check(CreateCommandPool(device,&pi,nullptr,&pool));
 VkCommandBuffer cb;VkCommandBufferAllocateInfo cai{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};cai.commandPool=pool;cai.level=VK_COMMAND_BUFFER_LEVEL_PRIMARY;cai.commandBufferCount=1;check(AllocateCommandBuffers(device,&cai,&cb));
 VkFenceCreateInfo fi{VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};VkFence fence;check(CreateFence(device,&fi,nullptr,&fence));
 std::vector<uint8_t> source(bytes);for(size_t i=0;i<source.size();i++)source[i]=uint8_t(i*13+7);
 auto clock=[](){return std::chrono::steady_clock::now();};
 auto elapsed=[&](auto start){return std::chrono::duration<double,std::milli>(clock()-start).count();};
 for(unsigned round=0;round<6;round++){
  bool wantCached=round%2;VkBuffer host=make_buffer();GetBufferMemoryRequirements(device,host,&req);
  uint32_t type=0;constexpr auto plain=VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT|VK_MEMORY_PROPERTY_HOST_COHERENT_BIT;
  while(type<mp.memoryTypeCount && (!(req.memoryTypeBits&(1u<<type)) || (mp.memoryTypes[type].propertyFlags&plain)!=plain || bool(mp.memoryTypes[type].propertyFlags&VK_MEMORY_PROPERTY_HOST_CACHED_BIT)!=wantCached))++type;
  if(type==mp.memoryTypeCount){std::printf("missing cached=%u\n",unsigned(wantCached));return 4;}
  ai.allocationSize=req.size;ai.memoryTypeIndex=type;VkDeviceMemory memory;check(AllocateMemory(device,&ai,nullptr,&memory));check(BindBufferMemory(device,host,memory,0));uint8_t* mapped=nullptr;check(MapMemory(device,memory,0,VK_WHOLE_SIZE,0,(void**)&mapped));
  double write_ms=0,submit_ms=0,read_ms=0;uint64_t sum=0;
  for(unsigned frame=0;frame<16;frame++){
   auto start=clock();
   // Small writes model per-draw uniform/storage upload blocks.
   for(uint64_t at=0;at<bytes;at+=256)std::memcpy(mapped+at,source.data()+at,256);
   write_ms+=elapsed(start);
   check(ResetCommandPool(device,pool,0));check(ResetFences(device,1,&fence));
   VkCommandBufferBeginInfo bi{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};bi.flags=VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;check(BeginCommandBuffer(cb,&bi));
   VkBufferCopy copy{0,0,bytes};CmdCopyBuffer(cb,host,gpu,1,&copy);
   VkMemoryBarrier barrier{VK_STRUCTURE_TYPE_MEMORY_BARRIER};barrier.srcAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT;barrier.dstAccessMask=VK_ACCESS_TRANSFER_READ_BIT;CmdPipelineBarrier(cb,VK_PIPELINE_STAGE_TRANSFER_BIT,VK_PIPELINE_STAGE_TRANSFER_BIT,0,1,&barrier,0,nullptr,0,nullptr);
   CmdCopyBuffer(cb,gpu,host,1,&copy);
   barrier.dstAccessMask=VK_ACCESS_HOST_READ_BIT;CmdPipelineBarrier(cb,VK_PIPELINE_STAGE_TRANSFER_BIT,VK_PIPELINE_STAGE_HOST_BIT,0,1,&barrier,0,nullptr,0,nullptr);check(EndCommandBuffer(cb));
   start=clock();VkSubmitInfo si{VK_STRUCTURE_TYPE_SUBMIT_INFO};si.commandBufferCount=1;si.pCommandBuffers=&cb;check(QueueSubmit(queue,1,&si,fence));check(WaitForFences(device,1,&fence,VK_TRUE,2000000000ull));submit_ms+=elapsed(start);
   start=clock();for(uint64_t at=0;at<bytes;at+=8){uint64_t actual,expected;std::memcpy(&actual,mapped+at,8);std::memcpy(&expected,source.data()+at,8);if(actual!=expected){std::puts("FAIL data");return 5;}sum+=actual;}
   read_ms+=elapsed(start);
  }
  std::printf("round=%u cached=%u memory_type=%u writes_ms=%.3f gpu_roundtrip_ms=%.3f read_compare_ms=%.3f total_ms=%.3f bytes=%llu output=PASS checksum=%llu\n",round,unsigned(wantCached),type,write_ms,submit_ms,read_ms,write_ms+submit_ms+read_ms,(unsigned long long)(bytes*16),(unsigned long long)sum);std::fflush(stdout);
  UnmapMemory(device,memory);DestroyBuffer(device,host,nullptr);FreeMemory(device,memory,nullptr);
 }
 DestroyFence(device,fence,nullptr);DestroyCommandPool(device,pool,nullptr);DestroyBuffer(device,gpu,nullptr);FreeMemory(device,gpuMemory,nullptr);
 ((PFN_vkDestroyDevice)gdp(device,"vkDestroyDevice"))(device,nullptr);((PFN_vkDestroyInstance)gip(instance,"vkDestroyInstance"))(instance,nullptr);
}
