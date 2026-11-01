/* GPL-3.0. Hash-bound display metadata; never a server/session acknowledgement. */
#ifndef RA_METADATA_H
#define RA_METADATA_H
#include "ra_bridge.h"
#define RA_METADATA_BYTES 146
int raMetadataLoad(const char *path,const char *hash,uint32_t game,char *title);
int raMetadataSave(const char *path,const char *hash,uint32_t game,uint32_t revision,const char *title);
#endif
