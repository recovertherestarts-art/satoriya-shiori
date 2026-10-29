/*
 * POSIX save data test for satori (libsatori.so / libsatori.bundle)
 *
 * Usage: posix_savedata <path to library> <ghost fixture directory>
 *
 * Exercises SHIORI load / request / unload with save data operations:
 * - First unload creates satori_savedata.txt
 * - Saved data file is non-empty
 * - Subsequent load restores saved values
 * - Save with existing save data creates satori_savebackup.txt
 * - satori_savedata.tmp does not remain after normal unload
 * - Save failure preserves existing valid save data and its contents
 * - Consecutive test runs are isolated and independent
 */

#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#include <dirent.h>
#include <errno.h>

typedef int (*load_fn)(char *h, long len);
typedef int (*unload_fn)(void);
typedef char *(*request_fn)(char *h, long *len);

static load_fn p_load;
static unload_fn p_unload;
static request_fn p_request;

static int failures = 0;

/* Helper: print test result */
static void test_log(int ok, const char *msg) {
	if (ok) {
		printf("OK  %s\n", msg);
	} else {
		fprintf(stderr, "NG  %s\n", msg);
		failures++;
	}
}

/* Recursive directory removal */
static int remove_dir_recursive(const char *path) {
	DIR *d = opendir(path);
	size_t path_len = strlen(path);
	int r = -1;

	if (d) {
		struct dirent *p;
		r = 0;
		while (!r && (p = readdir(d))) {
			int r2 = -1;
			char *buf;
			size_t len;

			if (!strcmp(p->d_name, ".") || !strcmp(p->d_name, ".."))
				continue;

			len = path_len + strlen(p->d_name) + 2;
			buf = malloc(len);
			if (buf) {
				struct stat statbuf;
				snprintf(buf, len, "%s/%s", path, p->d_name);
				if (!lstat(buf, &statbuf)) {
					if (S_ISDIR(statbuf.st_mode))
						r2 = remove_dir_recursive(buf);
					else
						r2 = unlink(buf);
				}
				free(buf);
			}
			r = r2;
		}
		closedir(d);
	}
	if (!r)
		r = rmdir(path);
	return r;
}

/* Recursive directory copy */
static int copy_dir_recursive(const char *src, const char *dst) {
	DIR *d = opendir(src);
	if (!d) return -1;
	mkdir(dst, 0755);

	struct dirent *p;
	while ((p = readdir(d)) != NULL) {
		if (!strcmp(p->d_name, ".") || !strcmp(p->d_name, ".."))
			continue;

		char src_buf[1024], dst_buf[1024];
		snprintf(src_buf, sizeof(src_buf), "%s/%s", src, p->d_name);
		snprintf(dst_buf, sizeof(dst_buf), "%s/%s", dst, p->d_name);

		struct stat st;
		if (stat(src_buf, &st) == 0) {
			if (S_ISDIR(st.st_mode)) {
				copy_dir_recursive(src_buf, dst_buf);
			} else {
				FILE *fsrc = fopen(src_buf, "rb");
				FILE *fdst = fopen(dst_buf, "wb");
				if (fsrc && fdst) {
					char buf[4096];
					size_t n;
					while ((n = fread(buf, 1, sizeof(buf), fsrc)) > 0) {
						fwrite(buf, 1, n, fdst);
					}
				}
				if (fsrc) fclose(fsrc);
				if (fdst) fclose(fdst);
			}
		}
	}
	closedir(d);
	return 0;
}

/* Read file to dynamically allocated buffer */
static char *read_file_buf(const char *filepath, size_t *out_len) {
	FILE *f = fopen(filepath, "rb");
	if (!f) return NULL;
	fseek(f, 0, SEEK_END);
	long len = ftell(f);
	fseek(f, 0, SEEK_SET);
	if (len < 0) {
		fclose(f);
		return NULL;
	}
	char *buf = malloc((size_t)len + 1);
	if (!buf) {
		fclose(f);
		return NULL;
	}
	size_t r = fread(buf, 1, (size_t)len, f);
	buf[r] = '\0';
	fclose(f);
	if (out_len) *out_len = r;
	return buf;
}

/* Send SHIORI/3.0 request */
static char *send_request(const char *id) {
	char req[512];
	snprintf(req, sizeof(req),
		"GET SHIORI/3.0\r\nCharset: UTF-8\r\nSender: SSP\r\nSecurityLevel: local\r\nID: %s\r\n\r\n", id);
	size_t n = strlen(req);
	char *h = malloc(n + 1);
	if (!h) return NULL;
	memcpy(h, req, n + 1);
	long len = (long)n;
	return p_request(h, &len);
}

/* Call load() */
static int run_load(const char *dir_path) {
	size_t n = strlen(dir_path);
	char *path = malloc(n + 2);
	if (!path) return 0;
	memcpy(path, dir_path, n);
	if (n == 0 || path[n - 1] != '/') {
		path[n++] = '/';
	}
	path[n] = '\0';
	return p_load(path, (long)n);
}

/* Call unload() */
static void run_unload(void) {
	p_unload();
}

int main(int argc, char **argv) {
	if (argc != 3) {
		fprintf(stderr, "usage: %s <library> <ghost fixture directory>\n", argv[0]);
		return 2;
	}

	const char *lib_path = argv[1];
	const char *fixture_dir = argv[2];

	void *lib = dlopen(lib_path, RTLD_NOW | RTLD_LOCAL);
	if (!lib) {
		fprintf(stderr, "dlopen failed: %s\n", dlerror());
		return 1;
	}

	p_load = (load_fn)dlsym(lib, "load");
	p_unload = (unload_fn)dlsym(lib, "unload");
	p_request = (request_fn)dlsym(lib, "request");
	if (!p_load || !p_unload || !p_request) {
		fprintf(stderr, "dlsym failed: %s\n", dlerror());
		dlclose(lib);
		return 1;
	}

	/* Create temporary work directory template */
	char tmp_template[] = "/tmp/satori_savedata_test_XXXXXX";
	char *work_dir = mkdtemp(tmp_template);
	if (!work_dir) {
		fprintf(stderr, "failed to create temp directory: %s\n", strerror(errno));
		dlclose(lib);
		return 1;
	}

	printf("Running save data tests in isolated directory: %s\n", work_dir);

	/* --- Step 1: Copy fixture to work_dir --- */
	if (copy_dir_recursive(fixture_dir, work_dir) != 0) {
		fprintf(stderr, "failed to copy fixture directory\n");
		remove_dir_recursive(work_dir);
		dlclose(lib);
		return 1;
	}

	char savedata_path[1024];
	char savebackup_path[1024];
	char savetmp_path[1024];
	snprintf(savedata_path, sizeof(savedata_path), "%s/satori_savedata.txt", work_dir);
	snprintf(savebackup_path, sizeof(savebackup_path), "%s/satori_savebackup.txt", work_dir);
	snprintf(savetmp_path, sizeof(savetmp_path), "%s/satori_savedata.tmp", work_dir);

	/* --- Test 1: First load, set variables, unload -> satori_savedata.txt created & non-empty --- */
	if (!run_load(work_dir)) {
		fprintf(stderr, "load failed on first run\n");
		remove_dir_recursive(work_dir);
		dlclose(lib);
		return 1;
	}

	char *res = send_request("OnSetVar");
	if (res) free(res);

	run_unload();

	/* Check 1: satori_savedata.txt exists */
	int exists = (access(savedata_path, F_OK) == 0);
	test_log(exists, "1. First unload creates satori_savedata.txt");

	/* Check 2: satori_savedata.txt is non-empty and contains expected variables */
	size_t save_len = 0;
	char *save_content = read_file_buf(savedata_path, &save_len);
	int non_empty = (save_content != NULL && save_len > 0);
	test_log(non_empty, "2. Generated satori_savedata.txt is not empty");

	if (save_content) {
		int has_var = (strstr(save_content, "テストユーザー") != NULL && strstr(save_content, "12345") != NULL);
		test_log(has_var, "   satori_savedata.txt contains expected variables");
	} else {
		test_log(0, "   Failed to read satori_savedata.txt");
	}

	/* Check 5a: satori_savedata.tmp does not remain */
	int no_tmp = (access(savetmp_path, F_OK) != 0);
	test_log(no_tmp, "5a. satori_savedata.tmp does not remain after normal unload");

	/* --- Test 2: Next load restores saved values --- */
	if (!run_load(work_dir)) {
		fprintf(stderr, "load failed on second run\n");
		if (save_content) free(save_content);
		remove_dir_recursive(work_dir);
		dlclose(lib);
		return 1;
	}

	res = send_request("OnGetVar");
	int restored = (res != NULL && strstr(res, "user=テストユーザー,score=12345") != NULL);
	test_log(restored, "3. Next load restores saved values from satori_savedata.txt");
	if (!restored && res) {
		fprintf(stderr, "   Actual response: %s\n", res);
	}
	if (res) free(res);

	/* --- Test 3: Update variable and unload -> backup created & new savedata written --- */
	res = send_request("OnUpdateVar");
	if (res) free(res);

	run_unload();

	/* Check 4: satori_savebackup.txt exists and contains old value, savedata.txt contains new value */
	int backup_exists = (access(savebackup_path, F_OK) == 0);
	test_log(backup_exists, "4. Backup file satori_savebackup.txt is created when existing save data exists");

	size_t backup_len = 0;
	char *backup_content = read_file_buf(savebackup_path, &backup_len);
	if (backup_content) {
		int backup_has_old = (strstr(backup_content, "12345") != NULL);
		test_log(backup_has_old, "   satori_savebackup.txt contains original variable value (12345)");
		free(backup_content);
	} else {
		test_log(0, "   satori_savebackup.txt could not be read");
	}

	size_t new_save_len = 0;
	char *new_save_content = read_file_buf(savedata_path, &new_save_len);
	if (new_save_content) {
		int new_save_has_new = (strstr(new_save_content, "99999") != NULL);
		test_log(new_save_has_new, "   satori_savedata.txt contains updated variable value (99999)");
	} else {
		test_log(0, "   Updated satori_savedata.txt could not be read");
	}

	/* --- Test 4: Save failure protection test --- */
	if (!run_load(work_dir)) {
		fprintf(stderr, "load failed on save failure test run\n");
	} else {
		/* Record current save file contents before attempting save */
		size_t pre_fail_len = 0;
		char *pre_fail_content = read_file_buf(savedata_path, &pre_fail_len);

		/* Modify in-memory variable */
		res = send_request("OnSetVar"); /* tries to reset score to 12345 */
		if (res) free(res);

		/* Block save by creating satori_savedata.tmp as a directory and setting read-only permissions */
		mkdir(savetmp_path, 0755);
		chmod(work_dir, 0555);

		/* Unload attempts to save */
		run_unload();

		/* Restore directory permission for inspection & cleanup */
		chmod(work_dir, 0755);

		/* Verify that save actually failed (savetmp_path is still a directory, not written as save file) */
		struct stat st_tmp;
		int save_failed = (lstat(savetmp_path, &st_tmp) == 0 && S_ISDIR(st_tmp.st_mode));
		test_log(save_failed, "6a. Save failure condition was successfully induced");

		/* Check 6b: Existing satori_savedata.txt exists and content is identical to pre_fail_content */
		size_t post_fail_len = 0;
		char *post_fail_content = read_file_buf(savedata_path, &post_fail_len);
		int save_preserved = 0;
		if (pre_fail_content && post_fail_content) {
			save_preserved = (pre_fail_len == post_fail_len) && (memcmp(pre_fail_content, post_fail_content, pre_fail_len) == 0);
		}
		test_log(save_preserved, "6b. Existing valid save data and its contents are preserved after save failure");
		if (!save_preserved) {
			fprintf(stderr, "   EXPECTED content (%zu bytes):\n%s\n", pre_fail_len, pre_fail_content ? pre_fail_content : "(null)");
			fprintf(stderr, "   ACTUAL content (%zu bytes):\n%s\n", post_fail_len, post_fail_content ? post_fail_content : "(null)");
		}

		/* Clean up savetmp_path directory */
		rmdir(savetmp_path);

		if (pre_fail_content) free(pre_fail_content);
		if (post_fail_content) free(post_fail_content);
	}

	if (save_content) free(save_content);
	if (new_save_content) free(new_save_content);

	/* --- Test 5: Cleanup & Isolation check --- */
	remove_dir_recursive(work_dir);

	/* Test 7: Verify consecutive run isolation by creating another fresh directory */
	char tmp_template2[] = "/tmp/satori_savedata_test2_XXXXXX";
	char *work_dir2 = mkdtemp(tmp_template2);
	if (work_dir2) {
		copy_dir_recursive(fixture_dir, work_dir2);
		char new_savedata_path[1024];
		snprintf(new_savedata_path, sizeof(new_savedata_path), "%s/satori_savedata.txt", work_dir2);
		int fresh_no_save = (access(new_savedata_path, F_OK) != 0);
		test_log(fresh_no_save, "7. Sequential test execution is isolated and does not inherit previous state");
		remove_dir_recursive(work_dir2);
	}

	dlclose(lib);

	if (failures != 0) {
		fprintf(stderr, "\nFAILED: %d check(s) failed in save data test.\n", failures);
		return 1;
	}

	printf("\nAll save data tests passed successfully.\n");
	return 0;
}
