#ifndef RA_QUEUE_FILE_H
#define RA_QUEUE_FILE_H

#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif

/* Recover an interrupted launcher rewrite before opening the queue or handing
 * its cluster to ARM7. False means leave all files alone and disable appends. */
int raQueueFileRecover(const char* path);
int raQueueFileReady(const char* path);
/* Checked temporary write, readback, then rename with a recovery copy. FAT is
 * not a journaled filesystem; this cannot guarantee survival of physical loss. */
int raQueueFileReplace(const char* path, const void* bytes, size_t length);

#ifdef __cplusplus
}
#endif
#endif
