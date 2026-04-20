from __future__ import annotations

import json
import time
from urllib.request import Request, urlopen

from configs.uapi_secrets import UapiSecrets


def fetch_hot_rank() -> dict:
    """
    Hot榜爬虫骨架：用 UAPI 拉取热榜数据。
    你后续只需要把 endpoint 与返回字段映射补齐即可。
    """
    secrets = UapiSecrets.from_env()
    if not secrets.api_key:
        raise RuntimeError("missing UAPI_API_KEY in env")

    # TODO: 替换成真实 uapi endpoint
    url = f"{secrets.base_url.rstrip('/')}/hot_rank"
    req = Request(url, headers={"Authorization": f"Bearer {secrets.api_key}"})
    with urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body)


def main() -> None:
    data = fetch_hot_rank()
    ts = int(time.time())
    out = f"hot_rank_{ts}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved: {out}")


if __name__ == "__main__":
    main()

