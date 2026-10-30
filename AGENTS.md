> Cập nhật 29/10/2026: phần dưới là lịch sử bàn giao. Trạng thái mới xem README.md và docs/OPERATIONS_GUIDE.md. Đã có CLOB depth, PENDING_MAKER, settlement, history SQLite, TLS có xác thực, API được bảo vệ, doctor/backup và CI. Không còn curl -k; Vercel chỉ đọc snapshot/backend. Live tại máy này còn bị connection reset kể cả qua DoH. Chạy `python3 -m unittest discover -s tests -v` để bao gồm tests/test_operations.py.

# AGENTS.md - Polymarket AI Autopilot Handoff & Context Guide

Tài liệu này dành cho mọi AI Coding Agent (Antigravity, Claude CLI, Cursor, Codex, Windsurf...) khi tiếp nhận dự án `/Users/taileduc/Personal/polymarket-autopilot`. Đọc kỹ file này trước khi chỉnh sửa code hoặc chạy lệnh.

---

## 1. CHÚNG TA ĐÃ LÀM GÌ (COMPLETED WORK)

### 1.1. Kiến trúc Hệ thống Quantitative Paper-Trading & AI Brain
- **Backend Python (`src/`):**
  - `src/config.py`: Cấu hình quản trị rủi ro định lượng (`TradingConfig`), vốn khởi điểm `$1,000.00 USDC`, giới hạn 8%/vị thế, tối đa 60% tổng vốn giải ngân, ngắt mạch tự động (Kill-Switch) khi sụt giảm 3%/ngày (`max_daily_drawdown_pct = 0.03`), kích thước lệnh tối thiểu `$5.00 USDC`.
  - `src/polymarket_client.py`: Kết nối API công khai của Polymarket (`https://gamma-api.polymarket.com/events` và `https://clob.polymarket.com/book`). Hỗ trợ tự động phân giải DNS qua Google/Cloudflare DoH (`_resolve_host_via_doh`) khi nhà mạng tại Việt Nam chặn DNS `polymarket.com` về `127.0.0.1`, đồng thời đồng bộ giờ chuẩn UTC từ HTTP Header `Date` của máy chủ Polymarket.
  - `src/strategy_engine.py`: 3 chiến lược định lượng:
    1. `BUNDLE_ARB`: Mua trọn giỏ các cửa loại trừ nhau (`negRisk=True`) chỉ khi tổng giá bán thực thi (`sum(best_ask)`) cộng phí taker (`10 bps/chân`) nhỏ hơn `$0.990`.
    2. `BOND_CARRY`: Săn kèo xác suất cao (`94.0c - 99.2c`) sắp đáo hạn (`<= 14 ngày`), đã khấu trừ phần bù rủi ro tranh chấp UMA Oracle (`1.2c - 3.0c`) và phí giao dịch.
    3. `MAKER_SPREAD`: Đặt lệnh chờ mua (`LIMIT_MAKER`) làm tròn đúng bước giá chuẩn `0.01` (`tick_size = 0.01`) trên các thị trường có chênh lệch Bid-Ask từ `2.0c - 10.0c`, đã trừ phần bù lựa chọn bất lợi (`adverse_selection_haircut = 0.002`).
  - `src/risk_manager.py`: Bộ lọc 7 cổng bảo vệ vốn và tính khối lượng giải ngân theo đúng công thức **Binary Quarter-Kelly**: `f* = 0.25 * (p - c) / (1 - c)`. Từ chối mở lệnh nếu quy mô Kelly nhỏ hơn `$5.00 USDC`.
  - `src/account_router.py`: Bộ định tuyến tự động chuyển đổi dự phòng (Failover) giữa 2 tài khoản Google Argon khi chạm giới hạn Quota (`HTTP 429 / RESOURCE_EXHAUSTED`):
    - `account_1`: `Nick Google #1 (leductai21204@gmail.com)`
    - `account_2`: `Nick Google #2 (taoyeumaygianga@gmail.com)`
    - Lưu trữ độc lập tại `~/.gemini/autopilot_accounts/account_1` và `account_2`. Hỗ trợ `isolated_mode=True` để khi chạy Unit Test tuyệt đối không ghi đè token thật.
  - `src/ai_analyst.py`: Kiểm duyệt điều khoản phân xử hợp đồng (`resolution_rules`) để phát hiện bẫy ngôn từ UMA Oracle (`VETO_TRAP`), có bộ nhớ đệm băm SHA-256 tại `data/ai_rules_cache.json` để không gọi lại LLM cho cùng một hợp đồng.
  - `src/paper_trader.py`: Sổ cái SQLite (`data/autopilot.db`) định giá vị thế mở (`mark_to_market`) **100% theo giá thanh lý thực tế trên sổ lệnh** (`best_bid` cho `BUY_YES`, `1.0 - best_ask` cho `BUY_NO`, `sum(best_bid)` cho `BUY_BUNDLE`). Tuyệt đối không dùng hàm tự tăng giá giả lập.

### 1.2. Giao diện Web Next.js 16 (`web/`)
- Thiết kế tại `web/src/` theo phong cách **MetaMask.com Neo-Brutalist Oversized Typography** (chữ cực lớn, viền đen `2px solid #111111`, nền kem ấm `#F4F0EA`, cam `#FF5C16`, xanh mint `#B8F397`) và thanh trạng thái thời gian thực (đồng hồ nhảy từng giây + thanh đếm ngược chu kỳ 5 giây).
- Đã loại bỏ hoàn toàn đoạn code cộng lãi giả `+$1.85` trong `web/src/lib/autopilot-server.ts`; khi chạy trên Vercel Serverless sẽ gọi trực tiếp Gamma API để cập nhật giá `bestBid` thực tế.

### 1.3. Kiểm toán độc lập bởi Claude CLI & Đã sửa toàn bộ lỗi P0/P1
- Đã chạy Claude CLI (`/Users/taileduc/.local/bin/claude`) để review độc lập toàn bộ mã nguồn và hoàn tất sửa 100% các vấn đề được chỉ ra:
  1. Xóa bỏ hoàn toàn vòng lặp tự đẩy `mark_price` về `fair_value` trong `src/paper_trader.py`.
  2. Xóa bỏ việc cộng `+0.028` xác suất giả trong `BOND_CARRY` và xóa bỏ `min(sum_ask, sum_mid)` trong `BUNDLE_ARB`.
  3. Sửa khóa chính bảng `positions` thành `pos-{market_id}-{uuid8}` kèm `INSERT INTO` (không ghi đè vị thế đã đóng).
  4. Bổ sung khóa tiến trình `fcntl.flock` (`data/autopilot.lock`) trong `run_autopilot.py` để chống xung đột khi nhiều tiến trình cùng quét.
  5. Bổ sung chốt chặn `OFFLINE_SNAPSHOT_PROTECTION`: Khi mất kết nối tới Polymarket Gamma API (`SNAPSHOT_FALLBACK`), hệ thống tự động khóa mở lệnh mới để không giao dịch trên dữ liệu mẫu.
  6. Đã xóa database cũ chứa số liệu lãi giả lập và khởi tạo lại `data/autopilot.db` về đúng `$1,000.00 USDC` tiền mặt gốc (`PnL = $0.00`).

---

## 2. CHÚNG TA ĐANG Ở ĐÂU (CURRENT STATUS & ENVIRONMENT NOTES)

1. **Trạng thái Kiểm thử (`tests/test_autopilot.py`):**
   - Toàn bộ 8/8 bài kiểm thử đơn vị (Unit Tests) đã chạy PASS (`Ran 8 tests in 0.009s - OK`).
   - Lệnh chạy test:
     ```bash
     python3 /Users/taileduc/Personal/polymarket-autopilot/tests/test_autopilot.py -v
     ```
2. **Trạng thái Dữ liệu (`data/autopilot.db` & `data/portfolio_state.json`):**
   - Đã reset sạch sẽ về trạng thái trung thực:
     - `Total Equity`: `$1,000.00 USDC` (`Cash`: `$1,000.00`, `Deployed`: `$0.00`, `Total PnL`: `$0.00`).
     - `Open Positions`: `0` | `Closed Positions`: `0`.
3. **Hai lưu ý đặc biệt về môi trường máy Mac mini này (Cực kỳ quan trọng cho Agent tiếp theo):**
   - **Lưu ý 1 - Nhà mạng Việt Nam chặn DNS `polymarket.com`:** DNS mặc định của nhà mạng phân giải `gamma-api.polymarket.com` về `127.0.0.1` (gây lỗi `Errno 61 Connection refused`). Trong `src/polymarket_client.py` đã viết sẵn hàm `_resolve_host_via_doh()` tự động hỏi IP thật của Cloudflare qua Google/Cloudflare DoH (`https://dns.google/resolve` / `https://1.1.1.1/dns-query`) và truyền vào `curl --resolve`.
   - **Lưu ý 2 - Đồng hồ hệ thống của máy Mac đang lệch về tháng 10/2026:** Vì đồng hồ OS đang đặt ở tương lai (`2026-10-29`), chứng chỉ SSL 90 ngày của Cloudflare sẽ bị báo hết hạn nếu kiểm tra bằng giờ máy local, và phép tính ngày đáo hạn (`days_to_expiry`) sẽ bị lệch nếu dùng `datetime.now()`. Hàm `_http_get_with_clock_skew_tolerance()` trong `src/polymarket_client.py` đã xử lý cả hai việc này bằng cách lấy giờ chuẩn từ HTTP Header `Date` của server Polymarket.

---

## 3. CHÚNG TA SẼ LÀM GÌ TIẾP THEO (NEXT STEPS ROADMAP)

Khi người dùng yêu cầu tiếp tục phát triển, Agent tiếp theo cần thực hiện theo thứ tự ưu tiên sau:

1. **Bước 1 - Xác nhận chu kỳ quét Live Polymarket qua DoH ngoài Sandbox:**
   - Chạy `python3 /Users/taileduc/Personal/polymarket-autopilot/run_autopilot.py` (cần quyền mạng ngoài sandbox) để xác nhận `Data Source` hiển thị `LIVE_POLYMARKET_GAMMA_API` thông qua cơ chế DoH mới trong `src/polymarket_client.py`.
2. **Bước 2 - Tích hợp độ sâu sổ lệnh thực tế (CLOB Orderbook Depth) vào định giá khớp lệnh:**
   - Sử dụng hàm `fetch_clob_book_top(token_id)` đã có trong `src/polymarket_client.py` để kiểm tra tổng khối lượng đặt mua/bán (`bid_depth_usd`, `ask_depth_usd`) tại 5 mức giá đầu tiên trên `https://clob.polymarket.com/book` trước khi duyệt lệnh trong `run_autopilot.py`.
3. **Bước 3 - Mô phỏng khớp lệnh Maker & Tất toán hợp đồng đáo hạn (Resolution Settlement):**
   - Đối với lệnh `LIMIT_MAKER`: Thêm trạng thái `PENDING_MAKER` và chỉ chuyển sang `OPEN` khi giá `best_ask` thực tế chạm xuống mức `entry_price` hoặc có giao dịch khớp qua mức giá đặt chờ.
   - Đối với hợp đồng đã đóng (`contract.closed == True`): Tự động tất toán vị thế ở mức giá `$1.00` (nếu thắng) hoặc `$0.00` (nếu thua) theo kết quả phân xử chính thức từ Gamma API.
4. **Bước 4 - Build lại Next.js 16 & Đẩy code đã kiểm toán lên GitHub / Vercel:**
   - Chạy `/Users/taileduc/.nvm/versions/node/v24.18.1/bin/npm --prefix /Users/taileduc/Personal/polymarket-autopilot/web run build -- --webpack`.
   - Commit toàn bộ các bản vá định lượng trung thực và push lên `origin/main` (`https://github.com/taild03/polymarket-autopilot`).
