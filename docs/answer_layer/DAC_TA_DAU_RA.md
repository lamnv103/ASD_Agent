# Đặc tả đầu ra tầng trả lời: `answer_contract_v0.2`

**Trạng thái:** bản nháp để phát triển nguyên mẫu nội bộ, soạn 07/11/2026. **Không phải MVP đã duyệt.** Phạm vi người dùng, nhóm câu hỏi và ngưỡng nghiệm thu vẫn chờ [MVP_SCOPE_DRAFT.md](../MVP_SCOPE_DRAFT.md). Đặc tả kiểm tra: [DAC_TA_KIEM_TRA.md](DAC_TA_KIEM_TRA.md). Rubric chấm: [RUBRIC_CHAM.md](RUBRIC_CHAM.md).

**Đã cài đặt:** `rag/answer_layer.py`, `rag/answer_render.py`, `rag/answer_policy.py`, `rag/answer_sources.py`, `rag/answer_client.py`, `rag/answer.py`. **Câu chữ của mọi mẫu lấy theo `deployments/answer_layer.json`**; các câu trích trong tài liệu này chỉ để minh họa. Cấu hình: `deployments/answer_layer.json`. Kiểm thử: `tests/test_answer_layer.py`.

**Thẩm định chuyên môn để sau.** Mọi mẫu câu, bảng ghi chú, danh sách cụm khẩn cấp và mọi đầu ra đều mang `review_status: "chua_duyet"`. Mọi bản hiển thị ở chế độ phát triển đều bắt đầu bằng dòng "NGUYÊN MẪU NỘI BỘ…". Cấu hình bị từ chối nếu nhãn này bị đổi. **Không dùng làm căn cứ mở pilot.**

### Thay đổi v0.1 → v0.2 (theo review ngày 07/11/2026)

| Điểm | v0.2 |
|---|---|
| P1: nguồn gốc bằng chứng | Trace **không được tin**. `rag/answer_sources.py` dựng chuỗi tin cậy: `deployments/retriever.json` (đang bị khóa hash) → `corpus_sha256` của `documents.json` → `content_sha256` từng nguồn. Mỗi khối phải có hash đúng và văn bản khớp nguồn phát hành; mỗi quote phải bằng `corpus[start:end]`; collection của trace phải trùng. Lệch thì là lỗi hệ thống `catalog_provenance`. Văn bản quote và metadata hiển thị (tên, tác giả, năm, link) lấy từ nguồn phát hành, không lấy từ trace |
| P2: nhãn chưa duyệt | `load_config` từ chối khi **bất kỳ** `review_status` nào khác `chua_duyet`, hoặc khi thiếu nhãn ở: cấp chung, câu miễn trừ, từng mẫu chính sách, khẩn cấp, ghi chú nguồn |
| P3: phạm vi câu trạng thái | Câu `mot_phan`, `khong_du` và câu thiếu ý chỉ nói về "các đoạn đã truy xuất và kiểm tra ở lượt này". `khong_du` nói thêm rằng điều này không có nghĩa cả kho không có thông tin. Mẫu dịch vụ/pháp lý mô tả phạm vi thiết kế của hệ thống, không khẳng định nội dung của kho |
| Client | Thêm 8 kiểm thử với HTTP giả: hình dạng request, lỗi 401/403/429/500, mạng, phản hồi thiếu, cache, `--no-cache`, cache bị sửa, ngân sách token |

### Thay đổi v0 → v0.1 (chốt các điểm mơ hồ)

| Điểm | v0.1 |
|---|---|
| Danh mục | Bỏ trùng theo (nguồn, start, end). Mỗi `quote` được đối chiếu với văn bản khối theo vị trí ký tự; lệch thì là lỗi hệ thống (kiểm trên 23 trace thật: 37/37 khớp). **Không** gửi liên kết bằng chứng ↔ nhu cầu cho model, vì đó là nhận định của reader |
| Trần trạng thái | Bảng cứng ở mục 5. Trạng thái reader lạ → lỗi hệ thống |
| Coverage sau khi loại nhận định | Thận trọng, không gọi thêm: nhu cầu chỉ được tính khi **mọi** nhận định được ghi công đều đạt (đặc tả kiểm tra, mục 3.3) |
| Ghi chú nguồn | Giá trị tạm, `chua_duyet`: CDC-/NIH- → Hoa Kỳ; ghi năm khi cũ hơn 8 năm so với ngày chạy |
| Kiểm tra đầu ra verifier | Thêm mục 3.5 của đặc tả kiểm tra; `evidence_span` phải là chuỗi con nguyên văn của đoạn được trích |
| Khẩn cấp | Đã có bước phát hiện theo cụm từ, chạy trước mọi lượt gọi provider (mục 6) |
| Intent | `unclassified` → mẫu cố định. Intent lạ → lỗi hệ thống |

## 0. Nguyên tắc

1. **Model không quyết định nguồn.** Chương trình lập danh mục bằng chứng hợp lệ. Model chỉ chọn ID trong danh mục. Chương trình kiểm tra rồi mới đổi sang số hiển thị.
2. **Đơn vị kiểm tra là nhận định**, không phải câu văn hay đoạn văn. Mỗi nhận định là một câu tiếng Việt hoàn chỉnh, tự đứng được, gắn với bằng chứng và nhu cầu.
3. **Render tất định.** Bản hiển thị được ghép từ các nhận định đã qua kiểm tra và các mẫu cố định. Sau khi kiểm tra không còn bước model nào viết lại nội dung.
4. **Trạng thái do chương trình tính** từ các nhận định còn hợp lệ. Model chỉ đề xuất trạng thái để ghi log.
5. Tự nhiên đến từ **cách viết từng nhận định** (giọng ấm, câu ngắn, thuật ngữ nhất quán), không đến từ việc nới căn cứ.

## 1. Phạm vi phát triển tạm thời

| Dùng để | Câu hỏi | Ghi chú |
|---|---|---|
| Hồi quy cơ chế | 23 trace reader v3: 14 `sufficient`, 3 `partially_sufficient` (S07, N04, F02), 2 `insufficient` trong phạm vi (H05, N02), 5 bị guard chặn (N09–N12, F05) | Nhiều câu ngoài nhóm A–D (ADHD, thuốc, trầm cảm tuổi teen). Chỉ dùng để thử cơ chế, **không** dùng để khẳng định phạm vi |
| Phát triển nội dung | ~10 câu mới tổng hợp, viết tự nhiên, thuộc nhóm A–D trong bản nháp MVP, không nêu tên nguồn | Không chứa thông tin cá nhân thật. Là dữ liệu phát triển, không phải bằng chứng nghiệm thu |
| Ca có chủ đích | S05, S08 (xem [điều tra 4 ca](../../reports/investigation_20261107/DIEU_TRA_4_CA.md)) | Bắt lỗi đổi mức chắc chắn, thêm ý thuốc, biến mô tả thành khuyến nghị |

## 2. Đầu vào của tầng G (chỉ những thứ này)

Lấy từ kết quả `GuardedEvidencePipeline.prepare()`:

| Trường | Dùng thế nào | Gửi cho model? |
|---|---|---|
| Câu hỏi đã qua guard (`screened text`) | Câu cần trả lời | Có |
| `medical_policy_after_selection.intent`, `.action` | Chọn nhánh: trả lời hay mẫu chính sách | Không (chương trình xử lý) |
| `assessment_after_selection.status` | **Trần** của trạng thái: G không được trả trạng thái cao hơn reader | Không |
| Danh sách nhu cầu (`claims`: `claim_id`, `text`, `required`) | Danh sách đối chiếu tạm thời | Có, chỉ để biết cần trả lời gì, **không phải nguồn** |
| Bằng chứng: mục trong `context_selection.selected_blocks[*].evidence` có `evidence_id` ∈ `selected_evidence_ids` | Đơn vị được phép trích dẫn | Có: chỉ nguyên văn `quote` + tên tài liệu + loại nguồn + năm |
| `metadata`, `applicability` của khối | Render nguồn và ghi chú điều kiện tất định | Chỉ tên, loại nguồn, năm |

**Không đưa vào tầng G như nguồn:**

- văn bản khối nằm ngoài các `quote` đã duyệt;
- `ancestor_introductions`, `additional_source_passages`;
- `stance`, `relation`, `reason` của reader (đều là nhận định của model);
- `applicability.limitations` (ghi chú quản lý nguồn bằng tiếng Anh; chỉ dùng làm danh mục đối chiếu cho bước kiểm tra và người chấm);
- toàn bộ trace, log, nhãn đánh giá.

Hệ quả đã biết: ở S08, đoạn nói về mức bằng chứng của ASI nằm trong khối nhưng không phải bằng chứng đã duyệt, nên G không được dùng. Đánh đổi này là chủ ý; sẽ xem lại khi có dữ liệu.

## 3. Danh mục bằng chứng

Chương trình tạo danh mục trước khi gọi model:

```json
{"catalog": [
  {"id": "E1", "evidence_id": "ev-d04a51f57d53abbfc066323f", "source_id": "ASD-OA-PMC4271434",
   "start": 38221, "end": 40936, "quote": "<nguyên văn tiếng Anh>",
   "source_label": "Tổng quan nghiên cứu, 2014"}
]}
```

- `E1…En` đánh theo thứ tự xuất hiện của nguồn, rồi theo `start`. Cùng đầu vào phải ra cùng danh mục.
- Model chỉ thấy `id`, `quote`, `source_label`. `evidence_id`, offset và hash được giữ để đối chiếu với PostgreSQL như các tầng trước.
- Danh mục rỗng nghĩa là không có bước gọi model: trả `khong_du` bằng mẫu.

## 4. Đầu ra nội bộ của model

```json
{
  "proposed_status": "du | mot_phan | khong_du",
  "claims": [
    {"claim_id": "c1", "role": "tra_loi_truc_tiep",
     "text": "Chưa. Tổng quan này cho rằng kết luận về tác động của giấc ngủ kém lên hành vi ban ngày vẫn còn sớm và cần nghiên cứu thêm.",
     "evidence_ids": ["E2"], "need_ids": ["n1"]},
    {"claim_id": "c2", "role": "chi_tiet", "text": "…", "evidence_ids": ["E1"], "need_ids": ["n1"]}
  ],
  "gaps": [
    {"need_id": "n2", "topic_vi": "cách phối hợp bảng tranh với lời nói tại nhà"}
  ]
}
```

| Trường | Quy tắc |
|---|---|
| `claims[].text` | Một câu tiếng Việt hoàn chỉnh, tự đứng được (không "Điều này…", "Do đó…" trỏ về câu khác). Chỉ chứa một nhận định nội dung chính. Không chứa URL, số điện thoại, tên thuốc kèm liều, tên tổ chức không có trong nguồn được trích |
| `role` | `tra_loi_truc_tiep` (tối đa 1, đứng đầu) hoặc `chi_tiet` |
| `evidence_ids` | ≥ 1 ID có trong danh mục |
| `need_ids` | ≥ 1 ID có trong danh sách nhu cầu |
| Giới hạn | Tối đa 8 nhận định, mỗi nhận định ≤ 60 từ. **Không** bắt độ dài tối thiểu, **không** bắt phần "điều nên làm tiếp" |
| `gaps[].topic_vi` | Cụm danh từ ≤ 20 từ, chỉ nêu lại phần câu hỏi chưa có căn cứ. Không được chứa nhận định |
| Điều kiện nguồn | Nếu nguyên văn có độ tuổi, nhóm đối tượng, quốc gia, mức chắc chắn hoặc phủ định, nhận định phải giữ lại |

**Không do model viết:** câu mở theo trạng thái, ghi chú bối cảnh nguồn, câu miễn trừ, danh sách nguồn, mẫu chính sách.

## 5. Trạng thái

| Trạng thái | Điều kiện, do chương trình tính sau kiểm tra |
|---|---|
| `du` | Mọi nhu cầu bắt buộc đều **được đáp ứng đủ**, không có phần câu hỏi nào bị bỏ sót, và trạng thái của reader là `sufficient` |
| *(trần theo reader)* | `sufficient` → tối đa `du`; `partially_sufficient` → tối đa `mot_phan`; `insufficient` → `khong_du`, **không gọi model**; trạng thái khác → lỗi hệ thống |
| `mot_phan` | Có ít nhất một nhu cầu bắt buộc được đáp ứng đủ, và còn ít nhất một nhu cầu hoặc phần câu hỏi chưa được đáp ứng |
| `khong_du` | Không còn nhận định hữu ích nào sau kiểm tra, hoặc danh mục bằng chứng rỗng |

- "Được đáp ứng đủ" là do bước kiểm tra đánh giá dựa trên **nội dung** các nhận định đã qua (xem đặc tả kiểm tra, mục 3.3). Chỉ gắn cùng ID nhu cầu thì chưa đủ.
- Danh sách nhu cầu của reader có thể thiếu. Bước kiểm tra đối chiếu thêm câu hỏi gốc. Phần câu hỏi không được nhu cầu nào bao phủ được ghi thành nhu cầu bổ sung chưa đáp ứng.
- Trạng thái của G không được cao hơn của reader: reader `partially_sufficient` thì G tối đa `mot_phan`.
- **Lỗi hệ thống** (lỗi provider, timeout, lỗi schema sau lượt sửa) **không** được hiển thị như `khong_du`. Phải dùng mẫu riêng, không nói "kho không có tài liệu" khi thực tế là hệ thống lỗi.

## 6. Nhánh chính sách: không gọi model sinh câu trả lời

| Intent / action | Mẫu (nháp, ☐ chuyên gia duyệt) |
|---|---|
| `individual_diagnosis` | "Hệ thống không thể xác định một trẻ cụ thể có tự kỷ hay không. Việc này cần chuyên gia được đào tạo đánh giá trực tiếp. Bạn có thể hỏi về thông tin chung, ví dụ: quy trình đánh giá tự kỷ thường gồm những bước nào." |
| `personalized_medication` | "Hệ thống không đưa ra tên thuốc, liều hay cách dùng cho một người cụ thể. Những câu hỏi này cần bác sĩ hoặc dược sĩ đang theo dõi người đó trả lời." |
| `current_services` | "Hệ thống chỉ dùng tài liệu giáo dục và nghiên cứu đã thu thập, không được thiết kế để cung cấp thông tin hiện hành về cơ sở, lịch, chỗ trống, giá hoặc địa chỉ, nên không trả lời câu hỏi này." |
| `scope_legal` | "Hệ thống không đưa ra kết luận pháp lý và không được thiết kế để tra cứu văn bản pháp luật hiện hành." |
| Khẩn cấp / nguy cơ tự hại | Pipeline không có intent khẩn cấp (danh sách intent cố định trong `rag/evidence.py`, đang bị khóa hash). v0.1 thêm `detect_emergency` (`rag/answer_policy.py`): so khớp cụm từ trong config, theo ranh giới từ, chạy **trước guard và trước mọi lượt gọi provider**. Khớp thì chỉ trả chỗ giữ tạm `[CHƯA CÓ NỘI DUNG KHẨN CẤP — chờ quyết định 8…]`, không kèm nội dung khác. Đây là heuristic thiên về bắt nhầm hơn bỏ sót, **không phải bộ phát hiện khủng hoảng đã kiểm chứng**. Không có số điện thoại nào được tự điền. **Vẫn là điều kiện chặn pilot.** |
| `unclassified` | "Hệ thống chưa xác định được loại câu hỏi này nên không đưa ra câu trả lời…" |

- Mẫu không cá nhân hóa theo chi tiết người dùng nhập (tuổi, cân nặng, triệu chứng) và không nhắc lại các chi tiết đó.
- Câu miễn trừ (mục 7) vẫn được thêm vào.

## 7. Render tất định

```
[Câu mở theo trạng thái]   du: (không có) · mot_phan: "Các đoạn tài liệu đã truy xuất và kiểm tra ở lượt này chỉ trả lời được một phần câu hỏi." · khong_du: mẫu mục 7.1
[Nhận định tra_loi_truc_tiep] [1]
[Các nhận định chi_tiet, mỗi câu kèm số nguồn] [1][2]
[mot_phan] "Trong các đoạn đã truy xuất và kiểm tra ở lượt này, chưa có căn cứ trực tiếp về: <topic_vi>; <topic_vi>."
[Ghi chú bối cảnh nguồn — tất định, mục 7.2]
[Câu miễn trừ cố định]
Nguồn:
[1] <tên tài liệu> — <tổ chức hoặc tác giả đầu> (<năm hoặc "không ghi năm">). <link>
    Đoạn được dùng: "<nguyên văn tiếng Anh>"   (có thể mở/thu gọn)
```

- Số hiển thị `[1]`, `[2]` đánh **theo nguồn**, theo thứ tự xuất hiện đầu tiên. Một nguồn có thể có nhiều đoạn bên dưới.
- Chương trình chỉ ghép nhận định theo thứ tự, **không thêm từ nối** ("Tuy nhiên", "Do đó"…), vì từ nối có thể tạo quan hệ suy luận không có trong nguồn.
- Câu miễn trừ có hai dạng (v0.2). Khi có nhận định được trích dẫn: "Đây là thông tin giáo dục chung dựa trên các đoạn tài liệu được trích dẫn, không thay thế việc khám và tư vấn của chuyên gia." Khi không hiển thị nội dung (`khong_du`, mẫu chính sách): "Hệ thống chỉ cung cấp thông tin giáo dục chung, không thay thế việc khám và tư vấn của chuyên gia." Không nói "dựa trên tài liệu được trích dẫn" khi không trích dẫn gì.
- Cùng một đầu vào đã kiểm tra thì phải ra cùng một chuỗi byte.

### 7.1 Mẫu `khong_du`

"Trong các đoạn tài liệu đã truy xuất và kiểm tra ở lượt này, hệ thống chưa có đủ căn cứ để trả lời câu hỏi, nên không đưa ra câu trả lời để tránh suy đoán. Điều này không có nghĩa là toàn bộ kho tài liệu không có thông tin liên quan." Lý do (ví dụ H05): một lượt truy xuất không chứng minh kho không có nguồn; nguồn có thể tồn tại nhưng không được tìm tới. Mẫu không liệt kê nguồn đã đọc nhưng không dùng.

### 7.2 Ghi chú bối cảnh nguồn

Đã kiểm tra trên 23 trace: trường `applicability.country` luôn rỗng, và ngày tháng có nhiều định dạng ("2016", "2016-2-4", "Revised 2024", rỗng). Vì vậy:

| Ghi chú | Cách lấy | Ví dụ |
|---|---|---|
| Bối cảnh quốc gia | Bảng ánh xạ **được duyệt** trong config (CDC, NIH/NIMH/NIDCD → Hoa Kỳ). Không suy từ văn bản | "Nguồn [2] mô tả hệ thống tại Hoa Kỳ." |
| Năm | Năm 4 chữ số đầu tiên trong `ngay_cap_nhat`, nếu không có thì trong `ngay_xuat_ban`. Không tìm được thì ghi "không ghi năm" | "Nguồn [1] xuất bản năm 2014." (chỉ hiện khi cũ hơn ngưỡng, ☐ ví dụ 8 năm) |
| Số nguồn | Đếm nguồn được trích | "Câu trả lời dựa trên 1 tài liệu." |
| Loại nguồn | `loai_nguon` → "nghiên cứu", "thông tin chính thức cho người bệnh", … | Hiện trong danh sách nguồn |

## 8. Ghi log và cache

- Mỗi lần chạy ghi: phiên bản contract, prompt hash, model, token và thời gian **riêng từng bước** (sinh, kiểm tra, sửa, kiểm tra lại), số lượt sửa, nhận định bị loại kèm lý do, trạng thái trước/sau.
- Cache sinh và kiểm tra dùng để phát lại offline như các tầng trước, **chỉ cho câu hỏi tổng hợp không có thông tin cá nhân thật**. Khả năng phát lại không phải lý do lưu dữ liệu người dùng: chế độ phục vụ mặc định không cache, thời hạn lưu theo quyết định 9 của bản nháp MVP.
- Cache của tầng này nằm ở `reports/answer_cache/` và được git bỏ qua. `--no-cache` tắt hoàn toàn việc đọc/ghi cache.
- Khóa NVIDIA chỉ lấy từ biến môi trường `NVIDIA_API_KEY` hoặc file `*.env` riêng. File YAML (cấu hình Continue) và file `.env` ở thư mục gốc bị từ chối. Ở chế độ chạy toàn luồng, reader cũng dùng cùng quy tắc này.
- Code mới đặt trong module mới, không sửa file đang bị khóa hash.

## 9. Việc chưa quyết

| # | Việc | Ai |
|---|---|---|
| 1 | Nội dung bốn mẫu chính sách và câu miễn trừ | Chuyên gia |
| 2 | Bảng ánh xạ quốc gia; ngưỡng năm "cũ" | Chủ dự án + chuyên gia |
| 3 | Bảng thuật ngữ (ASD = "rối loạn phổ tự kỷ", ASI, SBI, AAC…) | Chuyên gia |
| 4 | Nội dung khẩn cấp (quyết định 8) | Chuyên gia; chặn pilot |
| 5 | Có cho dùng văn bản khối ngoài bằng chứng đã duyệt không (ca S08) | Sau khi có dữ liệu bước 4 |
