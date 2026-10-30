# Polymarket Autopilot

Ứng dụng **paper trading** Python + Next.js. Quét Gamma/CLOB, kiểm tra điều khoản, quản trị vốn và ghi sổ SQLite. Không gửi lệnh tiền thật hoặc quản lý ví.

## Khởi động

```bash
npm ci --prefix web
python3 -m unittest discover -s tests -v
npm --prefix web run build
python3 scripts/doctor.py --network
```

Nếu kết nối đạt, chạy `python3 server.py` ở terminal thứ nhất. Copy `web/.env.example` thành `web/.env.local` khi chưa có file; chạy `npm --prefix web run start` ở terminal thứ hai. Mở http://localhost:3000.

**[Hướng dẫn vận hành, cấu hình Vercel và các bước tiếp theo](docs/OPERATIONS_GUIDE.md)**

## Luồng dữ liệu

Gamma → chiến lược → giới hạn vốn → độ sâu CLOB → kiểm duyệt điều khoản → sổ cái paper trading → snapshot nguyên tử → dashboard.

- Maker: `PENDING_MAKER` → `OPEN` khi đủ ask; hủy/hoàn tiền khi hết hạn hoặc bị chặn bởi giới hạn sụt giảm.
- Tất toán chỉ theo kết quả được xác nhận; mỗi chân giỏ được theo dõi riêng.
- AI chỉ thoát vị thế có đủ bid mới. Không tự tăng giá/PnL hoặc tạo lịch sử biểu đồ giả.
- Mất kết nối: giữ danh mục, khóa thực thi. Dashboard hiển thị dữ liệu cũ và lỗi thao tác.
- Vercel chỉ xem dữ liệu; backend Python cần máy chạy liên tục và ổ đĩa bền vững.

## Công cụ

```bash
python3 run_autopilot.py --limit 40  # một chu kỳ paper trading
python3 scripts/doctor.py           # kiểm tra database và snapshot, chỉ đọc
python3 scripts/doctor.py --network # kiểm tra thêm DNS/Gamma/CLOB, chỉ đọc
python3 scripts/backup.py           # backup SQLite nhất quán
python3 manage_accounts.py --help   # quản lý AI trên máy backend
```

Không commit token, `.env.local`, OAuth profile hoặc backup. `AUTOPILOT_DATA_DIR` cho phép đặt dữ liệu ngoài source. Xem `.env.example` và `web/.env.example`.

## Kiểm chứng và giới hạn

Bộ test bao phủ chiến lược, rủi ro, maker, depth, settlement, lịch sử vốn, rollover ngày và bảo vệ API. CI chạy test và build. Kết nối mạng live cần kiểm tra riêng tại máy chạy backend; build thành công không chứng minh dữ liệu live hoặc lợi nhuận. Phí còn tĩnh, chưa mô phỏng hàng đợi/khớp từng phần và chưa backtest lợi thế.
