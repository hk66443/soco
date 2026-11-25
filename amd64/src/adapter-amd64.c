#define _GNU_SOURCE
/* soco 0.1.0 - panel adapter for soga v2.18.1 (x86_64)
 *
 * Hooks panel_core_pull_users so the native module's hard 88-user truncation
 * no longer applies. Native pull_users is still called first to preserve its
 * side effects (without it the Shadowsocks credential table stays empty and
 * every handshake is dropped).
 *
 * amd64 facts (verified by static analysis of the v2.18.1 x86_64 build):
 *   panel_core_pull_users @ 0x35e8870
 *       41 b8 01 00 00 00   mov r8d, 1        ; mode = users
 *       e9 d5 02 fc ff      jmp 0x35a8b50
 *   shared native body   @ 0x35a8b50
 *        e8 ca be f3 03      call ...
 *        41 b8 25 b0 95 a5   mov r8d, 0xa595b025   ; magic
 *   ABI: rdi=cfg, rsi=len, rdx=out, rcx=outlen, r8=mode
 *
 * Only acts inside the process whose executable name is soco or soga.
 */
#include <curl/curl.h>
#include <json-c/json.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#ifndef MAP_FIXED_NOREPLACE
#define MAP_FIXED_NOREPLACE 0x100000
#endif
#define BODY_LIMIT (64U * 1024U * 1024U)

#define NATIVE_PULL_USERS 0x35e8870UL
#define NATIVE_SHARED     0x35a8b50UL
#define HOOK_LEN          5

struct body { char *data; size_t size; int failed; };

static unsigned char *g_stub = NULL;
static size_t g_limit = 0;

typedef int (*pull_fn)(const char *, size_t, char **, size_t *);

static size_t receive_body(char *chunk, size_t size, size_t nmemb, void *context) {
    struct body *b = context;
    if (size && nmemb > SIZE_MAX / size) return 0;
    size_t n = size * nmemb;
    if (n > BODY_LIMIT || b->size > BODY_LIMIT - n) { b->failed = 1; return 0; }
    char *p = realloc(b->data, b->size + n + 1);
    if (!p) { b->failed = 1; return 0; }
    b->data = p;
    memcpy(p + b->size, chunk, n);
    b->size += n;
    p[b->size] = 0;
    return n;
}

static int failure(char **output, size_t *length, const char *message) {
    struct json_object *error = json_object_new_object();
    if (!error) return 1;
    json_object_object_add(error, "error", json_object_new_string(message));
    const char *text = json_object_to_json_string_ext(error, JSON_C_TO_STRING_PLAIN);
    *output = strdup(text);
    *length = *output ? strlen(*output) : 0;
    json_object_put(error);
    return 1;
}

static const char *field(struct json_object *object, const char *key) {
    struct json_object *value = NULL;
    if (!json_object_object_get_ex(object, key, &value)) return NULL;
    if (!json_object_is_type(value, json_type_string)) return NULL;
    return json_object_get_string(value);
}

static const char *map_node_type(const char *type) {
    if (!strcmp(type, "ss")) return "shadowsocks";
    if (!strcmp(type, "v2ray")) return "vmess";
    return type;
}

/* keep every field the panel sent; native does the same */
__attribute__((used)) static char *rebuild_users(struct json_object *list, size_t *out_len) {
    struct json_object *root = json_object_new_object();
    struct json_object *arr = json_object_new_array();
    if (!root || !arr) {
        if (root) json_object_put(root);
        if (arr) json_object_put(arr);
        return NULL;
    }
    size_t n = json_object_array_length(list);
    if (g_limit && n > g_limit) n = g_limit;
    for (size_t i = 0; i < n; i++) {
        struct json_object *src = json_object_array_get_idx(list, i);
        if (!src || !json_object_is_type(src, json_type_object)) continue;
        json_object_get(src);
        json_object_array_add(arr, src);
    }
    json_object_object_add(root, "users", arr);
    const char *text = json_object_to_json_string_ext(root, JSON_C_TO_STRING_PLAIN);
    char *copy = text ? strdup(text) : NULL;
    json_object_put(root);
    *out_len = copy ? strlen(copy) : 0;
    return copy;
}

__attribute__((used)) static int fetch_users(const char *config, size_t config_length,
                       char **output, size_t *length) {
    if (!output || !length) return 1;
    *output = NULL;
    *length = 0;
    if (!config || config_length == 0 || config_length > 1048576)
        return failure(output, length, "Invalid panel configuration");

    struct json_tokener *tokener = json_tokener_new();
    if (!tokener) return failure(output, length, "Allocation failure");
    struct json_object *cfg = json_tokener_parse_ex(tokener, config, (int)config_length);
    enum json_tokener_error parse_error = json_tokener_get_error(tokener);
    json_tokener_free(tokener);
    if (!cfg || parse_error != json_tokener_success) {
        if (cfg) json_object_put(cfg);
        return failure(output, length, "Invalid configuration JSON");
    }

    const char *api = field(cfg, "api_type");
    const char *base = field(cfg, "api_url");
    const char *key = field(cfg, "api_key");
    const char *type = field(cfg, "server_type");

    if (!api || strcmp(api, "webapi") || !base || !key || !type || !*type) {
        json_object_put(cfg);
        return failure(output, length, "Missing api_url / api_key / server_type");
    }
    if (strncmp(base, "http://", 7) && strncmp(base, "https://", 8)) {
        json_object_put(cfg);
        return failure(output, length, "Panel URL must use HTTP or HTTPS");
    }
    const char *node_type = map_node_type(type);

    struct json_object *id_obj = NULL;
    if (!json_object_object_get_ex(cfg, "node_id", &id_obj)) {
        json_object_put(cfg);
        return failure(output, length, "Missing node_id");
    }
    int64_t node_id = json_object_get_int64(id_obj);
    if (node_id <= 0) {
        json_object_put(cfg);
        return failure(output, length, "Invalid node_id");
    }

    CURL *curl = curl_easy_init();
    if (!curl) {
        json_object_put(cfg);
        return failure(output, length, "HTTP client initialization failure");
    }
    char *escaped = curl_easy_escape(curl, key, 0);
    size_t base_length = strlen(base);
    while (base_length && base[base_length - 1] == '/') base_length--;
    size_t capacity = base_length + (escaped ? strlen(escaped) : 0) + 256;
    char *url = malloc(capacity);
    struct body body = { malloc(1), 0, 0 };
    if (!escaped || !url || !body.data) {
        if (escaped) curl_free(escaped);
        free(url);
        free(body.data);
        curl_easy_cleanup(curl);
        json_object_put(cfg);
        return failure(output, length, "Allocation failure");
    }
    body.data[0] = 0;
    snprintf(url, capacity,
             "%.*s/api/v1/server/UniProxy/user?node_id=%lld&node_type=%s&token=%s",
             (int)base_length, base, (long long)node_id, node_type, escaped);

    curl_easy_setopt(curl, CURLOPT_URL, url);
#if LIBCURL_VERSION_NUM >= 0x075500
    curl_easy_setopt(curl, CURLOPT_PROTOCOLS_STR, "http,https");
#else
    curl_easy_setopt(curl, CURLOPT_PROTOCOLS, (long)(CURLPROTO_HTTP | CURLPROTO_HTTPS));
#endif
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 10L);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 30L);
    curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 0L);
    curl_easy_setopt(curl, CURLOPT_PROXY, "");
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 2L);
    curl_easy_setopt(curl, CURLOPT_USERAGENT, "soco/0.1.0");
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, receive_body);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &body);
    CURLcode result = curl_easy_perform(curl);
    long status = 0;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &status);
    curl_free(escaped);
    free(url);
    curl_easy_cleanup(curl);
    json_object_put(cfg);

    if (result != CURLE_OK || status != 200 || body.failed || !body.size) {
        free(body.data);
        fprintf(stderr, "[soco] users failed: HTTP %ld, curl %d\n", status, (int)result);
        return failure(output, length, "Panel request failed");
    }

    struct json_object *response = json_tokener_parse(body.data);
    struct json_object *list = NULL;
    if (!response || !json_object_is_type(response, json_type_object) ||
        !json_object_object_get_ex(response, "users", &list) ||
        !json_object_is_type(list, json_type_array)) {
        if (response) json_object_put(response);
        free(body.data);
        return failure(output, length, "Unexpected panel response schema");
    }
    size_t count = json_object_array_length(list);
    size_t built_len = 0;
    char *built = rebuild_users(list, &built_len);
    json_object_put(response);
    free(body.data);
    if (!built) return failure(output, length, "Serialization failure");
    fprintf(stderr, "[soco] users=%zu out=%zu bytes\n", count, built_len);
    *output = built;
    *length = built_len;
    return 0;
}

__attribute__((used)) static int pull_users_hook(const char *cfg, size_t length, char **output, size_t *out_length) {
    /* 1) run the original native body first (keeps SS side effects) */
    if (g_stub) {
        pull_fn original = (pull_fn)g_stub;
        char *native_out = NULL;
        size_t native_len = 0;
        int rc = original(cfg, length, &native_out, &native_len);
        if (native_out) free(native_out);
        if (rc != 0)
            fprintf(stderr, "[soco] native pre-call rc=%d\n", rc);
    }
    /* 2) then serve the full list ourselves */
    return fetch_users(cfg, length, output, out_length);
}

static void fail_init(const char *why) {
    fprintf(stderr, "[soco] initialization failed: %s\n", why);
    _exit(125);
}

__attribute__((constructor)) static void initialize(void) {
    char actual[PATH_MAX];
    ssize_t n = readlink("/proc/self/exe", actual, sizeof(actual) - 1);
    if (n <= 0) return;
    actual[n] = 0;
    const char *slash = strrchr(actual, '/');
    const char *name = slash ? slash + 1 : actual;
    if (strcmp(name, "soga") && strcmp(name, "soco")) return;

    /* verify the exact build: mov r8d,1 ; jmp rel32 */
    const unsigned char expect[11] = {
        0x41, 0xb8, 0x01, 0x00, 0x00, 0x00, 0xe9, 0xd5, 0x02, 0xfc, 0xff
    };
    if (memcmp((void *)NATIVE_PULL_USERS, expect, sizeof(expect)))
        fail_init("exact-build native entry mismatch");

    long page_size = sysconf(_SC_PAGESIZE);
    if (page_size < 4096 || (page_size & (page_size - 1)))
        fail_init("unexpected page size");

    /* find a page within +/-2GB so a 5-byte jmp rel32 can reach it */
    void *near = MAP_FAILED;
    /* 必须页对齐，否则 mmap(MAP_FIXED_NOREPLACE) 返回 EINVAL */
    const uintptr_t base = NATIVE_PULL_USERS & ~((uintptr_t)page_size - 1);
    /* 先向低地址找（限制在 2GB 内，且不下溢） */
    for (uintptr_t addr = base; addr > 0x2000000UL; ) {
        addr -= 0x1000000UL;
        near = mmap((void *)addr, (size_t)page_size, PROT_READ | PROT_WRITE,
                    MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
        if (near != MAP_FAILED) break;
    }
    /* 再向高地址找 */
    if (near == MAP_FAILED) {
        for (uintptr_t addr = base + 0x1000000UL; addr < base + 0x7FFF0000UL; addr += 0x1000000UL) {
            near = mmap((void *)addr, (size_t)page_size, PROT_READ | PROT_WRITE,
                        MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
            if (near != MAP_FAILED) break;
        }
    }
    if (near == MAP_FAILED) fail_init("no reachable trampoline page");

    unsigned char *code = near;
    uintptr_t hook_fn = (uintptr_t)pull_users_hook;
    /* +0: mov rax, hook_fn ; jmp rax */
    code[0] = 0x48; code[1] = 0xB8;
    memcpy(code + 2, &hook_fn, 8);
    code[10] = 0xFF; code[11] = 0xE0;
    /* +16: mov r8d,1 ; mov rax, shared ; jmp rax   (native pre-call stub) */
    unsigned char *stub = code + 16;
    stub[0] = 0x41; stub[1] = 0xB8;
    uint32_t one = 1;
    memcpy(stub + 2, &one, 4);
    stub[6] = 0x48; stub[7] = 0xB8;
    uintptr_t shared = NATIVE_SHARED;
    memcpy(stub + 8, &shared, 8);
    stub[16] = 0xFF; stub[17] = 0xE0;
    g_stub = stub;

    __builtin___clear_cache((char *)near, (char *)near + 64);
    if (mprotect(near, (size_t)page_size, PROT_READ | PROT_EXEC))
        fail_init("trampoline RX transition");

    uintptr_t page = NATIVE_PULL_USERS & ~((uintptr_t)page_size - 1);
    if (mprotect((void *)page, (size_t)page_size, PROT_READ | PROT_WRITE | PROT_EXEC))
        fail_init("native page write transition");

    /* jmp rel32 to near */
    int64_t delta = (int64_t)(uintptr_t)near - (int64_t)(NATIVE_PULL_USERS + HOOK_LEN);
    if (delta < INT32_MIN || delta > INT32_MAX) fail_init("trampoline out of range");
    unsigned char *site = (unsigned char *)NATIVE_PULL_USERS;
    site[0] = 0xE9;
    int32_t rel = (int32_t)delta;
    memcpy(site + 1, &rel, 4);
    __builtin___clear_cache((char *)site, (char *)site + HOOK_LEN);
    if (mprotect((void *)page, (size_t)page_size, PROT_READ | PROT_EXEC))
        fail_init("native page RX restoration");

    const char *lim = getenv("SOCO_LIMIT");
    if (lim && *lim) g_limit = (size_t)strtoul(lim, NULL, 10);

    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK)
        fail_init("HTTP library initialization");
    fprintf(stderr, "[soco] v0.1.0 ready (x86_64, all-fields users, cap bypass)\n");
}