# Bàn giao reader ngữ nghĩa — 01/11/2026

Đã hoàn thành triển khai và nghiệm thu kỹ thuật tầng đọc bằng chứng tự động trên E:/AI4LIFE/ASD_AGENT. Tầng này đã chạy NVIDIA NIM thật và nối với Evidence Reading / Context Management. Chưa bật sinh câu trả lời cho người dùng. Chất lượng ngữ nghĩa vẫn còn các ca cần sửa/duyệt; chưa đạt nghiệm thu lâm sàng.

## Mở những gì trước

- [Kết quả nghiệm thu máy đọc được](verification.json).
- [Hướng dẫn kiến trúc, cấu hình, file và cách chạy](../../rag/README_SEMANTIC_READER.md).
- [15 câu phát triển — kết quả cuối](pilot_20261101_230702/results.csv).
- [5 câu riêng — kết quả cuối](pilot_20261101_230813/results.csv).
- [Các ca cần đọc lại](semantic_review_queue.jsonl).
- [Log 84 kiểm thử](final_tests.txt).

Không cần dùng các run trước sửa để vận hành. Chúng được giữ làm lịch sử lỗi và đối chiếu, không trộn điểm với kết quả cuối.

## Đã làm gì

Luồng hiện tại:

Câu hỏi → Cohere nhúng câu hỏi đúng không gian cũ → PostgreSQL tìm top 5 tài liệu → chọn các mục nguyên vẹn trong ngân sách đọc → NVIDIA chọn ID đoạn và nhận định quan hệ → chương trình lấy nguyên văn/vị trí từ PostgreSQL → guard điều kiện sử dụng → verifier kiểm tra liên kết bằng chứng → assessment/policy → context có ngân sách.

Cohere chỉ cần gọi cho câu hỏi mới chưa cache. NVIDIA sinh JSON review/kiểm tra, không sinh tư vấn y khoa trong giai đoạn này.

Mô hình đọc: `nvidia/nemotron-3-ultra-550b-a55b`. Tokenizer/chat template NVIDIA chính thức đã ghim được dùng để đếm toàn request. Đã quan sát delta 0 giữa đếm local và `usage.prompt_tokens` ở các request hoàn thành dùng cho nghiệm thu; đây không phải chứng minh mọi request tương lai đều khớp.

Reader không còn tự viết câu trích. Model chỉ chọn mã đoạn tồn tại. Code kiểm tra source ID, hash, offset Unicode [start,end), đoạn nguyên văn và giới hạn cùng nguồn; từ chối ID giả, trích metadata như nội dung nguồn, scope không truy nguyên được, JSON sai và đoạn chỉ là tiêu đề làm bằng chứng.

Verifier chỉ kiểm tra các liên kết đang được dùng như bằng chứng. Nó chỉ giữ/hạ mức, không nâng mức hoặc đổi chiều nhận định để tăng điểm. Nếu hai lượt hiểu khác chiều hoặc verifier bỏ sót liên kết bắt buộc, kết quả bị hạ/chặn. Verifier dùng cùng model, không phải thẩm định độc lập.

Guard chạy trước verifier. Với intent chẩn đoán cá nhân, kê liều cá nhân, quyền lợi pháp lý hoặc dịch vụ hiện hành, tài liệu giáo dục chung không được dùng làm căn cứ cho quyết định cụ thể. Bốn ca S12–S15 cuối đều thiếu căn cứ và có context bằng chứng rỗng. Raw review/nguồn vẫn được lưu trong trace nghiên cứu để kiểm tra.

## Giữ nguyên yêu cầu dữ liệu

- 33 tài liệu nguyên bản = 33 vector native Cohere embed-v4.0, 1536 chiều.
- Collection: `asd_fulltext_33_20261030_26eb017efca5`.
- Space: `cohere4_whole_1536_e83c596b9070`.
- Không nhúng lại tài liệu, không chia vector theo đoạn, không thay nội dung nguồn hoặc database.
- ID đoạn trong request chỉ phục vụ đọc/trích dẫn. Không ghi chúng thành chỉ mục embedding; không dùng `index_preview.jsonl` cũ.
- Bảy tệp cấu hình/retriever/nhãn cũ được bảo vệ vẫn khớp hash; 132 tệp trong manifest nguồn vẫn nguyên.
- Snapshot trước/sau còn kiểm tra các bảng/collection khác quan sát được trong database hiện tại. Con số 33 chỉ nói về collection đang dùng, không phải tổng tất cả hàng lịch sử trong database.

## Kết quả thật và cách hiểu

| Kiểm tra | Kết quả |
|---|---|
| Kiểm thử code, tokenizer, truy xuất và guard | 84 đạt, 0 lỗi, 0 bỏ qua |
| 15 câu phát triển, run cuối | 15/15 trace hợp lệ; 12/15 trạng thái khớp nhãn AI sơ bộ |
| 5 câu riêng, run cuối | 5/5 trace hợp lệ; 4/5 trạng thái khớp nhãn AI sơ bộ |
| Nguồn dự kiến có trong top 5 ở 16 câu có nguồn tham chiếu | 15/16; bộ nguồn tham chiếu chưa đầy đủ |
| Phát lại 20 câu từ PostgreSQL/cache | Kết quả assessment, policy, context khớp; 0 API |
| 30 câu truy xuất cũ | Thứ hạng và khoảng cách giữ nguyên |
| Dữ liệu/hash | Database, 33 vector và 132 tệp nguồn không thay đổi |
| Sinh câu trả lời người dùng | 0 cuộc gọi |

16/20 là độ khớp trạng thái với nhãn AI sơ bộ; không phải độ chính xác y khoa 80%. Nhãn không được đưa vào prompt reader/verifier. “Trace hợp lệ” nghĩa là qua kiểm tra cấu trúc/xuất xứ/ngân sách, không chứng minh model hiểu đúng.

Năm câu H được chốt trước lần chạy đầu. Sau khi đã đọc kết quả và phát lại, chúng không còn là một bài kiểm tra hoàn toàn chưa quan sát. Không thay nhãn theo output. Hai ca có trạng thái tự động khớp nhãn vẫn được đưa vào hàng chờ vì có dấu hiệu thiếu chi tiết.

## Các thiếu sót đã xác định

| Ca | Kết quả cuối | Vấn đề cần xử lý |
|---|---|---|
| S05 — nhân quả ngủ/hành vi | insufficient | Reader và verifier khác chiều supports/opposes đối với câu hỏi phủ định. Có đoạn nguồn và giới hạn phù hợp; code đang giữ kết quả thận trọng. Cần chuẩn hóa nhu cầu thông tin và mệnh đề để tránh mất câu trả lời phủ định hợp lệ. |
| S07 — AAC cùng lời nói, bảo đảm tăng lời nói | insufficient | Đoạn nói về bảng tranh/thiết bị không tự chứng minh dùng đồng thời lời nói hoặc bảo đảm tiến bộ. Verifier đã chặn suy rộng; cần đọc đúng bằng chứng từng nhu cầu, đồng thời duyệt lại nhãn sơ bộ. |
| S08 — ASI và hoạt động cảm giác khác | insufficient | Có đoạn phân biệt SBI/ASI nhưng hai lượt khác chiều diễn giải câu hỏi. Không đổi chiều tự động; cần sửa biểu diễn claim/stance và kiểm thử ngoài tập phát triển. |
| H03 — tự ngừng thuốc khi thấy đỡ | insufficient | Tìm đúng NIH-NIMH-MEDICATIONS nhưng mục được gửi reader không chứa đoạn tham chiếu [13762,14124). Đoạn thay thế nói về rối loạn vận động do thuốc, không đủ cho câu hỏi. Lỗi chọn phần để đọc, không chứng minh kho thiếu nội dung. |
| H04 — phân biệt ba nhóm biểu hiện ADHD | sufficient, cần duyệt | Đoạn được chọn nêu nhóm biểu hiện và kiểu triệu chứng; cần kiểm tra đã giải thích đủ nghĩa từng nhóm hay mới liệt kê thuật ngữ. |
| H05 — sự đa dạng giữa hai trẻ ASD | sufficient, cần duyệt | Nguồn dự kiến NIH-NIMH-ASD-2025 không nằm trong top 5. Model dùng ASD-CSV-002; cần duyệt mức đủ cho cả biểu hiện, điểm mạnh và nhu cầu. Không lấy nguồn ngoài top 5 để nâng điểm run. |

Các quan sát trên do AI đọc trace/nguồn trong phiên này, không phải quyết định của bác sĩ. Không gán thiếu căn cứ cho cả kho chỉ vì reader chưa chọn đúng đoạn. Ngược lại, việc tài liệu tồn tại trong kho không được dùng để tăng điểm ngữ cảnh chưa thực sự trả về.

Chưa có kiểm thử thật đủ rộng về mâu thuẫn nghiên cứu, injection tinh vi, nhiều lượt hội thoại, tính đầy đủ mọi câu hỏi và người dùng thật. Các kiểm thử mâu thuẫn hiện có chủ yếu là fixture tổng hợp. Phân loại intent của model vẫn có thể sai; guard không phải bộ phân loại an toàn y khoa hoàn chỉnh.

## Lịch sử chạy và lỗi được giữ lại

- `pilot_20261101_222818`: giao thức model tự trích dẫn v1, có lỗi viết lại câu/metadata/scope, HTTP 503 và timeout; đã dừng để sửa giao thức. Không tính các lỗi API như thiếu bằng chứng.
- `pilot_20261101_224335`: thử ba câu với giao thức ID đoạn.
- `pilot_20261101_225057`: 15 câu trước khi thêm verifier/guard; là bằng chứng vì sao kiểm tra ID đúng chưa đủ.
- `pilot_20261101_225326`: holdout đầu, H03 timeout.
- `pilot_20261101_225828`: guard/verifier bản đầu, S13/S14 bị chặn do verifier_schema.
- `pilot_20261101_230115`: H04 HTTP 503 ở verifier.
- `pilot_20261101_230702` và `pilot_20261101_230813`: hai run cuối sau sửa thứ tự guard và chỉ kiểm tra liên kết bằng chứng đủ điều kiện.

Có những lần chạy lại có chủ đích, dùng cache thành công của lần trước. Không có cơ chế tự thử lại API vô hạn. Thống kê “uncached completed calls” trong summary không phải hóa đơn tổng: các request thất bại phía dịch vụ có thể không cung cấp usage. Chưa thiết lập SLA độ trễ.

## File tạo/sửa và vận hành

File mới chính là `rag/semantic_reader.py`, `rag/read_evidence.py`, `deployments/semantic_reader.json`, `tests/test_semantic_reader.py`, hai công cụ trong `scripts/evaluation/` và hai bộ câu hỏi/nhãn mới. `rag/evidence.py` thêm reviewer model; `rag/evidence_pipeline.py` thêm adapter tùy chọn và trace. Retriever/tools cũ không sửa. [Manifest](implementation_manifest.json) ghi các artifact và hash.

Reader tự động được bật khi truyền adapter hoặc chạy CLI mới. Không truyền adapter thì pipeline giữ cách nhận review tường minh/chờ như trước. Chatbot cũ không bị chuyển sang model mới.

Chạy lại nghiệm thu, chỉ dùng cache, không cần khóa API:

```powershell
.\.venv-embedding\Scripts\python.exe -B scripts/evaluation/verify_semantic_reader.py
```

Lệnh sẽ dừng nếu thiếu cache, nguồn/config thay đổi hoặc kết quả không khớp; không âm thầm gọi API. PostgreSQL/Docker phải đang chạy.

Cách chạy câu mới, cấu hình khóa, budget và trace ở [hướng dẫn reader](../../rag/README_SEMANTIC_READER.md). Không in khóa ra console hoặc đưa vào báo cáo. Trace/cache có câu hỏi và nguồn, nên cần quản lý truy cập khi có dữ liệu người thật.

Bản module cũ để quay lại nằm trong `previous_evidence_code.json`. Có thể bỏ adapter để ngừng reader NIM mà không sửa database.

## Thứ tự nên làm tiếp

1. Sửa biểu diễn claim/stance, kiểm tra đủ từng nhu cầu và cơ chế chọn mục đọc; dùng S05/S07/S08/H03 làm ca phát triển. Không chỉnh nhãn chỉ để nâng tỷ lệ khớp.
2. Duyệt hàng chờ cùng người có chuyên môn; bổ sung câu hỏi hoàn toàn mới về phủ định, giới hạn quần thể, câu nhiều yêu cầu, mâu thuẫn và ngoài phạm vi. Đánh giá tách retrieval, chọn mục, đọc/diễn giải và quyết định an toàn.
3. Khi reader đạt các tiêu chí đã chốt trên tập mới, nối tầng trả lời tiếng Việt có dẫn nguồn. Chấm riêng tính đúng, đầy đủ, câu–nguồn và cách xử lý thiếu/mâu thuẫn; sau đó mới tích hợp giao diện/agent cho người dùng.

Kho nguồn đã đối chiếu phục vụ nghiên cứu; chưa có thẩm định lâm sàng độc lập. Phiên này hoàn tất mốc reader và nghiệm thu kỹ thuật, chưa hoàn tất hệ thống tư vấn y khoa.
