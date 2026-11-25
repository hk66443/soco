#!/usr/bin/env python3
"""Local SSH port forward for the ARM lab (paramiko, no external ssh client).

  python ssh_tunnel.py <host_key> <local_port> <remote_host> <remote_port>

host_key is "arm" or "amd" (credentials from HANDOFF.md).
"""
import select
import socket
import socketserver
import sys
import threading

import paramiko

HOSTS = {
    "arm": ("130.61.141.143", "root", "<REDACTED>"),
    "amd": ("141.148.139.236", "root", "<REDACTED>"),
}


class Forward(socketserver.BaseRequestHandler):
    ssh_transport = None
    remote = ("127.0.0.1", 19599)

    def handle(self):
        chan = self.ssh_transport.open_channel(
            "direct-tcpip", self.remote, self.request.getpeername())
        if chan is None:
            return
        while True:
            r, _, _ = select.select([self.request, chan], [], [], 0.5)
            if self.request in r:
                data = self.request.recv(16384)
                if not data:
                    break
                chan.sendall(data)
            if chan in r:
                data = chan.recv(16384)
                if not data:
                    break
                self.request.sendall(data)
        chan.close()
        self.request.close()


def main():
    key, lport, rhost, rport = sys.argv[1], int(sys.argv[2]), sys.argv[3], int(sys.argv[4])
    ip, user, pw = HOSTS[key]
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(ip, username=user, password=pw, timeout=20, banner_timeout=20, auth_timeout=20)
    tr = c.get_transport()
    tr.set_keepalive(20)
    Forward.ssh_transport = tr
    Forward.remote = (rhost, rport)
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", lport), Forward)
    print("forwarding 127.0.0.1:%d -> %s:%d via %s" % (lport, rhost, rport, ip), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()