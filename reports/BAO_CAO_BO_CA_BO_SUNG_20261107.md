# Bộ ca bổ sung và độ ổn định của verifier v0.5 (07/11/2026)

**Phạm vi:** nguyên mẫu nội bộ, `chua_duyet`. Nhãn là nhãn nháp của nhóm. Mã: v0.5 (`b98486f`); prompt verifier `fd7c1477` không đổi. **Không đổi prompt hay mã tầng G trong bước này.** Baseline vẫn là `f8bbd35`.

Tổng cộng 41 lượt gọi NIM mới. Mọi lần đo phát lại được bằng `measure_verifier.py --check` (có trong `tasks.ps1 verify`).

## 1. Baseline bộ ca bổ sung (`verifier_eval_20261107_v0.5_addendum`)

Bộ `answer_verifier_faults_v1_addendum` gồm 4 cặp: 4 ca đúng và 5 ca lỗi. Bộ này **báo cáo riêng**, không gộp với v1.

| | Kết quả |
|---|---|
| Ca đúng bị từ chối (ca đơn) | 0/4 |
| Ca lỗi bị bắt, core (n=4) | 2/4: bắt A03, A05 |
| Ca lỗi bị bắt, all (n=5) | 2/5 |
| Lọt | **A01** (S08 c4 của lượt 2), **A07** (nội dung điều trị không được hỏi, dù đọc nguồn đúng), A08 (không tự đứng được; chưa có cơ chế kiểm tra) |
| Nhóm GA1 | **A03 lọt khi đi theo nhóm**, dù bị bắt khi đứng riêng |

Cặp K1 cho thấy một điều đáng chú ý:
- A03 trích **chỉ E3**, câu nói "không thể rút ra kết luận". Verifier bắt được (`not_supported`).
- A01 cùng lỗi nhưng trích **E2 và E3**. Verifier cho qua; lời giải thích của nó dựa vào E2 để biện minh cho "kết luận sai lệch".

*(Sửa sau rà soát)* Chưa kết luận được. A01 và A03 khác nhau **cả ở câu chữ nhận định lẫn danh sách trích dẫn**, nên chưa tách được tác động riêng của việc thêm E2. Đối chứng chỉ đổi trích dẫn được ghi ở mục 4.

## 2. Độ ổn định: mỗi ca 3 mẫu

Mẫu 1 là lần đo đã có. Mẫu 2 và 3 là hai lần chạy lại **không dùng cache**, cùng prompt, temperature 0.

| Ca | Verifier qua 3 lần | |
|---|---|---|
| F01 (S05 c3, đọc sai "preliminary") | lọt · lọt · lọt | Tái hiện 3/3 |
| F10 (bỏ điều kiện "chức năng cao") | lọt · lọt · lọt | Tái hiện 3/3 |
| A01 (S08 c4) | lọt · lọt · lọt | Tái hiện 3/3 |
| A07 (điều trị không được hỏi) | lọt · lọt · lọt | Tái hiện 3/3 |
| A08 (không tự đứng được) | lọt · lọt · lọt | Chưa có cơ chế kiểm tra |
| F02, F06, A03, A05 | bắt · bắt · bắt | Ổn định. Riêng F06: lý do đổi từ `condition_dropped` sang `added_content` ở lần 3 |
| P03, P06, A02, A06, A09 | qua · qua · qua | Ổn định |
| **A04** (ca đúng) | qua · qua · **bị từ chối** | **Không ổn định** (`partially_supported`, `certainty_changed`) |

- Trên 45 verdict, **1 lần lật** (A04, một ca đúng). Nhiễu có thật nhưng nhỏ.
- *(Sửa sau rà soát)* F01, F10, A01 và A07 **lặp lại lỗi trong 3/3 mẫu** với cùng cấu hình và đầu vào (ba `request_id` khác nhau). Đây là các lỗi **tái hiện được**, đáng ưu tiên xử lý. Ba mẫu **chưa đủ** để loại trừ biến động, cũng chưa đủ để suy rộng sang cách diễn đạt khác hay nhóm nhận định khác.
- *(Sửa sau rà soát)* Lần lật của A04 cho thấy biến động có tồn tại, nhưng **chưa giải thích được** vì sao F06 đổi kết quả giữa B và baseline. Muốn kết luận về B, phải chạy lặp chính F06 trên cả hai phiên bản. Việc đó chưa cần làm; quyết định không nhận B giữ nguyên. Câu trước đây khẳng định chênh lệch của B "nằm trong mức nhiễu" đã bị rút lại.
- Khi đánh giá thay đổi tiếp theo, các ca trọng tâm vẫn được chạy lặp, và kết quả được theo dõi **theo từng ca**.

## 3. Mục tiêu đo cho bước tiếp theo (verifier đối chiếu điều kiện; bổ sung sau rà soát)

- **Bắt đúng lỗi trọng tâm, đúng loại lỗi:** F01/A01 là đổi ý nghĩa hoặc mức kết luận; F10 là bỏ điều kiện; A07 là nội dung không được hỏi.
- **Lý do phải là nội dung:** không tính là sửa thành công nếu ca bị loại vì lỗi schema hoặc trích dẫn hỏng.
- **Theo dõi từng ca:** không chỉ giữ tổng ≥ 11/16, vì tổng bằng nhau có thể che việc mất một lỗi quan trọng.
- **Ba cách gọi báo cáo riêng:** ca đơn, nhóm đầy đủ, nhóm sau chốt. Chạy lặp các tổ hợp trọng tâm.
- **Nhãn là nhãn phát triển.** Nếu thấy nhãn sai, ghi quyết định điều chỉnh riêng; không sửa âm thầm để bản mới đạt.
- **Phạm vi hẹp:** chỉ đổi cách verifier đối chiếu. Generator, các chốt tất định, thuật ngữ và ngân sách sửa giữ nguyên; chưa gộp C.
- **A07 không phải lý do** để chặn tất định mọi nội dung chứa chữ "điều trị".

Các mục tiêu đặt ra trước đó:

Điều kiện nhận, ngoài các điều kiện đã thống nhất:
- **Phải bắt ổn định:** F01, F10, A01. A07 nằm trong phạm vi cờ `unrequested_medical_content`, nên cũng phải bắt.
- **Không được từ chối:** P03, P06, A02, A04, A06, A09, và các ca sạch còn lại của v1.
- Verifier trên v1 không dưới 11/16.
- Đo đủ ba cách gọi: ca đơn, nhóm đầy đủ, nhóm theo pipeline.
- Chạy lặp 3 lần trên các ca trọng tâm.
- Ghi token và độ trễ.
- A08 cần một cơ chế riêng cho tính tự đứng. Chưa tính vào tiêu chí của bước này.

## 4. Đối chứng chỉ đổi danh sách trích dẫn (bổ sung sau rà soát)

`evaluation/answer_verifier_faults_v1_addendum/citation_controls.jsonl`: giữ **nguyên câu chữ nhận định**, chỉ đổi trích dẫn.

- **C01** = câu chữ của A03, trích **E2 + E3** (A03 chỉ trích E3).
- **C02** = câu chữ của A01, chỉ trích **E3** (A01 trích E2 + E3).

Kết quả đo ghi ở `reports/BAO_CAO_BUOC_2B_20261107.md`.
