# Polymarket Autopilot (2-Tier Quantitative AI Trading System)

Hệ thống tự động quét thị trường dự đoán **Polymarket**, phát hiện chênh lệch giá toán học (**Arbitrage**), tối ưu lợi suất đáo hạn ngắn (**Bond Carry**), làm tạo lập thị trường (**Maker Spread Capture**) và thực thi giao dịch giả lập (**Paper Trading**) với rào chắn quản trị rủi ro cứng.

---

## 1. Cấu Trúc Thư Mục

```text
polymarket-autopilot/
├── run_autopilot.py          # CLI chạy chu kỳ Quét -> Chiến lược -> Rủi ro -> Khớp lệnh
├── server.py                 # Web Server cục bộ phục vụ Visual Dashboard (http://localhost:8080)
├── dashboard.html            # Giao diện điều khiển trực quan (Command Center)
├── src/
│   ├── config.py             # Tham số cấu hình & giới hạn rủi ro cứng (Kill-switch, Kelly)
│   ├── polymarket_client.py  # Kết nối Gamma API & chuẩn hóa sổ lệnh CLOB
│   ├── strategy_engine.py    # 3 chiến lược định lượng: BUNDLE_ARB, BOND_CARRY, MAKER_SPREAD
│   ├── risk_manager.py       # Bộ lọc an toàn 7 bước & tính khối lượng lệnh Quarter-Kelly
│   └── paper_trader.py       # Sổ cái SQLite & quản lý danh mục $1,000 USDC tiền ảo
├── data/
│   ├── autopilot.db          # Cơ sở dữ liệu SQLite lưu vị thế & nhật ký kiểm toán (Audit Log)
│   └── portfolio_state.json  # Trạng thái danh mục xuất tự động cho Dashboard
├── docs/
│   └── OPERATIONS_GUIDE.md   # Cẩm nang vận hành 24/7 & quy trình nâng cấp lên Live Trading
└── tests/
    └── test_autopilot.py     # Bộ kiểm thử tự động (Unit Tests) cho Chiến lược & Cầu dao an toàn
```

---

## 2. Hướng Dẫn Sử Dụng Nhanh

### Chạy 1 chu kỳ Quét & Giao dịch Paper Trading
```bash
python3 run_autopilot.py
```

### Chạy Kiểm thử An toàn (Unit Tests)
```bash
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

### Khởi động Bảng điều khiển Web (Local Dashboard)
```bash
python3 server.py --port 8080
```
Sau đó mở trình duyệt tại `http://localhost:8080`.
