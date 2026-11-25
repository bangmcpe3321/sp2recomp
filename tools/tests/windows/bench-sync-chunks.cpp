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
 constexpr uint64_t bytes=8ull<<20;
 struct Buffer {VkBuffer buffer;VkDeviceMemory memory;};
 auto buffer=[&](VkMemoryPropertyFlags wanted){
  Buffer b{};VkBufferCreateInfo ci{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};ci.size=bytes;ci.usage=VK_BUFFER_USAGE_TRANSFER_SRC_BIT|VK_BUFFER_USAGE_TRANSFER_DST_BIT;
  check(CreateBuffer(device,&ci,nullptr,&b.buffer));VkMemoryRequirements req;GetBufferMemoryRequirements(device,b.buffer,&req);
  uint32_t type=0;while(type<mp.memoryTypeCount && (!(req.memoryTypeBits&(1u<<type)) || (mp.memoryTypes[type].propertyFlags&wanted)!=wanted))++type;
  if(type==mp.memoryTypeCount)std::exit(3);
  VkMemoryAllocateInfo ai{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};ai.allocationSize=req.size;ai.memoryTypeIndex=type;
  check(AllocateMemory(device,&ai,nullptr,&b.memory));check(BindBufferMemory(device,b.buffer,b.memory,0));return b;
 };
 Buffer a=buffer(VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT),b=buffer(VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT),out=buffer(VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT|VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
 uint32_t* mapped=nullptr;check(MapMemory(device,out.memory,0,VK_WHOLE_SIZE,0,(void**)&mapped));
 VkCommandPoolCreateInfo pi{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};pi.queueFamilyIndex=family;VkCommandPool pool;check(CreateCommandPool(device,&pi,nullptr,&pool));
 VkCommandBuffer cbs[8];VkCommandBufferAllocateInfo cai{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};cai.commandPool=pool;cai.level=VK_COMMAND_BUFFER_LEVEL_PRIMARY;cai.commandBufferCount=8;check(AllocateCommandBuffers(device,&cai,cbs));
 VkFenceCreateInfo fi{VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};VkFence fence;check(CreateFence(device,&fi,nullptr,&fence));
 auto barrier=[&](VkCommandBuffer cb){VkMemoryBarrier mb{VK_STRUCTURE_TYPE_MEMORY_BARRIER};mb.srcAccessMask=VK_ACCESS_MEMORY_WRITE_BIT;mb.dstAccessMask=VK_ACCESS_MEMORY_READ_BIT|VK_ACCESS_MEMORY_WRITE_BIT;CmdPipelineBarrier(cb,VK_PIPELINE_STAGE_ALL_COMMANDS_BIT,VK_PIPELINE_STAGE_ALL_COMMANDS_BIT,0,1,&mb,0,nullptr,0,nullptr);};
 for(unsigned round=0;round<6;round++){
  bool chunked=round%2;check(ResetCommandPool(device,pool,0));check(ResetFences(device,1,&fence));
  auto start=std::chrono::steady_clock::now();
  for(unsigned part=0;part<8;part++){
   auto cb=cbs[part];VkCommandBufferBeginInfo bi{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};bi.flags=VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;check(BeginCommandBuffer(cb,&bi));barrier(cb);
   CmdFillBuffer(cb,a.buffer,0,bytes,round*256+part);barrier(cb);
   VkBufferCopy copy{0,0,bytes};
   for(unsigned work=0;work<12;work++){CmdCopyBuffer(cb,a.buffer,b.buffer,1,&copy);barrier(cb);CmdCopyBuffer(cb,b.buffer,a.buffer,1,&copy);barrier(cb);}
   if(part==7){CmdCopyBuffer(cb,a.buffer,out.buffer,1,&copy);VkMemoryBarrier mb{VK_STRUCTURE_TYPE_MEMORY_BARRIER};mb.srcAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT;mb.dstAccessMask=VK_ACCESS_HOST_READ_BIT;CmdPipelineBarrier(cb,VK_PIPELINE_STAGE_TRANSFER_BIT,VK_PIPELINE_STAGE_HOST_BIT,0,1,&mb,0,nullptr,0,nullptr);}
   check(EndCommandBuffer(cb));
   if(chunked){VkSubmitInfo si{VK_STRUCTURE_TYPE_SUBMIT_INFO};si.commandBufferCount=1;si.pCommandBuffers=&cb;check(QueueSubmit(queue,1,&si,part==7?fence:VK_NULL_HANDLE));}
   // Model CPU work still needed for subsequent command recording.
   std::this_thread::sleep_for(std::chrono::milliseconds(2));
  }
  if(!chunked){VkSubmitInfo si{VK_STRUCTURE_TYPE_SUBMIT_INFO};si.commandBufferCount=8;si.pCommandBuffers=cbs;check(QueueSubmit(queue,1,&si,fence));}
  check(WaitForFences(device,1,&fence,VK_TRUE,2000000000ull));
  double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
  for(uint64_t i=0;i<bytes/4;i++)if(mapped[i]!=round*256+7){std::printf("FAIL output round%u word%llu\n",round,(unsigned long long)i);return 4;}
  std::printf("round=%u chunked=%u full_submit_ms=%.3f output=PASS\n",round,unsigned(chunked),ms);std::fflush(stdout);
 }
 UnmapMemory(device,out.memory);DestroyFence(device,fence,nullptr);DestroyCommandPool(device,pool,nullptr);
 for(auto item:{a,b,out}){DestroyBuffer(device,item.buffer,nullptr);FreeMemory(device,item.memory,nullptr);}
 ((PFN_vkDestroyDevice)gdp(device,"vkDestroyDevice"))(device,nullptr);((PFN_vkDestroyInstance)gip(instance,"vkDestroyInstance"))(instance,nullptr);
}
