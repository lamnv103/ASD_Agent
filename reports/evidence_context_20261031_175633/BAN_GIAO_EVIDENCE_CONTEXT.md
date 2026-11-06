# Bàn giao Evidence Reading và Context Management

Kế hoạch phù hợp với giai đoạn dự án. Đã triển khai tầng trích nguyên văn có truy nguyên, review/assessment rõ ràng và context có ngân sách token thật. Chưa triển khai reader ngữ nghĩa tự động hoặc sinh câu trả lời.

## Kết quả nghiệm thu cuối

- 47 kiểm thử đạt; không lỗi hoặc skip.
- 30/30 truy vấn PostgreSQL từ cache: ranking/khoảng cách không đổi. Không gọi API embedding hoặc model trả lời.
- 33 tài liệu/33 vector trước và sau; 132 tệp nguồn, profile/metadata/collection, mã retrieval và dữ liệu legacy không đổi.
- Tokenizer/chat template NVIDIA chính thức được tải, ghim revision/hash và chạy offline; không tải weights.
- Các trace bình thường đều nằm trong cửa sổ thử nghiệm 32.768 token, có chừa đầu ra và biên an toàn.

## Ví dụ trace

| Trace | Trạng thái/điều cần đọc |
|---|---|
| [Q15](traces/Q15.json) | Nguồn kén ăn thật từ PostgreSQL; sufficient theo review tham chiếu; context có giữ giới hạn. |
| [Q09](traces/Q09.json) | partially_sufficient về AAC; không nâng thành đủ chỉ vì tìm thấy đúng nguồn. |
| [Q27](traces/Q27.json) | partially_sufficient: phạm vi CDC, chưa đủ kết luận nghĩa vụ tại Việt Nam. |
| [Q29](traces/Q29.json) | insufficient; policy không kê đơn/tính liều cá nhân. |
| [Q01 không review](traces/Q01_without_review.json) | pending_semantic_review; không giả rằng agent đã tự hiểu nguồn. |
| [Q15 ngân sách nhỏ](traces/Q15_tight_budget.json) | Loại nguyên đơn vị bằng chứng, trạng thái sau chọn không còn đủ; không cắt ngầm nội dung. |
| [Mâu thuẫn giả lập](traces/SYNTHETIC_conflicting.json) | conflicting, dữ liệu TEST-*; chỉ chứng minh code giữ hai phía, không phải mâu thuẫn y khoa đã xác nhận. |

Không có ca conflicting thật được duyệt trong bộ này. Không biến khác biệt quần thể, phương pháp hoặc phân tích nhóm con thành mâu thuẫn để đủ số trạng thái.

## Cách đọc điểm kiểm thử

25 sufficient, 2 partially_sufficient và 3 insufficient là kết quả replay review v1 trên nguồn thực tìm được. Không dùng các con số này làm độ chính xác semantic/clinical của AI. Số điểm retrieval cũ cũng không thay thế đánh giá câu trả lời.
Nguồn chỉ tìm bằng từ khóa là topical và chưa được dùng để chứng minh claim. Review AI có provenance, nhưng người duyệt chưa được xác thực bằng hệ thống và chưa có thẩm định lâm sàng độc lập.

## Lỗi phát hiện đã sửa và phần chưa kiểm thử

- Đã sửa tương thích Mapping/BatchEncoding của tokenizer thực; kiểm tra trực tiếp với chat template và token IDs.
- Đã sửa truyền phần dẫn nhập mục cha vào context, bổ sung kiểm thử giữ điều kiện, phủ định, bảng và offset Unicode.
- Đã bổ sung xác thực source ID/hash và attribution với PostgreSQL khi gọi tầng chuẩn bị trực tiếp.
- Chưa có bộ đánh giá ngữ nghĩa tự động cho câu mới; ứng viên có thể thiếu do khác ngôn ngữ. Câu chưa review được chặn ở trạng thái chờ.
- Chưa đối chiếu token local với usage hoặc giới hạn endpoint NIM; chưa kiểm thử chất lượng sinh tiếng Việt, dẫn nguồn, từ chối hay chống injection của LLM.
- Mục/quần thể/điều kiện nằm ngoài phạm vi trích có thể cần đọc thêm toàn văn. Không tuyên bố tiểu mục tự động luôn đủ ngữ cảnh lâm sàng.
- Chưa có chuyên gia lâm sàng độc lập duyệt; chưa triển khai tư vấn sức khỏe thực tế.

## Bước tiếp theo

Đưa một cơ chế review ngữ nghĩa có đánh giá độc lập vào adapter, thử trên câu phụ huynh chưa có nhãn; giữ kiểm tra nguyên trích/source/hash và policy hiện có. Khi reader đạt yêu cầu, nối model NIM sinh câu trả lời dựa trên context đã chọn; hiệu chỉnh token với endpoint thật và chấm riêng đúng ý nguồn, trích dẫn, từ chối. Không tự bật generation bằng cách đổi một cờ; hiện chưa có code gọi model trả lời.

Xem [hướng dẫn và danh sách file](../../rag/README_EVIDENCE_CONTEXT.md), [verification.json](verification.json), [kết quả kiểm thử](tests.txt), [results.csv](results.csv).
