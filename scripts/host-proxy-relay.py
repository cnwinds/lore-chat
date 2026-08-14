#!/usr/bin/env python3
"""把宿主机本机代理转发到 Docker 可达的网卡地址。

典型场景（WSL2 + Windows Clash）：代理只在 127.0.0.1:7897 可用，
容器经 host.docker.internal 访问会被拒绝。本脚本在 0.0.0.0:RELAY_PORT
监听并转发到 LOCAL_PROXY，供 compose 里 HTTP_PROXY=http://host.docker.internal:RELAY_PORT 使用。
"""
from __future__ import annotations

import argparse
import os
import select
import signal
import socket
import sys
import threading


def _pipe(a: socket.socket, b: socket.socket) -> None:
    try:
        while True:
            ready, _, _ = select.select([a], [], [], 120)
            if not ready:
                break
            data = a.recv(65536)
            if not data:
                break
            b.sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                s.close()
            except OSError:
                pass


def _handle(client: socket.socket, target: tuple[str, int]) -> None:
    upstream = socket.socket()
    upstream.settimeout(30)
    try:
        upstream.connect(target)
    except OSError:
        client.close()
        return
    threading.Thread(target=_pipe, args=(client, upstream), daemon=True).start()
    _pipe(upstream, client)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--listen",
        default=os.environ.get("LORECHAT_PROXY_RELAY_LISTEN", "0.0.0.0:17897"),
        help="Docker 侧连接地址，默认 0.0.0.0:17897",
    )
    p.add_argument(
        "--target",
        default=os.environ.get("LORECHAT_PROXY_RELAY_TARGET", "127.0.0.1:7897"),
        help="本机代理，默认 127.0.0.1:7897",
    )
    args = p.parse_args()

    def _host_port(spec: str) -> tuple[str, int]:
        host, _, port = spec.rpartition(":")
        if not host or not port:
            raise SystemExit(f"invalid host:port: {spec}")
        return host, int(port)

    listen = _host_port(args.listen)
    target = _host_port(args.target)

    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(listen)
    srv.listen(128)

    stop = threading.Event()

    def _stop(*_a: object) -> None:
        stop.set()
        try:
            srv.close()
        except OSError:
            pass

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    print(f"[proxy-relay] {listen[0]}:{listen[1]} -> {target[0]}:{target[1]}", flush=True)
    while not stop.is_set():
        try:
            client, _ = srv.accept()
        except OSError:
            break
        threading.Thread(target=_handle, args=(client, target), daemon=True).start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
