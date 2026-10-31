# Vận hành Polymarket Autopilot (paper trading)

Dự án chỉ mô phỏng giao dịch. Không có chức năng gửi lệnh tiền thật, ký ví hoặc rút tiền. Kết quả và APR là số liệu/ước tính của mô hình, không phải cam kết lợi nhuận.

## 1. Chuẩn bị máy

Cần Python 3.9 trở lên, Node.js 24, npm, curl, Git. Backend dùng thư viện chuẩn Python. Chạy trên macOS/Linux vì khóa chu kỳ sử dụng `fcntl`.

```bash
cd /Users/taileduc/Personal/polymarket-autopilot
npm ci --prefix web
python3 -m unittest discover -s tests -v
npm --prefix web run build
python3 scripts/doctor.py --network
```

`doctor` chỉ đọc trạng thái và gọi API công khai, không tạo lệnh. Mã thoát 0 với `--network` chỉ khi kiểm tra Gamma và ít nhất một phản hồi CLOB thành công. Sổ lệnh rỗng vẫn chứng minh kết nối hoạt động; `clob_probe.two_sided_liquidity_found` cho biết có tìm được sổ lệnh có cả bên mua và bán hay không. Tìm `LIVE_POLYMARKET_GAMMA_API` và `clob: ok`.

Nếu DNS trả `127.0.0.1` hoặc `::1`, client thử DoH có xác thực TLS. Nếu vẫn `Connection reset by peer`, kiểm tra cấu hình DNS/proxy/firewall của máy và mạng hoặc chạy backend trên máy có quyền truy cập các endpoint đó. Không tắt xác thực SSL. Đặt ngày giờ hệ thống tự động; thời gian server chỉ hỗ trợ tính ngày và quản trị phiên giao dịch, không sửa lỗi chứng chỉ của máy.

Khi chưa truy cập API, bot giữ nguyên danh mục và chặn mở/đóng lệnh trên snapshot. Không đặt `allow_snapshot_trading=True` khi vận hành.

## 2. Chạy trên máy cá nhân

Terminal 1 — Python thực hiện chu kỳ và lưu SQLite bền vững:

```bash
cd /Users/taileduc/Personal/polymarket-autopilot
python3 server.py --host 127.0.0.1 --port 8080 --interval 30
```

Terminal 2 — dashboard Next.js:

```bash
cd /Users/taileduc/Personal/polymarket-autopilot
# Chỉ copy khi chưa có file; nếu có, chỉnh biến trong file hiện tại.
cp -n web/.env.example web/.env.local
npm --prefix web run start
```

Mở http://localhost:3000. File `web/.env.local` đặt `AUTOPILOT_BACKEND_URL=http://127.0.0.1:8080`. Dashboard tự đọc mỗi 5 giây; backend quét sau mỗi chu kỳ cộng khoảng nghỉ 30 giây. Một chu kỳ có thể lâu hơn 30 giây nếu nhiều API/AI cần gọi. Bấm quét yêu cầu backend chạy một chu kỳ; khóa file tránh chạy trùng. Ctrl+C để dừng mỗi tiến trình.

Nếu cổng 3000 đang được ứng dụng khác sử dụng, chạy `npm --prefix web run start -- --port 3001 --hostname 127.0.0.1` và mở http://127.0.0.1:3001.

`GET /health` xác nhận API đang phục vụ. `GET /api/state` trả trạng thái cuối cùng; chưa có snapshot trả 503. Không mở lệnh chỉ vì người dùng đọc dashboard.

## 3. Đọc số liệu và trạng thái

- `Cash`: tiền khả dụng sau khi giữ chỗ lệnh maker.
- `reserved_cash_usdc`: tiền đã giữ chỗ, vẫn nằm trong tổng tài sản; lệnh chờ chưa có PnL.
- Tổng tài sản = tiền khả dụng + tiền giữ chỗ + giá trị vị thế mở.
- Biểu đồ chỉ dùng các điểm đã lưu trong SQLite. Dữ liệu cũ chỉ có một điểm thì không tự tạo thêm lịch sử.
- `LIVE_POLYMARKET_GAMMA_API`: Gamma thành công trong chu kỳ đó. CLOB vẫn phải đạt kiểm tra riêng cho từng lệnh.
- `SNAPSHOT_FALLBACK`: dữ liệu mẫu, giao dịch bị khóa.
- `READONLY_SNAPSHOT`: dashboard không kết nối backend, chỉ xem bản chụp.
- `BACKEND_UNAVAILABLE`: đã cấu hình backend nhưng không đọc được. Xem API token, URL và log backend.
- Trạng thái quá 120 giây sẽ không được gắn nhãn live trên giao diện. Timestamp là lần ghi dữ liệu, không phải giờ trình duyệt tải lại. Thời gian tham chiếu lấy từ HTTP `Date` cộng `Age` khi phản hồi đi qua cache; điều này không làm giá Gamma trong cache trở thành giá mới. Lệnh vẫn phải qua kiểm tra CLOB.

Lệnh maker chỉ khớp ở chu kỳ sau khi đủ ask tại/dưới mức đặt. Hết hạn/đóng thì hoàn tiền. Giới hạn sụt giảm sẽ hủy lệnh chờ trước khi xử lý khớp mới. Vị thế được tất toán một lần khi Gamma xác nhận kết quả; cờ `closed` riêng lẻ không đủ.

## 4. Giới hạn rủi ro mặc định

Cấu hình nằm trong `src/config.py`: vốn mô phỏng $1.000; tối đa 8%/lệnh, 30%/chiến lược, 60% tổng phân bổ (gồm tiền giữ chỗ); dừng mở mới khi giảm 3% từ mốc vốn/ngưỡng cao nhất trong ngày UTC. Ngày mới tính lại mốc ngày, còn drawdown toàn kỳ được báo riêng. Định cỡ theo Quarter-Kelly, tối thiểu $5.

Thị trường cần thanh khoản $5.000, volume 24h $1.500, spread taker tối đa 3¢; maker 2–10¢. Giỏ arbitrage yêu cầu tổng giá ask và dự phòng phí không vượt 0,990. Carry dùng giá 0,94–0,992, tối đa 14 ngày, có dự phòng rủi ro phân xử.

## 5. AI và tài khoản

### 5.1. Cổng kiểm duyệt Argon bắt buộc trước khi vào lệnh (mặc định)

Chế độ vận hành mặc định (`require_argon_entry_review=True` trong `src/config.py`) BẮT BUỘC một đánh giá Argon thật (CLI `agy`, model `gemini-4-argon-high`) cho TOÀN BỘ lệnh đề xuất — mọi chân giỏ, đúng cửa YES/NO, giá vào hiện tại, điều khoản phân xử, thời hạn/thanh khoản và bối cảnh rủi ro/khối lượng — TRƯỚC khi giữ chỗ hay giải ngân bất kỳ đồng paper nào.

- Chỉ `APPROVE` mới mở lệnh. `REJECT`, `INSUFFICIENT_DATA`, `UNAVAILABLE` (JSON sai, timeout, chạm quota, thiếu đăng nhập) đều CHẶN lệnh.
- Argon phản biện lợi thế kinh tế sau phí, không chỉ độ rõ của luật. Fair value/edge của chiến lược và giá thị trường chỉ là giả định, không phải bằng chứng.
- **Giới hạn quan trọng:** task này KHÔNG nối nguồn tin tức/nghiên cứu độc lập. Bối cảnh gửi cho model ghi rõ `independent_research_available=false`; khi cần thông tin ngoài để xác định lợi thế, model trung thực trả `INSUFFICIENT_DATA` và hệ thống không vào lệnh. Một `APPROVE` tự nhận không có nghiên cứu độc lập sẽ bị hạ xuống `INSUFFICIENT_DATA`. Do đó với bản dựng hiện tại, APPROVE thật rất hiếm và phần lớn lệnh mới bị từ chối — đây là hành vi thận trọng có chủ đích.
- Mỗi chu kỳ bị chặn số lần gọi (`argon_max_calls_per_cycle`) và thời gian (`argon_cycle_time_budget_sec`); vượt hạn thì các tín hiệu còn lại bị chặn chứ không treo chờ.
- Sau khi suy luận (chậm), hệ thống TẢI LẠI sổ lệnh CLOB và kiểm tra lại độ sâu trước khi thực thi; không phóng đại khối lượng dựa trên model. Nếu dùng xác suất của model, nó là xác suất CỬA ĐÃ CHỌN; hệ thống lấy `min(fair_value, prob_model)` và định cỡ lại thận trọng, không bao giờ lớn hơn khối lượng ban đầu.
- Không có cache cũ nào được phép cấp phép lệnh mới. Cache (nếu có) nhạy theo giá/cửa/model/tài khoản/bối cảnh và TTL ngắn trong bộ nhớ tiến trình; khởi động lại là mất.

Định tuyến 2 profile: dùng tài khoản đang active đã cấu hình; khi gặp lỗi quota/rate-limit thật sẽ thử lại đúng MỘT lần sang profile dự phòng đã cấu hình và không trong cooldown. Cả hai không khả dụng thì chặn vào lệnh. Cổng không đọc/không ghi log token; không sửa `~/.gemini` ngoài cơ chế chuyển profile sẵn có.

Lệnh `PENDING_MAKER` tạo trước khi có cổng này không mang dấu APPROVE thật: khi khởi động lại chúng được hủy và hoàn tiền (migration), không được khớp. Phê duyệt cho lệnh chờ có thời hạn (`argon_approval_ttl_sec`); hết hạn thì bị hủy/hoàn tiền và cần một đánh giá mới. Vị thế đang mở, thoát lệnh và tất toán được giữ nguyên.

Xem quyết định: panel "CỔNG KIỂM DUYỆT ARGON" trên dashboard; các dòng `ARGON_ENTRY_REVIEW` trong `ai_brain_log`; khối `entry_review` trong `data/portfolio_state.json`; cột `entry_review_*` trong bảng `positions`. Thoát lệnh dùng quy tắc xác định (không phải suy luận AT entry) và được phân biệt rõ trên giao diện. Không coi các lệnh cũ là đã qua kiểm duyệt AI.

### 5.2. Kiểm duyệt điều khoản (cũ, tách biệt với cổng vào lệnh)

Không cần đăng nhập để chạy mô hình kiểm tra điều khoản xác định (`QUANT_SEMANTIC_AI`). Đây không phải một lần gọi LLM và KHÔNG được dùng để cấp phép vào lệnh ở chế độ mặc định. Tùy chọn `GEMINI_API_KEY` bật kiểm duyệt Gemini; `AUTOPILOT_ENABLE_AGY_SUBPROCESS=1` bật CLI `agy` cho lớp kiểm duyệt điều khoản này. Không đưa API key vào frontend hoặc Git.

```bash
python3 manage_accounts.py --help
python3 manage_accounts.py status
```

Đăng nhập/lưu profile/chuyển tài khoản thực hiện tại máy backend theo `--help`. Dashboard chỉ hiển thị trạng thái tài khoản; không có API công khai sao chép hoặc đổi OAuth token. Không chuyển sang tài khoản chưa cấu hình/đang cooldown. Xác minh log để biết bot thực sự đã dùng LLM hay fallback; không suy ra chỉ từ tên tài khoản hay tên model hiển thị.

## 6. Sao lưu và khôi phục

```bash
python3 scripts/backup.py
python3 scripts/doctor.py
```

Backup sử dụng SQLite Backup API và `integrity_check`, chạy được khi worker đang hoạt động. Mặc định lưu tại `data/backups/`, không đưa lên Git. Sao chép backup sang nơi lưu trữ riêng định kỳ.

Khôi phục: dừng backend và mọi `run_autopilot.py`; sao lưu database hiện tại; dùng bản backup đã kiểm chứng thay `autopilot.db` trong đúng thư mục dữ liệu; chạy `doctor`; chạy một chu kỳ để xuất lại snapshot. Không xóa database để sửa một lỗi kết nối.

Có thể đặt `AUTOPILOT_DATA_DIR=/absolute/path/polymarket-data` cho backend để giữ dữ liệu ngoài source. Trỏ Next.js tới backend bằng URL. Thư mục mới khởi tạo tài khoản mô phỏng mới; muốn giữ lịch sử phải chuyển bản backup sang đó trước khi chạy.

## 7. Chạy liên tục và Vercel

Vercel chỉ phục vụ dashboard. SQLite/worker Python phải chạy trên máy cá nhân luôn bật hoặc máy chủ có ổ đĩa bền vững. Có thể quản lý `python3 server.py` bằng launchd/systemd với tự khởi động lại và lưu stdout/stderr; không chạy thêm daemon `run_autopilot.py` song song nếu đã có worker trong `server.py`. Máy ngủ/tắt thì bot ngừng quét.

Với backend truy cập từ xa:

1. Sinh token dài ngẫu nhiên bằng `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`; lưu ngoài Git.
2. Đặt `AUTOPILOT_API_TOKEN` ở backend. Backend từ chối bind địa chỉ ngoài loopback nếu chưa có token.
3. Chạy backend sau reverse proxy HTTPS trên máy có truy cập Gamma/CLOB. Không công khai cổng HTTP thô.
4. Trong Vercel chọn root directory `web`, framework Next.js. `web/vercel.json` cố định cài đặt bằng `npm ci` và build bằng npm để dùng đúng lockfile. Đặt biến server `AUTOPILOT_BACKEND_URL=https://backend-cua-ban` và `AUTOPILOT_API_TOKEN` trùng backend. Không dùng tiền tố `NEXT_PUBLIC_`.
5. Deploy lại dashboard. Trên Vercel chỉ GET trạng thái; nút điều khiển bị vô hiệu hóa. Token chỉ ở server, không gửi xuống trình duyệt. Dashboard có thể công khai số liệu danh mục: dùng Deployment Protection nếu muốn giữ riêng tư.
6. Xem log backend và kiểm tra `doctor --network` trước khi coi hệ thống là live. Build/deploy thành công không xác nhận bot đang chạy 24/7.

Chưa cấu hình backend thì dashboard hiện rõ chế độ snapshot. Không tự cập nhật PnL ở frontend bằng một tập thị trường Gamma không đầy đủ.

## 8. Việc cần làm tiếp theo

1. Khôi phục kết nối Gamma/CLOB và đồng hồ hệ thống, chạy doctor đến khi đạt.
2. Chạy backend + dashboard theo mục 2; xác nhận timestamp, nguồn dữ liệu và danh mục khớp sổ cái. $1.000 là vốn khởi tạo; danh mục đã chạy có thể khác số này. Không reset database để đưa vốn về $1.000.
3. Để paper trading thu thập các chu kỳ, lệnh chờ/khớp/hủy và phân xử thật; đối chiếu một số lệnh với sổ lệnh. Không có số ngày cố định nào tự chứng minh lợi nhuận.
4. Sao lưu, kiểm tra lỗi vận hành và đánh giá phí/trượt giá trước khi cân nhắc mở rộng.

Giới hạn mô hình: chưa mô phỏng ưu tiên hàng đợi, khớp từng phần, độ trễ thực thi; phí dự phòng vẫn là tham số tĩnh, chưa đồng bộ từng thị trường; định giá có thể cũ nếu CLOB không đủ độ sâu (khi đó AI không được thoát vị thế đó); chưa có backtest chứng minh lợi thế. Tiền thật là một dự án bổ sung riêng, không phải bật một biến cấu hình.
