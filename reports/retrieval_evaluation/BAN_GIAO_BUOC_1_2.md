# Bàn giao bước 1 và 2 — retriever cho kho 33 tài liệu

Đã có retriever dùng trực tiếp trong agent và đã chạy bộ 30 câu qua API Cohere cùng PostgreSQL thật. Đây là tầng tìm nguồn, chưa có chatbot sinh câu trả lời.

## Những phần đã hoàn thành

1. Module `rag/` tìm kiếm và đọc toàn văn PostgreSQL; hai công cụ `search_sources`, `read_source` có schema để đăng ký vào agent.
2. Profile Cohere search_query đúng không gian của 33 vector tài liệu, cosine chính xác, lọc cứng collection. Không đọc Markdown cho mỗi truy vấn.
3. Kiểm tra hash toàn văn, metadata, vector và profile trước khi trả kết quả. Kết nối chỉ đọc; lỗi kết nối/API/cache không biến thành kết quả rỗng.
4. Bộ 30 câu hỏi, bằng chứng có vị trí và giới hạn nguồn, đóng băng trước khi xem ranking. Có CSV, JSONL kết quả và toàn văn nguồn thực trả về.

## Kết quả thật

| Kiểm tra | Kết quả |
|---|---|
| Truy vấn chạy thành công | 30/30; không có lỗi thực thi |
| Câu nội dung có nguồn đã gán nhãn trong top 5 | 26/26; gồm 25 nhãn đủ theo phạm vi câu và 1 nhãn một phần |
| Câu kiểm tra giới hạn quốc gia | 1/1 tìm thấy nguồn phạm vi CDC trong top 5; không đủ kết luận pháp luật Việt Nam |
| Câu thiếu căn cứ | 3; không đưa vào mẫu số recall, chưa chấm khả năng từ chối |
| MRR@5 trên 26 câu nội dung | 0.8186 |
| Nguồn đã gán nhãn ở hạng 1 | 18/26; không có nghĩa các nguồn khác đứng trước đều sai |
| Nhãn kỳ vọng đã đọc | 21 nguồn độc lập về danh tính, chưa kết luận độc lập về bằng chứng |
| Nguồn xuất hiện trong kết quả | 31/33; mỗi toàn văn lưu một lần |
| Kiểm thử tự động | 16 đạt, gồm kiểm tra database thật chỉ đọc |
| Chạy lại từ cache không có khóa/API | 30/30, thứ tự và khoảng cách khớp lần đầu |
| Bảo toàn dữ liệu | 132 tệp nguồn và snapshot các bảng database không đổi |

Một tài liệu vẫn bằng một vector. Lần này không chia đoạn, không dùng `index_preview.jsonl`, không gọi lại embedding tài liệu, không viết database và không đổi chatbot cũ.

## Điều còn giới hạn

Đây là bộ nhãn do AI đọc nguồn trước ranking, không phải nhãn lâm sàng độc lập và chưa liệt kê hết mọi nguồn phù hợp. Kết quả top 5 tốt trên bộ nhỏ này chưa chứng minh độ bao phủ của toàn kho hoặc chất lượng tư vấn.

Ví dụ Q03 có nguồn kỳ vọng NIMH ở hạng 5, nhưng các tổng quan đánh giá/sàng lọc đứng trước cũng có thể liên quan. Cần duyệt nguồn và bổ sung nhãn có căn cứ trong phiên bản mới; không tự kết luận các nguồn chưa gán nhãn là sai.

Q29 hỏi liều thuốc cá nhân và Q30 hỏi giá khám theo thời gian thực vẫn được trả top 5 nghiên cứu gần nghĩa. Retriever chưa biết từ chối; không được dùng top 5 hoặc khoảng cách cosine để khẳng định có đủ căn cứ trả lời. Q09 về AAC chỉ giữ nhãn một phần, không tự nâng vì tìm thấy đúng ID.

Nội dung trả về là toàn văn có thể rất dài. Tầng agent sau này phải quản lý ngân sách ngữ cảnh và dẫn nguồn rõ ràng; không cắt ngầm nguồn hoặc đưa mọi tài liệu dài vào một prompt khi vượt giới hạn.

## Bước tiếp theo

1. Duyệt bộ nhãn và các trường hợp giới hạn/thiếu căn cứ bằng nội dung thực trả về; nhờ chuyên gia thực sự duyệt trước khi gọi đây là chuẩn lâm sàng.
2. Nối LLM trả lời tiếng Việt với hai công cụ có sẵn: tìm nguồn → đọc nội dung → đối chiếu đủ căn cứ → trả lời và dẫn source ID/link. Giữ giới hạn tuổi, quần thể, quốc gia và chất lượng bằng chứng.
3. Tạo bài đánh giá câu trả lời riêng: đúng ý nguồn, không suy quá mức, trích dẫn đúng, xử lý mâu thuẫn và từ chối khi không đủ dữ liệu. Giữ bộ tìm nguồn v1 làm baseline; không tối ưu và chấm trên cùng một tập duy nhất.

Kho nguồn đã đối chiếu phục vụ nghiên cứu, **chưa có thẩm định lâm sàng độc lập**. Chưa triển khai phục vụ tư vấn y khoa thực tế.

Đọc hướng dẫn: [retriever](../../rag/README.md) và [bộ đánh giá](../../evaluation/retrieval_v1/README.md). Kết quả chi tiết ở `R33_20261031_124523_966748/` trong thư mục này.
