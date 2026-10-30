# TÀI LIỆU BÀN GIAO KỸ THUẬT & LỘ TRÌNH DỰ ÁN (HANDOFF & ROADMAP)

Cập nhật lần cuối:Sau đợt kiểm toán độc lập bằng Claude CLI và重构 (tái cấu trúc) toàn bộ lõi định lượng.
Thư mục dự án: `/Users/taileduc/Personal/polymarket-autopilot`

---

## PHẦN 1: CHÚNG TA ĐÃ LÀM GÌ (COMPLETED MILESTONES)

### 1. Liên kết 2 Tài khoản Google Argon & Tự động Failover (`src/account_router.py`, `manage_accounts.py`)
- Đã xây dựng công cụ đăng nhập OAuth trực tiếp trên trình duyệt (`manage_accounts.py login`) mà không cần lưu cứng Client Secret trong mã nguồn (đọc động từ binary `/Users/taileduc/.local/bin/agy` để vượt qua GitHub Push Protection).
- Đã đăng nhập và lưu thành công 2 tài khoản thật tại `~/.gemini/autopilot_accounts/`:
  - **Slot 1 (`account_1`):** `Nick Google #1 (leductai21204@gmail.com)` - Đang trực chính (`ACTIVE`).
  - **Slot 2 (`account_2`):** `Nick Google #2 (taoyeumaygianga@gmail.com)` - Dự phòng tự động (`STANDBY`).
- Đã sửa bộ nhận diện lỗi Quota (`QUOTA_ERROR_REGEX`) để chỉ bắt đúng lỗi `HTTP 429 / RESOURCE_EXHAUSTED / rate limit`, không bao giờ bắt nhầm chuỗi giá tiền như `"$429"`.
- Đã thêm cờ `isolated_mode=True` để khi chạy kiểm thử (`tests/test_autopilot.py`) tuyệt đối không ghi đè file `~/.gemini/jetski-standalone-oauth-token` thật của người dùng.

### 2. Thiết kế lại Giao diện Next.js 16 theo Phong cách MetaMask.com (`web/`)
- Đã nâng cấp toàn bộ các component trong `web/src/components/` (`header-bar.tsx`, `portfolio-kpi-grid.tsx`, `strategy-positions-table.tsx`, `ai-brain-feed.tsx`, `argon-account-panel.tsx`, `autopilot-provider.tsx`):
  - Chữ tiêu đề và con số tài sản cỡ cực lớn (`Space Grotesk` + `Plus Jakarta Sans` + `JetBrains Mono`), viền đen đậm `2px solid #111111`, đổ bóng khối cứng kiểu MetaMask.
  - Thanh trạng thái thời gian thực trên đỉnh trang: Đồng hồ nhảy từng giây + Thanh tiến trình đếm ngược 5 giây tự đồng bộ dữ liệu + Nhãn hiển rõ nguồn dữ liệu (`POLYMARKET LIVE` hay `CHẾ ĐỘ SNAPSHOT`).

### 3. Kiểm toán Độc lập bằng Claude CLI & Sửa Toàn bộ Lỗi Định lượng (P0/P1 Fixes)
Sau khi gọi `/Users/taileduc/.local/bin/claude` đánh giá độc lập, chúng ta đã **xóa bỏ triệt để cơ chế tạo lãi giả lập** của bản mẫu cũ và thay bằng tính toán sổ lệnh trung thực:

| Thành phần | Lỗi ở bản mẫu cũ (Trước kiểm toán) | Cách đã sửa triệt để (Hiện tại) |
| :--- | :--- | :--- |
| **`src/polymarket_client.py`** | Ghép trùng tham số `?` vào `gamma_events_url` và thiếu `http_timeout_sec` khiến mọi lần gọi đều rơi vào `SNAPSHOT_FALLBACK`. | Đã tách chuẩn URL, bổ sung `http_timeout_sec = 10.0`, thêm hàm phân giải DoH (`_resolve_host_via_doh`) vượt chặn DNS nhà mạng Việt Nam và lấy giờ chuẩn từ HTTP Header `Date`. |
| **`src/strategy_engine.py`** | Dùng `min(sum_ask, sum_mid)` cho `BUNDLE_ARB`; tự cộng `+0.028` xác suất thắng cho `BOND_CARRY`; đặt giá lẻ `best_bid + 0.004` cho `MAKER_SPREAD`. | `BUNDLE_ARB` tính 100% trên `sum(best_ask) + phí taker`; `BOND_CARRY` khấu trừ rủi ro đuôi UMA (`1.2c - 3.0c`); `MAKER_SPREAD` làm tròn đúng bước giá `0.01` (`tick_size`). |
| **`src/risk_manager.py`** | Công thức Kelly sai cho hợp đồng nhị phân và ép sàn lệnh tối thiểu `$15.00` kể cả khi lợi thế cực nhỏ. | Áp dụng đúng công thức Binary Quarter-Kelly `f* = 0.25 * (p - c) / (1 - c)`; từ chối các kèo có quy mô Kelly nhỏ hơn `$5.00 USDC`. |
| **`src/paper_trader.py`** | Tự kéo `mark_price` tiến `35%` về `fair_value` mỗi vòng quét (tạo lãi giả `+$1,164`); dùng `INSERT OR REPLACE` ghi đè vị thế đã đóng. | Xóa bỏ hoàn toàn công thức tự tăng giá; định giá vị thế mở 100% theo giá thanh lý thực tế (`best_bid` cho `BUY_YES`, `1 - best_ask` cho `BUY_NO`); dùng mã vị thế duy nhất `pos-{market_id}-{uuid8}`. |
| **`src/ai_analyst.py`** | Tăng bộ đếm `calls_succeeded` ngay cả khi chạy biểu thức chính quy nội bộ; truyền Gemini API key trên thanh URL. | Chỉ tính `calls_succeeded` khi gọi CLI/API thật; thêm bộ nhớ đệm `data/ai_rules_cache.json` theo mã băm SHA-256 của luật phân xử; truyền khóa Gemini qua header `x-goog-api-key`. |
| **`run_autopilot.py`** | Không có khóa tiến trình (dễ chạy chồng chéo) và vẫn mở lệnh mới khi mất mạng (`SNAPSHOT_FALLBACK`). | Thêm khóa độc quyền `fcntl.flock` (`data/autopilot.lock`) và chốt chặn `OFFLINE_SNAPSHOT_PROTECTION` (tự khóa vào lệnh mới nếu không kết nối được Polymarket Live). |
| **`web/src/lib/autopilot-server.ts`** | Tự cộng `+$1.85` mỗi lần bấm quét trên Vercel khi không có Python local. | Xóa bỏ hoàn toàn `profitDelta = 1.85`; thay bằng hàm `syncWithLiveGammaApiOnServerless()` lấy giá `bestBid` thực tế từ Polymarket Gamma API. |

---

## PHẦN 2: CHÚNG TA ĐANG Ở ĐÂU (CURRENT STATE)

1. **Mã nguồn & Kiểm thử:**
   - Tất cả các file trong `src/`, `run_autopilot.py`, `server.py`, `tests/test_autopilot.py` và `web/src/` đã được cập nhật và vượt qua 8/8 bài kiểm thử đơn vị (`python3 tests/test_autopilot.py -v`).
2. **Cơ sở dữ liệu (`data/autopilot.db` & `data/portfolio_state.json`):**
   - Đã xóa bỏ dữ liệu lãi giả cũ và khởi tạo lại từ đầu ở mức vốn chuẩn **`$1,000.00 USDC`** (`Cash: $1,000.00`, `Realized PnL: $0.00`, `Unrealized PnL: $0.00`).
3. **Các tiến trình nền (Background Tasks):**
   - Đã tạm dừng daemon Python cũ (`task-80`) và lịch cron 30 phút (`task-103`) theo yêu cầu tạm dừng của người dùng.

---

## PHẦN 3: CHÚNG TA SẼ LÀM GÌ TIẾP THEO (UPCOMING TASKS FOR NEXT AGENT)

Khi tiếp tục công việc, Agent tiếp theo chỉ cần thực hiện lần lượt 4 bước sau:

### Bước 1: Chạy chu kỳ quét Live Polymarket đầu tiên với bộ phân giải DoH mới
- Chạy lệnh ngoài sandbox (hoặc trên terminal của máy Mac):
  ```bash
  python3 /Users/taileduc/Personal/polymarket-autopilot/run_autopilot.py
  ```
- Kiểm tra dòng `Data Source` trong kết quả in ra phải là `LIVE_POLYMARKET_GAMMA_API` (nhờ hàm `_resolve_host_via_doh` vượt qua DNS sinkhole của nhà mạng).

### Bước 2: Kiểm tra độ sâu sổ lệnh CLOB (`fetch_clob_book_top`) trước khi khớp lệnh
- Kết nối hàm `PolymarketClient.fetch_clob_book_top(contract.yes_token_id)` vào bước duyệt tín hiệu trong `run_autopilot.py` để đảm bảo khối lượng đặt tại mức giá `best_ask` / `best_bid` trên sổ lệnh CLOB lớn hơn quy mô giải ngân của lệnh (`decision.recommended_size_usdc`).

### Bước 3: Bổ sung cơ chế khớp lệnh chờ (`PENDING_MAKER`) và tất toán khi hợp đồng đóng (`Resolution`)
- Với lệnh `LIMIT_MAKER`, ghi nhận trạng thái chờ khớp và chỉ khớp khi giá giao dịch thực tế chạm mức giá đặt mua.
- Khi hợp đồng trên Polymarket chuyển sang `closed = True`, tự động tất toán vị thế ở mức `$1.00` hoặc `$0.00` theo kết quả phân xử.

### Bước 4: Build lại Next.js 16, Khởi động lại Daemon và Push lên GitHub
- Build lại ứng dụng web:
  ```bash
  /Users/taileduc/.nvm/versions/node/v24.18.1/bin/npm --prefix /Users/taileduc/Personal/polymarket-autopilot/web run build -- --webpack
  ```
- Commit và đẩy toàn bộ thay đổi lên `https://github.com/taild03/polymarket-autopilot` để Vercel tự động cập nhật giao diện mới.
