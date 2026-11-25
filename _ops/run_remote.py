#!/usr/bin/env python3
"""Run a local shell script on a lab host as `bash -s` (no quoting games).

usage: run_remote.py <arm|amd> <local-script.sh> [timeout]
"""
import sys
import paramiko

HOSTS = {
    "arm": ("130.61.141.143", "root", "<REDACTED>"),
    "amd": ("141.148.139.236", "root", "<REDACTED>"),
}


def main():
    host = sys.argv[1]
    path = sys.argv[2]
    timeout = int(sys.argv[3]) if len(sys.argv) > 3 else 120
    ip, user, pw = HOSTS[host]
    script = open(path, encoding="utf-8").read()
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(ip, username=user, password=pw, timeout=20, banner_timeout=20, auth_timeout=20)
    tr = c.get_transport()
    tr.set_keepalive(15)
    ch = tr.open_session()
    ch.exec_command("bash -s")
    ch.sendall(script.encode("utf-8"))
    ch.shutdown_write()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    out = ch.makefile("rb")
    err = ch.makefile_stderr("rb")
    ch.settimeout(timeout)
    sys.stdout.write(out.read().decode("utf-8", "replace"))
    e = err.read().decode("utf-8", "replace")
    if e.strip():
        print("[stderr]\n" + e)
    print("[exit %d]" % ch.recv_exit_status())
    c.close()


if __name__ == "__main__":
    main()