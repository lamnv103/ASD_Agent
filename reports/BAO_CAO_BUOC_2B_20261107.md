# Bước 2: verifier đối chiếu điều kiện và mức kết luận (v0.6), kết quả **không nhận**

**Ngày:** 07/11/2026. **Mã thử nghiệm:** `70afadb` (`answer_contract_v0.6`, tag `answer-g-v0.6-rejected-table`). **Baseline:** v0.5 (`b98486f`), lượt chạy `f8bbd35`.
**Phạm vi:** nguyên mẫu nội bộ, `chua_duyet`. Nhãn là nhãn phát triển; **không điều chỉnh nhãn nào trong bước này**.
**Đã đổi:** chỉ verifier (prompt và bảng `checks`, kèm kiểm tra tất định). Generator, các chốt tất định, thuật ngữ, A và ngân sách sửa giữ nguyên.

Khoảng 110 lượt gọi NIM. Mọi lần đo phát lại được bằng `measure_verifier.py --check`.

## 1. Đối chứng chỉ đổi trích dẫn (v0.5, trước khi đổi verifier)

Giữ nguyên câu chữ, chỉ đổi danh sách trích dẫn; mỗi cấu hình chạy 3 lần, không dùng cache.

| Câu chữ | Chỉ E3 | E2 + E3 |
|---|---|---|
| của A01 ("dẫn đến kết luận sai lệch…", trích từ S08) | **bắt 3/3** (C02) | **bắt 0/3** (A01) |
| của A03 | bắt 3/3 (A03) | bắt 1/3 (C01) |

Với cặp này, chỉ cần thêm E2 (liên quan nhưng không nói đúng ý đó) là verifier v0.5 đổi kết quả. Phép thử chỉ có 3 mẫu mỗi ô, trên một cặp nhận định.

## 2. Kết quả v0.6 theo tiêu chí đã chốt

### 2.1 Lỗi trọng tâm (ca đơn, 3 mẫu)

| Ca | v0.5 | v0.6 | Lý do (v0.6) |
|---|---|---|---|
| F01 | lọt 3/3 | bắt 2/3 (**không ổn định**) | Qua bảng `checks` |
| F10 | lọt 3/3 | bắt 3/3, **nhưng 2/3 lần chỉ vì đầu ra verifier không hợp lệ** (lý do kỹ thuật, không tính) | |
| A01 | lọt 3/3 | bắt 3/3 | `certainty` / `conclusion_topic` |
| A07 | lọt 3/3 | bắt 3/3 | `question_fit` |
| C01, C02 | 1/3, 3/3 | 3/3, 3/3 | Không còn bị E2 làm lệch |

### 2.2 Ca sạch: **thất bại**

| Bộ | Ca sạch bị từ chối (ca đơn) |
|---|---|
| v1 | **7/10** (P01, P02, P04, P05, P06, P09, P10). P06 bị từ chối 3/3 lần |
| Bổ sung | **4/4** (A02, A04, A06, A09), mỗi ca 3/3 lần |

Nguyên nhân: **cả 11 ca đều có `check:question_fit:changed`**. Verifier đánh dấu "không được hỏi" cho cả những nhận định trả lời trực tiếp câu hỏi, chẳng hạn nội dung giảm liều ở H03.

**Phân tích thăm dò** (chấm lại chính các verdict đã ghi, bỏ qua `question_fit`; không phải một phép đo, vì prompt khi đo vẫn có khía cạnh này): vẫn còn **6/14 ca sạch bị từ chối**. Lý do là `population_scope` bị đánh giá quá khắt khe ("dropped", "broadened" cho những diễn đạt đúng) và câu chữ trích không nguyên văn.

### 2.3 Tổng theo tầng trên v1 (để theo dõi, không dùng làm tiêu chí)

| | v0.5 | v0.6 |
|---|---|---|
| Verifier bắt (core 16) | 11/16 | 15/16, trong đó **F10 và F13 chỉ vì lý do kỹ thuật**; đúng loại lỗi 10 |
| Ca sạch bị từ chối | 0/10 | **7/10** |

Tổng bắt lỗi tăng **chủ yếu do verifier từ chối gần như mọi thứ**, không phải vì phân biệt đúng sai tốt hơn.

### 2.4 Định dạng, chi phí và cách gọi

| | v0.5 | v0.6 |
|---|---|---|
| Ca đơn có đầu ra không hợp lệ | 0/75 | **7/75** |
| Nhóm lỗi (đầu ra không hợp lệ hoặc bị cắt vì vượt 3.072 token) | 0 | **3/20** |
| Token đầu ra, trung vị (lớn nhất) | 209 (289) | **477 (706)** |
| Độ trễ ca đơn, trung vị | 4,1 giây | 7,5 giây |

- **Đứng riêng và theo nhóm** lệch nhau ở 17/27 ca. Trong đó nhiều ca là do nhóm bị lỗi, nên con số này không so trực tiếp được với v0.5 (4/27).
- **Nhóm theo pipeline:** F10 bị bắt ở cả nhóm đầy đủ lẫn nhóm sau chốt.
- G1 (đúng tập nhận định thật của S05) cho kết quả khác nhau giữa các lần lặp: lần 1 cả nhóm qua, lần 2 cả nhóm bị loại.

## 3. Kết luận

Theo tiêu chí, **không nhận v0.6**, vì ca sạch bị từ chối hàng loạt và đầu ra không hợp lệ hoặc bị cắt.

Bài học rút ra:

1. **Khía cạnh `question_fit` gây hại lớn nhất.** Đây là phần thêm vào để bắt A07, nằm ngoài phạm vi hẹp "điều kiện / mức kết luận" đã chốt. Lẽ ra phải tách thành thử nghiệm riêng.
2. Quy tắc "mọi khía cạnh khác `same` thì trượt" **quá cứng** khi model gắn nhãn quan hệ không đáng tin (vẫn 6/14 ca sạch bị từ chối dù bỏ `question_fit`).
3. Bảng đối chiếu **giúp bắt các lỗi diễn giải đã biết** (A01, A07, C01) **và loại bỏ ảnh hưởng của E2**. Hướng đi có giá trị, nhưng cần một dạng hẹp hơn.
4. Đầu ra dài gấp khoảng 2,3 lần làm tăng lỗi định dạng và nguy cơ vượt giới hạn token khi gọi theo nhóm.

## 4. Lựa chọn tiếp theo (cần quyết định)

1. **Đưa HEAD về hành vi v0.5** bằng một commit mới, như đã làm với B. Lịch sử v0.6 giữ ở tag `answer-g-v0.6-rejected-table`.
2. Nếu thử lại, **dùng phạm vi hẹp hơn:**
   - chỉ hai khía cạnh, `certainty` và `conclusion_topic` (nhắm F01 và A01);
   - chỉ loại nhận định với quan hệ rõ ràng (`stronger`, `changed`), không loại với `narrowed` hay `broadened`;
   - không có `question_fit`; A07 để một thử nghiệm riêng;
   - kiểm tra lại giới hạn token khi gọi theo nhóm.

   Đo trên đúng bộ ca và đủ ba cách gọi như bước này.
3. Hoặc chuyển sang C trước, và giữ verifier v0.5.
