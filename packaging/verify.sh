#!/usr/bin/env bash
# Offline installed-file/service diagnostics; no network and no inferred traffic PASS.
# Candidate artifacts synchronized locally; verification is read-only, protocol status is independent.
set -uo pipefail
EXPECT_arm64_bin=1b280c886ae8c608af7acef5fb78114f1e3dff1ad12abfe1b61e6c1f8039e171
EXPECT_arm64_so=f5fc39df4f988cb4a8eb4c683f914a07d5836b1807720aab7b010736cf83293a
EXPECT_amd64_bin=c463791ac4bf9ba82f28b8e87b148976f13397e1407ddab04d366579e4c80fed
EXPECT_amd64_so=2f60b5f881c9ae462a9de843eaea4471bd4a386a467c4e4c82042355c7998ab7
DEST=${SOCO_DEST:-/usr/local/soco}
UNIT=${1:-soco.service}
case "$UNIT" in
    soco.service|soco@[A-Za-z0-9_.-]*.service) ;;
    *) printf 'Unsupported service unit: %s\n' "$UNIT" >&2; exit 2 ;;
esac
MACHINE=$(uname -m)
case "$MACHINE" in
    aarch64|arm64) ARCH=arm64 ;;
    x86_64|amd64) ARCH=amd64 ;;
    *) printf 'Unsupported architecture: %s\n' "$MACHINE" >&2; exit 2 ;;
esac
eval "EXP_BIN=\$EXPECT_${ARCH}_bin"
eval "EXP_SO=\$EXPECT_${ARCH}_so"
FAIL=0
printf 'soco diagnostic: arch=%s unit=%s\n' "$ARCH" "$UNIT"
check_file() {
    local path=$1 expected=$2 actual
    if [ ! -f "$path" ]; then printf 'file_status=FAIL missing=%s\n' "$path"; FAIL=1; return; fi
    actual=$(sha256sum "$path" | awk '{print $1}')
    printf '%s sha256=%s expected=%s\n' "$(basename "$path")" "$actual" "$expected"
    if [ "$actual" != "$expected" ]; then printf 'file_status=FAIL hash_mismatch=%s\n' "$path"; FAIL=1; else printf 'file_status=PASS artifact=%s\n' "$path"; fi
}
check_file "$DEST/soco" "$EXP_BIN"
check_file "$DEST/libsoco.so" "$EXP_SO"
if ! command -v systemctl >/dev/null; then
    printf 'service_status=NOT_CHECKED reason=systemctl_missing\n'
    FAIL=1
else
    ACTIVE=$(systemctl show "$UNIT" --property=ActiveState --value 2>/dev/null || true)
    PID=$(systemctl show "$UNIT" --property=MainPID --value 2>/dev/null || true)
    INVOCATION=$(systemctl show "$UNIT" --property=InvocationID --value 2>/dev/null || true)
    START_MONO=$(systemctl show "$UNIT" --property=ExecMainStartTimestampMonotonic --value 2>/dev/null || true)
    printf 'service_status=%s MainPID=%s invocation=%s start_monotonic=%s\n' "${ACTIVE:-unknown}" "${PID:-0}" "${INVOCATION:-unknown}" "${START_MONO:-unknown}"
    if [[ "$PID" =~ ^[0-9]+$ ]] && [ "$PID" -gt 0 ] && [ -e "/proc/$PID/exe" ] && [ "$ACTIVE" = active ]; then
        ACTUAL_EXE=$(readlink -f "/proc/$PID/exe" || true)
        EXPECTED_EXE=$(readlink -f "$DEST/soco" || true)
        printf 'process_exe=%s expected_exe=%s\n' "$ACTUAL_EXE" "$EXPECTED_EXE"
        if [ "$ACTUAL_EXE" != "$EXPECTED_EXE" ]; then
            printf 'process_status=FAIL different_executable\n'
            FAIL=1
        else
            printf 'process_status=PASS executable_identity_only\n'
        fi
        if [ -r "/proc/$PID/maps" ] && grep -Fq -- "$DEST/libsoco.so" "/proc/$PID/maps"; then
            printf 'adapter_mapping_status=PRESENT not_functional_proof\n'
        else
            printf 'adapter_mapping_status=NOT_OBSERVED\n'
            FAIL=1
        fi
        if command -v journalctl >/dev/null && [ -r /proc/sys/kernel/random/boot_id ]; then
            BOOT=$(</proc/sys/kernel/random/boot_id)
            JOURNAL_ARGS=(-b "_BOOT_ID=$BOOT" "_PID=$PID" -u "$UNIT" --no-pager -n 300)
            # No locale/weekday timestamp parsing; invocation identifies this service run.
            if [[ "$INVOCATION" =~ ^[0-9a-fA-F]{32}$ ]]; then
                JOURNAL_ARGS+=("_SYSTEMD_INVOCATION_ID=$INVOCATION")
                printf 'journal_scope=boot_pid_invocation source_contract_only_until_live_test\n'
            else
                printf 'journal_scope=boot_pid_fallback pid_reuse_not_fully_excluded\n'
            fi
            LOG=$(journalctl "${JOURNAL_ARGS[@]}" 2>/dev/null || true)
            printf '\nCurrent MainPID/current boot diagnostics (no credentials dumped):\n'
            printf '%s\n' "$LOG" | grep -E '\[soco\].*(ready|users=[0-9]+ out=[0-9]+ bytes|users failed|native pre-call rc=)|current user num: [0-9]+' | tail -15 || true
            COUNT=$(printf '%s\n' "$LOG" | grep -oE 'current user num: [0-9]+' | tail -1 || true)
            printf 'loaded_user_count=%s meaning=log_observation_only\n' "${COUNT:-NOT_OBSERVED}"
        else
            printf 'journal_status=NOT_CHECKED\n'
        fi
    else
        printf 'process_status=FAIL no_live_service_PID\n'
        FAIL=1
    fi
fi
traffic_status=NOT_TESTED
printf '\ntraffic_status=%s\n' "$traffic_status"
printf '%s\n' '文件hash、adapter映射、加载数量或listener均非端到端转发证明。' '协议验收须独立核对HTTP/HTTPS精确marker、TLS、正确/错误凭据和目标请求。'
exit "$FAIL"
