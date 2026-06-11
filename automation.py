#!/usr/bin/env python3
"""
Salework.net Automation Tool
Sử dụng session đã lưu & endpoints đã extract để tự động hoá các tác vụ giám sát.
"""

import json
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

import requests

BASE_URL = "https://zalo.salework.net"  # domain thực tế sau redirect
SESSION_FILE = "session.json"
ENDPOINTS_FILE = "api_data/api_endpoints_summary.json"
FULL_LOG_FILE = "api_data/api_full_log.json"
OUTPUT_DIR = "automation_output"

os.makedirs(OUTPUT_DIR, exist_ok=True)


class SaleworkClient:
    """Client tự động hoá Salework.net dùng session cookies."""

    def __init__(self):
        self.session = requests.Session()
        self.base_url = BASE_URL
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }
        self._load_session()

    def _load_session(self):
        """Nạp cookies session đã lưu."""
        if not os.path.exists(SESSION_FILE):
            print(f"[WARN] Không tìm thấy {SESSION_FILE}. Chạy extract_api.py trước.")
            return

        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            session_data = json.load(f)

        for cookie in session_data.get("cookies", []):
            self.session.cookies.set(
                cookie.get("name"),
                cookie.get("value"),
                domain=cookie.get("domain"),
                path=cookie.get("path"),
            )

        saved_at = session_data.get("saved_at", "unknown")
        print(f"[SESSION] Đã nạp session từ {saved_at}")

    def _call(self, method: str, path: str, **kwargs) -> Optional[dict]:
        """Gọi API endpoint."""
        url = f"{self.base_url}{path}" if not path.startswith("http") else path
        kwargs.setdefault("headers", {}).update(self.headers)
        kwargs.setdefault("timeout", 30)

        try:
            resp = self.session.request(method, url, **kwargs)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "application/json" in content_type:
                return resp.json()
            return {"_raw": resp.text, "_status": resp.status_code}
        except requests.exceptions.HTTPError as e:
            print(f"  ✗ HTTP {resp.status_code}: {e}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"  ✗ Request error: {e}")
            return None

    def get(self, path, **kwargs):
        return self._call("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self._call("POST", path, **kwargs)

    def put(self, path, **kwargs):
        return self._call("PUT", path, **kwargs)

    def delete(self, path, **kwargs):
        return self._call("DELETE", path, **kwargs)

    # ===================================================================
    # HIGH-LEVEL METHODS cho giám sát nhân sự
    # ===================================================================

    def get_employees(self):
        """Lấy danh sách nhân viên."""
        return self.get("/api/employees") or self.get("/api/users") or self.get("/api/members")

    def get_attendances(self, date_from=None, date_to=None):
        """Lấy dữ liệu chấm công."""
        if not date_from:
            date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not date_to:
            date_to = datetime.now().strftime("%Y-%m-%d")

        # Thử nhiều endpoint pattern khác nhau
        paths = [
            f"/api/attendances?from={date_from}&to={date_to}",
            f"/api/checkin?from={date_from}&to={date_to}",
            f"/api/timekeeping?from={date_from}&to={date_to}",
        ]
        for p in paths:
            result = self.get(p)
            if result:
                return result
        return None

    def get_timesheets(self, date_from=None, date_to=None):
        """Lấy bảng công / timesheet."""
        if not date_from:
            date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        paths = [
            f"/api/timesheets?from={date_from}",
            f"/api/worklogs?from={date_from}",
            f"/api/working-hours?from={date_from}",
        ]
        for p in paths:
            result = self.get(p)
            if result:
                return result
        return None

    def get_tasks(self):
        """Lấy danh sách task/công việc."""
        paths = ["/api/tasks", "/api/jobs", "/api/work-items"]
        for p in paths:
            result = self.get(p)
            if result:
                return result
        return None

    def get_kpi(self):
        """Lấy dữ liệu KPI."""
        return self.get("/api/kpi") or self.get("/api/performance")

    def get_leaves(self):
        """Lấy dữ liệu nghỉ phép."""
        return self.get("/api/leaves") or self.get("/api/leave-requests")

    def get_activities(self, user_id=None, limit=100):
        """Lấy log hoạt động của nhân viên."""
        url = f"/api/activities?limit={limit}"
        if user_id:
            url += f"&user_id={user_id}"
        return self.get(url) or self.get(f"/api/audit-logs?limit={limit}")

    def get_dashboard(self):
        """Lấy dữ liệu dashboard tổng quan."""
        paths = ["/api/dashboard", "/api/statistics", "/api/summary"]
        for p in paths:
            result = self.get(p)
            if result:
                return result
        return None

    def get_work_hours_today(self):
        """Lấy giờ làm việc hôm nay của tất cả nhân viên."""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.get(f"/api/attendances/today?date={today}") or self.get(f"/api/timesheets/today?date={today}")


def discover_and_save(client: SaleworkClient):
    """Thử gọi các endpoint đã biết và lưu kết quả."""
    print("\n" + "=" * 60)
    print("  DISCOVER: Thử gọi tất cả endpoint đã biết...")
    print("=" * 60)

    results = {}

    functions = [
        ("employees", client.get_employees),
        ("attendances", client.get_attendances),
        ("timesheets", client.get_timesheets),
        ("tasks", client.get_tasks),
        ("kpi", client.get_kpi),
        ("leaves", client.get_leaves),
        ("activities", client.get_activities),
        ("dashboard", client.get_dashboard),
        ("work_hours_today", client.get_work_hours_today),
    ]

    for name, fn in functions:
        print(f"\n[{name.upper()}] Đang gọi...")
        try:
            data = fn()
            results[name] = data
            if data:
                if isinstance(data, list):
                    print(f"  ✓ Thành công: {len(data)} items")
                elif isinstance(data, dict):
                    if "_raw" in data:
                        print(f"  ✓ Thành công: {len(data['_raw'])} chars HTML")
                    else:
                        keys = list(data.keys())[:10]
                        print(f"  ✓ Thành công: keys={keys}")
                else:
                    print(f"  ✓ Thành công: {type(data).__name__}")
            else:
                print(f"  ✗ Không có dữ liệu / endpoint không tồn tại")
        except Exception as e:
            print(f"  ✗ Lỗi: {e}")
            results[name] = {"error": str(e)}

    # Lưu results
    output_path = os.path.join(OUTPUT_DIR, "discovered_data.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n[DISCOVER] Đã lưu tất cả dữ liệu vào {output_path}")

    return results


def show_endpoints_summary():
    """Hiển thị danh sách endpoints đã extract được."""
    if not os.path.exists(ENDPOINTS_FILE):
        print(f"[WARN] Chưa có {ENDPOINTS_FILE}. Chạy extract_api.py trước.")
        return

    with open(ENDPOINTS_FILE, "r", encoding="utf-8") as f:
        endpoints = json.load(f)

    print("\n" + "=" * 60)
    print(f"  ENDPOINTS ĐÃ EXTRACT ({len(endpoints)} endpoints)")
    print("=" * 60)

    for ep in endpoints:
        method = ep.get("method", "?")
        path = ep.get("path", "?")
        status = ep.get("response_status", "?")
        count = ep.get("call_count", 0)
        print(f"\n  [{method}] {path}  (status={status}, calls={count})")

        if ep.get("post_data_example"):
            pd = ep["post_data_example"]
            pd_str = json.dumps(pd, ensure_ascii=False)[:200] if isinstance(pd, dict) else str(pd)[:200]
            print(f"    POST data: {pd_str}")

        if ep.get("response_example"):
            print(f"    Response:  {ep['response_example'][:200]}")


def monitor_mode(client: SaleworkClient):
    """Chế độ giám sát liên tục - in ra console."""
    print("\n" + "=" * 60)
    print("  MONITOR MODE - Giám sát nhân sự")
    print("  Nhấn Ctrl+C để thoát")
    print("=" * 60)

    try:
        while True:
            now = datetime.now().strftime("%H:%M:%S")
            print(f"\n--- {now} ---")

            # Check work hours today
            wh = client.get_work_hours_today()
            if wh:
                print("[WORK HOURS]", json.dumps(wh, ensure_ascii=False)[:500])

            # Check activities
            act = client.get_activities(limit=5)
            if act:
                print("[ACTIVITIES]", json.dumps(act, ensure_ascii=False)[:300])

            time.sleep(60)  # Check mỗi 60 giây
    except KeyboardInterrupt:
        print("\n[MONITOR] Đã dừng giám sát.")


def main():
    import sys

    if "--monitor" in sys.argv:
        client = SaleworkClient()
        monitor_mode(client)
        return

    if "--summary" in sys.argv:
        show_endpoints_summary()
        return

    if "--discover" in sys.argv:
        client = SaleworkClient()
        discover_and_save(client)
        return

    # Default: show summary + discover
    show_endpoints_summary()

    client = SaleworkClient()
    results = discover_and_save(client)

    # In kết quả tóm tắt
    print("\n" + "=" * 60)
    print("  TÓM TẮT DỮ LIỆU GIÁM SÁT")
    print("=" * 60)

    for name, data in results.items():
        if data and "error" not in data:
            if isinstance(data, list):
                print(f"\n  {name.upper()}: {len(data)} bản ghi")
                if data:
                    sample = data[0] if isinstance(data[0], dict) else data[0]
                    if isinstance(sample, dict):
                        print(f"    Sample keys: {list(sample.keys())[:10]}")
            elif isinstance(data, dict) and "_raw" not in data:
                print(f"\n  {name.upper()}: {list(data.keys())[:10]}")


if __name__ == "__main__":
    main()
