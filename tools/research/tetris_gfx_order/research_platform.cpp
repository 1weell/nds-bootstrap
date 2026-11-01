#include "Platform.h"
#include <cstdio>
#include <cstdarg>
#include <cstring>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <chrono>
namespace melonDS::Platform {
struct FileHandle { FILE* f; };
struct Thread { std::thread t; };
struct Mutex { std::mutex m; };
struct Semaphore { std::mutex m; std::condition_variable cv; int n=0; };
struct AACDecoder {};
struct DynamicLibrary {};
void SignalStop(StopReason r,void*) { fprintf(stderr,"STOP %d\n",int(r)); }
std::string GetLocalFilePath(const std::string& f) { return f; }
FileHandle* OpenFile(const std::string& p,FileMode m) {
 const char* mode=(m&Write)?((m&Preserve)?"r+b":((m&Read)?"w+b":"wb")):"rb";
 FILE* f=fopen(p.c_str(),mode);return f?new FileHandle{f}:nullptr;
}
FileHandle* OpenLocalFile(const std::string& p,FileMode m) { return OpenFile(p,m); }
bool FileExists(const std::string& p) { auto f=OpenFile(p,Read);if(!f)return false;CloseFile(f);return true; }
bool LocalFileExists(const std::string& p) { return FileExists(p); }
bool CheckFileWritable(const std::string&) { return true; }
bool CheckLocalFileWritable(const std::string&) { return true; }
bool CloseFile(FileHandle* f) { if(!f)return false;int r=fclose(f->f);delete f;return r==0; }
bool IsEndOfFile(FileHandle* f) { return feof(f->f); }
bool FileReadLine(char* s,int n,FileHandle* f) { return fgets(s,n,f->f)!=nullptr; }
u64 FilePosition(FileHandle* f) { return ftell(f->f); }
bool FileSeek(FileHandle* f,s64 n,FileSeekOrigin o) { return !fseek(f->f,n,o==FileSeekOrigin::Start?SEEK_SET:o==FileSeekOrigin::Current?SEEK_CUR:SEEK_END); }
void FileRewind(FileHandle* f) { rewind(f->f); }
u64 FileRead(void* p,u64 s,u64 n,FileHandle* f) { return fread(p,s,n,f->f); }
u64 FileWrite(const void* p,u64 s,u64 n,FileHandle* f) { return fwrite(p,s,n,f->f); }
bool FileFlush(FileHandle* f) { return !fflush(f->f); }
u64 FileWriteFormatted(FileHandle* f,const char* fmt,...) { va_list a;va_start(a,fmt);int r=vfprintf(f->f,fmt,a);va_end(a);return r; }
u64 FileLength(FileHandle* f) { long p=ftell(f->f);fseek(f->f,0,SEEK_END);long n=ftell(f->f);fseek(f->f,p,SEEK_SET);return n; }
void Log(LogLevel l,const char* fmt,...) { if(l<Warn)return;va_list a;va_start(a,fmt);vfprintf(stderr,fmt,a);va_end(a); }
Thread* Thread_Create(std::function<void()> f) { return new Thread{std::thread(std::move(f))}; }
void Thread_Wait(Thread* t) { if(t&&t->t.joinable())t->t.join(); }
void Thread_Free(Thread* t) { Thread_Wait(t);delete t; }
Semaphore* Semaphore_Create() { return new Semaphore; }
void Semaphore_Free(Semaphore* s) { delete s; }
void Semaphore_Reset(Semaphore* s) { std::lock_guard<std::mutex> l(s->m);s->n=0; }
void Semaphore_Wait(Semaphore* s) { std::unique_lock<std::mutex> l(s->m);s->cv.wait(l,[&]{return s->n>0;});--s->n; }
bool Semaphore_TryWait(Semaphore* s,int ms) { std::unique_lock<std::mutex> l(s->m);if(!s->cv.wait_for(l,std::chrono::milliseconds(ms),[&]{return s->n>0;}))return false;--s->n;return true; }
void Semaphore_Post(Semaphore* s,int n) { std::lock_guard<std::mutex> l(s->m);s->n+=n;s->cv.notify_all(); }
Mutex* Mutex_Create() { return new Mutex; }
void Mutex_Free(Mutex* m) { delete m; }
void Mutex_Lock(Mutex* m) { m->m.lock(); }
void Mutex_Unlock(Mutex* m) { m->m.unlock(); }
bool Mutex_TryLock(Mutex* m) { return m->m.try_lock(); }
void Sleep(u64 us) { std::this_thread::sleep_for(std::chrono::microseconds(us)); }
u64 GetUSCount() { return std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now().time_since_epoch()).count(); }
u64 GetMSCount() { return GetUSCount()/1000; }
void WriteNDSSave(const u8*,u32,u32,u32,void*) {}
void WriteGBASave(const u8*,u32,u32,u32,void*) {}
void WriteFirmware(const Firmware&,u32,u32,void*) {}
void WriteDateTime(int,int,int,int,int,int,void*) {}
void MP_Begin(void*) {} void MP_End(void*) {}
int MP_SendPacket(u8*,int,u64,void*) { return 0; }
int MP_RecvPacket(u8*,u64*,void*) { return 0; }
int MP_SendCmd(u8*,int,u64,void*) { return 0; }
int MP_SendReply(u8*,int,u64,u16,void*) { return 0; }
int MP_SendAck(u8*,int,u64,void*) { return 0; }
int MP_RecvHostPacket(u8*,u64*,void*) { return 0; }
u16 MP_RecvReplies(u8*,u64,u16,void*) { return 0; }
int Net_SendPacket(u8*,int,void*) { return 0; }
int Net_RecvPacket(u8*,void*) { return 0; }
void Camera_Start(int,void*) {} void Camera_Stop(int,void*) {}
void Camera_CaptureFrame(int,u32* p,int w,int h,bool,void*) { memset(p,0,w*h*4); }
void Mic_Start(void*) {} void Mic_Stop(void*) {}
int Mic_ReadInput(s16*,int,void*) { return 0; }
AACDecoder* AAC_Init() { return nullptr; }
void AAC_DeInit(AACDecoder*) {}
bool AAC_Configure(AACDecoder*,int,int) { return false; }
bool AAC_DecodeFrame(AACDecoder*,const void*,int,void*,int) { return false; }
bool Addon_KeyDown(KeyType,void*) { return false; }
void Addon_RumbleStart(u32,void*) {} void Addon_RumbleStop(void*) {}
float Addon_MotionQuery(MotionQueryType,void*) { return 0; }
DynamicLibrary* DynamicLibrary_Load(const char*) { return nullptr; }
void DynamicLibrary_Unload(DynamicLibrary*) {}
void* DynamicLibrary_LoadFunction(DynamicLibrary*,const char*) { return nullptr; }
}
