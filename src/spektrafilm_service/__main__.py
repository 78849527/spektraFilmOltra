"""启动本地服务：``python -m spektrafilm_service --port 0 --token <token>``。

启动成功后向 stdout 打一行 JSON，Electron 主进程据此拿到真实端口。
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import threading

from spektrafilm_service.server import make_server


def _warmup() -> None:
    try:
        from spektrafilm.utils.numba_warmup import warmup

        warmup()
    except Exception:  # noqa: BLE001 - 预热失败不影响服务
        return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='spektrafilm_service')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--token', default='')
    args = parser.parse_args(argv)

    token = args.token or secrets.token_urlsafe(24)
    server, _api = make_server(port=args.port, token=token)
    host, port = server.server_address[:2]

    print(
        json.dumps({'event': 'ready', 'port': int(port), 'token': token}, ensure_ascii=False),
        flush=True,
    )
    threading.Thread(target=_warmup, name='spektrafilm-warmup', daemon=True).start()
    thread = threading.Thread(target=server.serve_forever, name='spektrafilm-http', daemon=True)
    thread.start()
    try:
        thread.join()
    except KeyboardInterrupt:
        server.shutdown()
        return 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
