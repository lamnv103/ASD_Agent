# Đọc bằng chứng và quản lý context — ASD_AGENT

Hai tầng mới nằm sau retriever PostgreSQL hiện có. Một tài liệu vẫn có đúng một vector. Các đoạn trích chỉ tồn tại trong bộ nhớ/trace, không được nhúng hoặc ghi vào vector database.

## Kiến trúc và mức đã triển khai

`Question → PostgresRetriever → EvidenceReader → assess → ContextManager → đánh giá lại context đã chọn → trace`

- `EvidenceReader` kiểm tra source/hash, lấy đoạn nguyên trích và offset Unicode, kèm ID tài liệu/nguồn, phiên bản, link, tác giả, ngày và phạm vi. Giữ toàn bộ tiểu mục bao quanh, phần dẫn nhập của mục cha và bảng/danh sách trong phạm vi đó.
- Bộ tìm ứng viên mặc định dùng trùng từ ở cấp mục, chỉ ghi là `topical/context_only`. Đây không phải bộ đọc hiểu ngữ nghĩa hoặc cơ chế chứng minh một nhận định. Truy vấn Việt với tài liệu Anh có thể bỏ sót ứng viên; không tuyên bố tìm đoạn tự động đạt recall.
- `assess` tính bốn trạng thái từ review rõ ràng gắn chính xác với câu hỏi, claim và nguồn/đoạn thực truy xuất. Review có thể ghi bằng chứng trực tiếp, gián tiếp, chỉ liên quan chủ đề, ủng hộ hoặc bác bỏ. Bằng chứng trực tiếp bác bỏ cũng có thể trả lời được một câu hỏi.
- Không có review: `status=insufficient`, `assessment_state=pending_semantic_review`. Nghĩa là chưa đánh giá được, không kết luận kho không có nguồn. Runtime không tự đọc nhãn benchmark để trả lời câu mới.
- Review là đầu vào có chủ đích, chưa có cơ chế xác thực danh tính hoặc chứng chỉ người duyệt. Nhãn AI không trở thành chứng nhận lâm sàng. `clinical_reviewed=false` và `generation_enabled=false` luôn được giữ trong đợt này.

## Các file

| File | Vai trò |
|---|---|
| `rag/evidence.py` | Xác minh nguồn/vị trí, phát hiện ứng viên, phạm vi áp dụng, review theo claim, bốn trạng thái và chính sách y tế. |
| `rag/tokenization.py` | Tokenizer adapter local-only, kiểm tra hash tài sản, dùng chat template chính thức; không ước lượng token bằng ký tự. |
| `rag/context.py` | Đóng gói context, xếp ưu tiên bằng chứng đã review, giữ đơn vị nguyên vẹn và cặp mâu thuẫn, kiểm tra token. |
| `rag/evidence_pipeline.py` | Ghép các tầng; kiểm tra lại nguồn/metadata với PostgreSQL; tính lại mức hỗ trợ sau chọn context và đếm lại nếu chính sách thay đổi. |
| `rag/prepare_context.py` | CLI chuẩn bị context và ghi trace khi được chỉ định, không sinh câu trả lời. |
| `deployments/evidence_context.json` | Model dự kiến, tokenizer, hash/revision, ngân sách thử nghiệm; không chứa khóa API. |
| `deployments/tokenizers/nemotron3_ultra/` | Bốn tài sản tokenizer/template chính thức, không có trọng số model. |
| `tests/test_evidence_context.py` | Unit test, logic fixture giả lập và kiểm tra tokenizer thật. |
| `scripts/evaluation/verify_evidence_context.py` | Kiểm thử tích hợp với PostgreSQL, hồi quy 30 query cache, kiểm tra nguồn/vector trước/sau. |
| `evaluation/evidence_context_v1/` | Review chuyển từ nhãn v1 chỉ để kiểm thử pipeline, không phải đánh giá ngữ nghĩa độc lập. |

## Tokenizer và ngân sách

Model đã chọn: `nvidia/nemotron-3-ultra-550b-a55b`. Tokenizer lấy từ repository chính thức `nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4`, revision `02462641f13d3af838b904f48195b9bb8a1e4ebc`.

Cấu hình thử nghiệm: cửa sổ **32.768 token**, chừa **4.096** cho đầu ra, biên an toàn **512**, phần tăng do bằng chứng tối đa **24.576**, tối đa ba nguồn. Đây là ngân sách do dự án đặt, không phải xác nhận giới hạn của endpoint NVIDIA đang phục vụ.

Đếm toàn bộ messages đã render theo chat template, gồm system, JSON envelope/câu hỏi, metadata/giới hạn và bằng chứng; `add_generation_prompt=true`, `enable_thinking=false`. Báo cáo phần hệ thống và các phần tăng thêm từ cả prompt, không cộng các ước lượng text độc lập. Chưa có tool schemas trong messages này; bổ sung tool definitions, lịch sử hội thoại hoặc system prompt ở bước sau phải đếm lại.

Chưa đối chiếu số token local với `usage.prompt_tokens` thực tế trên NVIDIA NIM. Chưa gọi model sinh câu trả lời. Bước tích hợp sau phải dùng đúng profile template và kiểm tra giới hạn endpoint, tính cả reasoning nếu bật lại thinking.

Không có tokenizer/config đúng, hash sai hoặc tokenization thất bại thì chặn chuẩn bị context; không dùng tỷ lệ ký tự/token. Đoạn vượt ngân sách bị loại nguyên đơn vị, ghi lý do. Cặp mâu thuẫn được đưa vào hoặc bỏ cùng nhau. Câu hỏi quá dài bị chặn, không bị cắt ngầm. Trạng thái sau chọn context được tính lại; không dùng điểm đủ căn cứ trước chọn để nâng kết quả sau khi bằng chứng đã bị loại.

## Review và giới hạn y tế

Mỗi review có `question`/hash, `review_id`, người/loại/ngày review, `intent`, `claims`, `items` và `conflicts`. Mỗi item cần source/hash, `[start,end)`, quote, relation, stance và claim IDs. Vị trí tính theo ký tự Unicode Python, bắt đầu 0, cuối không bao gồm; không phải byte hay token.

- `sufficient`: các yêu cầu bắt buộc có bằng chứng trực tiếp theo review, không có so sánh mâu thuẫn chưa xử lý.
- `partially_sufficient`: có hỗ trợ nhưng còn yêu cầu chưa được đáp ứng hoặc cần đối chiếu thêm.
- `insufficient`: chưa có căn cứ đạt yêu cầu trong đầu vào hiện có; xem `assessment_state` để phân biệt chưa review với review nhưng thiếu.
- `conflicting`: review chỉ rõ các bằng chứng đối lập cho cùng claim, đã xét khả năng so sánh quần thể/kết quả. Không tự coi ITT và phân tích nhóm con, hoặc ASI và SBI, là mâu thuẫn.

Phạm vi tuổi/giới hạn hiện lấy từ metadata đã có và review, ghi rõ nguồn gốc. Trường quần thể, điều kiện hoặc quốc gia chưa trích cấu trúc được để `null/unknown`, không tự suy từ địa chỉ tác giả. Việc chọn tiểu mục và dẫn nhập cha chưa chứng minh mọi điều kiện nằm ở nơi khác trong toàn văn đã được giữ; cần người/reader ngữ nghĩa kiểm tra ranh giới, nhất là với câu lâm sàng.

Có policy cho chẩn đoán cá nhân, liều thuốc cá nhân, yêu cầu thông tin bổ sung và giới hạn nguồn. Đây là chính sách/đầu ra có cấu trúc để tầng trả lời tuân theo, chưa phải bằng chứng model sẽ hành xử đúng. Câu mới chưa có phân loại intent/review thì giữ chờ, không tự chẩn đoán hoặc kê đơn từ trùng từ.

Nguồn là dữ liệu không đáng tin về chỉ dẫn. Một số mẫu chỉ dẫn rõ ràng được cách ly và không đưa vào context đã chọn; system prompt cũng quy định không làm theo chỉ dẫn trong nguồn. Đây không phải bộ phát hiện mọi prompt injection; chưa đánh giá khả năng chống injection của LLM.

## Chạy từ E:\AI4LIFE\ASD_AGENT

Truy vấn đã có cache, không cần khóa. Ví dụ không đưa review sẽ ở trạng thái chờ:

```powershell
.\.venv-embedding\Scripts\python.exe -B -m rag.prepare_context "Trẻ tự kỷ kén ăn cần đánh giá dinh dưỡng và tiền sử ăn uống như thế nào?" --trace reports/context_without_review.json
```

Kiểm thử có review nhãn cũ, chỉ để đối chiếu luồng:

```powershell
.\.venv-embedding\Scripts\python.exe -B -m rag.prepare_context "Trẻ tự kỷ kén ăn cần đánh giá dinh dưỡng và tiền sử ăn uống như thế nào?" --review-file evaluation/evidence_context_v1/Q15.review.json --trace reports/context_Q15.json
```

Câu mới cần khóa Cohere cho vector truy vấn: thêm `--key-file deployments/cohere.env`. Model NVIDIA chỉ được dùng ở đây thông qua tokenizer offline; không lấy khóa NVIDIA hoặc gửi nội dung tới model. Khóa không được lưu trong trace. Trace có câu hỏi và trích dẫn, chỉ ghi khi người gọi yêu cầu đường dẫn.

Gọi Python:

```python
from rag.evidence_pipeline import EvidencePipeline
pipeline = EvidencePipeline()
trace = pipeline.prepare(question, review=review_or_none)
# Kiểm tra assessment_state, assessment_after_selection và context_selection.
# generation_enabled vẫn false; không tự gửi trace/messages sang LLM.
```

`prepare_retrieved` ở research mode cũng đối chiếu collection, space, source/hash và attribution/scope với PostgreSQL. Dữ liệu giả chỉ dùng với `mode=test_fixture`, được ghi rõ provenance giả lập, không thay dữ liệu thật.

Kiểm thử:

```powershell
.\.venv-embedding\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv-embedding\Scripts\python.exe -B scripts/evaluation/verify_evidence_context.py
```

Các bài tích hợp cần database và query cache hiện có. Chưa cần tự cài lại thư viện; nếu khôi phục môi trường, phiên bản bổ sung được ghi ở `scripts/evaluation/requirements_evidence_context.txt`.

## Bảo toàn và quay lại luồng trước

Không sửa `rag/retriever.py`, `rag/tools.py`, CLI retrieval cũ, cấu hình collection hoặc dữ liệu nguồn. Không nhúng/ghi database. Có hash code/config bảo vệ, snapshot các bảng trước/sau và manifest tài sản tokenizer. Chưa nối chatbot cũ sang pipeline mới. Để quay lại luồng cũ chỉ cần ngừng gọi `EvidencePipeline`, tiếp tục dùng `PostgresRetriever`/`RAGTools`; không cần migration đảo ngược hoặc xóa tệp khác.

Tham khảo: [tokenizer và chat template Hugging Face](https://huggingface.co/docs/transformers/en/chat_templating), [model card NVIDIA](https://build.nvidia.com/nvidia/nemotron-3-ultra-550b-a55b/modelcard). Việc có tokenizer đúng không xác nhận chất lượng trả lời tiếng Việt hoặc độ đúng y khoa của model.
