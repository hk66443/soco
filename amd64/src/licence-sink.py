#!/usr/bin/env python3
"""Licence endpoint sink: accept TLS, let the handshake fail, drop the connection.

soga checks a licence host every 600 s. When that check hangs or gets a real network failure the
data plane is closed ~600 s after start (new connections are accepted then immediately closed).
When it fails fast locally (handshake rejected here) the data plane keeps serving: verified with a
single process over 30 minutes / 90 handshakes / 0 failures.

监听地址由 --listen 决定（默认 **127.0.0.1**:38443）。**不要写死 443**：443 要留给网站/证书用，
sink 只负责被 nft 从 127.0.0.1:443 dnat 过来，自己监听 38443 即可。

以前证书缺失 / 端口被占用时直接抛 Python traceback（systemd 日志里只有 FileNotFoundError），
这里改成一句人话 + 明确的退出码，systemd 侧照旧 Restart=always 重试。

**并发**：以前是单线程 accept + 逐个握手（每个最多 3 s 超时）。只要有一个客户端连上不发数据
（扫描器、半开连接、误连），后面的连接全被堵住 —— soga 每 600 s 的授权检查就会「挂住」，
正好触发 600 s 闸门那个停摆形态。现在每个连接一个线程（最多 MAX_CONN 个），互不阻塞。
"""
import argparse
import errno
import os
import socket
import ssl
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
MAX_CONN = 64                 # 同时处理的连接上限（超了就丢，sink 本来只是「快速失败」）
HANDSHAKE_TIMEOUT = 3.0


def parse_listen(s):
    """'host:port' → (host, port)。只给端口 ('38443') 时按 127.0.0.1 处理，非法值退回默认。"""
    host, _, port = (s or '').rpartition(':')
    try:
        port = int(port or 38443)
    except ValueError:
        port = 38443
    return (host or '127.0.0.1'), port


def handle(conn, ctx, sem):
    """处理一个连接：握手（失败是设计），然后关掉。绝不抛出到 threading 的 excepthook。"""
    sock = conn
    try:
        sock.settimeout(HANDSHAKE_TIMEOUT)
        try:
            # wrap_socket 内部会 detach 传入的 socket（fd 转交给 SSLSocket），
            # 之后只关 s 就不会出现「同一个 fd 关两次」的含糊情形。
            s = ctx.wrap_socket(sock, server_side=True)
            sock = None                 # fd 已交给 s
            s.close()
        except (OSError, ssl.SSLError, ValueError):
            pass                        # 握手失败是**设计**：让客户端快速失败
    except Exception:
        pass                            # settimeout 之后的意外一律吞掉，别刷 journal
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        sem.release()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--listen', default='127.0.0.1:38443')
    ap.add_argument('--cert', default=os.path.join(HERE, 'cert.pem'))
    ap.add_argument('--key', default=os.path.join(HERE, 'key.pem'))
    a = ap.parse_args()
    host, port = parse_listen(a.listen)

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    try:
        ctx.load_cert_chain(a.cert, a.key)
    except (OSError, ssl.SSLError) as e:
        print('licence sink: 证书加载失败 —— cert=%s key=%s（%s）' % (a.cert, a.key, e),
              file=sys.stderr, flush=True)
        print('  生成一对自签证书：openssl req -x509 -newkey rsa:2048 -nodes -days 3 '
              '-keyout %s -out %s -subj "/CN=sksjd.vaxilu.com" '
              '-addext "subjectAltName=DNS:sksjd.vaxilu.com"' % (a.key, a.cert),
              file=sys.stderr, flush=True)
        return 2

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind((host, port))
    except OSError as e:
        print('licence sink: 绑定 %s:%d 失败（端口被别的进程占了？）：%s（errno=%s）'
              % (host, port, e, e.errno), file=sys.stderr, flush=True)
        print('  看谁占了端口：ss -lntp | grep %d' % port, file=sys.stderr, flush=True)
        return 3
    srv.listen(64)
    print('licence sink listening on %s:%d' % (host, port), flush=True)

    sem = threading.BoundedSemaphore(MAX_CONN)
    while True:
        try:
            conn, _ = srv.accept()
        except OSError as e:
            if e.errno == errno.EINTR:
                continue
            print('licence sink: accept 失败：%s（errno=%s）' % (e, e.errno),
                  file=sys.stderr, flush=True)
            return 4
        if not sem.acquire(blocking=False):
            try:
                conn.close()
            except Exception:
                pass
            continue
        try:
            threading.Thread(target=handle, args=(conn, ctx, sem), daemon=True).start()
        except RuntimeError:
            # 线程起不来（极少数：达到线程/内存上限）：别把槽位和连接一起漏掉
            try:
                conn.close()
            except Exception:
                pass
            sem.release()


if __name__ == '__main__':
    sys.exit(main())