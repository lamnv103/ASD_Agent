# Cách đọc kho nguồn

Cập nhật 30/10/2026. Tập chính: 33 tài liệu, 2,307,606 ký tự nội dung. **Phục vụ nghiên cứu; chưa có thẩm định lâm sàng độc lập.**

## Nội dung trong JSON

documents.json có hai trường chính:

- thong_tin_bo_du_lieu: số tài liệu, lượng nội dung, ngày xuất, hash danh mục và trạng thái sử dụng.
- tai_lieu: danh sách tài liệu. Mỗi phần tử có id, ten_tai_lieu, nguon, noi_dung, ngay_thang và doi_chieu.

nguon chứa tên tổ chức/tạp chí, link nguồn, link toàn văn và tác giả khi được công bố. Không tự tạo tên tác giả cá nhân cho bài CDC do cơ quan phát hành. noi_dung là toàn bộ phần nguồn đã chuyển đổi, giữ ngôn ngữ gốc, không phải bài giải thích tiếng Việt do AI viết. Phần biên tập về phạm vi/quyền/hạn chế nằm ở metadata và đầu Markdown, tách khỏi mốc ORIGINAL_DOCUMENT_BODY.

ngay_thang phân biệt ngày xuất bản, cập nhật và đối chiếu. Giá trị null nghĩa là chưa được công bố/xác định theo loại ngày đó. Với CDC Treatment, nguồn hiển thị 16/05/2024 nhưng không ghi rõ đó là ngày xuất bản hay cập nhật; ngày hiển thị được giữ trong nội dung và trường displayed_source_date của catalog.jsonl, không tự gán thành ngày xuất bản. Bài nghiên cứu có thể có ngày xuất bản trực tuyến khác năm/số báo; verified_bibliography giữ các ngày gốc. Không coi ngày tải là ngày xuất bản.

doi_chieu chứa quyền sử dụng, phạm vi tuổi gốc, giới hạn, đường dẫn Markdown/bản gốc/tài sản và SHA-256. Tài liệu nghiên cứu có thể chứa bảng HTML và công thức MathML trong Markdown; không xóa chúng vì tưởng là mã thừa.

## Tập chính và tập chờ

documents/ và documents.json có cùng 33 nội dung. core_catalog.jsonl có cùng các ID. “Tập chính” ở đây chỉ là nhóm đã đáp ứng kiểm tra xuất xứ/quyền/chuyển đổi của kho nghiên cứu, chưa được duyệt lâm sàng hoặc production.

pending_documents/ và documents_pending_review.json chứa 7 nguồn bổ sung có bản gốc nhưng còn hình/bảng/phụ lục hoặc quan hệ phiên bản cần xử lý. JSON chờ dùng cấu trúc source_id, title, source_url, status, conversion_gaps, metadata, content và mang nhãn NOT_ACCEPTED_FOR_INDEXING. Không nhập nhầm JSON này cùng documents.json để tăng quy mô.

catalog.jsonl có cả hồ sơ lịch sử chưa được tải toàn văn, nguồn bị loại và hồ sơ chỉ có đường dẫn. Chỉ dùng core_catalog.jsonl/documents.json khi muốn đọc tập chính hiện hành. Trường coverage_eligible trong bản phát hành này là điều kiện nhận nguồn của kho; không phải bằng chứng đã đạt đủ độ phủ y khoa.

Hai bản CDC bổ sung được lưu dưới dạng bản đọc web có đầy đủ các dòng nội dung bài, kèm đường dẫn đã đối chiếu. Đuôi bản gốc là .web.txt; đây không phải HTML gốc (máy chủ trả HTTP 403 khi tải HTML trực tiếp). Ảnh minh họa không được sao chép theo giả định quyền của phần chữ; alt text và việc loại ảnh được ghi rõ. Không chứng nhận bố cục/scripts của trang.

Mỗi nghiên cứu được nhận giữ nguyên bản XML và các bảng, tài liệu bổ sung cùng một Markdown nguồn. Ba sơ đồ đã được đối chiếu hình để chép lại nhãn/số liệu; ba phụ lục DOCX đã chuyển đầy đủ phần văn bản/bảng. Bản hình/DOCX vẫn được giữ để kiểm tra. Các biểu đồ chưa chuyển an toàn tiếp tục làm tài liệu chờ, không đoán số liệu từ vị trí điểm trên hình.

## Kiểm tra lặp lại

Dùng Python đã có của dự án trước, không cần khóa API hay kết nối database:

    & 'E:\AI4LIFE\Carobud_ASD_2026\.venv-rag\Scripts\python.exe' -B scripts/source_library/export_json.py --check
    & 'E:\AI4LIFE\Carobud_ASD_2026\.venv-rag\Scripts\python.exe' -B scripts/source_library/audit_supplement_20261030.py

Chạy từ E:/AI4LIFE/ASD_AGENT. Lệnh đầu chỉ đọc và đối chiếu JSON/Markdown/hash. Lệnh audit đọc kho, chạy kiểm thử và cập nhật báo cáo/hướng dẫn/manifest cục bộ; không gọi mạng, LLM, embedding hoặc database.

scripts/source_library/supplement_20261030.py plan tái dựng kế hoạch đợt bổ sung từ cache và danh mục cha đã sao lưu. Lệnh publish chỉ dùng một lần và sẽ từ chối ghi đè bản đã phát hành. Mọi bổ sung tiếp cần phiên bản mới thay vì sửa âm thầm dữ liệu nguồn.

index_preview.jsonl giữ nguyên 183 mục của 27 tài liệu cũ; chưa phải cấu hình chunk cuối cùng, không phản ánh các tài liệu bổ sung. Đợt này ưu tiên dữ liệu nguồn theo yêu cầu của bạn.

## Quyền và phạm vi

Không dùng số lượng file, phụ lục hoặc bài tổng quan trùng nghiên cứu để đếm bằng chứng độc lập. Không đổi phạm vi nguồn thành toàn bộ 0–18 tuổi. ASI khác hoạt động cảm giác nói chung; PEERS khác Social Stories và không có nghĩa đã có giáo trình PEERS được cấp phép. Dịch vụ/quyền lợi Hoa Kỳ không tự áp dụng tại Việt Nam.

Chưa làm embedding, chưa đếm lại token cho bộ mới, chưa cập nhật database và chưa thay dữ liệu chatbot đang sử dụng. Các trạng thái vector thử nghiệm trong dự án trước vẫn là lịch sử của tập cũ, không tự áp cho 33 tài liệu hiện tại.
