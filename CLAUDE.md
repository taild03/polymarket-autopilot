# CLAUDE.md - Project Context & Quantitative Architecture Guide

File này cung cấp ngữ cảnh đầy đủ cho Claude CLI (`claude`) và các AI Agent khác khi làm việc trên dự án `/Users/taileduc/Personal/polymarket-autopilot`.

## Tổng quan Dự án
**Polymarket AI Autopilot** là hệ thống giao dịch định lượng tự hành (Paper-Trading chuẩn bị cho Live CLOB Execution) với vốn khởi điểm `$1,000.00 USDC`, kết hợp:
1. **3 Chiến lược Định lượng (`src/strategy_engine.py`):**
   - `BUNDLE_ARB`: Arbitrage giỏ sự kiện đa kết quả (`negRisk`) tính hoàn toàn trên giá `best_ask` thực thi + phí.
   - `BOND_CARRY`: Nắm giữ hợp đồng xác suất cao (`94c - 99.2c`) gần ngày đáo hạn có khấu trừ rủi ro đuôi UMA Oracle (`1.2c - 3.0c`).
   - `MAKER_SPREAD`: Đặt lệnh chờ mua (`LIMIT_MAKER`) bám đúng bước giá `0.01` (`tick_size = 0.01`) có khấu trừ rủi ro lựa chọn bất lợi (`adverse_selection_haircut`).
2. **Quản trị Rủi ro 7 Cổng & Binary Quarter-Kelly (`src/risk_manager.py`):**
   - Công thức Kelly nhị phân chính xác: `f* = 0.25 * (p - c) / (1 - c)`.
   - Khóa lệnh dưới `$5.00 USDC`, trần `8%` mỗi thị trường, tối đa `60%` tổng vốn giải ngân, và Kill-Switch ngắt mạch khi sụt giảm `3%` tính từ đầu ngày hoặc từ đỉnh tài sản (`peak_equity_usdc`).
3. **Bộ định tuyến 2 Tài khoản Google Argon (`src/account_router.py` & `manage_accounts.py`):**
   - Tự động chuyển đổi dự phòng giữa `account_1` (`leductai21204@gmail.com`) và `account_2` (`taoyeumaygianga@gmail.com`) khi chạm giới hạn Quota 429.
4. **Giao diện Web Next.js 16 (`web/`):**
   - Thiết kế chữ lớn độ tương phản cao lấy cảm hứng từ MetaMask.com, cập nhật trạng thái trực tiếp qua `/api/state` và `/api/scan`.

## Trạng thái Hiện tại (Sau đợt Kiểm toán & Sửa lỗi Toàn diện)
- Toàn bộ các lỗi sinh lời giả lập trong bản mẫu ban đầu (như tự hội tụ `mark_price` về `fair_value`, cộng `+2.8c` xác suất giả trong `BOND_CARRY`, dùng `sum_mid` trong `BUNDLE_ARB`, ép sàn lệnh `$15`, ghi đè vị thế đóng bằng `INSERT OR REPLACE`, và cộng `+$1.85` trên Vercel Serverless) **đã được xóa bỏ và sửa lại hoàn toàn**.
- Xem chi tiết những việc **Đã làm**, **Đang làm**, và **Sẽ làm tiếp theo** tại file [AGENTS.md](./AGENTS.md) và [HANDOFF_ROADMAP.md](./HANDOFF_ROADMAP.md).

## Các Lệnh Thường Dùng
- **Chạy bộ Unit Test (chế độ cô lập, không chạm DB hay OAuth token thật):**
  ```bash
  python3 tests/test_autopilot.py -v
  ```
- **Chạy 1 chu kỳ quét thị trường:**
  ```bash
  python3 run_autopilot.py
  ```
- **Kiểm tra trạng thái 2 tài khoản Google Argon:**
  ```bash
  python3 manage_accounts.py status
  ```
- **Build giao diện Next.js 16:**
  ```bash
  /Users/taileduc/.nvm/versions/node/v24.18.1/bin/npm --prefix web run build -- --webpack
  ```
