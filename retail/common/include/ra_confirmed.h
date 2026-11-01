#ifndef RA_CONFIRMED_H
#define RA_CONFIRMED_H
#include <stdint.h>
#include <stddef.h>

#define RA_CONFIRMED_MAX 128
#define RA_CONFIRMED_BYTES (40 + RA_CONFIRMED_MAX * 4)
typedef struct raConfirmed {
    uint32_t ids[RA_CONFIRMED_MAX];
    uint16_t count;
} raConfirmed;

void raConfirmedUserKey(const char* user, char out[33]);
int raConfirmedAdd(raConfirmed* confirmed, uint32_t id);
int raConfirmedMerge(const raConfirmed* confirmed, uint32_t* ids, int count, int capacity);
int raConfirmedEncode(const raConfirmed* confirmed, const char* user, unsigned char* out, size_t capacity);
int raConfirmedDecode(raConfirmed* confirmed, const char* user, const unsigned char* bytes, size_t length);
#endif
