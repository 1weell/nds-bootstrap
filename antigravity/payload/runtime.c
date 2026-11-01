/* GPL-3.0. Freestanding routines; no libc is present in TwlBg. */
#include <stddef.h>
void *memcpy(void *dst,const void *src,size_t n) {
    unsigned char *d=dst;const unsigned char *s=src;while(n--)*d++=*s++;return dst;
}
void *memset(void *dst,int value,size_t n) {
    unsigned char *d=dst;while(n--)*d++=(unsigned char)value;return dst;
}
size_t strlen(const char *s) {size_t n=0;while(s[n])n++;return n;}
int strcmp(const char *a,const char *b) {
    while(*a && *a==*b){a++;b++;}return (unsigned char)*a-(unsigned char)*b;
}
int strncmp(const char *a,const char *b,size_t n) {
    while(n && *a && *a==*b){a++;b++;n--;}
    return n?(unsigned char)*a-(unsigned char)*b:0;
}
