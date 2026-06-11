# Salework/Zalo Agent Toolkit — Hướng dẫn sử dụng

## Cài đặt

```bash
cd /Users/macos/Documents/salework
source venv/bin/activate
```

## 1. Login (lần đầu)

```bash
python extract_api.py
```
→ Browser mở ra, đăng nhập thủ công. Script tự bắt API, lưu session + tokens.

Hoặc login bằng code:
```python
from salework_client import SaleworkClient
client = SaleworkClient()
client.login("black", "admin@123")
```

## 2. Dùng nhanh qua CLI

```bash
python salework_client.py                    # Tổng quan: tài khoản + thống kê
python salework_client.py --report           # Báo cáo hôm nay
python salework_client.py --contacts "Duy"   # Tìm danh bạ
python salework_client.py --conversations    # Danh sách hội thoại
python salework_client.py --messages         # Tin nhắn mới nhất
python salework_client.py --search-msg "giá" # Tìm trong tin nhắn
python salework_client.py --log              # Activity log nhân viên
python salework_client.py --stats            # Thống kê 3 kênh
python salework_client.py --export           # Xuất tất cả JSON
```

## 3. Dùng trong Python / Agent

```python
from salework_client import SaleworkClient
client = SaleworkClient()
client.login()
```

### Tài khoản
```python
accounts = client.accounts_get_all()
# [
#   {"accountId": "856268701098479404", "displayName": "Huyền Camera Creta"},
#   {"accountId": "2222439369543489081", "displayName": "Phụ kiện camera CRETA"},
#   {"accountId": "542711705589461152", "displayName": "Trang PK camera Creta"},
# ]
```

### Danh bạ (3176 contacts)
```python
# Tất cả
contacts = client.contacts_get_all(account_id="856268701098479404")

# Tìm kiếm
results = client.contacts_search("Duy")

# Danh bạ đã lưu trong hệ thống
sw = client.contacts_sw_list()

# Gợi ý kết bạn
recs = client.contacts_recommend_friends()

# Đã gửi lời mời kết bạn
reqs = client.contacts_requested_friends()
```

### Hội thoại
```python
# Danh sách (V1)
convs = client.conversations_list(page_size=100, search_key="Lâm")

# Danh sách (V2 - có phân trang, lọc type)
convs = client.conversations_list_v2(account_id="...", page=1, conv_type="all")
# type: "all" | "personal" | "group" | "hidden"

# Thống kê
stats = client.conversations_count("856268701098479404")
# {"all": 3176, "personal": 3084, "group": 88, "hidden": 8}

# Hội thoại chưa đọc
unread = client.conversations_list(page_size=200, unread_only=True)

# Đã ghim
pinned = client.conversations_pinned()
```

### Tin nhắn
```python
conv_id = "856268701098479404_2843928821831153337_0_0"
acc_id = "856268701098479404"

# Lấy 50 tin gần nhất
msgs = client.messages_get(conv_id, acc_id, page_size=50)

# Lấy tất cả (tự phân trang)
all_msgs = client.messages_get_all(conv_id, acc_id, max_pages=20)

# Tin nhắn đã ghim
pinned = client.messages_pinned(acc_id, to_id="2843928821831153337")

# Lọc ảnh/video
media = client.messages_media(conv_id, acc_id)

# Lọc links
links = client.messages_links(conv_id, acc_id)

# Tìm từ khóa trong nhiều hội thoại
results = client.messages_search("giá camera")
```

### Gửi tin nhắn
```python
# Gửi text theo số điện thoại (tự tìm conversation)
client.send_message_by_phone("0932032732", "Xin chào!")

# Gửi text trực tiếp
client.send_message(
    account_id="856268701098479404",
    to_id="2843928821831153337",
    conversation_id="856268701098479404_2843928821831153337_0_0",
    message="Nội dung",
)

# Gửi ảnh (1 ảnh)
client.send_photo_direct(
    "856268701098479404",
    "2843928821831153337",
    "856268701098479404_2843928821831153337_0_0",
    "/path/to/photo.jpg",
)

# Gửi nhiều ảnh trong 1 khung
client.send_photos_direct_group(
    acc_id, to_id, conv_id,
    ["photo1.jpg", "photo2.jpg", "photo3.jpg"],
)

# Gửi typing indicator
client.send_typing(acc_id, conv_id, username="cretashop/black")
```

### Profile người dùng
```python
profile = client.profile_get(acc_id, to_id="2843928821831153337")
# {displayName, avatar, gender, isBlocked, lastOnline, ...}

online = client.profile_online_status(acc_id, to_id)
# {show_online_status, lastOnline}
```

### Activity Log (giám sát nhân viên)
```python
logs = client.activity_log(acc_id, page=1, page_size=50)
# [
#   {conversationId, accountId, type: "send"/"accept"/"undo",
#    swUsername: "cretashop/trang", timestamp},
#   ...
# ]

# Tất cả log
all_logs = client.activity_log_all(acc_id, max_pages=20)

# Lọc theo nhân viên
logs = client.activity_log(acc_id, sw_username="cretashop/trang")
```

### Báo cáo
```python
# Báo cáo hôm nay
report = client.report_today_summary()
# {
#   "date": "11/06/2026",
#   "total_conversations_today": 79,
#   "unique_people_today": 57,
#   "by_account": {
#     "Trang PK camera Creta": {conversations: 52, unique_people: 52, likely_buying: 18},
#     ...
#   }
# }

# In ra console
client.report_print_today()
```

### Export dữ liệu
```python
client.export_contacts()                # api_data/contacts.json
client.export_conversations()           # api_data/conversations.json
client.export_messages(conv_id, acc_id) # api_data/messages.json
client.export_activity_log()            # api_data/activity_log.json
client.export_all()                     # Tất cả cùng lúc
```

## 4. Cấu trúc file

```
salework/
├── salework_client.py    ← Tool chính cho agent
├── extract_api.py        ← Script extract API (dùng Playwright)
├── automation.py         ← Script tự động hoá (cũ)
├── session.json          ← Cookies đăng nhập
├── tokens.json           ← JWT tokens
├── requirements.txt      ← playwright, requests, Pillow
├── api_data/             ← Dữ liệu JSON export
│   ├── conversations.json
│   ├── contacts.json
│   ├── messages.json
│   └── activity_log.json
└── venv/                 ← Python virtualenv
```

## 5. API Reference

| Endpoint | Method | Mô tả |
|---|---|---|
| `/api/auth/verify` | GET | Verify token |
| `/api/account/getAll` | GET | 3 tài khoản Zalo |
| `/api/contact/filter` | GET | Danh bạ (search + phân trang) |
| `/api/contact/swContact` | GET | Danh bạ đã lưu |
| `/api/contact/recommendFriend` | GET | Gợi ý kết bạn |
| `/api/contact/requestedFriends` | GET | Đã gửi lời mời |
| `/api/conversation` | POST | Hội thoại (V1) |
| `/api/conversationV2/allV2` | POST | Hội thoại (V2 - phân trang) |
| `/api/conversationV2/count-by-type` | POST | Thống kê |
| `/api/message/filter` | POST | Lấy tin nhắn |
| `/api/message/sms` | POST | Gửi text |
| `/api/message/sendMsgPhoto` | POST | Gửi ảnh (multipart) |
| `/api/message/sendPhoto` | GET | Gửi ảnh (từ library) |
| `/api/conversation/typing` | POST | Typing indicator |
| `/api/messageV2/getProfileInfo` | POST | Profile người dùng |
| `/api/messageV2/onlineStatus` | POST | Trạng thái online |
| `/api/messageV2/pinMsgList` | POST | Tin nhắn đã ghim |
| `/api/log` | POST | Activity log |
| `/api/tag` | GET | Tags |
| `/api/noti/fetch` | GET | Thông báo |
| `/api/hub/saveImageByClient` | POST | Upload ảnh library |
| `/api/v2/image` | GET | Xem thư viện ảnh |
