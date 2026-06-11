# Salework/Zalo Agent Toolkit

> Complete Python API wrapper for Salework.net + Zalo Chat.  
> Agent-ready: login, contacts, conversations, messages, send text/photo, activity log, reports.

## Quick Start (Agent)

```python
from salework_client import SaleworkClient

client = SaleworkClient()
client.login("username", "password")  # hoặc client.login() dùng mặc định

# 3 tài khoản Zalo kinh doanh:
#   "856268701098479404" = Huyền Camera Creta
#   "2222439369543489081" = Phụ kiện camera CRETA
#   "542711705589461152"  = Trang PK camera Creta
```

## API Reference

### 1. Tài khoản

```python
# Lấy 3 tài khoản Zalo
accounts = client.accounts_get_all()
# Returns: list[dict] với keys: accountId, displayName, phoneNumber, avatar
```

### 2. Danh bạ (Contacts)

```python
# Danh sách danh bạ (có phân trang)
contacts = client.contacts_list(
    account_id="856268701098479404",  # ID tài khoản Zalo
    page=0, page_size=50
)
# Returns: list[dict] keys: displayName, zaloName, phoneNumber, id, avatar

# Tìm danh bạ theo tên hoặc số điện thoại
results = client.contacts_search(
    keyword="Duy",                    # từ khóa tìm
    account_id="856268701098479404"
)

# Tải TOÀN BỘ danh bạ (tự động phân trang)
all_contacts = client.contacts_get_all(
    account_id="856268701098479404",
    max_pages=50
)

# Danh bạ đã lưu trong hệ thống (có phone đầy đủ)
sw_contacts = client.contacts_sw_list(account_id="856268701098479404")
# Returns: list[dict] keys: name, phone, uid, id, avatar

# Gợi ý kết bạn
recs = client.contacts_recommend_friends(account_id="856268701098479404")

# Danh sách đã gửi lời mời kết bạn
reqs = client.contacts_requested_friends(account_id="856268701098479404")
```

### 3. Hội thoại (Conversations)

```python
# Danh sách hội thoại (V1)
convs = client.conversations_list(
    page_size=100,
    search_key="Lâm",       # tìm theo tên (bỏ trống = tất cả)
    unread_only=False       # True = chỉ hội thoại chưa đọc
)
# Returns: list[dict] keys: id, toName, accountId, toId, phone,
#          lastMessageContent, lastMessageTime, avatar, unreadCount

# Danh sách hội thoại (V2 - có phân trang)
convs = client.conversations_list_v2(
    account_id="856268701098479404",
    search_key="",
    page=1, page_size=20,
    conv_type="all"   # "all" | "personal" | "group" | "hidden"
)

# Thống kê số lượng
stats = client.conversations_count("856268701098479404")
# Returns: {"all": 3176, "personal": 3084, "group": 88, "hidden": 8}

# Hội thoại đã ghim
pinned = client.conversations_pinned()
```

### 4. Tin nhắn (Messages)

```python
# Lấy tin nhắn của 1 hội thoại
msgs = client.messages_get(
    conversation_id="856268701098479404_2843928821831153337_0_0",
    account_id="856268701098479404",
    page_size=50,                      # max ~50
    before_timestamp="",               # để trống = lấy mới nhất
)
# Returns: list[dict] keys: id.msgId, id.uidFrom, content, msgType, ts, status

# Lấy tin CŨ HƠN 1 mốc (pagination về quá khứ)
older = client.messages_get(
    conv_id, acc_id,
    before_timestamp="1781192980170",   # ts của tin cũ nhất đã có
    page_size=50
)

# Lấy tin MỚI HƠN 1 mốc (poll realtime — kiểm tra có tin mới không)
newer = client.messages_get(
    conv_id, acc_id,
    after_timestamp="1781193224051",   # ts của tin mới nhất đã có
    page_size=50
)

# Tải TOÀN BỘ tin nhắn (tự động phân trang, từ mới nhất → cũ nhất)
all_msgs = client.messages_get_all(
    conv_id, acc_id,
    max_pages=50     # max 50 trang × 50 tin = 2500 tin
)

# Lọc tin nhắn theo LOẠI (V2)
photos_only = client.messages_filter_by_type(
    conv_id, acc_id,
    msg_types=["chat.photo"]            # "chat.photo" | "chat.video.msg" | "webchat" | "chat.sticker"
)

# Tin nhắn đã ghim
pinned = client.messages_pinned(acc_id, to_id="2843928821831153337")

# Tìm từ khóa trong nhiều hội thoại
results = client.messages_search(
    keyword="giá camera",
    account_ids=["856268701098479404"],  # None = tất cả tài khoản
    max_convs=30
)
```

### 5. Parse tin nhắn — Biết ai gửi

```python
# Mỗi tin nhắn raw có uidFrom (ID Zalo). Dùng message_parse để biết ai gửi:

msgs = client.messages_get(conv_id, acc_id, page_size=20)

for msg in msgs:
    parsed = client.message_parse(
        msg,
        account_name="Huyền (Creta)",   # tên hiển thị cho tin MÌNH gửi
        contact_name="Võ Thanh Lâm",    # tên hiển thị cho tin HỌ gửi
        account_id=acc_id
    )
    # parsed = {
    #     "direction": "in" hoặc "out",
    #     "sender": "Võ Thanh Lâm" hoặc "Huyền (Creta)",
    #     "content": "text message" hoặc "[Ảnh] url" hoặc "[Sticker]" hoặc "[Video]"...,
    #     "ts": "1781193080961",           # timestamp milliseconds
    #     "type": "webchat" hoặc "chat.photo" hoặc "chat.sticker"...,
    #     "msg_id": "7926442586615",
    #     "raw": {...}                     # raw message object
    # }

# Hoặc chỉ cần direction:
direction = client.message_sender(msg, account_id=acc_id)
# Returns: "in" (họ gửi) hoặc "out" (mình gửi)
```

### 6. Gửi tin nhắn

```python
# Gửi TEXT — tự tìm conversation theo số điện thoại
result = client.send_message_by_phone(
    phone="0932032732",
    message="Xin chào anh!",
    account_id="856268701098479404"   # None = tài khoản đầu tiên
)
# Returns: {"msgId": "7926442586615", "status": "success"}

# Gửi TEXT — dùng conversation ID trực tiếp
result = client.send_message(
    account_id="856268701098479404",
    to_id="2843928821831153337",
    conversation_id="856268701098479404_2843928821831153337_0_0",
    message="Nội dung tin nhắn",
    banned_keyword=[]      # từ khóa cấm (nếu có)
)

# Gửi ẢNH — upload trực tiếp (multipart)
result = client.send_photo_direct(
    account_id=acc_id,
    to_id=to_id,
    conversation_id=conv_id,
    file_path="/path/to/photo.jpg"    # hỗ trợ jpg, png, gif
)

# Gửi NHIỀU ẢNH trong 1 khung
result = client.send_photos_direct_group(
    account_id=acc_id,
    to_id=to_id,
    conversation_id=conv_id,
    file_paths=["photo1.jpg", "photo2.jpg", "photo3.jpg"]
)

# Gửi typing indicator
client.send_typing(acc_id, conv_id, username="cretashop/black")
```

### 7. Profile

```python
# Thông tin người dùng Zalo
profile = client.profile_get("856268701098479404", to_id="2843928821831153337")
# Returns: {displayName, avatar, gender, isBlocked, lastOnline, ...}

# Trạng thái online
online = client.profile_online_status("856268701098479404", to_id="2843928821831153337")
# Returns: {show_online_status, lastOnline}
```

### 8. Activity Log (giám sát nhân viên)

```python
# Lịch sử hoạt động
logs = client.activity_log(
    account_id="856268701098479404",
    page=1, page_size=50,
    log_type="all",                    # "all" | "send" | "accept" | "undo"
    sw_username=""                     # lọc theo nhân viên: "cretashop/trang"
)
# Returns: list[dict] keys: conversationId, accountId, type, swUsername, timestamp

# Tất cả log (tự động phân trang)
all_logs = client.activity_log_all(account_id="856268701098479404")
```

### 9. Báo cáo

```python
# Báo cáo hôm nay
report = client.report_today_summary()
# Returns: {
#     "date": "11/06/2026",
#     "total_conversations_today": 79,
#     "unique_people_today": 57,
#     "by_account": {
#         "Trang PK camera Creta": {
#             "conversations": 52,
#             "unique_people": 52,
#             "likely_buying": 18
#         },
#         ...
#     },
#     "top_conversations": [...]
# }

# In báo cáo ra console
client.report_print_today()
```

### 10. Export dữ liệu

```python
client.export_contacts()               # → api_data/contacts.json
client.export_conversations()          # → api_data/conversations.json
client.export_messages(conv_id, acc_id) # → api_data/messages.json
client.export_activity_log()           # → api_data/activity_log.json
client.export_all()                    # Tất cả cùng lúc
```

### 11. Nhóm (Groups)

```python
info = client.group_info(group_id)
members = client.group_members(group_id)
all_ids = client.groups_get_all_ids()
```

### 12. Khác

```python
# Thông báo từ Salework.net
noti = client.notifications_fetch()

# Tags
tags = client.tags_get_all()

# Nhân viên (cần quyền admin)
employees = client.employees_get_all()
```

## Workflow ví dụ cho Agent

```python
# Kịch bản: Agent kiểm tra tin nhắn mới, trả lời khách hỏi giá

from salework_client import SaleworkClient

client = SaleworkClient()
client.login()

# B1: Lấy hội thoại có tin nhắn hôm nay
report = client.report_today_summary()
for conv in report["top_conversations"][:10]:
    conv_id = conv["id"]
    acc_id = conv["accountId"]
    
    # B2: Đọc 5 tin mới nhất
    msgs = client.messages_get(conv_id, acc_id, page_size=5)
    
    # B3: Kiểm tra có phải khách hỏi hàng không
    last_text = ""
    for m in msgs:
        direction = client.message_sender(m, acc_id)
        content = str(m.get("content", ""))
        if direction == "in":
            last_text = content
            break
    
    buy_keywords = ["giá", "bao nhiêu", "còn hàng", "báo giá"]
    if any(kw in last_text.lower() for kw in buy_keywords):
        # B4: Gửi phản hồi
        client.send_message(acc_id, conv["toId"], conv_id,
            "Dạ anh/chị cho em xin mã sản phẩm cần báo giá ạ!")
```

## Cấu trúc file

```
salework-hub/
├── salework_client.py    ← Tool chính (import dùng cho agent)
├── extract_api.py        ← Script extract API (chạy 1 lần để lấy session)
├── GUIDE.md              ← File này
├── requirements.txt      ← playwright, requests, Pillow
└── .gitignore            ← Bỏ qua tokens, api_data
```
