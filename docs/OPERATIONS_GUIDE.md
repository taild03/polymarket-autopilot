# Cẩm Nang Vận Hành Chi Tiết: Polymarket Autopilot 24/7

Tài liệu này giải thích chi tiết cơ chế vận hành của từng mô-đun bên trong hệ thống **Polymarket Autopilot**, cách đọc các chỉ số trên **Visual Command Center**, và quy trình chuyển đổi từ **Paper Trading (Tiền ảo)** sang **Live Trading (Tiền thật)** an toàn.

---

## 1. Giải Phẫu 3 Chiến Lược Định Lượng (`src/strategy_engine.py`)

### 1.1. `BUNDLE_ARB` (Arbitrage Giỏ Sự Kiện Loại Trừ Nhau)
* **Nguyên lý toán học:** Trong một sự kiện có $N$ kịch bản loại trừ lẫn nhau và bao quát toàn bộ khả năng (ví dụ: Quyết định lãi suất của Fed gồm 3 cửa: *Giảm 25bps*, *Giữ nguyên*, *Giảm 50+ bps hoặc Tăng*), khi sự kiện kết thúc, **chính xác 1 cửa sẽ trả về `$1.00`** và các cửa còn lại trả về `$0.00`.
* **Điều kiện vào lệnh:** Khi tổng giá mua (`Ask`) của cả $N$ cửa nhỏ hơn `$0.985`:
  $$\sum_{i=1}^{N} P_{\text{ask}}(\text{YES}_i) \le 0.985$$
* **Lợi thế:** Khóa lợi nhuận thuần từ `1.5%` đến `3.5%` bất chấp kết quả sự kiện ra sao.

### 1.2. `BOND_CARRY` (Thu Lợi Suất Đáo Hạn Ngắn Hạn)
* **Nguyên lý:** Nhiều thị trường có kết quả gần như chắc chắn (`88% - 97.5%`) và sắp phân xử trong vòng `1 - 14 ngày`, nhưng người chơi muốn rút vốn sớm nên bán rẻ lại hợp đồng ở giá `$0.94 - $0.97`.
* **Công thức APR quy đổi:**
  $$\text{APR} = \left(\frac{1.00 - P_{\text{entry}}}{P_{\text{entry}}}\right) \times \left(\frac{365}{\text{Days to Expiry}}\right) \times 100\%$$
* **Ví dụ:** Mua ở giá `$0.945`, đáo hạn sau `4.5 ngày` $\rightarrow$ Lãi tĩnh `+5.82%` sau 4.5 ngày, tương đương hiệu suất quay vòng vốn **472% APR**.

### 1.3. `MAKER_SPREAD` (Làm Tạo Lập Thị Trường Hưởng Chênh Lệch Bid-Ask)
* **Nguyên lý:** Thay vì đặt lệnh Market (mất chênh lệch giá Bid-Ask), Bot tìm các thị trường có thanh khoản tốt nhưng sổ lệnh đang giãn khoảng cách mua-bán (`Spread >= 2.0¢`). Bot đặt lệnh chờ mua (`Limit Maker`) ngay trên giá `Best Bid` để thu lợi thế từ chênh lệch giá trung bình (`Fair Mid`).

---

## 2. Cơ Chế Bảo Vệ Vốn 7 Lớp (`src/risk_manager.py`)

Mọi tín hiệu từ `StrategyEngine` đều phải đi qua 7 cổng kiểm duyệt tự động trước khi được phép vào lệnh:

1. `KILL_SWITCH_OK`: Kiểm tra tổng lãi/lỗ trong ngày. Nếu lỗ chạm `-3.0%` (`-$30.00`), khóa toàn bộ hệ thống.
2. `NO_DUPLICATE`: Không bao giờ nhồi thêm lệnh vào một thị trường đang có vị thế mở.
3. `LIQUIDITY_OK`: Loại bỏ mọi thị trường có thanh khoản `< $5,000` hoặc khối lượng giao dịch 24h `< $1,500`.
4. `SPREAD_OK`: Chặn các thị trường có chênh lệch giá mua-bán quá rộng (`> 4.5¢`), tránh trượt giá (Slippage).
5. `ORACLE_RULES_CLEAR`: Kiểm tra độ dài và tính chi tiết của văn bản `Resolution Rules` để tránh "bẫy chữ nghĩa" khi phân xử trên UMA Oracle.
6. `EXPOSURE_BUDGET_OK`: Đảm bảo tổng số vốn đang nằm trong các lệnh mở không bao giờ vượt quá `50%` tổng tài sản (luôn giữ tối thiểu `50%` tiền mặt USDC).
7. `KELLY_SIZED`: Tính toán khối lượng vào lệnh theo công thức **Quarter-Kelly (1/4 Kelly)** và khóa trần tối đa `5%` tổng vốn (`$50.00`) cho mỗi lệnh.

---

## 3. Quy Trình Vận Hành Tự Động 24/7

* **Chạy định kỳ bằng `/schedule` hoặc Cron:**
  Hệ thống chỉ cần quét mỗi `15 - 30 phút/lần` qua lệnh:
  ```bash
  python3 /Users/taileduc/Personal/polymarket-autopilot/run_autopilot.py
  ```
* **Khi nào mới nên chuyển sang Tiền Thật (Live Trading)?**
  1. Chạy Paper Trading tối thiểu **14 ngày liên tục**.
  2. Kiểm tra nhật ký `audit_log` trong `data/autopilot.db` đảm bảo tỷ lệ thắng (Win Rate) và lợi nhuận kỳ vọng sát với thực tế phân xử của sàn.
  3. Khi kết nối API thật (`py-clob-client`), sử dụng **1 ví Polygon phụ chuyên biệt**, chỉ nạp đúng số vốn nhỏ chấp nhận rủi ro (ví dụ `$100 - $200 USDC`).
