> Tài liệu này mô tả mốc v2 lịch sử. CLI hiện mặc định v3; xem [hướng dẫn v3](README_READER_V3.md). Thêm --reader-version v2 để đối chiếu hành vi cũ.

# Reader ngữ nghĩa NVIDIA NIM — nghiên cứu nội bộ

Luồng: câu hỏi → retriever PostgreSQL/Cohere → chọn phần nguồn → NVIDIA chọn mã đoạn và quan hệ bằng chứng → chương trình lấy nguyên văn/vị trí → assessment/policy → context có ngân sách.

Giữ nguyên 33 tài liệu/33 vector, collection/profile và mã retriever. Đoạn chỉ tồn tại trong request/trace, không được nhúng hoặc ghi vào database.

## File chính

| File | Vai trò |
|---|---|
| rag/semantic_reader.py | NIM client/cache, token budget đọc, chọn phần nguồn, giải mã và xác thực mã đoạn. |
| rag/read_evidence.py | CLI reader tự động hoặc kiểm tra token endpoint. |
| rag/evidence.py | Thêm reviewer model_semantic_review, không biến thành thẩm định lâm sàng. |
| rag/evidence_pipeline.py | Nhận adapter semantic_reader, xác minh nguồn trước API và tái sử dụng hai tầng cũ. |
| deployments/semantic_reader.json | Endpoint/model, protocol, timeout và budget; không có khóa. |
| tests/test_semantic_reader.py | Kiểm thử source/quote/ID/metadata, provider/cache và hồi quy giao thức. |
| scripts/evaluation/evaluate_semantic_reader.py | Pilot có nhãn tách khỏi model, trace/CSV/lỗi và đối chiếu dữ liệu trước/sau. |
| evaluation/semantic_reader_v1/ | 15 câu phát triển, đã dùng để sửa giao thức; không gọi là tập chưa thấy sau sửa. |
| evaluation/semantic_reader_holdout_v1/ | Năm câu chốt trước khi chạy, không dùng sửa prompt; nhãn AI, chưa duyệt lâm sàng. |

## Vì sao chọn mã đoạn

Pilot đầu phát hiện model viết lại câu nguồn hoặc trích metadata như nguyên văn. Bộ kiểm tra đã chặn và giữ báo cáo lỗi.

Protocol vận hành `passage_ids_v2` chỉ cho model chọn ID đoạn tồn tại trong phần nguồn đã đọc. Code ánh xạ ID sang source/hash/[start,end) rồi lấy nguyên văn. Không nhận câu trích do model viết, ID giả, metadata làm bằng chứng, scope từ nguồn khác hoặc ID trùng để tăng số bằng chứng.

Mỗi đoạn là khối văn bản gốc; bảng HTML giữ nguyên. Phần vượt budget bị loại nguyên đơn vị và ghi lý do, không âm thầm cắt đầu/đuôi. Toàn văn vẫn nguyên trong database. Chọn đoạn đọc không chứng minh đã đọc hết nguồn hay tìm hết bằng chứng.

ID/quote đúng chỉ chứng minh xuất xứ. Model vẫn có thể hiểu sai, bỏ sót yêu cầu, chọn đoạn không đủ hỗ trợ hoặc so sánh sai quần thể. Những phần đó cần đánh giá ngữ nghĩa/lâm sàng riêng.

## Model và token

Model: `nvidia/nemotron-3-ultra-550b-a55b`, endpoint HTTPS NVIDIA cố định. Dùng lại tokenizer/chat template chính thức đã ghim với `enable_thinking=false`.

Ngân sách đọc 32.768 token, tối đa 2.800 token tăng thêm mỗi nguồn, chừa 1.536 token đầu ra và biên an toàn 512. Đếm toàn request JSON thật; không suy từ ký tự.

Sau request, đối chiếu `usage.prompt_tokens` thực và local, lưu delta. Nếu actual usage/reservation vượt budget dự án, review bị loại. Khớp ở các mẫu thử không bảo đảm mọi payload tương lai.

API chỉ sinh JSON review, chưa sinh tư vấn cho người dùng. HTTP lỗi/timeout/JSON sai/ID không hợp lệ được tách riêng, không biến thành “thiếu nguồn”, không tự lặp request.

Cache chứa request/response để audit nhưng không chứa khóa hoặc reasoning ẩn. Trace có câu hỏi và phần nguồn; cần quản lý truy cập nếu dùng dữ liệu người thật. Các mẫu injection rõ ràng được cách ly, prompt coi nguồn là dữ liệu; chưa chứng minh chống được mọi injection.

Review mang `model_semantic_review_not_independent_clinical_validation`. Chẩn đoán cá nhân, liều thuốc, quyền lợi địa phương hoặc giá hiện hành có thêm yêu cầu server không được đáp ứng chỉ bằng tài liệu giáo dục chung. Phân loại intent của model vẫn có thể sai; không coi đây là chứng nhận an toàn lâm sàng.

## Khóa và cách chạy

Cohere dùng vector câu hỏi đúng không gian cũ: `COHERE_API_KEY` hoặc `--cohere-key-file deployments/cohere.env`. Câu đã cache không gọi Cohere lại.

NVIDIA dùng `NVIDIA_API_KEY` hoặc `--nvidia-key-file`. Khi không chỉ định, lấy đúng entry model chat trong `C:/Users/Admin/.continue/config.yaml`. Không lấy entry embedding khác, không gửi khóa Cohere sang NVIDIA hoặc lưu khóa vào repo.

Từ E:\AI4LIFE\ASD_AGENT:

```powershell
.\.venv-embedding\Scripts\python.exe -B -m rag.read_evidence "Con chưa nói được nhiều. Ngoài việc tập nói, có cách nào để con diễn đạt nhu cầu bằng tranh hoặc thiết bị không?" --reader-version v2 --trace reports/reader_example.json
```

Câu trên đã có cache sau pilot. Câu mới thêm file khóa Cohere hoặc `--prompt-cohere-key`. CLI in assessment/policy/usage, không tạo tư vấn. Chỉ ghi trace khi chỉ định đường dẫn.

Kiểm tra endpoint/token bằng JSON nhỏ:

```powershell
.\.venv-embedding\Scripts\python.exe -B -m rag.read_evidence --calibrate
```

Python:

```python
from rag.evidence_pipeline import EvidencePipeline
from rag.semantic_reader import NimEvidenceReader
pipeline = EvidencePipeline()
pipeline.semantic_reader = NimEvidenceReader(counter=pipeline.counter)
trace = pipeline.prepare(question)
# Không truyền nhãn kỳ vọng cho reader.
# Kiểm tra assessment_after_selection, policy và context_selection.
# generation_enabled vẫn false.
```

Kiểm thử:

```powershell
.\.venv-embedding\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv-embedding\Scripts\python.exe -B scripts/evaluation/evaluate_semantic_reader.py --max-cases 3
```

Mỗi lần chạy tạo thư mục mới; giữ riêng kết quả trước sửa. Không sửa nhãn theo output để tăng điểm.

## Quay lại và bước sau

Không truyền adapter semantic_reader thì EvidencePipeline giữ review tường minh/chờ như trước. PostgresRetriever/RAGTools nguyên vẹn; không cần đảo migration. Bản module cũ nằm trong báo cáo triển khai.

Duyệt claim/đoạn/ngữ cảnh với người có chuyên môn, bổ sung mâu thuẫn và câu ngoài phạm vi. Khi reader đạt yêu cầu mới nối model trả lời tiếng Việt có dẫn nguồn và chấm riêng tính đúng, đầy đủ, trích dẫn, từ chối.

Tham chiếu: [NVIDIA API](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-ultra-550b-a55b-infer), [model card](https://build.nvidia.com/nvidia/nemotron-3-ultra-550b-a55b/modelcard).

## Kiểm tra mức hỗ trợ và guard sau pilot

Có thêm lượt verifier kiểm tra từng liên kết claim–đoạn nguồn. Verifier chỉ được giữ hoặc hạ mức hỗ trợ, không nâng bằng chứng từ gián tiếp thành trực tiếp. Liên kết bị bỏ sót hoặc output không hợp lệ làm review bị chặn.

Verifier vẫn dùng cùng model NVIDIA, nên không phải người duyệt độc lập hay chứng nhận lâm sàng. Cơ chế này giúp phát hiện một số suy quá mức; không bảo đảm hiểu đúng mọi đoạn. Trace lưu riêng output reader ban đầu, các hạ mức và token usage của verifier.

Server chuyển bằng chứng cho quyết định chẩn đoán/liều thuốc cá nhân, quyền lợi pháp lý địa phương và dữ liệu dịch vụ hiện hành thành nội dung chỉ liên quan, không dùng làm căn cứ cho quyết định. Vì vậy các đoạn có liều thuốc không được đưa vào context tư vấn cho yêu cầu kê liều cá nhân. Nguồn nguyên bản trong database và trace nghiên cứu vẫn giữ nguyên để đối chiếu.

Các ca không có item không gọi verifier. Ca có item thường có thêm một request NIM, có cache riêng. Tổng số gọi reader và verifier được báo cáo tách biệt. Không có cơ chế tự thử lại lỗi mạng; một lần chạy lại có chủ đích được ghi thành run mới và giữ run lỗi cũ.

## Kết quả bàn giao 01/11/2026

[Báo cáo đầy đủ](../reports/semantic_reader_20261101_111654/BAN_GIAO_READER_NGU_NGHIA.md) ghi 84 kiểm thử đạt, 20/20 trace hợp lệ, kiểm tra lại dữ liệu/hash và giới hạn thực tế. 16/20 trạng thái khớp nhãn AI sơ bộ không phải độ chính xác lâm sàng.

S05/S08 còn khác chiều diễn giải câu phủ định; S07 chưa có đủ đoạn hỗ trợ nhu cầu; H03 chọn thiếu đoạn nguồn. H04/H05 cũng được đưa vào hàng chờ duyệt độ đầy đủ. Chưa bật tầng trả lời người dùng.

Chạy nghiệm thu từ cache, không gọi API và không cần khóa:

```powershell
.\.venv-embedding\Scripts\python.exe -B scripts/evaluation/verify_semantic_reader.py
```

PostgreSQL phải đang chạy. Lệnh dừng nếu thiếu cache hoặc dữ liệu/config/kết quả thay đổi. Đây là công cụ kiểm tra kỹ thuật, không tự chấm đúng y khoa.
