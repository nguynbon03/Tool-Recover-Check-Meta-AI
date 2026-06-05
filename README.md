# FB Hacked Recovery Tool

Tkinter desktop app tự động hoá quy trình khôi phục tài khoản Facebook bị hack,
hỗ trợ chạy song song nhiều tài khoản qua Selenium + Chrome.

## Platforms

| Platform | File | Runtime |
|----------|------|---------|
| macOS | `macOS/fb_recovery_mac.py` | Python 3.11+, selenium, Pillow |
| Windows | `Windows/fb_recovery.py` | Python 3.11+, selenium, paramiko, sshtunnel |

## Cài đặt nhanh

### macOS
```bash
pip install -r macOS/requirements.txt   # (nếu có file này)
python3 macOS/fb_recovery_mac.py
```

### Windows
1. Cài Python 3.11+, tick **Add Python to PATH**
2. Mở cmd:
   ```
   pip install -r Windows\requirements.txt
   ```
3. Double-click `Windows\RUN.bat` hoặc chạy `python fb_recovery.py`

## Tính năng chính

- **Multi-thread**: chạy đồng thời nhiều tài khoản (semaphore giới hạn tối đa concurrency)
- **Proxy support**: HTTP/SOCKS proxy pool + SSH tunnel qua VPS
- **Fingerprint spoofing**: rotate User-Agent, canvas noise
- **Screenshot live**: thumbnail cập nhật liên tục từng tab đang chạy
- **SUCCESS keep**: Chrome window giữ nguyên sau khi tài khoản recover thành công
- **State persistence**: tự lưu/load trạng thái giữa các lần chạy

## Cấu trúc class

```
ProxyBridge        — HTTP CONNECT proxy tunnel nội bộ
SSHTunnel          — SSH forward tunnel qua paramiko
VPSPool            — parse và quản lý pool VPS
ProxyPool          — parse và quản lý pool HTTP/SOCKS proxy
FingerprintProfile — sinh Chrome fingerprint ngẫu nhiên (macOS only)
AccountWorker      — thread worker cho 1 tài khoản: driver, tunnel, recovery flow
FBHackedRecoveryTool — tk.Tk UI chính: quản lý worker, stats, results table
```

## Input format

- **Accounts**: mỗi dòng 1 email hoặc số điện thoại
- **Proxy Pool**: `host:port:user:pass` hoặc `host:port` (HTTP proxy)
- **VPS Pool**: `host user` (mỗi dòng 1 VPS, dùng SSH key)

## Tài liệu chi tiết

Xem `process/context/` cho architecture và flow docs.
