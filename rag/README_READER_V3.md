# Reader v3: đọc bằng chứng từ tài liệu gốc

Reader v3 chuẩn bị ngữ cảnh có nguồn cho RAG. Nó chưa sinh câu trả lời tư vấn cho người dùng. Kho PostgreSQL vẫn là 33 tài liệu nguyên văn với 33 vector Cohere; không nhúng lại hoặc sửa bản gốc.

## Ba việc model thực hiện

1. Lập kế hoạch câu hỏi: tách nhu cầu được hỏi, giữ phạm vi và mệnh đề cần kiểm chứng.
2. Chọn các mã đoạn có thật trong phần nguồn được gửi đọc. Đây là ứng viên, chưa được coi là bằng chứng.
3. Kiểm tra từng liên kết nhu cầu–đoạn, mức đầy đủ và các mã đoạn thực sự dùng để chứng minh.

Câu hỏi có/không dùng một mệnh đề cố định. `affirms`/`refutes` nói về mệnh đề ấy, tránh việc một lượt trả lời câu hỏi còn lượt kia phủ định cách đặt câu. Câu hỏi giải thích dùng `explains`, không gán chiều đúng/sai.

`direct` không tự đồng nghĩa đủ: nếu đoạn chỉ giải thích được một phần, code chuyển thành hỗ trợ gián tiếp để assessment giữ mức một phần. Nhu cầu thiếu vẫn bắt buộc; không được bỏ để làm kết quả thành đủ.

## Nội dung gốc và metadata

Model chọn/kiểm tra chỉ nhận đoạn gốc có ID, vị trí và hash. Ghi chú biên soạn về chất lượng, tuổi hoặc giới hạn không được đưa vào hai lượt này làm bằng chứng.

Metadata tên/tác giả/tổ chức/link/ngày vẫn nguyên trong database và được chương trình gắn lại để truy nguyên. Không xóa metadata của bộ dữ liệu.

Mỗi item có một gói ngữ cảnh: đoạn chính, phần liên quan trong cùng mục/mở đầu mục cha và các đoạn giới hạn được chọn rõ ràng. Verifier phải khai báo `support_passage_ids` thuộc gói của item, có đoạn chính; các mục so sánh được gộp rõ ràng theo cùng nhu cầu và cùng nguồn. Ngữ cảnh bổ sung được giữ trong context cuối; ID ngoài gói bị chặn. Chương trình lấy nguyên văn bằng vị trí gốc và đưa các đoạn chứng minh vào chú thích bằng chứng cuối.

Đây là kiểm soát xuất xứ và phạm vi dữ liệu đầu vào. Nó chưa chứng minh mọi diễn giải của model đúng về y khoa.

## Chọn nội dung và giữ điều kiện

Từ khái niệm tiếng Anh của kế hoạch câu hỏi, code xếp ưu tiên các mục nguyên vẹn. Bộ chọn xét cả phần mở đầu của mục cha và mục con. Nếu phải giữ phần điều kiện nhưng cả đơn vị vượt ngân sách thì bỏ đơn vị đó, ghi lý do; không cắt riêng kết quả khỏi điều kiện.

Một tài liệu đủ ngân sách có thể được gửi toàn bộ. Đoạn/mục trong request chỉ dùng đọc/trích dẫn; chúng không trở thành vector mới hoặc thay thế tài liệu gốc.

Mỗi cặp đoạn–nhu cầu có annotation riêng. Cùng một đoạn có thể hỗ trợ một nhu cầu và bác bỏ mệnh đề khác mà không ghi đè lẫn nhau. Việc này không biến một nguồn thành nhiều nguồn độc lập.

## Lỗi, giới hạn và cache

- HTTP, timeout, thiếu quyền API hoặc JSON không hợp lệ là lỗi thực thi, không phải kết luận thiếu kiến thức.
- Không tự thử lại lỗi mạng/HTTP. Việc chạy lại thủ công tạo run mới, giữ run cũ và dùng lại cache thành công.
- Có tối đa một lượt sửa schema kế hoạch câu hỏi và một lượt chọn ID, cấu hình `max_plan_schema_repairs=1`, `max_selection_repairs=1`. Model được yêu cầu chọn lại trong danh sách ID hợp lệ; code không đoán/fuzzy-map ID. Vẫn sai thì dừng.
- Nếu bất kỳ cờ nào nói không có bằng chứng, code chỉ hạ mức và ghi normalization; không sửa thành bằng chứng tích cực. Nhận định không trỏ tới đoạn chính bị loại khỏi bằng chứng; liên kết model tự thêm không được cộng điểm.
- Yêu cầu chẩn đoán/kê liều cá nhân, dữ liệu dịch vụ hiện hành hoặc kết luận pháp lý địa phương dừng sau bước lập kế hoạch: không đọc đoạn liều thuốc như căn cứ cho quyết định đó.
- Guard intent vẫn phụ thuộc phân loại của model. Các kiểm tra hiện tại không phải chứng nhận an toàn lâm sàng.

Câu mới thường cần một vector câu hỏi Cohere và ba lượt NIM; đôi khi có thêm một lượt sửa kế hoạch và một lượt chọn lại ID. Câu đã cache không gọi lại provider. Chưa có SLA độ trễ; đã gặp HTTP 503 và timeout.

## Các file

| File | Vai trò |
|---|---|
| `rag/semantic_reader_v3.py` | Kế hoạch câu hỏi, chọn mục, gói nguồn, kiểm tra ID chứng minh, chuyển thành review. |
| `deployments/semantic_reader_v3.json` | Budget đọc 32.768, đầu ra tối đa 3.072, biên 512; ngân sách mỗi nguồn 4.800; không chứa khóa. |
| `rag/evidence.py` | Giữ riêng annotation của mỗi cặp đoạn–nhu cầu khi dùng giao thức v3. V2 giữ hành vi cũ. |
| `rag/context.py` | Giữ mệnh đề, kết luận và nguyên văn chứng minh theo từng nhu cầu trong context. Đếm token của payload cuối. |
| `rag/read_evidence.py` | CLI mặc định v3; có thể chọn v2 để đối chiếu. |
| `scripts/evaluation/evaluate_reader_v3.py` | Chạy câu hỏi thật, lưu trace, lỗi theo stage và số liệu tìm nguồn/chọn mục/assessment riêng. |
| `scripts/evaluation/verify_reader_v3.py` | Nghiệm thu từ cache, đối chiếu PostgreSQL, trích dẫn, bản v2 và 30 thứ hạng cũ; không gọi API. |
| `tests/test_semantic_reader_v3.py` | Các ca kiểm thử tổng hợp về phủ định, thiếu nhu cầu, giới hạn, scope chéo nguồn, metadata và ID giả. |

Các bộ `reader_v3_development` và `reader_v3_holdout` là bộ hồi quy sau khi đã được dùng phát hiện lỗi. `reader_v3_final_holdout` gồm năm câu chốt sau khi siết đầu vào nguồn gốc, trước lần gọi model đầu tiên. Nhãn đều do AI đọc nguồn, chưa thẩm định lâm sàng độc lập; không đưa nhãn vào prompt.

Chỉ số giao nhau với mục tham chiếu không đồng nghĩa model đã được gửi toàn bộ mục. CSV phân biệt `reference_span_overlap_sent` với `reference_units_fully_sent`. Nguồn có trong kho nhưng không có trong kết quả thực tế không được dùng để nâng điểm run.

## Cách chạy

Tại E:/AI4LIFE/ASD_AGENT, với PostgreSQL đang chạy:

```powershell
.\.venv-embedding\Scripts\python.exe -B -m rag.read_evidence "Khi thấy triệu chứng đã đỡ, gia đình có nên tự dừng thuốc đang được bác sĩ kê cho trẻ không?" --trace reports/my_reader_trace.json
```

Câu trên đã có cache sau đợt đánh giá. Câu mới cần `COHERE_API_KEY` hoặc `--cohere-key-file` là một file dotenv đúng định dạng, hoặc `--prompt-cohere-key` nhập ẩn. Không dùng khóa NVIDIA để gọi Cohere. Tệp .env hiện tại của dự án có thể là YAML cấu hình NIM, không tự coi đó là dotenv Cohere.

NIM dùng `NVIDIA_API_KEY` hoặc `--nvidia-key-file`; mặc định đọc đúng entry model chat đã có trong Continue config. Không sao chép giá trị khóa vào báo cáo.

Đối chiếu bản v2:

```powershell
.\.venv-embedding\Scripts\python.exe -B -m rag.read_evidence "Câu hỏi đã có cache v2" --reader-version v2 --trace reports/v2_trace.json
```

Từ Python:

```python
from rag.evidence_pipeline import EvidencePipeline
from rag.semantic_reader_v3 import AtomicNeedsReader
pipeline = EvidencePipeline()
pipeline.semantic_reader = AtomicNeedsReader(counter=pipeline.counter)
trace = pipeline.prepare(question)
# Xem assessment_after_selection, medical_policy_after_selection,
# context_selection và các support_passage_ids.
# generation_enabled vẫn False.
```

Token được đếm bằng tokenizer/chat template NVIDIA chính thức đã ghim; không suy từ ký tự. Token thực ở endpoint được lưu để đối chiếu từng request; khớp trên mẫu thử không bảo đảm mọi payload tương lai.

Bỏ adapter hoặc chọn CLI v2 để trở về cách đọc trước; không cần đảo migration/database. Nguồn, vector và cấu hình retriever được giữ nguyên.

Tham chiếu kỹ thuật: [NVIDIA API](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-ultra-550b-a55b-infer). Kết quả và phần còn thiếu nằm trong báo cáo bàn giao của đợt reader_refinement.

[Báo cáo bàn giao và kết quả cuối](../reports/reader_refinement_20261101_232742/BAN_GIAO_CAI_THIEN_READER_V3.md).

Sau lượt sửa schema kế hoạch, neo câu hỏi phối hợp được phép đối chiếu theo thứ tự từ thực và giữ nguyên khoảng văn bản gốc cùng mọi điều kiện xen giữa. Không áp dụng cách đối chiếu này cho ID hoặc trích dẫn nguồn.

Assessment: sufficient = ?? c?n c? theo c?c nh?n ??nh ?? ki?m tra; partially_sufficient = h? tr? m?t ph?n; insufficient = ch?a c? ?? c?n c? ?? x?c minh trong ng? c?nh th?c t?; conflicting = c? b?ng ch?ng m?u thu?n theo c?ng m?nh ??. Nh?ng tr?ng th?i n?y kh?ng ch?ng nh?n ??ng y khoa ho?c kh?ng ??nh to?n b? kho thi?u th?ng tin.
