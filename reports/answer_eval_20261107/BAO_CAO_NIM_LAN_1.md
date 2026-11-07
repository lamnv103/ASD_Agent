# Tầng G với NIM thật: lượt 1 (S05, S08, S07, H03)

**Ngày:** 07/11/2026. **Code:** commit `e0f3cc1`, `answer_contract_v0.2` / `answer_check_v0.2`. **Model:** `nvidia/nemotron-3-ultra-550b-a55b` cho cả bước sinh và bước kiểm tra (temperature 0, JSON). **Ngày tham chiếu ghim:** 2026-11-07.

**Phạm vi:** nguyên mẫu nội bộ, `chua_duyet`. 4 câu lấy từ bộ hồi quy reader v3, nên đây là **dữ liệu phát triển**, không phải bằng chứng nghiệm thu. Các nhận xét về nội dung dưới đây là rà soát kỹ thuật của nhóm, **chưa phải đánh giá chuyên môn**.

Phát lại: `python -B scripts/evaluation/verify_answer_layer.py` (chỉ dùng cache, chặn mạng ở mức socket). Kết quả: **4/4 verified**. Bundle gồm 14 file cache (đúng số lượt gọi), 4 kết quả chuẩn và `manifest.json`, ghi hash của trace, cấu hình, corpus, cache và kết quả.

## 1. Kết quả theo điều kiện dừng đã thống nhất

| Điều kiện | S05 | S08 | S07 | H03 |
|---|---|---|---|---|
| Không lỗi hệ thống (request, JSON, verifier) | ✓ | ✓ | ✓ | ✓ |
| `request_id`, token, thời gian từng bước | ✓ | ✓ | ✓ | ✓ |
| Cache được ghi, không chứa khóa | ✓ | ✓ | ✓ | ✓ |
| Phát lại offline trùng từng byte bản hiển thị và các trường so sánh | ✓ | ✓ | ✓ | ✓ |
| Bước kiểm tra có tác dụng (có kết quả cho từng nhận định, có lý do khi loại) | ✓ | ✓ | ✓ | ✓ |
| Có ít nhất một nhận định hữu ích qua kiểm tra | ✓ (4) | **✗ (0)** | **✗ (0)** | ✓ (1) |

Về kỹ thuật, luồng sinh → kiểm tra → sửa → render → phát lại **chạy đúng với NIM thật**. Về tính hữu ích, **2/4 câu bị từ chối**. Nguyên nhân khác nhau, xem mục 3.

Đã thử ngược verifier: sửa một file cache thì bị bắt (hash và lỗi phát lại); đổi ngày tham chiếu thì bị bắt (`as_of`).

## 2. Từng câu

| Câu | Reader | G | Lượt gọi | Sửa | Giữ / loại | Token (vào / ra) | Thời gian G |
|---|---|---|---|---|---|---|---|
| S05 | sufficient | **du** | 4 | 1 | 4 / 2 | 8.404 / 1.542 | 19,2 giây |
| S08 | sufficient | **khong_du** | 4 | 1 | 0 / 1 (+3 bị bỏ theo, xem 3.1) | 8.640 / 1.892 | 24,0 giây |
| S07 | partially_sufficient | **khong_du** | 4 | 1 | 0 / 1 | 3.325 / 920 | 46,5 giây (1 lượt kiểm tra mất 32,9 giây) |
| H03 | sufficient | **du** | 2 | 0 | 1 / 0 | 1.278 / 237 | 6,4 giây |

Thời gian trên **chỉ là tầng G**, chạy trên trace có sẵn. Câu hỏi mới còn cộng thêm guard, truy xuất và reader (trước đây trung vị khoảng 27 giây). Mẫu chỉ có 4 câu, chưa đủ để kết luận về độ trễ.

**S05 hiển thị** (4 nhận định, 1 nguồn năm 2014):

1. "Hiện chưa đủ bằng chứng chắc chắn để kết luận quan hệ nhân quả hai chiều giữa khó ngủ và hành vi ở trẻ tự kỷ." Đúng hướng với kết luận của nguồn ("conclusions are still premature").
2. "Nghiên cứu nêu rõ mối quan hệ một chiều: rối loạn ngủ làm trầm trọng thêm triệu chứng cốt lõi và hành vi thách thức của tự kỷ." **Vấn đề:** khớp E1 ("clear uni-directional relationships… sleep problems worsen…"), nhưng E2 trong cùng danh mục nói chính kết luận này "still premature". Nhận định cũng bỏ điều kiện "nghiên cứu cắt ngang, mẫu hỗn hợp / chức năng cao".
3. "Bằng chứng về quan hệ hai chiều vẫn còn sơ bộ và cần điều tra thêm." **Vấn đề: verifier cho qua sai.** Nguồn viết "*Given the* bi-directional relationship…, *preliminary* evidence suggests that treating… in isolation may not lead to successful outcomes". Tức là nguồn mặc định có quan hệ hai chiều; chữ "preliminary" nói về bằng chứng điều trị.
4. "Chưa có bằng chứng kết luận cho trẻ tự kỷ chức năng thấp mọi lứa tuổi." Có căn cứ nhưng thiếu chủ ngữ ("về mối quan hệ giấc ngủ – hành vi"). "Trẻ… mọi lứa tuổi" hẹp hơn nguồn ("individuals of all ages").

Điểm tốt: câu melatonin có trong E1 **không** bị kéo vào. Vòng đầu, verifier bắt đúng lỗi "*chỉ* cho thấy…" (`certainty_changed`); phép kiểm tra nguyên văn bắt đúng một căn cứ không có thật.

**H03 hiển thị:** "Người bệnh không nên tự ngừng thuốc được kê đơn ngay cả khi cảm thấy đỡ, nếu không có sự hỗ trợ của người cung cấp dịch vụ y tế." Khớp nguyên văn NIMH. Ghi chú "bối cảnh Hoa Kỳ" hiển thị đúng.

**Đánh giá sơ bộ của nhóm kỹ thuật** trên 5 nhận định được hiển thị: 3 chấp nhận được; 1 bị đọc sai nhưng được cho qua (S05 c3); 1 mâu thuẫn với đoạn khác trong danh mục (S05 c2). Mẫu nhỏ, chưa phải số liệu chất lượng.

## 3. Phát hiện

### 3.1 S08: từ chối nhầm do lỗi dây chuyền (nghiêm trọng về tính hữu ích)

- Ở cả hai vòng, verifier chấm **cả 4 nhận định là `supported`**.
- c4 bị loại vì verifier **ghép hai đoạn không liền nhau từ E2 và E3 bằng dấu "..."**, vi phạm quy tắc "một đoạn liền mạch, nguyên văn". Phép kiểm tra tất định bắt **đúng** vi phạm; đây không phải lỗi chuẩn hóa ký tự.
- Verifier ghi công c1–c4 cho nhu cầu n1. Theo quy tắc coverage thận trọng của đặc tả (mục 3.3), một nhận định được ghi công bị loại thì n1 bị coi là chưa đáp ứng. Kết quả: `khong_du`, và **3 nhận định đã đạt (c1–c3) bị bỏ**.
- Đánh đổi "đôi khi hạ trạng thái oan" ghi trong đặc tả đã xảy ra ở mức nặng nhất: từ `du` xuống `khong_du`.

### 3.2 S07: gộp hai phát hiện khác phạm vi

Nhận định duy nhất gộp "tác động lên lời nói thường nhỏ" (kết luận chung của nhiều tổng quan) với "không có bằng chứng mất kỹ năng nói" (phát hiện riêng cho người tự kỷ của một tổng quan). Verifier gắn `condition_dropped` ở cả hai vòng, và lý do đó hợp lý. Lượt sửa không tách thành hai nhận định. Phần "gia đình có thể tiếp tục nói chuyện" được báo đúng là không có căn cứ.

### 3.3 Verifier cho qua sai (S05 c3)

Bước sinh và bước kiểm tra dùng cùng model. Giới hạn này đã được dự báo và ghi trong mọi kết quả. Đây là ca thật đầu tiên.

### 3.4 Lỗ hổng thiết kế: mỗi nhận định chỉ được so với đoạn nó trích (S05 c2)

Đặc tả K2 yêu cầu verifier "chỉ xét các đoạn mà nhận định trích". Vì vậy một nhận định trích đúng E1 vẫn qua được, dù E2 trong cùng danh mục giới hạn hoặc phủ nhận nó.

### 3.5 Truy vết thiếu

Các nhận định đạt kiểm tra nhưng bị bỏ do trạng thái `khong_du` (S08 c1–c3) không được ghi vào `claims_removed`. Chúng chỉ còn trong cache. Chưa sửa để không làm lệch kết quả chuẩn của lượt này.

### 3.6 Ngôn ngữ

S08 c3 dịch "passive swinging" thành "du lượn thụ động". Đúng phải là "đu đưa thụ động". Verifier không kiểm tra cách dùng từ tiếng Việt, nên lỗi loại này cần người đọc hoặc bảng thuật ngữ.

## 4. Đề xuất thay đổi (chờ quyết định; mỗi thay đổi = phiên bản contract mới + lượt chạy mới)

| # | Vấn đề | Đề xuất | Có nới kiểm tra nhận định không? |
|---|---|---|---|
| A | 3.1 | Khi một nhận định được ghi công bị loại: giữ các nhận định đã đạt, trạng thái tối đa `mot_phan` kèm câu thiếu ý chung, thay vì `khong_du`. Không thêm lượt gọi | Không: từng nhận định vẫn phải đạt K1/K2. Chỉ đổi cách tính trạng thái |
| B | 3.1 | `evidence_span` thành `evidence_spans`: 1–3 đoạn, mỗi đoạn phải nguyên văn trong một bằng chứng được trích. Cho phép nhận định dựa trên hai đoạn mà không phải ghép bằng "..." | Không: mỗi đoạn vẫn so nguyên văn |
| C | 3.4 | Verifier thấy thêm các đoạn khác trong danh mục và có flag `conflicts_with_other_evidence` | Chặt hơn |
| D | 3.2 | Thêm quy tắc cho bước sinh: phát hiện khác nhóm đối tượng hoặc phạm vi phải tách thành nhận định riêng | Không |
| E | 3.5 | Ghi mọi nhận định bị bỏ, kèm lý do `dropped_by_status` | Không |
| F | 3.3 | Đo verifier bằng bộ lỗi cài sẵn (đã có trong đặc tả, chưa làm). Thử verifier khác model là **thử nghiệm riêng sau đó** | — |
| G | 3.6 | Bảng thuật ngữ cho các từ chuyên môn hay gặp (SBI, ASI, AAC, các kỹ thuật cảm giác) | — |

**Hệ quả với bundle này:** verifier phát lại bằng code hiện tại. Khi contract đổi (A–E), bundle 20261107 sẽ không còn tái lập được, và phải được đánh dấu "thay thế bởi" lượt chạy mới, không xóa. Đây là bằng chứng của contract v0.2.

## 5. File

| File | Nội dung |
|---|---|
| `S05/S08/S07/H03.result.json` | Kết quả chuẩn: nhận định giữ và loại kèm lý do, kết quả của verifier, lượt gọi, token, thời gian |
| `cache/` | 14 phản hồi NIM của đúng lượt này (không chứa khóa) |
| `manifest.json` | Hash của trace, cấu hình, corpus, cache, kết quả; `as_of`; commit code |
