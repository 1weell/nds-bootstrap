/* Exercise the production file transaction with injected I/O errors and exits. */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/wait.h>
static int at, target, mode;
static int checkpoint(void) {
    ++at;
    if (at != target) return 0;
    if (mode == 2) _exit(77);
    errno = EIO;
    return mode == 1;
}
static FILE* test_open(const char* p, const char* m) { if (checkpoint()) return NULL; return fopen(p,m); }
static size_t test_write(const void* p,size_t n,size_t c,FILE* f) { if(checkpoint()) { fwrite(p,n,c/2,f); return c/2; } return fwrite(p,n,c,f); }
static size_t test_read(void* p,size_t n,size_t c,FILE* f) { if(checkpoint()) return 0; return fread(p,n,c,f); }
static int test_flush(FILE* f) { if(checkpoint()) return EOF; return fflush(f); }
static int test_sync(int f) { if(checkpoint()) return -1; return fsync(f); }
static int test_close(FILE* f) { int fail=checkpoint(); int r=fclose(f); return fail ? EOF:r; }
static int test_rename(const char* a,const char* b) { if(checkpoint()) return -1; return rename(a,b); }
static int test_remove(const char* a) { if(checkpoint()) return -1; return remove(a); }
#define fopen test_open
#define fwrite test_write
#define fread test_read
#define fflush test_flush
#define fsync test_sync
#define fclose test_close
#define rename test_rename
#define remove test_remove
#include "../retail/arm9/source/ra_queue_file.c"
#undef fopen
#undef fwrite
#undef fread
#undef fflush
#undef fsync
#undef fclose
#undef rename
#undef remove
static void die(const char* message) { fprintf(stderr,"FAIL queue transaction: %s\n",message); exit(1); }
static void put(const char* path,const char* data,size_t n) {
    FILE* f=fopen(path,"wb");
    if(!f || fwrite(data,1,n,f)!=n || fclose(f)) die("fixture write");
}
int main(void) {
    char dir[]="/tmp/ra-queue-XXXXXX", path[128], bak[128], tmp[128];
    char old[3072], next[3072], got[3073];
    int tests=0, oldsize, fault, m;
    if(!mkdtemp(dir)) die("mkdtemp");
    snprintf(path,sizeof(path),"%s/queue",dir);
    if(!queuePaths(path,bak,tmp)) die("paths");
    memset(old,0,sizeof(old)); memcpy(old,"230047\n",7);
    memset(next,0,sizeof(next)); memcpy(next,"230048\n",7);
    for(oldsize=1024;oldsize<=3072;oldsize+=1024) {
        mode=target=at=0; put(path,old,oldsize);
        if(!raQueueFileReplace(path,next,sizeof(next))) die("normal replacement");
        int steps=at;
        for(m=1;m<=2;++m) for(fault=1;fault<=steps+1;++fault) {
            remove(path); remove(bak); remove(tmp); put(path,old,oldsize);
            pid_t child=fork();
            if(child<0) die("fork");
            if(child==0) { at=0;target=fault;mode=m;raQueueFileReplace(path,next,sizeof(next));_exit(0); }
            int status; waitpid(child,&status,0);
            if(!WIFEXITED(status)) die("child crashed unexpectedly");
            mode=target=at=0;
            if(!raQueueFileRecover(path) || !raQueueFileReady(path)) die("recovery");
            FILE* f=fopen(path,"rb");
            if(!f) die("original missing");
            size_t n=fread(got,1,sizeof(got),f); fclose(f);
            if(!((n==(size_t)oldsize && !memcmp(got,old,n)) ||
                 (n==sizeof(next) && !memcmp(got,next,n)))) die("torn/lost records");
            ++tests;
        }
    }
    /* An outstanding backup blocks cluster handoff and a second rewrite. */
    mode=target=0; put(bak,old,1024);
    if(raQueueFileReady(path) || raQueueFileReplace(path,next,sizeof(next))) die("backup overwritten");
    if(!raQueueFileRecover(path)) die("backup restore");
    remove(path); remove(bak); remove(tmp); rmdir(dir);
    printf("PASSED queue file: %d injected errors/interruption points, 16/32/48-byte formats\n",tests);
    return 0;
}
