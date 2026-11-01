/* GPL-3.0. Small recoverable cache, separate from legacy achievement/queue files. */
#include "ra_metadata.h"
#include <stdio.h>

static int path_suffix(char *out,size_t size,const char *path,const char *suffix) {
    size_t n=strlen(path),k=strlen(suffix);
    if(n+k>=size)return 0;
    memcpy(out,path,n);memcpy(out+n,suffix,k+1);return 1;
}
static int valid(const uint8_t *r,const char *hash,uint32_t game,char *title) {
    if(strlen(hash)!=32 || memcmp(r,"RAM1",4) || ra_bridge_get32(r+4)!=1 ||
       !game || ra_bridge_get32(r+8)!=game || memcmp(r+16,hash,32) ||
       ra_bridge_crc(r,144)!=((uint16_t)r[144]|((uint16_t)r[145]<<8)) ||
       !memchr(r+48,0,RA_BRIDGE_TEXT))return 0;
    if(ra_bridge_text(title,RA_BRIDGE_TEXT,(const char *)r+48) || strcmp(title,(const char *)r+48))return 0;
    return title[0]!=0;
}
static int read_record(const char *path,uint8_t *r) {
    FILE *f=fopen(path,"rb");if(!f)return 0;
    size_t n=fread(r,1,RA_METADATA_BYTES,f);
    int ok=n==RA_METADATA_BYTES && fgetc(f)==EOF && !ferror(f);
    if(fclose(f))ok=0;
    return ok;
}
int raMetadataLoad(const char *path,const char *hash,uint32_t game,char *title) {
    uint8_t r[RA_METADATA_BYTES];char backup[160];
    if(read_record(path,r)&&valid(r,hash,game,title))return 1;
    if(!path_suffix(backup,sizeof(backup),path,".bak"))return 0;
    return read_record(backup,r)&&valid(r,hash,game,title);
}
int raMetadataSave(const char *path,const char *hash,uint32_t game,uint32_t revision,const char *title) {
    uint8_t r[RA_METADATA_BYTES]={0},check[RA_METADATA_BYTES];char tmp[160],backup[160],clean[RA_BRIDGE_TEXT];
    if(strlen(hash)!=32 || !game || !title[0] || ra_bridge_text(clean,sizeof(clean),title) || strcmp(clean,title))return 0;
    if(!path_suffix(tmp,sizeof(tmp),path,".tmp") ||
       !path_suffix(backup,sizeof(backup),path,".bak"))return 0;
    memcpy(r,"RAM1",4);ra_bridge_put32(r+4,1);ra_bridge_put32(r+8,game);
    ra_bridge_put32(r+12,revision);memcpy(r+16,hash,32);memcpy(r+48,title,strlen(title));
    uint16_t crc=ra_bridge_crc(r,144);r[144]=(uint8_t)crc;r[145]=(uint8_t)(crc>>8);
    FILE *f=fopen(tmp,"wb");if(!f)return 0;
    int ok=fwrite(r,1,sizeof(r),f)==sizeof(r);if(fclose(f))ok=0;
    if(!ok || !read_record(tmp,check) || memcmp(check,r,sizeof(r)))return 0;
    /* Keep a valid previous generation until the verified replacement has a name. */
    char previous[RA_BRIDGE_TEXT],bad[160];
    int old=read_record(path,check)&&valid(check,hash,game,previous),bad_moved=0;
    FILE *existing=fopen(path,"rb");int exists=existing!=NULL;if(existing)fclose(existing);
    if(old) {
        remove(backup);
        if(rename(path,backup))return 0;
    } else if(exists) {
        if(!path_suffix(bad,sizeof(bad),path,".bad"))return 0;
        FILE *held=fopen(bad,"rb");if(held){fclose(held);return 0;}
        if(rename(path,bad))return 0;
        bad_moved=1; /* Keep corrupt bytes and the valid previous generation. */
    }
    if(rename(tmp,path)) {
        if(old)rename(backup,path);
        if(bad_moved)rename(bad,path);
        return 0;
    }
    return read_record(path,check)&&!memcmp(check,r,sizeof(r));
}
