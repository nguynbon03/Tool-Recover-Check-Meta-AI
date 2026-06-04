# FB Hacked Recovery Tool — macOS PRD

**File chính:** `macOS/fb_recovery_mac.py` (~2700 lines)
**Stack:** Python 3.11 + Tkinter + Selenium + Chrome headless=new

---

## Tính năng đã hoàn thiện (2026-06-04)

### Core Recovery Flow
- Selenium headless Chrome (`--headless=new`, off-screen `--window-position=10000,0`)
- Multi-thread: semaphore giới hạn concurrent Chrome (spinbox)
- SSH SOCKS5 tunnel qua VPS pool (SSHTunnel class, port 10000+)
- Proxy pool: `ip:port:user:pass` — dùng Chrome Extension để auth (không dùng `--proxy-server` thô)
- Fingerprint spoofing: UA, platform, screen, canvas noise, font list qua CDP injection
- Clean browser state mỗi attempt (delete cookies + localStorage + sessionStorage)
- RETRY loop 15s giữa các lần thử

### SUCCESS Detection
- Bottom-right zone (60%×60% viewport) — bất kỳ button/link nào hiện = SUCCESS
- Keyword match: "nhận hỗ trợ", "get support", "meta ai support assistant", etc.
- Guard false SUCCESS: `_is_failure_page()` + check URL vẫn trên `/identify`

### SUCCESS Worker Lifecycle
- Worker SUCCESS → sleep vô hạn, KHÔNG bao giờ quit driver
- Auto refresh trang mỗi N phút (configurable)
- Screenshot thread chạy liên tục, update thumbnail 2s/lần

### Telegram Notification
- Bot token + Chat ID nhập trong UI
- Gửi khi có SUCCESS: email + status
- **Chat ID đúng:** `6902266294` (Ngiyen)
- Dùng `urllib.request` (không cần thư viện ngoài)

### Popup Live View (click thumbnail)
- Tkinter Toplevel 900×620, căn giữa màn hình
- Screenshot headless Chrome cập nhật 1.5s/lần
- CDP click forwarding: click trên popup → Chrome thực hiện
- Copy URL button
- Session info bar: proxy + session live/dead status

### Open Chrome Button (trong popup)
- Mở Chrome visible (không headless) với cùng proxy
- Inject cookies từ headless session → navigate đến URL hiện tại
- Proxy auth dùng Chrome Extension (ip:port:user:pass) — KHÔNG dùng `--proxy-server` thô
- Track visible driver trong `self._view_drivers[email]`

### Results Panel
- Canvas + Frame scroll pattern
- Scrollbar width=16px
- **Scroll fix:** `bind_all("<MouseWheel>")` + Enter/Leave hover guard
- Bind `results_scroll` vào Enter/Leave — không bị mất hover khi chuột di vào scrollbar
- Thumbnail click → popup live view

### UI Layout
- Top bar: Threads, Auto refresh, Telegram Token, Chat ID
- Middle: Accounts | VPS Pool | Proxy Pool (3 cột)
- Results panel (scrollable) + Stats panel
- Log box (bottom)

---

## Bug đã fix hôm nay

| Bug | Root Cause | Fix |
|-----|-----------|-----|
| Chrome crash "session not created" | `--user-data-dir` + `--headless=new` crash macOS M-chip | Xóa toàn bộ `--user-data-dir` block |
| False SUCCESS trên identify page | Bottom-right detection trigger trước khi qua recover | `_is_failure_page()` + URL check `still_on_identify` |
| Scroll lúc được lúc không | Enter/Leave không bind `results_scroll` → hover=False khi chuột vào scrollbar | Thêm `results_scroll` vào bind list |
| Open Chrome "This site can't be reached" | `--proxy-server=ip:port:user:pass` Chrome không tự auth | Dùng `_make_proxy_extension()` như `_make_driver` |
| Popup ảnh quá to, ctrl bar mất | `_apply_image` dùng screenwidth làm fallback → scale = màn hình | `ratio = min(..., 1.0)` + fallback 860×520 |
| Telegram không nhận thông báo | Chat ID nhập sai (nhập token thay Chat ID) | Chat ID = `6902266294` |

---

## Known Patterns / Constraints

- **KHÔNG** dùng `--user-data-dir` với `--headless=new` trên macOS Apple Silicon
- **KHÔNG** dùng `--proxy-server=ip:port:user:pass` — Chrome không auth được, dùng extension
- **KHÔNG** dùng `-zoomed` (native fullscreen macOS) cho popup — che mất ctrl bar
- SUCCESS worker: `self.driver` tồn tại mãi mãi, không được quit
- `bind_all("<MouseWheel>")` cần hover guard để không steal scroll từ log box
- `winfo_rootx()` trả về 0 khi widget chưa render — không dùng để check vùng

---

## Next Dev Ideas

- [ ] Click vào nút trong popup (CDP click đã có) → auto click "I've been hacked" / "Help with my account"
- [ ] Export SUCCESS accounts ra file CSV/TXT
- [ ] Windows port sync với macOS features mới (proxy extension, fingerprint, Telegram)
- [ ] Retry proxy rotation: mỗi attempt dùng proxy khác từ pool
- [ ] VPS auto-scale: thêm nhiều VPS port tự động theo số accounts
