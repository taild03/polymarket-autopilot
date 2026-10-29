# Polymarket AI Autopilot (Quantitative Paper-Trading & Dual-Argon AI System)

Hệ thống tự động quét thị trường dự đoán **Polymarket**, phát hiện chênh lệch giá toán học (**Bundle Arbitrage**), tối ưu lợi suất đáo hạn ngắn (**Bond Carry**), làm tạo lập thị trường (**Maker Spread Capture**) và thực thi giao dịch giả lập (**Paper Trading**) định giá trực tiếp theo sổ lệnh thực tế (`best_bid` / `best_ask`), tích hợp bộ định tuyến dự phòng 2 tài khoản **Google Argon** và bảng điều khiển **Next.js 16**.

---

## Tài Liệu Bàn Giao Cho AI Agent (Đọc Trước Tiên)

Nếu bạn là một AI Coding Agent (Antigravity, Claude CLI, Cursor, Codex, Windsurf...) vừa tiếp nhận dự án này, hãy đọc ngay 3 tài liệu sau để nắm rõ toàn bộ những gì **đã làm**, **đang làm** và **sẽ làm tiếp theo**:

1. **[AGENTS.md](./AGENTS.md)**: Ngữ cảnh tổng thể cho mọi AI Agent, các lưu ý đặc biệt về môi trường mạng/đồng hồ hệ thống trên máy Mac này và lộ trình 4 bước tiếp theo.
2. **[CLAUDE.md](./CLAUDE.md)**: Tài liệu kiến trúc định lượng dành cho Claude CLI (`claude`) và các công cụ kiểm toán mã nguồn.
3. **[HANDOFF_ROADMAP.md](./HANDOFF_ROADMAP.md)**: Bảng đối chiếu chi tiết toàn bộ các lỗi P0/P1 từ đợt kiểm toán độc lập đã được sửa triệt để và trạng thái hiện tại của cơ sở dữ liệu.

---

## 1. Cấu Trúc Thư Mục

```text
polymarket-autopilot/
├── AGENTS.md                 # Tài liệu bàn giao chuẩn cho mọi AI Agent (Đã / Đang / Sẽ làm gì)
├── CLAUDE.md                 # Ngữ cảnh tự động nạp cho Claude CLI
├── HANDOFF_ROADMAP.md        # Báo cáo chi tiết các bản vá định lượng & lộ trình tiếp theo
├── run_autopilot.py          # CLI chạy chu kỳ Quét -> Chiến lược -> AI Audit -> Rủi ro -> Khớp lệnh
├── manage_accounts.py        # Quản lý & đăng nhập OAuth cho 2 tài khoản Google Argon
├── server.py                 # Backend API Server (127.0.0.1:8080) & tiến trình chạy nền
├── src/
│   ├── config.py             # Tham số cấu hình & giới hạn rủi ro cứng (Kill-switch 3%, Binary Kelly)
│   ├── polymarket_client.py  # Kết nối Gamma API & CLOB Book (tích hợp DoH vượt chặn DNS ISP)
│   ├── strategy_engine.py    # 3 chiến lược định lượng trung thực: BUNDLE_ARB, BOND_CARRY, MAKER_SPREAD
│   ├── risk_manager.py       # Bộ lọc an toàn 7 bước & tính khối lượng lệnh Binary Quarter-Kelly
│   ├── ai_analyst.py         # Kiểm duyệt bẫy ngôn từ UMA Oracle & bộ nhớ đệm SHA-256
│   ├── account_router.py     # Tự động chuyển đổi dự phòng (Failover) giữa 2 tài khoản Google Argon
│   └── paper_trader.py       # Sổ cái SQLite định giá 100% theo giá Bid thanh lý thực tế
├── web/                      # Ứng dụng Next.js 16 App Router (Phong cách chữ lớn MetaMask.com)
├── data/
│   ├── autopilot.db          # Cơ sở dữ liệu SQLite ($1,000 USDC vốn gốc, lịch sử vị thế & nhật ký AI)
│   └── portfolio_state.json  # Trạng thái danh mục xuất tự động cho Web UI
└── tests/
    └── test_autopilot.py     # Bộ kiểm thử tự động (15 Unit Tests chạy ở chế độ cô lập)
```

---

## 2. Hướng Dẫn Sử Dụng Nhanh

### Chạy Kiểm thử An toàn (Unit Tests)
```bash
python3 tests/test_autopilot.py -v
```

### Chạy 1 chu kỳ Quét & Giao dịch Paper Trading
```bash
python3 run_autopilot.py
```

### Kiểm tra trạng thái 2 tài khoản Google Argon
```bash
python3 manage_accounts.py status
```

### Khởi động Giao diện Next.js 16 (Cổng 3000) & Backend API (Cổng 8080)
```bash
python3 server.py --host 127.0.0.1 --port 8080
npm --prefix web run dev
```


## Cập nhật luồng thực thi paper trading

- `src/execution.py` kiểm tra CLOB cho từng token YES/NO và từng chân giỏ; sắp xếp 5 mức giá gần nhất, kiểm tra độ sâu và chi phí khớp đầy đủ gồm dự phòng phí. Dữ liệu thiếu hoặc giá vượt ngân sách sẽ chặn lệnh.
- Maker bắt đầu ở `PENDING_MAKER`: giữ chỗ tiền, tính vào giới hạn vốn, không tạo PnL và không được đặt trùng. Chỉ chuyển `OPEN` ở chu kỳ sau khi đủ lượng ask tại hoặc dưới giá chờ. Lệnh chờ bị hủy và hoàn tiền khi thị trường đóng/hết hạn.
- Vị thế được định giá theo lượng bid thực tế cho toàn bộ khối lượng. AI chỉ được thoát những vị thế có báo giá mới, đủ độ sâu. Giỏ lưu chính xác ID từng chân.
- Thị trường đang giữ được truy vấn riêng qua `/markets/{id}`. Chỉ tất toán khi `closed`, `umaResolutionStatus=resolved` và giá kết quả là 1/0, 0/1 hoặc 0.5/0.5. Cập nhật tiền, PnL và trạng thái trong cùng giao dịch SQLite để không tất toán hai lần.
- Snapshot được ghi bằng thay thế file nguyên tử. Next.js hiển thị lệnh chờ riêng; refresh Gamma trên serverless được ghi `GAMMA_QUOTE_REFRESH_ONLY`, không tăng chu kỳ bot hoặc giả lập đổi tài khoản. Lỗi mạng được ghi `STALE_SNAPSHOT`.

### Kiểm chứng và giới hạn hiện tại

15 kiểm thử độc lập đã qua; Next.js production build và TypeScript đã qua. Lần thử mạng ngoài sandbox ngày 29/10/2026 theo giờ máy vẫn gặp `Connection refused`; chưa xác nhận Gamma/CLOB live. Chốt offline giữ vốn $1,000, không mở lệnh.

Đây là mô hình paper trading: chưa mô phỏng hàng đợi maker, khớp từng phần hoặc độ trễ mạng. Phí vẫn là tham số cấu hình, chưa lấy biểu phí riêng từng thị trường. Kỳ vọng của chiến lược là giả định mô hình, chưa được backtest để xác nhận lợi nhuận. Các vị thế giỏ cũ thiếu ID từng chân cần đối soát thủ công. Fallback TLS `curl -k` có sẵn vẫn cần được thay bằng xác thực chứng chỉ sau khi sửa giờ hệ thống. Chưa có xác nhận end-to-end live hoặc triển khai mới lên Vercel.

Tham khảo cấu trúc Gamma: https://docs.polymarket.com/api-reference/markets/get-market-by-id
