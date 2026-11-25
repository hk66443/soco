#define _GNU_SOURCE
/* soga 2.18.1 panel adapter v5
 *
 * Finding: hooking panel_core_pull_users outright breaks Shadowsocks handshakes
 * even though the Go side logs all users as added. A native call is required for
 * its side effects on the SS credential table. So v5:
 *   1. calls the ORIGINAL native pull_users first (keeps side effects, yields 88),
 *   2. frees that buffer,
 *   3. fetches the full list itself and returns native-shaped JSON.
 *
 * The native entry stub is rebuilt with an absolute jump because the original
 * "B 0x33292e4" is PC-relative and cannot be copied to another address.
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
#define NATIVE_BODY 0x33292e4UL   /* shared native entry, W4 selects node/users */

struct body { char *data; size_t size; int failed; };

/* native pull_users 的原生跳板：MOV W4,#1 ; LDR X16,#8 ; BR X16 ; <addr> */
static unsigned char *g_stub = NULL;
static void *g_near = NULL;

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

/* 复刻 native 的 users 输出形态 */
static size_t g_limit = 0;   /* 0 = no limit; set by env SOCO_LIMIT */

static char *rebuild_users(struct json_object *list, size_t *out_len) {
    const char *keys[] = { "id", "uuid", "speed_limit", "device_limit" };
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
    (void)keys;
    json_object_object_add(root, "users", arr);
    const char *text = json_object_to_json_string_ext(root, JSON_C_TO_STRING_PLAIN);
    char *copy = text ? strdup(text) : NULL;
    json_object_put(root);
    *out_len = copy ? strlen(copy) : 0;
    return copy;
}

static int fetch_users(const char *config, size_t config_length,
                       char **output, size_t *length, int users) {
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
             "%.*s/api/v1/server/UniProxy/%s?node_id=%lld&node_type=%s&token=%s",
             (int)base_length, base, users ? "user" : "config",
             (long long)node_id, node_type, escaped);

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
        fprintf(stderr, "[soco] %s failed: HTTP %ld, curl %d\n",
                users ? "users" : "node", status, (int)result);
        return failure(output, length, "Panel request failed");
    }

    struct json_object *response = json_tokener_parse(body.data);
    struct json_object *list = NULL;
    if (!response || !json_object_is_type(response, json_type_object) ||
        (users && (!json_object_object_get_ex(response, "users", &list) ||
                   !json_object_is_type(list, json_type_array)))) {
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
    (void)users;
    return 0;
}

/* 真正对外的 users 入口：先原生，再全量 */
static int pull_users_v5(const char *cfg, size_t length, char **output, size_t *out_length) {
    /* 1) 先执行原生实现，保留它的副作用 */
    char *native_out = NULL;
    size_t native_len = 0;
    int rc = 1;
    if (g_stub) {
        pull_fn original = (pull_fn)g_stub;
        rc = original(cfg, length, &native_out, &native_len);
        if (native_out) free(native_out);
        native_out = NULL;
        if (rc != 0)
            fprintf(stderr, "[soco] native pre-call rc=%d\n", rc);
    }

    /* 2) 再自己拉全量并交给下面对接 */
    return fetch_users(cfg, length, output, out_length, 1);
}

__attribute__((unused)) static int pull_users(const char *cfg, size_t length,
                                              char **output, size_t *out_length) {
    return pull_users_v5(cfg, length, output, out_length);
}

static uint32_t branch(uintptr_t origin, uintptr_t target) {
    int64_t delta = (int64_t)target - (int64_t)origin;
    if ((delta & 3) || delta < -0x8000000LL || delta > 0x7fffffcLL) _exit(125);
    return 0x14000000U | ((uint32_t)(delta >> 2) & 0x03ffffffU);
}

static void fail_init(const char *why) {
    fprintf(stderr, "[soco] initialization failed: %s\n", why);
    _exit(125);
}

__attribute__((constructor)) static void initialize(void) {
#ifndef __aarch64__
    return;
#else
    char actual[PATH_MAX];
    ssize_t n = readlink("/proc/self/exe", actual, sizeof(actual) - 1);
    if (n <= 0) return;
    actual[n] = 0;
    const char *slash = strrchr(actual, '/');
    const char *name = slash ? slash + 1 : actual;
    if (strcmp(name, "soga") && strcmp(name, "soco")) return;

    uintptr_t users = 0x335f3d8UL;
    const uint32_t user_words[2] = { 0x52800024U, 0x17ff27c2U };
    if (memcmp((void *)users, user_words, 8))
        fail_init("native pull_users entry mismatch");

    long page_size = sysconf(_SC_PAGESIZE);
    if (page_size < 4096 || (page_size & (page_size - 1)))
        fail_init("Unexpected page size");

    void *near = MAP_FAILED;
    for (uintptr_t address = 0x9000000UL; address <= 0xb000000UL; address += 0x100000UL) {
        near = mmap((void *)address, (size_t)page_size, PROT_READ | PROT_WRITE,
                    MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
        if (near != MAP_FAILED) break;
    }
    if (near == MAP_FAILED) fail_init("No free near trampoline page");
    g_near = near;

    unsigned char *code = near;
    uint32_t load = 0x58000050U, jump = 0xd61f0200U;
    uintptr_t hook_fn = (uintptr_t)pull_users_v5;
    memcpy(code, &load, 4);
    memcpy(code + 4, &jump, 4);
    memcpy(code + 8, &hook_fn, 8);

    /* stub 放在 +32：MOV W4,#1 ; LDR X16,#8 ; BR X16 ; <0x33292e4> */
    unsigned char *stub = code + 32;
    uint32_t mov_w4_1 = 0x52800024U;
    memcpy(stub, &mov_w4_1, 4);
    memcpy(stub + 4, &load, 4);
    memcpy(stub + 8, &jump, 4);
    uintptr_t target = NATIVE_BODY;
    memcpy(stub + 12, &target, 8);
    g_stub = stub;

    __builtin___clear_cache((char *)near, (char *)near + 64);
    if (mprotect(near, (size_t)page_size, PROT_READ | PROT_EXEC))
        fail_init("Trampoline RX transition");

    uintptr_t page = users & ~((uintptr_t)page_size - 1);
    if (mprotect((void *)page, (size_t)page_size, PROT_READ | PROT_WRITE | PROT_EXEC))
        fail_init("Native page write transition");
    *(volatile uint32_t *)users = branch(users, (uintptr_t)near);
    __builtin___clear_cache((char *)users, (char *)users + 4);
    if (mprotect((void *)page, (size_t)page_size, PROT_READ | PROT_EXEC))
        fail_init("Native page RX restoration");

    const char *lim = getenv("SOCO_LIMIT");
    if (lim && *lim) g_limit = (size_t)strtoul(lim, NULL, 10);
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK)
        fail_init("HTTP library initialization");
    fprintf(stderr, "[soco] v0.1.0 ready (all-fields users, cap bypass)\n");
#endif
}