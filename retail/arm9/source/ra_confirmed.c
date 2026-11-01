/* Positive server acknowledgements survive stale unlock queries. No credentials
 * are stored: a case-folded account digest binds each checksummed ROM sidecar. */
#include "ra_confirmed.h"
#include "ra_wifi.h"
#if RA_LAUNCHER_WIFI
#include <string.h>
#include "rhash/md5.h"

static void accountDigest(const char* user, unsigned char out[16]) {
    md5_state_t md5;
    md5_init(&md5);
    while (*user) {
        unsigned char c = (unsigned char)*user++;
        if (c >= 'A' && c <= 'Z') c += 'a' - 'A';
        md5_append(&md5, &c, 1);
    }
    md5_finish(&md5, out);
}
void raConfirmedUserKey(const char* user, char out[33]) {
    static const char hex[] = "0123456789abcdef";
    unsigned char digest[16];
    unsigned i;
    accountDigest(user, digest);
    for (i = 0; i < 16; ++i) {
        out[2*i] = hex[digest[i] >> 4];
        out[2*i+1] = hex[digest[i] & 15];
    }
    out[32] = 0;
}
int raConfirmedAdd(raConfirmed* confirmed, uint32_t id) {
    unsigned i;
    if (!id || id >= RA_ODD_ID_FROM || confirmed->count > RA_CONFIRMED_MAX) return -1;
    for (i = 0; i < confirmed->count; ++i)
        if (confirmed->ids[i] == id) return 0;
    if (confirmed->count >= RA_CONFIRMED_MAX) return -1;
    confirmed->ids[confirmed->count++] = id;
    return 1;
}
int raConfirmedMerge(const raConfirmed* confirmed, uint32_t* ids, int count, int capacity) {
    unsigned i;
    if (count < 0 || count > capacity || confirmed->count > RA_CONFIRMED_MAX) return count;
    for (i = 0; i < confirmed->count && count < capacity; ++i) {
        int k;
        for (k = 0; k < count && ids[k] != confirmed->ids[i]; ++k) {}
        if (k == count) ids[count++] = confirmed->ids[i];
    }
    return count;
}
static void put32(unsigned char* bytes, uint32_t n) {
    bytes[0] = n; bytes[1] = n >> 8; bytes[2] = n >> 16; bytes[3] = n >> 24;
}
static uint32_t get32(const unsigned char* bytes) {
    return (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8)
         | ((uint32_t)bytes[2] << 16) | ((uint32_t)bytes[3] << 24);
}
int raConfirmedEncode(const raConfirmed* confirmed, const char* user, unsigned char* out, size_t capacity) {
    md5_state_t md5;
    unsigned i;
    size_t body;
    if (confirmed->count > RA_CONFIRMED_MAX) return -1;
    body = 24 + 4 * confirmed->count;
    if (capacity < body + 16) return -1;
    memcpy(out, "RAC1", 4);
    accountDigest(user, out + 4);
    put32(out + 20, confirmed->count);
    for (i = 0; i < confirmed->count; ++i) put32(out + 24 + 4*i, confirmed->ids[i]);
    md5_init(&md5); md5_append(&md5, out, body); md5_finish(&md5, out + body);
    return (int)(body + 16);
}
int raConfirmedDecode(raConfirmed* confirmed, const char* user, const unsigned char* bytes, size_t length) {
    unsigned char digest[16], account[16];
    md5_state_t md5;
    raConfirmed staged;
    uint32_t count, i;
    if (length < 40 || memcmp(bytes, "RAC1", 4)) return 0;
    count = get32(bytes + 20);
    if (count > RA_CONFIRMED_MAX || length != 40 + 4*count) return 0;
    accountDigest(user, account);
    if (memcmp(account, bytes + 4, 16)) return 0;
    md5_init(&md5); md5_append(&md5, bytes, length - 16); md5_finish(&md5, digest);
    if (memcmp(digest, bytes + length - 16, 16)) return 0;
    memset(&staged, 0, sizeof(staged));
    for (i = 0; i < count; ++i)
        if (raConfirmedAdd(&staged, get32(bytes + 24 + 4*i)) != 1) return 0;
    *confirmed = staged;
    return 1;
}
#endif
