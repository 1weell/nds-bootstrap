/* Recoverable launcher queue replacement. No network or credentials here. */
#include "ra_queue_file.h"
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <sys/stat.h>
#include <unistd.h>

static int queuePaths(const char* path, char* backup, char* temporary) {
	if (strlen(path) + 19 >= 128) return 0;
	sprintf(backup, "%s.ra-rewrite-backup", path);
	sprintf(temporary, "%s.ra-rewrite-new", path);
	return 1;
}

int raQueueFileReady(const char* path) {
	char backup[128], temporary[128];
	struct stat st;
	if (!queuePaths(path, backup, temporary)) return 0;
	if (stat(backup, &st) == 0) return 0;
	return errno == ENOENT;
}

int raQueueFileRecover(const char* path) {
	char backup[128], temporary[128];
	struct stat st;
	if (!queuePaths(path, backup, temporary)) return 0;
	if (stat(backup, &st) != 0) return errno == ENOENT;
	/* A backup means the previous commit never finished. No game may use the
	 * replacement until the backup has been removed. Retry already sent IDs
	 * rather than lose any records from the previous queue. */
	if (remove(path) != 0 && errno != ENOENT) return 0;
	return rename(backup, path) == 0;
}

int raQueueFileReplace(const char* path, const void* bytes, size_t length) {
	char backup[128], temporary[128];
	unsigned char chunk[128];
	const unsigned char* expected = bytes;
	size_t offset = 0;
	FILE* out;
	struct stat st;
	int existed, ok;
	if (!queuePaths(path, backup, temporary) || !raQueueFileReady(path)) return 0;
	existed = stat(path, &st) == 0;
	if (!existed && errno != ENOENT) return 0;
	out = fopen(temporary, "wb");
	if (!out) return 0;
	ok = fwrite(bytes, 1, length, out) == length;
	if (fflush(out) != 0) ok = 0;
	if (fsync(fileno(out)) != 0) ok = 0;
	if (fclose(out) != 0) ok = 0;
	if (!ok) return 0;
	out = fopen(temporary, "rb");
	if (!out) return 0;
	while (offset < length) {
		size_t n = length - offset;
		if (n > sizeof(chunk)) n = sizeof(chunk);
		if (fread(chunk, 1, n, out) != n || memcmp(chunk, expected + offset, n)) {
			ok = 0;
			break;
		}
		offset += n;
	}
	if (fgetc(out) != EOF || ferror(out)) ok = 0;
	if (fclose(out) != 0) ok = 0;
	if (!ok) return 0;
	if (existed && rename(path, backup) != 0) return 0;
	if (rename(temporary, path) != 0) {
		if (existed) raQueueFileRecover(path);
		return 0;
	}
	/* Failure leaves the recovery copy, so the cluster handoff stays disabled. */
	if (existed && remove(backup) != 0) return 0;
	return 1;
}
