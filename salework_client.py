#!/usr/bin/env python3
"""
Salework.net / Zalo Client — Full API Wrapper cho Agent & Automation
=====================================================================
Tất cả API đã được extract & test từ: salework.net + zalo.salework.net

Dùng cho:
  - Giám sát tin nhắn Zalo (3 kênh kinh doanh)
  - Quản lý danh bạ (3176 contacts)
  - Theo dõi hoạt động nhân viên
  - Báo cáo tự động
  - Agent tự động hóa

Usage:
  from salework_client import SaleworkClient
  client = SaleworkClient()
  client.login()
  contacts = client.contacts_search("Duy")
  msgs = client.messages_get("542711..._153265..._0_0", "542711...")
  log = client.activity_log("856268701098479404")
"""

import json
import os
import uuid
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

import requests
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_URL = "https://salework.net"
ZALO_URL = "https://zalo.salework.net"
SESSION_FILE = "session.json"
TOKENS_FILE = "tokens.json"
TZ7 = timezone(timedelta(hours=7))  # UTC+7 Vietnam

# 3 tài khoản Zalo kinh doanh
ACCOUNTS_MAP = {
    "856268701098479404": "Huyền Camera Creta",
    "2222439369543489081": "Phụ kiện camera CRETA",
    "542711705589461152": "Trang PK camera Creta",
}


class SaleworkClient:
    """Client đầy đủ cho toàn bộ hệ thống Salework + Zalo."""

    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        })
        self.user_token = None
        self.accounts: List[Dict] = []
        self._load_auth()

    # ===================================================================
    # AUTHENTICATION
    # ===================================================================

    def _load_auth(self):
        """Nạp token & cookies từ file đã lưu."""
        if os.path.exists(TOKENS_FILE):
            with open(TOKENS_FILE) as f:
                tokens = json.load(f)
            self.user_token = tokens.get("userToken")
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE) as f:
                sess = json.load(f)
            for c in sess.get("cookies", []):
                self.s.cookies.set(
                    c["name"], c["value"],
                    domain=c.get("domain", "").lstrip("."),
                    path=c.get("path", "/"),
                )

    def login(self, username: str = "black", password: str = "admin@123") -> bool:
        """
        Đăng nhập tự động bằng Playwright headless.
        Lưu session cookies + JWT tokens để tái sử dụng.

        Returns:
            True nếu thành công.
        """
        print(f"[LOGIN] {username} -> salework.net...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()

            # Step 1: Login form
            page.goto(f"{BASE_URL}/login/cretashop", wait_until="networkidle", timeout=30000)
            page.fill('input[name="staffUsername"]', username)
            page.fill('input[name="password"]', password)
            page.click('button[type="submit"]')

            try:
                page.wait_for_url(lambda u: "login" not in u.lower(), timeout=15000)
            except Exception:
                print(f"[LOGIN] FAILED -> {page.url}")
                browser.close()
                return False

            # Step 2: Lưu cookies
            cookies = context.cookies()
            with open(SESSION_FILE, "w") as f:
                json.dump({"cookies": cookies, "base_url": page.url}, f, ensure_ascii=False, indent=2)
            for c in cookies:
                self.s.cookies.set(c["name"], c["value"], domain=c.get("domain", "").lstrip("."), path=c.get("path", "/"))

            # Step 3: Vào Zalo SPA để lấy JWT tokens
            page.goto(ZALO_URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(5000)
            tokens = page.evaluate("""() => ({
                userToken: localStorage.getItem('userToken'),
                loginV2Token: localStorage.getItem('loginV2Token'),
                cToken: localStorage.getItem('cToken'),
                userTokenExpTime: localStorage.getItem('userTokenExpTime'),
            })""")
            with open(TOKENS_FILE, "w") as f:
                json.dump(tokens, f, ensure_ascii=False, indent=2)
            self.user_token = tokens.get("userToken")

            browser.close()
        print(f"[LOGIN] OK — session + tokens saved.")
        return True

    @property
    def is_authenticated(self) -> bool:
        """Kiểm tra đã có token chưa, nếu chưa thì login."""
        if not self.user_token:
            return self.login()
        return True

    def _api_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.user_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _api_get(self, path: str, base: str = ZALO_URL, **kwargs) -> requests.Response:
        kwargs.setdefault("headers", {}).update(self._api_headers())
        return self.s.get(f"{base}{path}", timeout=kwargs.pop("timeout", 15), **kwargs)

    def _api_post(self, path: str, base: str = ZALO_URL, **kwargs) -> requests.Response:
        kwargs.setdefault("headers", {}).update(self._api_headers())
        return self.s.post(f"{base}{path}", timeout=kwargs.pop("timeout", 15), **kwargs)

    # ===================================================================
    # ACCOUNTS (tài khoản Zalo)
    # ===================================================================

    def accounts_get_all(self) -> List[Dict]:
        """Lấy danh sách tài khoản Zalo đã kết nối."""
        r = self._api_get("/api/account/getAll")
        if r.status_code == 200 and r.json().get("status") == "success":
            self.accounts = r.json()["data"]
            return self.accounts
        return []

    def accounts_get_settings(self) -> List[Dict]:
        """Lấy cài đặt từng tài khoản (displayName, checkBadWord...)."""
        r = self._api_get("/api/account/setting/get")
        return r.json().get("data", []) if r.status_code == 200 else []

    # ===================================================================
    # CONTACTS / DANH BẠ (API từ trang /contact)
    # ===================================================================

    def contacts_list(self, account_id: str = None, page: int = 0, page_size: int = 50) -> List[Dict]:
        """
        Lấy danh sách danh bạ đầy đủ (có phân trang).

        Args:
            account_id: ID tài khoản Zalo (mặc định: tài khoản đầu tiên)
            page: Trang (bắt đầu từ 0)
            page_size: Số lượng mỗi trang
        """
        if not account_id:
            self.accounts_get_all()
            account_id = self.accounts[0]["accountId"] if self.accounts else None
            if not account_id:
                return []
        r = self._api_get(f"/api/contact/filter?searchKey=&accountId={account_id}&page={page}&pageSize={page_size}")
        if r.status_code == 200:
            return r.json().get("data", {}).get("content", [])
        return []

    def contacts_search(self, keyword: str, account_id: str = None, page_size: int = 50) -> List[Dict]:
        """
        Tìm kiếm danh bạ theo tên / số điện thoại.

        Args:
            keyword: Từ khóa tìm kiếm
            account_id: ID tài khoản (None = tài khoản đầu tiên)
        """
        if not account_id:
            self.accounts_get_all()
            account_id = self.accounts[0]["accountId"] if self.accounts else None
            if not account_id:
                return []
        r = self._api_get(f"/api/contact/filter?searchKey={keyword}&accountId={account_id}&page=0&pageSize={page_size}")
        if r.status_code == 200:
            return r.json().get("data", {}).get("content", [])
        return []

    def contacts_get_all(self, account_id: str = None, max_pages: int = 50) -> List[Dict]:
        """
        Lấy TOÀN BỘ danh bạ (tự động phân trang).

        Args:
            account_id: ID tài khoản
            max_pages: Giới hạn số trang (mỗi trang 100)
        """
        all_contacts = []
        if not account_id:
            self.accounts_get_all()
            account_id = self.accounts[0]["accountId"] if self.accounts else None
            if not account_id:
                return []
        for page in range(max_pages):
            contacts = self.contacts_list(account_id, page=page, page_size=100)
            if not contacts:
                break
            all_contacts.extend(contacts)
        return all_contacts

    def contacts_sw_list(self, account_id: str = None) -> List[Dict]:
        """
        Lấy danh sách SW Contact (đã lưu trong hệ thống Salework).

        Mỗi contact có: id, accountId, phone, uid, name, avatar, tags...
        """
        if not account_id:
            self.accounts_get_all()
            account_id = self.accounts[0]["accountId"] if self.accounts else None
            if not account_id:
                return []
        r = self._api_get(f"/api/contact/swContact?accountId={account_id}")
        return r.json().get("data", []) if r.status_code == 200 else []

    def contacts_recommend_friends(self, account_id: str = None) -> Dict:
        """Lấy danh sách gợi ý kết bạn."""
        if not account_id:
            self.accounts_get_all()
            account_id = self.accounts[0]["accountId"] if self.accounts else None
            if not account_id:
                return {}
        r = self._api_get(f"/api/contact/recommendFriend?accountId={account_id}")
        return r.json().get("data", {}) if r.status_code == 200 else {}

    def contacts_requested_friends(self, account_id: str = None) -> Dict:
        """Lấy danh sách đã gửi lời mời kết bạn."""
        if not account_id:
            self.accounts_get_all()
            account_id = self.accounts[0]["accountId"] if self.accounts else None
            if not account_id:
                return {}
        r = self._api_get(f"/api/contact/requestedFriends?accountId={account_id}")
        return r.json().get("data", {}) if r.status_code == 200 else {}

    # ===================================================================
    # CONVERSATIONS (hội thoại)
    # ===================================================================

    def conversations_list(self, page_size: int = 100, search_key: str = "",
                           unread_only: bool = False) -> List[Dict]:
        """
        Lấy danh sách hội thoại (API V1).

        Args:
            page_size: Số lượng (max ~100)
            search_key: Từ khóa tìm kiếm theo tên
            unread_only: Chỉ lấy hội thoại chưa đọc
        """
        body = {
            "isGroup": None, "unread": unread_only, "unReplied": None,
            "searchKey": search_key, "accountIds": [], "lastMessageTime": 0,
            "selectedTags": [], "dateRange": [], "pageSize": page_size,
            "searchId": str(uuid.uuid4())[:6],
        }
        r = self._api_post("/api/conversation", json=body)
        if r.status_code == 200 and r.json().get("status") == "success":
            return r.json()["data"]
        return []

    def conversations_list_v2(self, account_id: str = None, search_key: str = "",
                              page: int = 1, page_size: int = 20,
                              conv_type: str = "all") -> List[Dict]:
        """
        Lấy danh sách hội thoại (API V2 — có phân trang).

        Args:
            account_id: ID tài khoản
            search_key: Từ khóa
            page: Trang (bắt đầu từ 1)
            page_size: Số lượng mỗi trang
            conv_type: "all" | "personal" | "group" | "hidden"
        """
        if not account_id:
            self.accounts_get_all()
            account_id = self.accounts[0]["accountId"] if self.accounts else None
            if not account_id:
                return []
        body = {
            "accountId": account_id, "searchKey": search_key,
            "selectedTags": None, "page": page, "pageSize": page_size,
            "type": conv_type,
        }
        r = self._api_post("/api/conversationV2/allV2", json=body)
        if r.status_code == 200:
            return r.json().get("data", {}).get("content", [])
        return []

    def conversations_count(self, account_id: str = None) -> Dict:
        """
        Thống kê số lượng hội thoại.

        Returns:
            {"all": N, "personal": N, "group": N, "hidden": N, "page": N}
        """
        if not account_id:
            self.accounts_get_all()
            account_id = self.accounts[0]["accountId"] if self.accounts else None
            if not account_id:
                return {}
        r = self._api_post("/api/conversationV2/count-by-type", json={
            "accountId": account_id, "searchKey": "", "selectedTags": None,
            "page": 1, "pageSize": 20, "type": "all",
        })
        return r.json().get("data", {}) if r.status_code == 200 else {}

    def conversations_pinned(self) -> List[Dict]:
        """Lấy danh sách hội thoại đã ghim."""
        r = self._api_get("/api/conversation/pin")
        return r.json().get("data", []) if r.status_code == 200 else []

    # ===================================================================
    # MESSAGES (tin nhắn)
    # ===================================================================

    def messages_get(self, conversation_id: str, account_id: str,
                     page_size: int = 50, before_timestamp: str = "",
                     after_timestamp: str = "") -> List[Dict]:
        """
        Lấy tin nhắn của 1 hội thoại.

        Args:
            conversation_id: "542711..._153265..._0_0"
            account_id: ID tài khoản Zalo
            page_size: Số lượng (max ~50)
            before_timestamp: Lấy tin nhắn CŨ HƠN ts này (exclusive)
            after_timestamp: Lấy tin nhắn MỚI HƠN hoặc bằng ts này (inclusive)
        """
        body = {
            "conversationId": conversation_id,
            "accountId": account_id,
            "timestamp": before_timestamp,
            "timestampAfter": after_timestamp,
            "pageSize": page_size,
        }
        r = self._api_post("/api/message/filter", json=body)
        if r.status_code == 200 and r.json().get("status") == "success":
            return r.json()["data"]
        return []

    def messages_get_all(self, conversation_id: str, account_id: str,
                         max_pages: int = 50) -> List[Dict]:
        """Lấy tất cả tin nhắn từ mới nhất đến cũ nhất (tự động phân trang)."""
        all_msgs = []
        oldest_ts = ""
        for _ in range(max_pages):
            msgs = self.messages_get(conversation_id, account_id,
                                     page_size=50, before_timestamp=oldest_ts)
            if not msgs:
                break
            all_msgs.extend(msgs)
            oldest_ts = msgs[-1].get("ts", "")
            if len(msgs) < 50:
                break
        return all_msgs

    def messages_pinned(self, account_id: str, to_id: str, is_group: bool = False) -> Dict:
        """Lấy tin nhắn đã ghim trong hội thoại."""
        r = self._api_post("/api/messageV2/pinMsgList", json={
            "accountId": account_id, "toId": to_id, "group": is_group, "page": False,
        })
        return r.json() if r.status_code == 200 else {}

    def messages_media(self, conversation_id: str, account_id: str) -> List[Dict]:
        """Lấy ảnh/video trong hội thoại."""
        r = self._api_post("/api/message/filterMedia", json={
            "conversationId": conversation_id, "accountId": account_id,
        })
        return r.json().get("data", []) if r.status_code == 200 else []

    def messages_links(self, conversation_id: str, account_id: str) -> List[Dict]:
        """Lấy link đã gửi trong hội thoại."""
        r = self._api_post("/api/message/filterLink", json={
            "conversationId": conversation_id, "accountId": account_id,
        })
        return r.json().get("data", []) if r.status_code == 200 else []

    def messages_files(self, conversation_id: str, account_id: str) -> List[Dict]:
        """Lấy file đã gửi trong hội thoại."""
        r = self._api_post("/api/message/filterFile", json={
            "conversationId": conversation_id, "accountId": account_id,
        })
        return r.json().get("data", []) if r.status_code == 200 else []

    def messages_filter_by_type(self, conversation_id: str, account_id: str,
                                 msg_types: List[str], page_size: int = 50,
                                 before_timestamp: str = "") -> List[Dict]:
        """
        Lọc tin nhắn theo loại (V2 API).

        Args:
            msg_types: Danh sách loại tin nhắn
                ["chat.photo"]         -> chỉ ảnh
                ["chat.video.msg"]     -> chỉ video
                ["webchat"]            -> chỉ text
                ["chat.sticker"]       -> chỉ sticker
                ["chat.photo","chat.video.msg"] -> ảnh + video
                []                     -> tất cả
            before_timestamp: Phân trang (lấy tin cũ hơn ts này)
        """
        r = self._api_post("/api/messageV2/filter", json={
            "conversationId": conversation_id,
            "accountId": account_id,
            "timestamp": before_timestamp,
            "msgTypes": msg_types,
            "pageSize": page_size,
        })
        if r.status_code == 200:
            return r.json().get("data", [])
        return []

    def messages_search(self, keyword: str, account_ids: List[str] = None,
                        max_convs: int = 30) -> List[Dict]:
        """
        Tìm tin nhắn theo từ khóa trong nhiều hội thoại.

        Args:
            keyword: Từ khóa
            account_ids: Giới hạn tài khoản (None = tất cả)
            max_convs: Số hội thoại tối đa để quét
        """
        convs = self.conversations_list(page_size=max_convs)
        if account_ids:
            convs = [c for c in convs if c["accountId"] in account_ids]

        results = []
        for c in convs:
            msgs = self.messages_get(c["id"], c["accountId"], page_size=50)
            for m in msgs:
                content = m.get("content", "")
                if isinstance(content, dict):
                    content = json.dumps(content, ensure_ascii=False)
                if keyword.lower() in content.lower():
                    results.append({
                        "conversation": c["toName"],
                        "conversation_id": c["id"],
                        "account_id": c["accountId"],
                        "message": m,
                    })
        return results

    # ===================================================================
    # SEND MESSAGE (gửi tin nhắn)
    # ===================================================================

    def send_message(self, account_id: str, to_id: str, conversation_id: str,
                     message: str, banned_keyword: List[str] = None) -> Dict:
        """
        Gửi tin nhắn Zalo qua API.

        Args:
            account_id: ID tài khoản Zalo gửi
            to_id: Zalo UID người nhận
            conversation_id: ID hội thoại
            message: Nội dung tin nhắn
            banned_keyword: Danh sách từ khóa cấm (mặc định [])

        Returns:
            {"msgId": "...", "status": "success"}
        """
        r = self._api_post("/api/message/sms", json={
            "accountId": account_id,
            "toId": to_id,
            "message": message,
            "conversationId": conversation_id,
            "bannedKeyword": banned_keyword or [],
        })
        if r.status_code == 200:
            return r.json()
        return {"error": r.text}

    def send_typing(self, account_id: str, conversation_id: str,
                    username: str, typing_type: str = "typing") -> Dict:
        """Gửi trạng thái đang nhập (typing indicator)."""
        r = self._api_post("/api/conversation/typing", json={
            "accountId": account_id,
            "conversationId": conversation_id,
            "type": typing_type,
            "username": username,
        })
        return r.json() if r.status_code == 200 else {}

    def send_message_by_phone(self, phone: str, message: str,
                              account_id: str = None) -> Dict:
        """
        Gửi tin nhắn theo số điện thoại (tự tìm conversation).

        Args:
            phone: Số điện thoại (vd: "0932032732")
            message: Nội dung
            account_id: Tài khoản gửi (mặc định: Huyền)
        """
        if not account_id:
            self.accounts_get_all()
            account_id = self.accounts[0]["accountId"] if self.accounts else None
            if not account_id:
                return {"error": "No account available"}

        # Tìm conversation bằng phone
        conv = None
        for fmt in [phone, f"+84{phone[1:]}", f"84{phone[1:]}"]:
            r = self._api_post("/api/conversationV2/allV2", json={
                "accountId": account_id, "searchKey": fmt,
                "selectedTags": None, "page": 1, "pageSize": 10, "type": "all",
            })
            for item in r.json().get("data", {}).get("content", []):
                zc = item.get("zaloConversation", item)
                if phone.replace("+84", "").replace("84", "").lstrip("0") in \
                   (zc.get("phone", "") or "").replace("+84", "").replace("84", "").lstrip("0"):
                    conv = zc
                    break
            if conv:
                break

        if not conv:
            return {"error": f"Không tìm thấy conversation cho số {phone}"}

        return self.send_message(
            account_id=account_id,
            to_id=conv["toId"],
            conversation_id=conv["id"],
            message=message,
        )

    # ===================================================================
    # SEND PHOTO / FILE (gửi ảnh, file)
    # ===================================================================

    def send_photo(self, account_id: str, to_id: str, conversation_id: str,
                   file_id: str, id_in_group: str = "0",
                   total_items: str = "0", group_msg_id: str = "0") -> Dict:
        """
        Gửi ảnh từ thư viện tài liệu.

        Args:
            file_id: ID file trong thư viện (vd: "85313b9ef2ce4270a.png")
        """
        r = self._api_get("/api/message/sendPhoto", params={
            "conversationId": conversation_id,
            "id": file_id,
            "accountId": account_id,
            "toId": to_id,
            "idInGroup": id_in_group,
            "totalItems": total_items,
            "groupMsgId": group_msg_id,
        })
        return r.json() if r.status_code == 200 else {"error": r.text}

    def send_photos_group(self, account_id: str, to_id: str, conversation_id: str,
                          file_ids: List[str]) -> Dict:
        """
        Gửi nhiều ảnh trong 1 khung (group).

        Args:
            file_ids: Danh sách ID file trong thư viện
        """
        total = len(file_ids)
        group_msg_id = str(int(time.time() * 1000))
        results = []
        for i, file_id in enumerate(file_ids):
            r = self._api_get("/api/message/sendPhoto", params={
                "conversationId": conversation_id,
                "id": file_id,
                "accountId": account_id,
                "toId": to_id,
                "idInGroup": str(i),
                "totalItems": str(total),
                "groupMsgId": group_msg_id,
            })
            results.append(r.json() if r.status_code == 200 else {"error": r.text})
        return {"groupMsgId": group_msg_id, "totalItems": total, "results": results}

    def send_photo_direct(self, account_id: str, to_id: str, conversation_id: str,
                          file_path: str) -> Dict:
        """
        Gửi ảnh trực tiếp (multipart upload, không qua thư viện).

        Args:
            file_path: Đường dẫn file ảnh
        """
        import os as _os
        file_name = _os.path.basename(file_path)
        mime = "image/jpeg" if file_path.lower().endswith((".jpg", ".jpeg")) else \
               "image/png" if file_path.lower().endswith(".png") else \
               "image/gif" if file_path.lower().endswith(".gif") else "image/jpeg"

        with open(file_path, "rb") as f:
            r = self.s.post(
                f"{ZALO_URL}/api/message/sendMsgPhoto",
                params={
                    "accountId": account_id, "toId": to_id,
                    "conversationId": conversation_id,
                    "groupId": "0", "totalItems": "0",
                    "idInGroup": "0", "debtId": "",
                },
                files={"file": (file_name, f, mime)},
                headers=self._api_headers(),
                timeout=60,
            )
        return r.json() if r.status_code == 200 else {"error": r.text}

    def send_photos_direct_group(self, account_id: str, to_id: str,
                                 conversation_id: str, file_paths: List[str]) -> Dict:
        """
        Gửi nhiều ảnh trong 1 khung (multipart upload).

        Args:
            file_paths: Danh sách đường dẫn file ảnh
        """
        import os as _os
        total = len(file_paths)
        group_msg_id = str(int(time.time() * 1000))
        results = []

        # Nếu gửi 1 ảnh: dùng totalItems=0
        if total == 1:
            return self.send_photo_direct(account_id, to_id, conversation_id, file_paths[0])

        # Nhiều ảnh: gửi từng cái với cùng groupMsgId
        for i, fp in enumerate(file_paths):
            file_name = _os.path.basename(fp)
            mime = "image/jpeg" if fp.lower().endswith((".jpg", ".jpeg")) else \
                   "image/png" if fp.lower().endswith(".png") else "image/jpeg"
            with open(fp, "rb") as f:
                r = self.s.post(
                    f"{ZALO_URL}/api/message/sendMsgPhoto",
                    params={
                        "accountId": account_id, "toId": to_id,
                        "conversationId": conversation_id,
                        "groupId": str(group_msg_id),
                        "totalItems": str(total),
                        "idInGroup": str(i),
                        "debtId": "",
                    },
                    files={"file": (file_name, f, mime)},
                    headers=self._api_headers(),
                    timeout=60,
                )
                results.append(r.json() if r.status_code == 200 else {"error": r.text})
        return {"groupMsgId": group_msg_id, "totalItems": total, "results": results}

    def image_library_list(self, folder_id: str = "0", account_id: str = "0") -> List[Dict]:
        """Lấy danh sách ảnh trong thư viện tài liệu."""
        r = self._api_get(f"/api/v2/image?accountId={account_id}&folderId={folder_id}")
        return r.json().get("data", []) if r.status_code == 200 else []

    def image_library_upload(self, file_path: str, account_id: str) -> Dict:
        """
        Upload ảnh lên thư viện tài liệu.

        Args:
            file_path: Đường dẫn file ảnh trên máy
            account_id: ID tài khoản Zalo
        """
        import base64
        with open(file_path, "rb") as f:
            file_data = base64.b64encode(f.read()).decode("ascii")
            file_name = file_path.split("/")[-1]

        r = self._api_post("/api/hub/saveImageByClient", json={
            "accountId": account_id,
            "fileName": file_name,
            "fileData": file_data,
        })
        return r.json() if r.status_code == 200 else {"error": r.text}

    def send_photo_by_phone(self, phone: str, file_path: str,
                            account_id: str = None) -> Dict:
        """
        Gửi ảnh theo số điện thoại (tự upload + gửi).

        Args:
            phone: Số điện thoại người nhận
            file_path: Đường dẫn file ảnh
            account_id: Tài khoản gửi
        """
        if not account_id:
            self.accounts_get_all()
            account_id = self.accounts[0]["accountId"] if self.accounts else None
            if not account_id:
                return {"error": "No account available"}

        # Tìm conversation
        conv = None
        for fmt in [phone, f"+84{phone[1:]}", f"84{phone[1:]}"]:
            r = self._api_post("/api/conversationV2/allV2", json={
                "accountId": account_id, "searchKey": fmt,
                "selectedTags": None, "page": 1, "pageSize": 10, "type": "all",
            })
            for item in r.json().get("data", {}).get("content", []):
                zc = item.get("zaloConversation", item)
                if phone.replace("+84", "").replace("84", "").lstrip("0") in \
                   (zc.get("phone", "") or "").replace("+84", "").replace("84", "").lstrip("0"):
                    conv = zc
                    break
            if conv:
                break

        if not conv:
            return {"error": f"Không tìm thấy conversation cho số {phone}"}

        # Upload ảnh
        upload_result = self.image_library_upload(file_path, account_id)
        print(f"[UPLOAD] {upload_result}")

        # Lấy file ID từ response
        file_id = upload_result.get("data", {}).get("id") or upload_result.get("data", "")
        if not file_id:
            return {"error": f"Upload failed: {upload_result}"}

        # Gửi ảnh
        return self.send_photo(
            account_id=account_id,
            to_id=conv["toId"],
            conversation_id=conv["id"],
            file_id=str(file_id),
        )

    # ===================================================================
    # PROFILE / USER INFO
    # ===================================================================

    def profile_get(self, account_id: str, to_id: str) -> Dict:
        """Lấy thông tin chi tiết 1 người dùng Zalo."""
        r = self._api_post("/api/messageV2/getProfileInfo", json={
            "accountId": account_id, "toId": to_id, "group": False, "page": False,
        })
        if r.status_code == 200:
            data = r.json()
            profiles = data.get("data", {}).get("data", {}).get("changed_profiles", {})
            return profiles.get(str(to_id), {})
        return {}

    def profile_online_status(self, account_id: str, to_id: str) -> Dict:
        """Kiểm tra trạng thái online của 1 người."""
        r = self._api_post("/api/messageV2/onlineStatus", json={
            "accountId": account_id, "toId": to_id, "group": False, "page": False,
        })
        if r.status_code == 200:
            return r.json().get("data", {}).get("data", {})
        return {}

    # ===================================================================
    # ACTIVITY LOG (lịch sử hoạt động nhân viên)
    # ===================================================================

    def activity_log(self, account_id: str = None, page: int = 1, page_size: int = 50,
                     log_type: str = "all", sw_username: str = "") -> List[Dict]:
        """
        Lấy log hoạt động (ai gửi/nhận/chấp nhận, lúc nào).

        Args:
            account_id: ID tài khoản Zalo
            page: Trang (bắt đầu từ 1)
            page_size: Số lượng mỗi trang
            log_type: "all" | "send" | "accept" | "undo" | ...
            sw_username: Lọc theo nhân viên (vd: "cretashop/trang")
        """
        if not account_id:
            self.accounts_get_all()
            account_id = self.accounts[0]["accountId"] if self.accounts else None
            if not account_id:
                return []
        r = self._api_post("/api/log", json={
            "page": page, "pageSize": page_size, "accountId": account_id,
            "type": log_type, "swUsername": sw_username,
        })
        if r.status_code == 200:
            return r.json().get("data", {}).get("content", [])
        return []

    def activity_log_all(self, account_id: str = None, max_pages: int = 20) -> List[Dict]:
        """Lấy toàn bộ activity log (tự động phân trang)."""
        all_logs = []
        for page in range(1, max_pages + 1):
            logs = self.activity_log(account_id, page=page, page_size=100)
            if not logs:
                break
            all_logs.extend(logs)
        return all_logs

    # ===================================================================
    # GROUP INFO
    # ===================================================================

    def group_info(self, group_id: str) -> Dict:
        """Lấy thông tin nhóm."""
        r = self._api_get(f"/api/message/groupInfoV2?groupId={group_id}")
        return r.json() if r.status_code == 200 else {}

    def group_members(self, group_id: str) -> List[Dict]:
        """Lấy danh sách thành viên nhóm."""
        r = self._api_post("/api/conversation/groupMember", json={"groupId": group_id})
        return r.json().get("data", []) if r.status_code == 200 else []

    def groups_get_all_ids(self) -> List[str]:
        """Lấy tất cả group IDs."""
        r = self._api_get("/api/conversation/getAllGroupId")
        return r.json().get("data", []) if r.status_code == 200 else []

    # ===================================================================
    # NOTIFICATIONS (Salework.net)
    # ===================================================================

    def notifications_fetch(self) -> Dict:
        """Lấy thông báo mới nhất từ Salework.net."""
        r = self._api_get("/api/noti/fetch", base=BASE_URL)
        if r.status_code == 200:
            return r.json().get("data", {})
        return {}

    # ===================================================================
    # TAGS
    # ===================================================================

    def tags_get_all(self) -> List[Dict]:
        """Lấy tất cả tags."""
        r = self._api_get("/api/tag")
        return r.json().get("data", []) if r.status_code == 200 else []

    # ===================================================================
    # EMPLOYEE / NHÂN SỰ (Salework.net)
    # ===================================================================

    def employees_get_all(self) -> List[Dict]:
        """Lấy danh sách nhân viên (cần quyền admin)."""
        r = self._api_get("/api/employee/all", base=BASE_URL)
        if r.status_code == 200 and r.json().get("status") == "success":
            return r.json()["data"]
        return []

    # ===================================================================
    # REPORTS / BÁO CÁO
    # ===================================================================

    def report_today_summary(self) -> Dict:
        """
        Báo cáo tổng quan hôm nay:
        - Số người nhắn tin
        - Phân theo 3 kênh
        - Top hội thoại
        """
        today_start_ms = int(
            datetime.now(TZ7).replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000
        )
        convs = self.conversations_list(page_size=200)
        today_convs = [c for c in convs
                       if isinstance(c.get("lastMessageTime"), (int, float))
                       and c["lastMessageTime"] >= today_start_ms]

        unique_people = set(c["toName"] for c in today_convs)

        by_account = {}
        for c in today_convs:
            acc = ACCOUNTS_MAP.get(c["accountId"], c["accountId"])
            by_account.setdefault(acc, []).append(c)

        # Keywords hỏi hàng
        buy_keywords = ["giá", "bao nhiêu", "còn hàng", "mua", "đặt", "ship", "giao",
                        "báo giá", "tổng đơn", "ck", "chuyển khoản", "tiền", "gửi a",
                        "gửi e", "nha a", "nha e", "vat", "tx", "cọc"]

        result = {
            "date": datetime.now(TZ7).strftime("%d/%m/%Y"),
            "total_conversations_today": len(today_convs),
            "unique_people_today": len(unique_people),
            "by_account": {},
            "top_conversations": sorted(today_convs, key=lambda x: x.get("lastMessageTime", 0), reverse=True)[:30],
        }

        for acc_name, items in by_account.items():
            uniq = set(c["toName"] for c in items)
            asking = sum(1 for c in items
                        if any(kw in str(c.get("lastMessageContent", "")).lower() for kw in buy_keywords))
            result["by_account"][acc_name] = {
                "conversations": len(items),
                "unique_people": len(uniq),
                "likely_buying": asking,
            }

        return result

    def report_print_today(self):
        """In báo cáo hôm nay ra console."""
        r = self.report_today_summary()
        print(f"\n{'='*60}")
        print(f"  📊 BÁO CÁO NGÀY {r['date']}")
        print(f"{'='*60}")
        print(f"  Tổng hội thoại active: {r['total_conversations_today']}")
        print(f"  Số người nhắn: {r['unique_people_today']}")
        print(f"\n  --- Phân theo kênh ---")
        for acc, info in r["by_account"].items():
            print(f"  {acc}: {info['conversations']} tin / {info['unique_people']} người / ~{info['likely_buying']} hỏi hàng")
        print(f"\n  --- Top tin nhắn ---")
        for c in r["top_conversations"][:15]:
            ts = datetime.fromtimestamp(c["lastMessageTime"] / 1000, tz=TZ7).strftime("%H:%M")
            last = str(c.get("lastMessageContent", ""))[:70]
            print(f"  [{ts}] {c['toName'][:40]}")
            print(f"         {last}")

    # ===================================================================
    # EXPORT
    # ===================================================================

    def export_contacts(self, filepath: str = "api_data/contacts.json", account_id: str = None):
        """Xuất toàn bộ danh bạ ra JSON."""
        contacts = self.contacts_get_all(account_id)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(contacts, f, ensure_ascii=False, indent=2)
        print(f"[EXPORT] {len(contacts)} contacts -> {filepath}")
        return contacts

    def export_conversations(self, filepath: str = "api_data/conversations.json"):
        """Xuất toàn bộ hội thoại ra JSON."""
        convs = self.conversations_list(page_size=200)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(convs, f, ensure_ascii=False, indent=2)
        print(f"[EXPORT] {len(convs)} conversations -> {filepath}")
        return convs

    def export_messages(self, conversation_id: str, account_id: str,
                        filepath: str = "api_data/messages.json", max_pages: int = 20):
        """Xuất toàn bộ tin nhắn của 1 hội thoại."""
        msgs = self.messages_get_all(conversation_id, account_id, max_pages=max_pages)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(msgs, f, ensure_ascii=False, indent=2)
        print(f"[EXPORT] {len(msgs)} messages -> {filepath}")
        return msgs

    def export_activity_log(self, filepath: str = "api_data/activity_log.json", account_id: str = None):
        """Xuất toàn bộ activity log."""
        logs = self.activity_log_all(account_id)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
        print(f"[EXPORT] {len(logs)} log entries -> {filepath}")
        return logs

    def export_all(self):
        """Xuất tất cả dữ liệu."""
        os.makedirs("api_data", exist_ok=True)
        self.export_conversations()
        self.export_contacts()
        self.export_activity_log()
        for c in self.conversations_list(page_size=5):
            safe_name = c["toName"][:30].replace(" ", "_").replace("/", "-")
            self.export_messages(c["id"], c["accountId"],
                                 filepath=f"api_data/messages_{safe_name}.json",
                                 max_pages=3)
        print("[EXPORT] All done!")


# ===================================================================
# CLI
# ===================================================================

if __name__ == "__main__":
    import sys

    os.makedirs("api_data", exist_ok=True)
    client = SaleworkClient()

    if not client.is_authenticated:
        print("Không thể đăng nhập.")
        sys.exit(1)

    if "--report" in sys.argv:
        client.report_print_today()

    elif "--contacts" in sys.argv:
        if len(sys.argv) > 2 and sys.argv[2] not in ("--",):
            keyword = sys.argv[2]
            results = client.contacts_search(keyword)
            print(f"\n=== Tìm '{keyword}' -> {len(results)} kết quả ===")
            for c in results:
                print(f"  {c.get('displayName', '?')[:50]} | {c.get('zaloName', '?')} | {c.get('phoneNumber', '?')}")
        else:
            contacts = client.contacts_list(page_size=30)
            print(f"\n=== DANH BẠ ({len(contacts)} trên page 1) ===")
            for c in contacts:
                print(f"  {c.get('displayName', '?')[:50]} | {c.get('zaloName', '?')}")

    elif "--sw-contacts" in sys.argv:
        contacts = client.contacts_sw_list()
        print(f"\n=== SW CONTACTS ({len(contacts)}) ===")
        for c in contacts:
            print(f"  {c.get('name', '?')[:40]} | {c.get('phone', '?')}")

    elif "--messages" in sys.argv:
        convs = client.conversations_list(page_size=5)
        for conv in convs:
            msgs = client.messages_get(conv["id"], conv["accountId"], page_size=5)
            print(f"\n=== {conv['toName'][:50]} ===")
            for m in msgs:
                direction = "←" if m.get("id", {}).get("uidFrom") != conv["accountId"] else "→"
                content = str(m.get("content", ""))[:80]
                print(f"  {direction} {content}")

    elif "--log" in sys.argv:
        logs = client.activity_log(page_size=20)
        print(f"\n=== ACTIVITY LOG ({len(logs)}) ===")
        for l in logs:
            ts = datetime.fromtimestamp(l.get("timestamp", 0)).strftime("%d/%m %H:%M")
            print(f"  [{ts}] {l.get('type', '?')} | {l.get('swUsername', '?')}")

    elif "--search-msg" in sys.argv:
        kw = sys.argv[sys.argv.index("--search-msg") + 1]
        results = client.messages_search(kw)
        print(f"\n=== Tìm '{kw}' trong tin nhắn -> {len(results)} kết quả ===")
        for r in results:
            print(f"\n  Conv: {r['conversation'][:50]}")
            print(f"  Msg: {str(r['message'].get('content', ''))[:150]}")

    elif "--export" in sys.argv:
        client.export_all()

    elif "--conversations" in sys.argv:
        convs = client.conversations_list(page_size=30)
        for i, c in enumerate(convs):
            last = str(c.get("lastMessageContent", ""))[:60]
            print(f"  [{i}] {c['toName'][:45]} | {last}")

    elif "--stats" in sys.argv:
        for acc_id, acc_name in ACCOUNTS_MAP.items():
            counts = client.conversations_count(acc_id)
            print(f"  {acc_name}: {counts.get('all', '?')} total ({counts.get('personal', '?')} cá nhân + {counts.get('group', '?')} nhóm)")

    else:
        print("""
Salework/Zalo Client — Agent Toolkit
═══════════════════════════════════════

Commands:
  --report              Báo cáo tổng quan hôm nay
  --contacts [keyword]  Danh bạ / tìm kiếm
  --sw-contacts         Danh bạ đã lưu trong hệ thống
  --conversations       Danh sách hội thoại
  --messages            Tin nhắn mới nhất (5 conv)
  --search-msg <kw>     Tìm từ khóa trong tin nhắn
  --stats               Thống kê tổng 3 kênh
  --log                 Activity log nhân viên
  --export              Xuất tất cả dữ liệu ra JSON

Python usage:
  from salework_client import SaleworkClient
  client = SaleworkClient()
  client.login()
  contacts = client.contacts_search("Duy")
  report = client.report_today_summary()
""")
        # Default: show summary
        print("=== TÀI KHOẢN ===")
        for a in client.accounts_get_all():
            print(f"  {a['accountId']} | {a.get('displayName', '?')}")
        print(f"\n=== THỐNG KÊ ===")
        for acc_id, acc_name in ACCOUNTS_MAP.items():
            counts = client.conversations_count(acc_id)
            print(f"  {acc_name}: {counts.get('all', '?')} contacts")
