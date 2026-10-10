"""验证已运行的 Web 服务始终返回最新 SPA 入口。"""

import argparse
import urllib.request


def verify(origin: str) -> None:
    """用旧版本缓存校验头验证首页、入口和深层路由。"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    validators = [
        {"If-Modified-Since": "Thu, 01 Jan 1970 00:00:00 GMT"},
        {"If-None-Match": '"0-3d5"'},
    ]
    entries = []
    for path in ["/", "/index.html", "/family?tab=profiles"]:
        for headers in validators:
            request = urllib.request.Request(origin.rstrip("/") + path, headers=headers)
            with opener.open(request, timeout=15) as response:
                assert response.status == 200, (path, response.status)
                assert "no-store" in response.headers.get("Cache-Control", ""), path
                assert response.headers.get("ETag") is None, path
                body = response.read()
                assert b"/assets/" in body and b"<html" in body, path
                entries.append(body)
    assert all(body == entries[0] for body in entries), "SPA 入口内容不一致"
    print("WEB_ENTRY_CACHE_VERIFIED: 6 conditional requests returned fresh, uncached HTML")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origin", help="待验证 Web 服务的 HTTP(S) 根地址")
    verify(parser.parse_args().origin)
