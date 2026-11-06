"""网络环境兼容：某些 Windows 环境把 IPv6 回环写成 [::1]，httpx 会误判成端口。"""

import os


def sanitize_proxy_env() -> None:
    for key in ("NO_PROXY", "no_proxy"):
        raw = os.environ.get(key)
        if raw and "[::1]" in raw:
            fixed = raw.replace("[::1]", "::1")
            os.environ[key] = fixed
