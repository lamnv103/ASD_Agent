# Đánh giá retriever PostgreSQL — 33 tài liệu

Chỉ đánh giá tìm nguồn; không sinh câu trả lời. Nhãn do AI đọc nguồn trước khi chạy, chưa được chuyên gia độc lập duyệt.

- Trạng thái: complete; chạy thành công 30/30 câu.
- Database và 132 tệp nguồn giữ nguyên: True.
- Câu trực tiếp: {'eligible_questions': 26, 'successful_queries': 26, 'execution_errors': 0, 'hit_at_5': 1.0, 'mrr_at_5': 0.8185897435897437, 'labeled_source_recall_at_5': 1.0, 'metric_denominator': 'successful queries with independently source-read candidate labels; reference sets are not exhaustive'}
- Câu giới hạn phạm vi: {'eligible_questions': 1, 'successful_queries': 1, 'execution_errors': 0, 'hit_at_5': 1.0, 'mrr_at_5': 0.3333333333333333, 'labeled_source_recall_at_5': 1.0, 'metric_denominator': 'successful queries with independently source-read candidate labels; reference sets are not exhaustive'}
- Ba câu không đủ căn cứ được loại khỏi mẫu số recall. Trả về top 5 không có nghĩa hệ thống biết từ chối.
- DU/MOT_PHAN chỉ áp dụng nếu bằng chứng đã gán nhãn thực sự có trong toàn văn được trả về. Nguồn khác chưa gán nhãn cần đọc bổ sung.
- Chưa đo độ đúng câu trả lời, độ đúng trích dẫn, khả năng từ chối hay hiệu quả tư vấn y tế.

Xem ket_qua.csv, raw_results.jsonl, retrieved_sources.jsonl và các input/hash đã đóng băng trong cùng thư mục.
