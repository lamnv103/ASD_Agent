# Đặc tả kiểm tra tầng trả lời: `answer_check_v0.2`

**Trạng thái:** bản nháp để phát triển nguyên mẫu nội bộ, 07/11/2026, đã cài đặt trong `rag/answer_layer.py`. Đi kèm [DAC_TA_DAU_RA.md](DAC_TA_DAU_RA.md).

**Thay đổi v0.1 → v0.2:**

- thêm K-1, kiểm tra nguồn gốc với nguồn phát hành (mục 1);
- nhãn `chua_duyet` được kiểm ở mọi thành phần;
- thêm kiểm thử client với HTTP giả;
- mở rộng kiểm tra đột biến (mục 6).

**Thay đổi v0 → v0.1:**

- mục 3.3: bỏ "gọi kiểm tra lại", vì mâu thuẫn với quy tắc một lượt sửa;
- thêm mục 3.5 (kiểm tra đầu ra verifier);
- mục 4: không gọi verifier khi không nhận định nào qua K1, và nêu rõ điều kiện kích hoạt lượt sửa;
- mục 6: ghi kết quả kiểm thử.

**Nguyên tắc:** kiểm tra **ID hợp lệ** và kiểm tra **nội dung được nguồn hỗ trợ** là hai việc riêng, đo riêng, báo cáo riêng. Đạt kiểm tra tự động không có nghĩa là đúng về y khoa. Kết quả kiểm tra bằng model là tạm thời cho tới khi có người chấm.

## 1. Các tầng kiểm tra

| Tầng | Loại | Kiểm tra gì | Khi trượt |
|---|---|---|---|
| K-1 | Tất định | Nguồn gốc: hash khối, văn bản khối và mọi quote khớp nguồn phát hành theo `deployments/retriever.json`; cùng collection. Metadata hiển thị lấy từ nguồn phát hành | Lỗi hệ thống `catalog_provenance`; không gọi model |
| K0 | Tất định | JSON đúng schema `answer_contract_v0` | Sửa 1 lần (mục 4); trượt nữa → lỗi hệ thống |
| K1 | Tất định | ID và cấu trúc từng nhận định (mục 2) | Đánh dấu nhận định trượt |
| K2 | Model | Nhận định có được đoạn được trích hỗ trợ không (mục 3.1–3.2) | Đánh dấu nhận định trượt |
| K3 | Model + tất định | Nhu cầu và câu hỏi gốc đã được đáp ứng đủ chưa (mục 3.3) | Hạ trạng thái |
| K4 | Tất định | Tính lại trạng thái, render (mục 5) | — |

## 2. K1: kiểm tra tất định từng nhận định

Một nhận định **trượt K1** nếu vi phạm bất kỳ điều nào sau:

1. `evidence_ids` rỗng, hoặc có ID không thuộc danh mục của lượt này.
2. `need_ids` rỗng, hoặc có ID không thuộc danh sách nhu cầu.
3. Có hơn một nhận định `tra_loi_truc_tiep`, hoặc nhận định này không đứng đầu.
4. Dài hơn 60 từ; tổng số nhận định hơn 8.
5. Văn bản chứa URL, email, số điện thoại, hoặc mẫu liều thuốc (số kèm `mg`, `ml`, `viên`, `lần/ngày`…).
6. Nhắc tên tổ chức hoặc tài liệu có trong danh mục nguồn nhưng không thuộc các nguồn mà chính nhận định này trích.
7. Bắt đầu bằng từ nối trỏ về câu khác ("Điều này", "Do đó", "Vì vậy", "Tuy nhiên", "Ngoài ra"…). Danh sách cụ thể đặt trong config.
8. `gaps[].topic_vi` dài hơn 20 từ. Việc topic có chứa nhận định hay không được kiểm ở K2.

Kết quả K1 được báo cáo riêng: **tỷ lệ nhận định có trích dẫn hợp lệ về ID**.

## 3. K2–K3: kiểm tra bằng model

### 3.1 Đầu vào của lượt kiểm tra

Một lượt gọi cho cả câu trả lời, gồm:

- câu hỏi đã qua guard;
- danh sách nhu cầu;
- với mỗi nhận định đã qua K1: văn bản tiếng Việt cùng **nguyên văn tiếng Anh** của các đoạn nó trích (không dùng bản dịch);
- `gaps[].topic_vi`.

Lượt kiểm tra không thấy đề xuất trạng thái của model sinh, lý do của reader, hay nhãn đánh giá.

### 3.2 Kết quả cho từng nhận định

```json
{"claim_id": "c1",
 "support": "supported | partially_supported | not_supported | contradicted",
 "flags": ["added_content", "certainty_changed", "condition_dropped", "negation_flipped",
           "unrequested_medical_content", "recommendation_added"],
 "evidence_span": "<câu nguyên văn tiếng Anh làm căn cứ chính>",
 "explanation": "<ngắn>"}
```

| Flag | Nghĩa | Ví dụ (S05/S08) |
|---|---|---|
| `added_content` | Có ý không có trong đoạn được trích | Thêm "giấc ngủ kém gây chậm nói" |
| `certainty_changed` | Đổi mức chắc chắn: "có thể" thành "chắc chắn", "liên quan" thành "gây ra" | "Khó ngủ gây ra hành vi khó khăn và ngược lại" |
| `condition_dropped` | Bỏ độ tuổi, nhóm đối tượng, quốc gia, thời điểm, loại nghiên cứu | Bỏ "trẻ 4–12 tuổi" của tổng quan ASI |
| `negation_flipped` | Đảo chiều phủ định hoặc khẳng định | "Các hoạt động cảm giác đều là ASI" |
| `unrequested_medical_content` | Thêm thông tin thuốc hoặc điều trị mà câu hỏi không hỏi | Kéo câu melatonin vào S05 |
| `recommendation_added` | Biến mô tả thành lời khuyên hoặc khuyến nghị | "Nên chọn ASI cho trẻ" |

**Nhận định đạt K2** khi và chỉ khi `support = supported` **và** không có flag nào. Kết quả `partially_supported` là trượt; lượt sửa có thể thu hẹp nhận định cho khớp nguồn.

Mỗi `gaps[].topic_vi` cũng được kiểm: nếu chứa nhận định nội dung thì loại.

### 3.3 K3: mức đáp ứng nhu cầu và câu hỏi gốc

Lượt kiểm tra trả thêm:

```json
{"needs": [{"need_id": "n1", "fully_addressed": true, "by_claims": ["c1", "c2"], "missing": ""}],
 "question_parts_uncovered": ["<phần câu hỏi không thuộc nhu cầu nào>"]}
```

- `fully_addressed` chỉ được tính dựa trên **các nhận định đã đạt K1 và K2**. Quy tắc thận trọng: nhu cầu được tính là đáp ứng chỉ khi `fully_addressed=true`, `by_claims` không rỗng, và **mọi** nhận định trong `by_claims` đều đạt và đều gắn `need_id` đó. Chỉ cần một nhận định được ghi công bị loại là nhu cầu thành chưa đáp ứng. **Không gọi kiểm tra lại**: cái giá là đôi khi hạ trạng thái oan, chấp nhận được hơn việc nâng trạng thái oan.
- Mỗi phần trong `question_parts_uncovered` được thêm thành nhu cầu bổ sung **chưa đáp ứng**. Đây là chỗ bù cho việc reader có thể bỏ sót nhu cầu, ví dụ S05: plan bỏ phần tiền đề "khó ngủ có liên quan đến hành vi".
- Chương trình kiểm tra lại tính nhất quán: `by_claims` phải là ID có thật và nhận định đó phải gắn `need_id` tương ứng.

### 3.4 Chọn model kiểm tra

- Khác model **không** đồng nghĩa kiểm tra độc lập. Đó chỉ là biện pháp giảm lỗi tương quan, và phải đo hiệu quả.
- Bản v0 ghi rõ model nào sinh và model nào kiểm tra. Nếu dùng cùng model, báo cáo phải ghi: "Bước kiểm tra dùng cùng model với bước sinh; lỗi có thể tương quan."
- **Đo hiệu quả bằng bộ lỗi cài sẵn.** Từ các nhận định đạt, tạo biến thể có lỗi đã biết (đảo phủ định, bỏ độ tuổi, đổi "liên quan" thành "gây ra", thêm câu thuốc, tráo ID trích dẫn sang đoạn khác). Báo cáo tỷ lệ phát hiện theo từng loại lỗi, kèm tỷ lệ báo nhầm trên các nhận định gốc. Bộ lỗi này là dữ liệu phát triển và không thay thế người chấm.

### 3.5 Kiểm tra tất định đầu ra của verifier

Verifier là một model nên đầu ra của nó cũng phải được kiểm:

| Tình huống | Xử lý |
|---|---|
| Không phải JSON, sai khóa, `support` hoặc `flag` ngoài danh sách, `claim_id`/`need_id` lạ hoặc trùng, `by_claims` chứa ID lạ | **Lỗi hệ thống** (`verifier_output_invalid`); không hiển thị nội dung |
| Thiếu kết quả cho một nhận định đã gửi | Nhận định đó trượt (`verdict_missing`) |
| `evidence_span` ngắn hơn 20 ký tự, hoặc không phải chuỗi con nguyên văn của **một đoạn chính nhận định đó trích** (chỉ chuẩn hóa khoảng trắng và dấu nháy cong) | Nhận định trượt (`span_not_in_cited_evidence`). Bắt được kiểu lỗi "ý có trong lý do của reader hoặc đoạn lân cận, nhưng không có trong đoạn được trích" |
| Thiếu kết quả cho một nhu cầu | Nhu cầu chưa đáp ứng |
| Thiếu `contains_claim` cho một gap | Topic không được hiển thị; dùng câu chung |

## 4. Một lượt sửa

```
sinh → K0 → K1 → K2/K3 → có nhận định trượt hoặc nhu cầu chưa đủ?
   không → K4
   có    → SỬA (1 lần): gửi lại danh mục, các nhận định trượt kèm lý do, nhu cầu chưa đủ
         → K0 → K1 → K2/K3 cho bộ nhận định mới
         → loại mọi nhận định vẫn trượt → K4
```

- Lượt sửa được kích hoạt khi: K0 trượt, **hoặc** có nhận định trượt K1/K2, **hoặc** có nhu cầu bắt buộc vừa chưa được đáp ứng vừa không được khai trong `gaps`.
- Nếu không nhận định nào qua K1 thì **không gọi verifier**. Khi đó topic trong `gaps` chưa được kiểm, nên không hiển thị.
- Chỉ có **một** lượt sửa cho cả câu trả lời. Không lặp.
- Lượt sửa được phép: viết lại hoặc thu hẹp nhận định trượt, bỏ nhận định, thêm nhận định mới cho nhu cầu chưa đủ (vẫn chỉ dùng danh mục cũ).
- Sau lượt sửa, **toàn bộ** bộ nhận định cuối được kiểm tra K1–K3 lại. Lý do: K3 phụ thuộc cả bộ, và nhận định mới chưa từng được kiểm.
- Nếu K0 trượt ở lượt sửa, hoặc provider lỗi: trả **lỗi hệ thống**, không dùng nội dung chưa kiểm.

## 5. K4: tính lại trạng thái

Chỉ dựa trên các nhận định còn hợp lệ sau lượt sửa:

```
hữu ích  = nhận định đạt K1 và K2
đáp ứng  = nhu cầu bắt buộc có fully_addressed=true, chỉ tính từ các nhận định hữu ích
thiếu    = nhu cầu bắt buộc chưa đáp ứng + question_parts_uncovered

nếu hữu ích rỗng hoặc đáp ứng rỗng           → khong_du
nếu thiếu rỗng và reader = sufficient         → du
ngược lại                                     → mot_phan (gaps chỉ gồm topic_vi đã qua kiểm tra; thiếu topic thì dùng câu chung)
```

- **Không bao giờ** giữ nhận định trượt rồi chỉ đổi nhãn thành `mot_phan`.
- Nếu loại nhận định làm mất `tra_loi_truc_tiep`, câu trả lời không có câu mở trực tiếp. Chương trình **không** tự đẩy một nhận định `chi_tiet` lên thay.
- Ghi lại trạng thái do model đề xuất, trạng thái cuối và lý do chênh lệch.

## 6. Kiểm thử tự động bắt buộc trước khi gọi API (bước 2)

Mock model, không gọi provider:

| # | Ca | Kỳ vọng |
|---|---|---|
| 1 | Nhận định trích `E9` không có trong danh mục | Trượt K1, không xuất hiện trong bản render |
| 2 | Nhận định không có `evidence_ids` | Trượt K1 |
| 3 | Mock K2 trả `certainty_changed` cho c2 | c2 bị loại sau lượt sửa nếu vẫn trượt |
| 4 | Mọi nhận định trượt sau lượt sửa | `khong_du`; bản render không chứa văn bản của nhận định nào |
| 5 | Reader `partially_sufficient`, mọi nhận định đạt | Trạng thái tối đa `mot_phan` |
| 6 | K3 trả `question_parts_uncovered` không rỗng | Không được `du` |
| 7 | Lượt sửa trả JSON hỏng | Lỗi hệ thống; không render nội dung |
| 8 | Intent `personalized_medication` | Mẫu chính sách; không gọi model sinh |
| 9 | Danh mục rỗng | `khong_du` bằng mẫu, không gọi model |
| 10 | Render hai lần cùng đầu vào | Cùng chuỗi byte |
| 11 | Nhận định chứa "5 mg" hoặc số điện thoại | Trượt K1 |
| 12 | Nhận định nhắc "CDC" nhưng chỉ trích nguồn NIMH | Trượt K1 |

**Kết quả (07/11/2026):** `tests/test_answer_layer.py` có 30 kiểm thử, đạt 30/30, không gọi provider. Gồm 12 ca trên, cộng thêm:

- kiểm tra đầu ra verifier (`evidence_span` sai, lấy từ đoạn không được trích, thiếu kết quả, ID lạ, flag lạ);
- coverage thận trọng;
- khẩn cấp (kể cả các câu không được báo nhầm: "đánh giá", "từ từ", "tự xoay vòng");
- nhãn `chua_duyet` và việc cấu hình bị từ chối khi nhãn bị đổi;
- quy tắc file khóa;
- lập danh mục từ trace S05 thật (khẳng định câu "longitudinal" trong lý do của reader không nằm trong đoạn được trích).

**Kiểm tra đột biến:** cố tình gài 6 lỗi vào bản sao của code. Test bắt được 5:

- tắt kiểm tra `evidence_span`;
- coverage không thận trọng;
- render cả nhận định trượt;
- chấp nhận JSON hỏng ở lượt sửa;
- bỏ qua nhánh chính sách.

Lỗi không bị bắt là "bỏ trần trạng thái theo reader". Lý do: logic K4 đã chỉ cho `du` khi reader là `sufficient`, nên dòng trần chỉ là phòng thủ thừa, không có đường chạy nào tới nó.

**Cập nhật v0.2 (07/11/2026):** tổng cộng 45 kiểm thử (37 ở `tests/test_answer_layer.py`, 8 ở `tests/test_answer_client.py`), đạt 45/45, không gọi mạng. Thêm:

- nguồn gốc trên trace S05 thật: sửa khối + quote cùng lúc, sửa ngoài quote, sửa hash, sửa offset, đổi collection, giả metadata;
- nhãn chưa duyệt ở từng thành phần;
- phạm vi câu trạng thái;
- client với HTTP giả.

Kiểm tra đột biến lần 2, chạy trong bộ nhớ trên code thật, gài 11 lỗi: lần đầu bắt được 9. Hai lỗi sống sót do test có lỗ hổng thật:

- sửa văn bản khối ngoài quote không bị phát hiện;
- `--no-cache` vẫn ghi đè cache cùng tên mà không bị phát hiện.

Đã thêm test cho hai trường hợp này. Hiện **11/11 lỗi bị bắt**.

## 7. Số liệu báo cáo (bước 3–4)

Báo cáo **riêng** từng dòng, kèm mẫu số. Tách theo nhóm dữ liệu: 23 trace hồi quy, câu mới, cache hay lượt gọi thật.

| Chỉ số | Nguồn đo |
|---|---|
| Nhận định có trích dẫn hợp lệ về ID | K1 |
| Nhận định được nguồn hỗ trợ (theo model) | K2 |
| Nhận định được nguồn hỗ trợ (theo người chấm, trên mẫu) | Rubric |
| Mức đồng thuận model kiểm tra và người chấm | So sánh hai dòng trên |
| Nhu cầu đã đáp ứng / còn thiếu; phần câu hỏi bị bỏ sót | K3 |
| Giữ điều kiện nguồn (theo người chấm) | Rubric |
| Phân bố trạng thái; số lượt sửa; số nhận định bị loại; số lỗi hệ thống | Log |
| Độ trễ và token từng bước (sinh, kiểm tra, sửa, kiểm tra lại) và toàn luồng: trung vị, lớn nhất | Log |
| Bộ lỗi cài sẵn: tỷ lệ phát hiện theo loại, tỷ lệ báo nhầm | Mục 3.4 |

Chưa cam kết ngưỡng độ trễ. Mọi con số trước đây chỉ là giả thuyết.

## 8. Điều kiện trước lượt gọi API đầu tiên

1. Kiểm thử ở mục 6 đạt (đã đạt 30/30).
2. Khóa được cấp qua biến môi trường hoặc file `*.env` riêng; code đã từ chối YAML và `.env` ở thư mục gốc.
3. Chỉ dùng câu hỏi tổng hợp, không chứa thông tin cá nhân thật.
4. **Chưa có bằng chứng khóa cũ đã bị thu hồi.** Gọi API thành công không chứng minh điều đó. Đây là rủi ro tài khoản (người khác dùng hạn mức), không làm sai kết quả thử nghiệm, nên không chặn thử nghiệm nội bộ. Việc thu hồi vẫn là việc của chủ tài khoản.
