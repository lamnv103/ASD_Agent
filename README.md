# Dữ liệu toàn văn ASD cho ASD_AGENT

> **Trạng thái 07/11/2026:** nguyên mẫu nghiên cứu (truy xuất + đọc bằng chứng + context). **Chưa có tầng trả lời cho người dùng; chưa có thẩm định lâm sàng độc lập.**
>
> - Bắt đầu: [SETUP.md](SETUP.md) — dựng môi trường, database, sao lưu/khôi phục; `.\tasks.ps1 all` chạy toàn bộ kiểm tra (167 test, 4 verifier, chỉ dùng cache).
> - Việc vừa làm: [bàn giao nền tảng 07/11](reports/foundation_20261107/BAN_GIAO_NEN_TANG.md). Đánh giá hiện trạng: [kiểm định độc lập 06/11](reports/review_20261106/KIEM_DINH_DOC_LAP_VA_UU_TIEN.md).
> - Chờ chủ dự án và chuyên gia chốt: [phạm vi MVP (bản nháp)](docs/MVP_SCOPE_DRAFT.md).
> - Chạy một câu hỏi, có kiểm tra đầu vào trước truy xuất: `python -m rag.prepare_evidence "câu hỏi"`.
>
> Trước đó: [bàn giao reader v3, 02/11/2026](reports/reader_refinement_20261101_232742/BAN_GIAO_CAI_THIEN_READER_V3.md).

Kho chính nằm tại `knowledge/rag/source_library` trong thư mục gốc dự án (trước 06/11/2026 dự án ở ổ E:, nay ở D:; mã nguồn không còn phụ thuộc vị trí ổ đĩa). Chương trình và database của dự án trước vẫn ở Carobud_ASD_2026.

Đợt bổ sung ngày 30/10/2026 đã giữ nguyên 27 tài liệu ban đầu, bổ sung 6 tài liệu đạt kiểm tra chuyển đổi. Hiện tập chính có **33 tài liệu, 2,307,606 ký tự nội dung**; tăng 399,532 ký tự. Mỗi tài liệu/phiên bản vẫn ở một tệp đầy đủ. Không chia đoạn mới hoặc cắt ngắn tài liệu nguồn. Sau đợt bổ sung và pilot NVIDIA, đã nhúng đủ 33 tài liệu nguyên văn bằng Cohere embed-v4.0 và nạp vào collection PostgreSQL mới.

## Mở tệp nào trước

- [Báo cáo bổ sung theo bốn chủ đề bạn yêu cầu](reports/source_supplement_20261030/BAO_CAO_BO_SUNG_NGUON.md): đã thêm gì và phần nào còn thiếu.
- [Danh sách 33 tài liệu trong tập chính](knowledge/rag/source_library/CORE_DOCUMENTS.md).
- [documents.json](knowledge/rag/source_library/documents.json): toàn bộ nội dung của 33 tài liệu, có tên, nguồn/link/tác giả, nội dung và ngày tháng.
- [Hướng dẫn chi tiết cấu trúc dữ liệu](knowledge/rag/source_library/README.md).
- [Kết quả kiểm tra cuối](reports/source_supplement_20261030/verification.json).

## Những thư mục và danh mục chính

| Vị trí | Ý nghĩa |
|---|---|
| documents/ | 33 Markdown được nhận về mặt chuyển đổi; có thông tin nguồn và nội dung đầy đủ. |
| originals/ | 83 tệp gốc/tài sản đi kèm cho cả tập chính và nhóm bổ sung đang chờ; không phải 83 tài liệu độc lập. |
| pending_documents/ và documents_pending_review.json | 7 bản chuyển đổi bổ sung còn khoảng trống; không trộn vào documents.json hoặc coi là dữ liệu sẵn sàng nhúng. |
| core_catalog.jsonl | Danh mục của 33 tài liệu trong tập chính, có quyền sử dụng, phạm vi, giới hạn và hash. |
| catalog.jsonl | Danh mục rộng hơn, gồm cả hồ sơ chờ/loại từ dự án cũ. Không phải mọi dòng đều có toàn văn trong thư mục này. |
| CLINICAL_REVIEW_QUEUE.csv | Hàng chờ để chuyên gia thực sự thẩm định; không tự điền tên chuyên gia hay quyết định duyệt. |
| index_preview.jsonl | 183 mục cũ, chỉ thuộc 27 tài liệu ban đầu; chưa bổ sung chỉ mục cho các nguồn mới và không chứa vector. |

AAP, ASHA, AOTA và một bài Project AIM chưa xác minh được quyền tái sử dụng toàn văn chỉ được ghi thông tin nguồn/đường dẫn trong danh mục. Các nghiên cứu PEERS/SST, giao tiếp/ngôn ngữ và SenITA đã lấy được bản gốc nhưng một số hình/bảng/phụ lục chưa chuyển đủ; phần còn thiếu được ghi riêng.

**Kho nguồn đã đối chiếu phục vụ nghiên cứu, chưa có thẩm định lâm sàng độc lập.** “Đạt kiểm tra chuyển đổi” không có nghĩa phương pháp điều trị đã được chứng minh phù hợp cho mọi trẻ, hoặc chatbot đã đủ điều kiện tư vấn y khoa. Có nguồn có phạm vi tuổi rộng hơn 0–18 hoặc có điều kiện nghiên cứu cụ thể; giữ đúng phạm vi nguồn. Giấy phép áp dụng riêng từng nguồn, gồm cả giới hạn phi thương mại nếu có.

[DATA_TRANSFER_MANIFEST.json](DATA_TRANSFER_MANIFEST.json) là biên bản lịch sử lúc sao chép 27 tài liệu. Các con số/hash trong biên bản đó không phải snapshot hiện tại sau bổ sung; biên bản được giữ nguyên. [SUPPLEMENT_20261030_MANIFEST.json](knowledge/rag/source_library/SUPPLEMENT_20261030_MANIFEST.json) ghi hash của kho hiện tại. Danh mục cũ được sao lưu ở reports/source_supplement_20261030/before_release/.

Thư mục reports lưu bằng chứng thu thập, kết quả kiểm tra và cache nguồn; scripts/source_library lưu công cụ xử lý dữ liệu ngoại tuyến. Không dùng mọi tệp trong reports/cache làm tài liệu RAG. Không sao chép khóa API, môi trường Python, SQL hoặc vector vào kho mới trong đợt này; không thay database hay cấu hình agent cũ.

## Thử nghiệm embedding NVIDIA ngày 30/10/2026

Đã nhận vector thật 4096 chiều từ nvidia/nemotron-3.5-embed-8b cho một đoạn CDC 107 ký tự, request mất khoảng 0,97 giây. Tập nguồn không thay đổi; chưa nhúng toàn bộ kho hoặc ghi database. Các trạng thái chưa embedding trong hướng dẫn/BUILD_STATUS của đợt phát hành nguồn trước đó không phải nhật ký thử nghiệm hiện tại.

Xem [hướng dẫn chạy thử](scripts/embedding/README_NIM_PILOT.md), [kết quả JSON](reports/embedding_nim_pilot/pilot_embedding.json) và [kiểm tra kết quả](reports/embedding_nim_pilot/verification.json).

## Embedding nguyên văn 33 tài liệu và PostgreSQL

Đã hoàn tất **33 tài liệu = 33 vector Cohere 1536 chiều**, giữ đủ toàn văn, không chia đoạn hoặc trung bình vector. Collection mới đã bật cho công cụ truy xuất; các collection/vector cũ giữ nguyên. Không tự chuyển chatbot cũ sang Cohere.

Xem [hướng dẫn vận hành](scripts/embedding/README_WHOLE_DOCUMENTS.md), [33 vector JSONL](reports/whole_document_embedding_20261030/whole_document_embeddings.jsonl) và [nghiệm thu](reports/whole_document_embedding_20261030/verification.json). Các trạng thái embedding cũ trong source_library là snapshot lịch sử của đợt phát hành nguồn, không phải trạng thái vector hiện tại.


## Retriever và đánh giá tìm nguồn — 31/10/2026

Đã có module truy xuất PostgreSQL dùng trực tiếp trong agent: `rag/`, cùng bộ đánh giá 30 câu có bằng chứng được chốt trước khi tìm kiếm. Không thay 33 vector tài liệu hoặc nối chatbot cũ.

- [Cách gọi retriever, đọc toàn văn và cấu hình khóa](rag/README.md).
- [Cách đánh giá riêng khả năng tìm nguồn](evaluation/retrieval_v1/README.md).
- [Kết quả PostgreSQL/API thật của 30 câu](reports/retrieval_evaluation/R33_20261031_124523_966748/BAO_CAO.md).

Đây là kiểm tra tầng tìm nguồn; chưa có kết quả chấm câu trả lời LLM hay thẩm định lâm sàng độc lập.

[Bàn giao bước 1–2 và những giới hạn còn lại](reports/retrieval_evaluation/BAN_GIAO_BUOC_1_2.md): đã chạy 30 câu thật, 16 kiểm thử đạt; nguồn kỳ vọng xuất hiện trong top 5 ở 26/26 câu nội dung và 1 câu giới hạn. Ba câu thiếu căn cứ chưa được chấm khả năng từ chối.


## Evidence Reading và Context Management — 31/10/2026

Đã thêm hai tầng sau retriever, giữ nguyên 33 tài liệu/33 vector. Có tokenizer NVIDIA chính thức và context budget offline; chưa sinh câu trả lời hoặc tự phán xét đầy đủ bằng chứng cho câu mới.

- [Hướng dẫn kiến trúc, file, cách chạy và giới hạn](rag/README_EVIDENCE_CONTEXT.md).
- [Báo cáo nghiệm thu 47 kiểm thử và 30 truy vấn hồi quy](reports/evidence_context_20261031_175633/BAN_GIAO_EVIDENCE_CONTEXT.md).

## Reader tự động NVIDIA NIM — 01/11/2026

Đã nối reader ngữ nghĩa tự động với retriever PostgreSQL và hai tầng evidence/context. Model chọn ID đoạn; chương trình lấy đúng nguyên văn, kiểm tra mức hỗ trợ và xây context có ngân sách. Vẫn giữ 33 tài liệu = 33 vector; chưa sinh câu trả lời cho người dùng.

- [Bàn giao phiên hiện tại: đã làm gì, kết quả và việc còn thiếu](reports/semantic_reader_20261101_111654/BAN_GIAO_READER_NGU_NGHIA.md).
- [Hướng dẫn file/cấu hình/cách chạy reader](rag/README_SEMANTIC_READER.md).
- [Kết quả 20 câu cuối](reports/semantic_reader_20261101_111654/results_latest_20.csv).
- [Nghiệm thu kỹ thuật](reports/semantic_reader_20261101_111654/verification.json).

84 kiểm thử đạt; 20/20 trace hợp lệ và hash/database giữ nguyên. Có 4 ca khác nhãn tham chiếu sơ bộ và 2 ca khác cần duyệt độ đầy đủ; chưa chứng minh độ chính xác y khoa. Bước tiếp theo là cải thiện chọn mục/claim và duyệt các ca này trước khi nối model trả lời tiếng Việt có dẫn nguồn.
