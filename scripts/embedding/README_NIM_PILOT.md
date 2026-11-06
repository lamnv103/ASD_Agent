# Thử embedding một đoạn bằng NVIDIA NIM

Đã gọi API thật thành công ngày 30/10/2026. Model sử dụng là **nvidia/nemotron-3.5-embed-8b**, đúng model NVIDIA trong tệp cấu hình người dùng chỉ định.

## Kết quả

- Nguồn: CDC-EARLY-INTERVENTION, Early Intervention.
- Đầu vào: một đoạn nguyên văn 107 ký tự, 16 từ phân tách theo khoảng trắng; không coi số từ là token.
- API trả usage: 23 token.
- Vector: 4096 chiều; tất cả giá trị hữu hạn, norm xấp xỉ 1.
- Thời gian request: 0.966639 giây (không gồm thời gian viết/kiểm tra chương trình).
- Đã lưu toàn bộ vector và vị trí/hash nguồn trong reports/embedding_nim_pilot/pilot_embedding.json.
- console_output.txt chứa nội dung in console, gồm toàn bộ vector, được tạo bằng cách đọc lại kết quả đã lưu; không gọi API thêm.

Kết quả chỉ đại diện cho đúng đoạn thử, có scope pilot_excerpt_not_complete_document. Chưa tạo embedding nguyên tài liệu, chưa nhúng toàn bộ 33 tài liệu và chưa cập nhật PostgreSQL/pgvector. Thành công này chưa chứng minh độ chính xác truy xuất/y khoa.

## Chạy lại để xem kết quả, không gọi API

Chạy từ E:/AI4LIFE/ASD_AGENT:

    python -B scripts/embedding/smoke_test_nim.py
    python -B scripts/embedding/smoke_test_nim.py --print-full

Nếu pilot_embedding.json còn nguyên và khớp nguồn/model, script đọc cache trước; không cần đọc khóa và không gửi request. Mặc định in 16 giá trị đầu, tùy chọn --print-full in toàn bộ vector.

Khi cần chạy ở vị trí terminal khác, dùng đường dẫn tuyệt đối tới script. Script tự tìm thư mục dự án từ vị trí tệp.

## Khóa và cấu hình

Người dùng cung cấp E:/AI4LIFE/ASD_AGENT/.env. Tệp này đang dùng cấu trúc YAML của Continue (models, provider, model, apiKey), không phải định dạng dotenv KEY=VALUE. Script hỗ trợ cả hai cách:

- Dotenv: đọc đúng biến NVIDIA_API_KEY.
- YAML: chỉ lấy apiKey ở model NVIDIA trùng model embedding đã chọn và endpoint NVIDIA chính thức; cần PyYAML, đã có trong Python sử dụng để chạy thử.
- Hoặc dùng biến môi trường NVIDIA_API_KEY.

Không sửa/đổi tên tệp .env hay config.yaml của Continue. Không in, chép hoặc lưu khóa trong kết quả, báo cáo và source code.

Nếu chưa có cache và muốn gọi API với đúng cấu hình hiện tại:

    python -B scripts/embedding/smoke_test_nim.py --env-file .env --model nvidia/nemotron-3.5-embed-8b --timeout 45

Lệnh vẫn dùng cache khi kết quả tương ứng đã tồn tại. Để chạy một thí nghiệm khác, chỉ định tên kết quả mới bằng --output bên trong reports/embedding_nim_pilot; không xóa kết quả cũ. Không tự chuyển model khi lỗi.

Model mặc định đã được giữ theo cấu hình hiện tại là nemotron-3.5-embed-8b. Nemotron Ultra là model chat/agent, không được dùng để sinh danh sách số giả làm vector.

## Thời gian chờ và khả năng tiếp tục

Mỗi lần chạy mới gửi tối đa một request, timeout mặc định 45 giây, không tự retry. Có khóa request.lock để tránh các bản script gọi trùng đồng thời. Tệp attempt-*.json ghi trạng thái và fingerprint nhưng không chứa khóa.

Nếu ngắt tiến trình hoặc timeout, phía máy chủ có thể đã xử lý request; kiểm tra attempt và tiến trình trước khi gọi lại. Không tự xóa lock còn thuộc tiến trình đang hoạt động. Nếu kết quả thành công đã lưu, chạy lại sẽ kiểm tra và tái sử dụng vector.

Chương trình lưu JSON qua tệp tạm rồi thay thế an toàn, kiểm tra lại nội dung đã ghi. Không sửa dataset, chia đoạn hàng loạt, tự cắt chiều vector hay tự chuẩn hóa số liệu API trả về. Payload sử dụng input_type=passage, encoding_format=float, truncate=NONE.

## Tệp và kiểm tra

- smoke_test_nim.py: chương trình chạy thử và đọc lại kết quả.
- test_smoke_test_nim.py: 8 kiểm thử ngoại tuyến, gồm chống gọi API khi có cache, sai provenance, sai model và giá trị vector không hợp lệ.
- reports/embedding_nim_pilot/verification.json: kết quả kiểm tra, số request thật và hash dữ liệu.
- reports/embedding_nim_pilot/before_implementation/smoke_test_nim.py: bản giữ lại của tệp trước khi triển khai (lúc đó chỉ chứa chữ test).

Tất cả 132 tệp thuộc manifest kho nguồn được đối chiếu lại và vẫn khớp hash. Trạng thái BUILD_STATUS.json trong kho nguồn là trạng thái đợt phát hành dữ liệu trước thử nghiệm, không phải nhật ký vector; kết quả embedding thử được quản lý riêng ở reports/embedding_nim_pilot.

Tài liệu API chính thức:
https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3_5-embed-8b-infer
