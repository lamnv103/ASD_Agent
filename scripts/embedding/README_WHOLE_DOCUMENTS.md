# Embedding nguyên văn và PostgreSQL cho 33 tài liệu

Đã giữ một tài liệu = một vector native, không chia đoạn/chương, tóm tắt hoặc trung bình vector. Nội dung Markdown/HTML/MathML giữ nguyên khi gửi API. Tên, URL, tác giả, ngày và phạm vi được lưu cùng toàn văn trong PostgreSQL.

## Model và database

- Cohere embed-v4.0, ngữ cảnh 128k; đầu ra 1536 chiều.
- API đặt truncate=NONE, max_tokens=128000; quá dài phải báo lỗi.
- Collection: asd_fulltext_33_20261030_26eb017efca5.
- Không gian: cohere4_whole_1536_e83c596b9070.
- Document input_type=search_document; query input_type=search_query.
- PostgreSQL/pgvector cosine exact search; 33 tài liệu chưa cần ANN.
- UNIQUE riêng cho collection buộc mỗi tài liệu chỉ có một vector, kể cả giữa các space.
- Chỉ bật enabled khi đủ 33 vector và toàn văn được xác minh trong một transaction.
- clinical_reviewed/production_ingest vẫn false: kiểm tra kỹ thuật không phải thẩm định lâm sàng.

API NVIDIA của pilot công bố giới hạn 10240 token. Vì yêu cầu giữ toàn văn, đợt đầy đủ chuyển sang Cohere 128k. Không gian Cohere khác Gemini/NVIDIA; số chiều bằng nhau không làm hai model tương thích.

## Các tệp cần biết

- knowledge/rag/source_library/documents.json: 33 nguyên văn, giữ nguyên hash.
- reports/whole_document_embedding_20261030/whole_document_embeddings.jsonl: 33 vector, mỗi dòng một tài liệu.
- vectors/: cùng vector ở từng tệp để tiếp tục khi ngắt; không tính thành vector khác.
- embedding_manifest.json: profile và hash từng nguồn/vector.
- verification.json: kiểm tra kỹ thuật, dữ liệu cũ và smoke truy xuất.
- document_lengths_and_embeddings.csv: ký tự nguyên văn/thực gửi và token tính phí do API trả về. Không suy token từ ký tự.
- postgres_before.dump / backup.json: backup database trước cập nhật và hash.
- deployments/database.env: cấu hình PostgreSQL riêng của ASD_AGENT; chứa thông tin đăng nhập, được gitignore, không chia sẻ/in ra.
- deployments/cohere.env.example: mẫu trống để người dùng tự đặt khóa Cohere mới.
- .env NVIDIA hiện có không bị sửa; khóa NVIDIA không được gửi tới Cohere.
- Khóa Cohere cung cấp trong phiên được nhập ẩn trong tiến trình, không lưu vào tệp hoặc database.

## Chạy từ E:/AI4LIFE/ASD_AGENT

Xác minh kho và database, không gọi API:

    .\.venv-embedding\Scripts\python.exe -B scripts/embedding/whole_documents.py verify

Đọc nguyên văn một nguồn từ PostgreSQL, không gọi API:

    .\.venv-embedding\Scripts\python.exe -B scripts/embedding/whole_documents.py source --source-id ASD-SUP-PMC4513196

Tìm nguồn với câu hỏi tiếng Việt (nhập khóa ẩn nếu chưa có cache query):

    .\.venv-embedding\Scripts\python.exe -B scripts/embedding/whole_documents.py search --query "Can thiệp phát triển hành vi tự nhiên NDBI là gì?" --prompt-key

Có thể dùng --cohere-env deployments/cohere.env sau khi tự tạo tệp từ mẫu. Không đặt giá trị khóa trên dòng lệnh hoặc trong cuộc trò chuyện.

Tiếp tục embedding: tài liệu đã lưu và khớp hash sẽ không gọi API lại:

    .\.venv-embedding\Scripts\python.exe -B scripts/embedding/whole_documents.py embed --prompt-key

Nạp lại vector đã lưu, không gọi API:

    .\.venv-embedding\Scripts\python.exe -B scripts/embedding/whole_documents.py load-vectors

Luồng đầy đủ trong workspace đã có backup hợp lệ:

    .\.venv-embedding\Scripts\python.exe -B scripts/embedding/whole_documents.py run --prompt-key

run không thay cho bước pg_dump. Khi thay nguồn/model, tạo phiên bản collection mới thay vì sửa âm thầm vector cũ. Cấu hình PostgreSQL cục bộ không phụ thuộc đường dẫn cấu hình dự án trước.

## Gián đoạn và tốc độ

Đợt đầu Cohere trả HTTP 429 sau 14 tài liệu, tổng usage gần 100k token. Pipeline giữ cache, giãn tốc độ theo usage; ước lượng cho tài liệu kế tiếp chỉ dùng pacing, không công bố là token count. Chỉ retry có giới hạn với 429 đã xác nhận từ chối.

Nếu timeout/mất mạng, máy chủ có thể đã xử lý. Kiểm tra .attempt.json và tiến trình trước khi dùng --retry-uncertain. Không xóa lock còn hoạt động. Cache sai hash/model/kích thước bị từ chối, không tự ghi đè.

Các bảng/collection cũ, 7 vector Gemini và 113 phần curated giữ nguyên fingerprint. Các dịch vụ Docker khác và cấu hình ứng dụng cũ không thay đổi.

## Tích hợp agent

Dùng search lấy ID/metadata từ pgvector, rồi source đọc toàn văn trong PostgreSQL. Chưa nối tự động chatbot cũ sang Cohere và chưa gọi LLM tạo lời khuyên.

Một vector cho tài liệu dài có thể khó tìm chi tiết nhỏ trong tài liệu. Ba câu smoke chỉ xác nhận luồng hoạt động và truy xuất các trường hợp cụ thể; cần đánh giá tiếp bằng bộ câu hỏi độc lập và thẩm định y khoa.

Tài liệu API: https://docs.cohere.com/docs/cohere-embed
https://docs.cohere.com/v2/reference/embed
