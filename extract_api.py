#!/usr/bin/env python3
"""
Salework.net API Extractor
- Mở browser cho bạn đăng nhập thủ công
- Bắt tất cả API requests/responses với đầy đủ headers, body
- Tự động crawl các trang chính sau khi login
- Lưu dữ liệu ra file JSON để dùng tự động hoá sau này
"""

import json
import os
import re
import time
from datetime import datetime
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright

BASE_URL = "https://salework.net"
LOGIN_URL = f"{BASE_URL}/login/cretashop"
OUTPUT_DIR = "api_data"
SESSION_FILE = "session.json"
actual_base_url = None  # sẽ được detect sau login redirect

# Các trang quan trọng sẽ tự động crawl sau login
AUTO_CRAWL_PAGES = [
    "/",
    "/dashboard",
    "/employees",
    "/attendances",
    "/timesheets",
    "/reports",
    "/tasks",
    "/projects",
    "/customers",
    "/orders",
    "/products",
    "/settings",
    "/users",
    "/teams",
    "/kpi",
    "/salary",
    "/leaves",
    "/overtime",
    "/checkin",
    "/worklogs",
    "/activities",
]

os.makedirs(OUTPUT_DIR, exist_ok=True)

api_log = []
seen_requests = set()


def clean_headers(headers):
    """Loại bỏ headers nhạy cảm trước khi lưu."""
    sensitive = {"cookie", "authorization", "set-cookie", "x-csrf-token"}
    return {k: v for k, v in (headers or {}).items() if k.lower() not in sensitive}


def truncate_body(body, max_len=50000):
    """Giới hạn kích thước body lưu trữ. Luôn trả về string (decode bytes)."""
    if body is None:
        return None
    if isinstance(body, bytes):
        try:
            body = body.decode("utf-8")
        except UnicodeDecodeError:
            import base64
            body = "[base64] " + base64.b64encode(body).decode("ascii")
    if isinstance(body, str) and len(body) > max_len:
        return body[:max_len] + "..."
    return body


def extract_api_info(request, response=None):
    """Trích xuất thông tin từ 1 API request/response."""
    url = request.url
    method = request.method
    resource_type = request.resource_type

    # Chỉ bắt XHR, fetch, websocket, eventsource
    if resource_type not in ("xhr", "fetch", "websocket", "eventsource"):
        return None

    # Bỏ qua static resources
    if any(url.endswith(ext) for ext in (".js", ".css", ".png", ".jpg", ".svg", ".woff2", ".ico", ".gif", ".webp", ".mp4", ".webm")):
        return None

    # Tạo key duy nhất
    req_key = f"{method}:{url}"
    if req_key in seen_requests:
        return None
    seen_requests.add(req_key)

    parsed = urlparse(url)
    info = {
        "method": method,
        "url": url,
        "path": parsed.path,
        "query_params": dict(parse_qs(parsed.query)) if parsed.query else {},
        "resource_type": resource_type,
        "request_headers": clean_headers(request.headers),
        "post_data": None,
        "response_status": None,
        "response_headers": None,
        "response_body_snippet": None,
        "response_body_full": None,
        "timing": None,
        "timestamp": datetime.now().isoformat(),
    }

    # Lấy post data
    try:
        post_data = request.post_data
        if post_data:
            try:
                info["post_data"] = json.loads(post_data)
            except (json.JSONDecodeError, TypeError):
                info["post_data"] = post_data[:2000]
    except Exception:
        pass

    # Lấy response
    if response:
        info["response_status"] = response.status
        info["response_headers"] = clean_headers(response.headers)

        try:
            body = response.body()
            info["response_body_full"] = truncate_body(body)

            # Thử parse JSON
            if body:
                try:
                    parsed_body = json.loads(body)
                    info["response_body_parsed"] = parsed_body
                    info["response_body_snippet"] = json.dumps(parsed_body, ensure_ascii=False)[:2000]
                except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
                    text_body = body.decode("utf-8", errors="replace")[:2000]
                    info["response_body_snippet"] = text_body
        except Exception:
            pass

    return info


def save_data():
    """Lưu toàn bộ dữ liệu API đã bắt được."""
    api_log.sort(key=lambda x: x.get("timestamp", ""))

    # 1. Lưu full log
    full_path = os.path.join(OUTPUT_DIR, "api_full_log.json")
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(api_log, f, ensure_ascii=False, indent=2)
    print(f"\n[SAVE] Đã lưu full log: {full_path} ({len(api_log)} APIs)")

    # 2. Tạo summary các endpoint duy nhất (theo path + method)
    endpoints = {}
    for api in api_log:
        key = f"{api['method']} {api['path']}"
        if key not in endpoints:
            endpoints[key] = {
                "method": api["method"],
                "path": api["path"],
                "full_urls": [],
                "query_params_example": api.get("query_params", {}),
                "post_data_example": api.get("post_data"),
                "response_status": api.get("response_status"),
                "response_example": api.get("response_body_snippet"),
                "headers_used": list(api.get("request_headers", {}).keys()),
                "call_count": 0,
            }
        endpoints[key]["call_count"] += 1
        if api["url"] not in endpoints[key]["full_urls"]:
            endpoints[key]["full_urls"].append(api["url"])

    summary_path = os.path.join(OUTPUT_DIR, "api_endpoints_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(list(endpoints.values()), f, ensure_ascii=False, indent=2)
    print(f"[SAVE] Đã lưu summary endpoints: {summary_path} ({len(endpoints)} endpoints)")

    # 3. Tạo file riêng cho từng loại resource
    by_type = {}
    for api in api_log:
        rtype = api.get("resource_type", "unknown")
        if rtype not in by_type:
            by_type[rtype] = []
        by_type[rtype].append(api)

    for rtype, apis in by_type.items():
        path = os.path.join(OUTPUT_DIR, f"api_by_type_{rtype}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(apis, f, ensure_ascii=False, indent=2)
        print(f"[SAVE] {rtype}: {path} ({len(apis)} calls)")

    # 4. Lưu session (cookies, localStorage, token) để dùng sau
    return summary_path


def save_session(context):
    """Lưu session để tự động đăng nhập lần sau."""
    cookies = context.cookies()
    session_data = {
        "cookies": cookies,
        "saved_at": datetime.now().isoformat(),
    }
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(session_data, f, ensure_ascii=False, indent=2)
    print(f"[SAVE] Session đã lưu vào {SESSION_FILE}")
    print(f"[INFO] Lần sau dùng --session để tự động đăng nhập")


def find_api_endpoints(page, text_pattern=None):
    """Dùng regex tìm endpoint patterns trong HTML/JS của page."""
    if text_pattern is None:
        text_pattern = r'(?:["\'])(\/api\/[^"\'\s]+|api\/[^"\'\s]+|\/v\d\/[^"\'\s]+)(?:["\'])'

    try:
        html = page.content()
        matches = set(re.findall(text_pattern, html, re.IGNORECASE))
        return list(matches)
    except Exception:
        return []


def auto_crawl(page):
    """Tự động điều hướng qua các trang chính để bắt API."""
    global actual_base_url

    # Detect domain thực tế sau login redirect
    current_url = page.url
    from urllib.parse import urlparse
    parsed = urlparse(current_url)
    actual_base_url = f"{parsed.scheme}://{parsed.netloc}"
    print(f"\n[INFO] Phát hiện domain thực tế: {actual_base_url}")

    print("\n" + "=" * 60)
    print("[CRAWL] Bắt đầu tự động crawl các trang chính...")
    print("=" * 60)

    successful = []
    failed = []

    for i, path in enumerate(AUTO_CRAWL_PAGES, 1):
        url = f"{actual_base_url}{path}"
        print(f"\n[{i}/{len(AUTO_CRAWL_PAGES)}] Đang truy cập: {url}")
        try:
            response = page.goto(url, timeout=30000, wait_until="networkidle")
            if response and response.ok:
                print(f"  ✓ OK ({response.status})")
                successful.append(url)
            else:
                status = response.status if response else "no response"
                print(f"  ✗ Status: {status}")
                failed.append(url)

            # Tìm thêm API endpoints trong HTML
            found = find_api_endpoints(page)
            if found:
                print(f"  [FOUND] {len(found)} potential API endpoints in page source")

            time.sleep(1)
        except Exception as e:
            print(f"  ✗ Error: {str(e)[:100]}")
            failed.append(url)

    print(f"\n[CRAWL] Hoàn thành: {len(successful)} OK, {len(failed)} lỗi")
    return successful, failed


def load_session(context):
    """Nạp session đã lưu để tự động đăng nhập."""
    if not os.path.exists(SESSION_FILE):
        return False

    with open(SESSION_FILE, "r", encoding="utf-8") as f:
        session_data = json.load(f)

    cookies = session_data.get("cookies", [])
    if cookies:
        context.add_cookies(cookies)
        print(f"[SESSION] Đã nạp {len(cookies)} cookies từ session")
        return True
    return False


def main():
    import sys

    use_session = "--session" in sys.argv

    print("=" * 60)
    print("  SALEWORK.NET API EXTRACTOR")
    print("=" * 60)
    print(f"  Target: {LOGIN_URL}")
    print(f"  Output: {OUTPUT_DIR}/")
    print(f"  Session: {'CÓ' if use_session else 'KHÔNG'}")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
            ],
        )

        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )

        # Nạp session nếu có
        if use_session:
            load_session(context)

        page = context.new_page()

        # ===================================================================
        # INTERCEPT: Bắt tất cả network requests/responses
        # ===================================================================
        def on_request(request):
            info = extract_api_info(request)
            if info:
                # Lưu tạm để gán response sau
                api_log.append(info)

        def on_response(response):
            request = response.request
            req_key = f"{request.method}:{request.url}"

            # Tìm request tương ứng đã lưu và gán response
            for api in reversed(api_log):
                if f"{api['method']}:{api['url']}" == req_key and api.get("response_status") is None:
                    api["response_status"] = response.status
                    api["response_headers"] = clean_headers(response.headers)

                    try:
                        body = response.body()
                        api["response_body_full"] = truncate_body(body)
                        if body:
                            try:
                                if isinstance(body, bytes):
                                    body_str = body.decode("utf-8", errors="replace")
                                else:
                                    body_str = body
                                parsed = json.loads(body_str)
                                api["response_body_parsed"] = parsed
                                api["response_body_snippet"] = json.dumps(parsed, ensure_ascii=False)[:2000]
                            except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
                                snippet = body_str if 'body_str' in dir() else str(body)[:2000]
                                api["response_body_snippet"] = snippet[:2000]
                    except BaseException:
                        pass
                    break

        page.on("request", on_request)
        page.on("response", on_response)

        # ===================================================================
        # BƯỚC 1: Mở trang login cho user đăng nhập thủ công
        # ===================================================================
        print("\n[BROWSER] Đang mở browser...")
        page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)

        print("\n" + "=" * 60)
        print("  👉 VUI LÒNG ĐĂNG NHẬP THỦ CÔNG TRÊN BROWSER")
        print("  Script sẽ tự động phát hiện khi bạn đăng nhập xong...")
        print("=" * 60)

        # ===================================================================
        # BƯỚC 2: Tự động phát hiện login thành công (URL rời khỏi /login)
        # ===================================================================
        print("\n[WAIT] Đang chờ bạn đăng nhập...")
        try:
            page.wait_for_url(
                lambda url: "login" not in url.lower(),
                timeout=300000  # 5 phút
            )
            print("\n[OK] Phát hiện đăng nhập thành công!")
        except Exception:
            print("\n[WARN] Không phát hiện redirect, tiếp tục...")

        print("[WAIT] Đợi trang load hoàn tất...")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        time.sleep(2)

        current_url = page.url
        print(f"[INFO] URL hiện tại: {current_url}")

        # Lưu session ngay sau login
        save_session(context)

        # ===================================================================
        # BƯỚC 3: Tự động crawl nhanh các trang chính (để có baseline APIs)
        # ===================================================================
        auto_crawl(page)

        # ===================================================================
        # BƯỚC 4: FREEBROWSE MODE - Bạn lướt tự do, script bắt hết API
        # ===================================================================
        print("\n" + "=" * 60)
        print("  🖱️  FREEBROWSE MODE")
        print("  Bạn cứ lướt tự do trên browser (5-10 phút tuỳ ý).")
        print("  Script đang bắt TẤT CẢ API trong background.")
        print("  Tự động lưu định kỳ mỗi 60 giây.")
        print("  KHI XONG: ĐÓNG BROWSER hoặc nhấn Ctrl+C tại terminal này.")
        print("=" * 60)

        last_save_count = 0
        start_browse = time.time()

        try:
            while page and not page.is_closed():
                time.sleep(10)  # check mỗi 10s
                elapsed = time.time() - start_browse
                current_count = len(api_log)

                # Tự động save định kỳ mỗi 60s nếu có API mới
                if current_count > last_save_count and elapsed > 60:
                    mins = int(elapsed // 60)
                    secs = int(elapsed % 60)
                    print(f"\n[AUTOSAVE] {mins}m{secs}s | {current_count} APIs đã bắt | Đang lưu...")
                    save_data()
                    last_save_count = current_count

                # Tự động kết thúc sau 30 phút (tránh treo)
                if elapsed > 1800:
                    print("\n[TIMEOUT] 30 phút đã hết, tự động lưu & thoát.")
                    break

        except KeyboardInterrupt:
            print("\n[INTERRUPT] Đã nhấn Ctrl+C.")
        except Exception as e:
            print(f"\n[WARN] Browser đã đóng hoặc lỗi: {e}")

        # ===================================================================
        # BƯỚC 5: Final save
        # ===================================================================
        print("\n[SAVE] Đang lưu dữ liệu cuối cùng...")
        total_elapsed = time.time() - start_browse

        # Lưu lần cuối
        if page and not page.is_closed():
            final_endpoints = find_api_endpoints(page)
            if final_endpoints:
                ep_path = os.path.join(OUTPUT_DIR, "found_endpoints_in_html.json")
                with open(ep_path, "w", encoding="utf-8") as f:
                    json.dump(final_endpoints, f, ensure_ascii=False, indent=2)
                print(f"[SAVE] Endpoints từ HTML: {ep_path} ({len(final_endpoints)} found)")

        save_data()

        try:
            browser.close()
        except Exception:
            pass

    print("\n" + "=" * 60)
    print("  🎉 HOÀN TẤT!")
    print(f"  Dữ liệu đã lưu trong: {OUTPUT_DIR}/")
    print(f"  - api_full_log.json            : Tất cả API đã bắt")
    print(f"  - api_endpoints_summary.json    : Danh sách endpoint")
    print(f"  - api_by_type_*.json            : Phân loại theo kiểu")
    print(f"  - session.json                  : Phiên đăng nhập")
    print(f"  Lần sau chạy: python extract_api.py --session")
    print("=" * 60)


if __name__ == "__main__":
    main()
