# Dữ liệu toàn văn ASD cho ASD_AGENT

Nguồn sao chép: `E:\AI4LIFE\Carobud_ASD_2026`. Thư mục này là bản dữ liệu độc lập để bạn bắt đầu dự án RAG Agent mới; không phải bản sao toàn bộ chương trình.

## Mở dữ liệu ở đâu

- [Danh sách 27 tài liệu](knowledge/rag/source_library/CORE_DOCUMENTS.md).
- `knowledge/rag/source_library/documents/`: **27 tệp Markdown toàn văn**, mỗi nguồn/phiên bản một tệp, giữ nguyên tên, tác giả/tổ chức, đường dẫn nguồn, ngày tháng và toàn bộ nội dung.
- [documents.json](knowledge/rag/source_library/documents.json): cùng 27 nội dung, theo cấu trúc tên tài liệu – nguồn/link/tác giả – nội dung – ngày tháng. Tổng **1.908.074 ký tự phần nội dung**.
- `knowledge/rag/source_library/originals/`: **35 bản gốc và tài sản hình/phụ lục** đi kèm tập chính, giữ đường dẫn tương đối để hình trong Markdown vẫn mở được. Các tệp này không được tính thành 35 tài liệu mới.
- `core_catalog.jsonl`: danh mục 27 nguồn chính, gồm giấy phép, phạm vi, giới hạn và hash.
- `catalog.jsonl`, `BUILD_STATUS.json`: snapshot danh mục/trạng thái phát hành của kho gốc. Danh mục đầy đủ có cả nguồn chờ/loại; không có nghĩa tất cả các nguồn được liệt kê đều được chép hoặc đủ điều kiện sử dụng trong tập này.
- `index_preview.jsonl`: bản xem trước 183 mục dẫn xuất có vị trí truy nguyên; chưa phải cấu hình chunk cuối cùng hoặc vector.
- `CLINICAL_REVIEW_QUEUE.csv`: chỗ để chuyên gia ghi thẩm định thật.

Giữ cấu trúc `knowledge/rag/source_library` để các đường dẫn hiện có của dữ liệu vẫn tương ứng. Một số trường lịch sử như `original_profile_path`, báo cáo đối chiếu hoặc snapshot phiên bản trước vẫn chỉ tới tài liệu trong dự án gốc; không phải tệp bắt buộc để đọc 27 toàn văn. Bản Markdown, XML/HTML/bản đọc web gốc và các hình/phụ lục của tập chính đều đã được chép và kiểm tra hash.

## Trạng thái và phạm vi sao chép

Bản này có 27 tài liệu đã qua kiểm tra kỹ thuật/chuyển đổi. **Kho nguồn đã đối chiếu phục vụ nghiên cứu, chưa có thẩm định lâm sàng độc lập.** Không tự coi tài liệu là hướng dẫn điều trị được duyệt. Quyền sử dụng áp dụng riêng từng nguồn; có nguồn chỉ cho nghiên cứu phi thương mại.

Không trộn 36 bản chuyển đổi còn thiếu hoặc các bộ tóm tắt/biên soạn cũ vào `documents/`. Chưa chép chương trình, khóa API, môi trường Python, SQL hay cache vector sang đây. Tập 7 vector thử nghiệm vẫn nằm trong database/các báo cáo của dự án gốc; 20 tài liệu dài chưa được nhúng nguyên văn.

Đây là **sao chép có đối chiếu**, chưa xóa tệp gốc, chưa đổi cấu hình hoặc đường dẫn database của agent. Khi chạy dự án hiện tại, tiếp tục dùng bản chương trình trong Carobud_ASD_2026. Thư mục ASD_AGENT hiện mới chứa dữ liệu để phát triển tiếp.

Xem [biên bản sao chép và SHA-256 từng tệp](DATA_TRANSFER_MANIFEST.json). Chỉ các tệp thuộc bộ dữ liệu nêu trên và README/biên bản này được tạo trong ASD_AGENT; các thư mục khác không bị sửa.
