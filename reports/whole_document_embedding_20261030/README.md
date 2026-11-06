# Kết quả nhúng nguyên văn 33 tài liệu

**Đã nhúng và nạp PostgreSQL: 33 tài liệu = 33 vector.** Không chia đoạn, tóm tắt, lấy phần đầu/cuối hoặc trung bình vector.

- Model Cohere embed-v4.0, ngữ cảnh 128k, vector 1536 chiều.
- Toàn văn gốc documents.json giữ nguyên hash; database giữ đủ 2.307.606 ký tự nguồn.
- whole_document_embeddings.jsonl: 33 dòng, mỗi dòng một vector kèm metadata/hash nguồn.
- vectors/: cùng các vector ở tệp riêng để tiếp tục, không phải tập vector khác.
- embedding_manifest.json: model/profile, ID và hash nguồn/vector.
- document_lengths_and_embeddings.csv: số ký tự thực gửi và token tính phí API trả về.
- database_verification.json / verification.json: nghiệm thu và bảo toàn dữ liệu cũ.
- postgres_before.dump / backup.json: bản pg_dump trước cập nhật và hash backup.
- retrieval_smoke.json: thử truy xuất tiếng Việt từ PostgreSQL/pgvector, chưa phải benchmark y khoa.
- active_collection.json: cấu hình collection/không gian đã xác minh.

Cấu hình chatbot trong dự án cũ chưa bị sửa. Không dùng query Gemini/NVIDIA để tìm trong vector Cohere.
Kho vẫn phục vụ nghiên cứu, chưa có thẩm định lâm sàng độc lập. Xem scripts/embedding/README_WHOLE_DOCUMENTS.md.
