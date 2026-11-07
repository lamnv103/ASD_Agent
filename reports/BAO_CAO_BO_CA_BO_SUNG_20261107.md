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

Tức là thêm một đoạn trích liên quan nhưng không nói đúng điều đó đủ làm verifier đổi kết luận.

## 2. Độ ổn định: mỗi ca 3 mẫu

Mẫu 1 là lần đo đã có. Mẫu 2 và 3 là hai lần chạy lại **không dùng cache**, cùng prompt, temperature 0.

| Ca | Verifier qua 3 lần | |
|---|---|---|
| F01 (S05 c3, đọc sai "preliminary") | lọt · lọt · lọt | **lỗi hệ thống, không phải nhiễu** |
| F10 (bỏ điều kiện "chức năng cao") | lọt · lọt · lọt | **lỗi hệ thống** |
| A01 (S08 c4) | lọt · lọt · lọt | **lỗi hệ thống** |
| A07 (điều trị không được hỏi) | lọt · lọt · lọt | **lỗi hệ thống** |
| A08 (không tự đứng được) | lọt · lọt · lọt | Chưa có cơ chế kiểm tra |
| F02, F06, A03, A05 | bắt · bắt · bắt | Ổn định. Riêng F06: lý do đổi từ `condition_dropped` sang `added_content` ở lần 3 |
| P03, P06, A02, A06, A09 | qua · qua · qua | Ổn định |
| **A04** (ca đúng) | qua · qua · **bị từ chối** | **Không ổn định** (`partially_supported`, `certainty_changed`) |

- Trên 45 verdict, **1 lần lật** (A04, một ca đúng). Nhiễu có thật nhưng nhỏ.
- **Mọi lỗi để lọt đều lặp lại ở cả 3 lần.** Đó là lỗ hổng có hệ thống của verifier hiện tại, không phải do may rủi. Đây là cơ sở để thử verifier đối chiếu điều kiện.
- Hệ quả cho tiêu chí nhận thay đổi: chênh lệch 1 ca giữa hai phiên bản (như B: 10 so với 11) **nằm trong mức nhiễu** quan sát được. Khi đánh giá thay đổi tiếp theo, các ca trọng tâm nên được chạy lặp, và kết luận dựa trên những ca lật **ổn định**.

## 3. Mục tiêu đo cho bước tiếp theo (verifier đối chiếu điều kiện)

Điều kiện nhận, ngoài các điều kiện đã thống nhất:
- **Phải bắt ổn định:** F01, F10, A01. A07 nằm trong phạm vi cờ `unrequested_medical_content`, nên cũng phải bắt.
- **Không được từ chối:** P03, P06, A02, A04, A06, A09, và các ca sạch còn lại của v1.
- Verifier trên v1 không dưới 11/16.
- Đo đủ ba cách gọi: ca đơn, nhóm đầy đủ, nhóm theo pipeline.
- Chạy lặp 3 lần trên các ca trọng tâm.
- Ghi token và độ trễ.
- A08 cần một cơ chế riêng cho tính tự đứng. Chưa tính vào tiêu chí của bước này.
