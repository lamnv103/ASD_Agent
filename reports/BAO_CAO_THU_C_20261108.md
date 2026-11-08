# Thử nhỏ C (verifier xem đoạn không trích): **dừng giữa chừng, đã trượt R2 và R5**

**Ngày:** 08/11/2026.
**Tiêu chí:** `evaluation/trials/verifier_c_small/criteria.json`, đăng ký ở commit `3afe289` trước lượt gọi đầu tiên và không sửa sau đó.
**Mã:** baseline v0.5 (cấu hình tại `3afe289`); chặng thử dùng v0.8 (`cc0c9fd`, `verifier_context_v0.1`).
**Phạm vi:** nguyên mẫu nội bộ, `chua_duyet`. Không đổi nhãn nào.

## 1. Chạy và chi phí

| Chặng | Lượt bắt đầu | Phản hồi đã lưu | Lỗi | Chi phí chưa xác định | Token đầu ra đã lưu |
|---|---|---|---|---|---|
| Baseline v0.5 | 20 | 20 | 0 | 0 | 4.442 |
| Thử C | 25 / 37 dự kiến | 24 | 1 (`nim_rate_limit`, HTTP 429) | 1 | 6.111 |

- Ở lượt thứ 25 (lần chạy `singles_c_rep3`), NIM trả HTTP 429. Lô **dừng ngay**: bản ghi dở nằm trong `singles_c_rep3/results.partial.json`, 4 lần chạy nhóm **không được khởi động**, và `trial_state.json` ghi rõ lần chạy lỗi cùng các lần còn chờ. Cơ chế an toàn hoạt động đúng thiết kế.
- `trial_state.json` chỉ tổng hợp chặng thử. Số liệu baseline lấy từ `calls.jsonl` của từng thư mục.
- **Chưa chấm chính thức:** `check_trial.py` từ chối chấm vì thiếu `singles_c_rep3` và 4 lần chạy nhóm (đúng quy tắc "đủ ca, đủ lần lặp mới chấm đạt").
- Phần dưới đây phân tích các lần chạy đã có. Hai quy tắc đã trượt **không thể đảo ngược**, dù có chạy thêm.

## 2. Kết quả trên dữ liệu đã có

| Ca | v0.5 (baseline hoặc đo trước) | C | Ghi chú |
|---|---|---|---|
| CD1 (bỏ mức thận trọng) | lọt 5/5 | **bắt 3/3**, đúng câu chính đã đăng ký, không kèm lỗi kỹ thuật | Kể cả lần trong bản ghi dở |
| F02 (đơn) | bắt, nhưng lý do khác (`contradicted`) | **bắt đúng câu 2/3**; lần 3 **đầu ra thiếu `other_passage_issue`** (lỗi schema) | |
| CC1, CC2 | qua | qua mọi lần | |
| CC3 | qua 3/3 | **bị loại 1/3** (`context_limit:E1`) | Câu E1 "SBI trái với ASI" thực ra đồng ý với nhận định |
| P08 | qua | **bị loại 3/3** (`context_limit:E1`, câu "clear uni-directional relationships") | Đúng nguy cơ báo nhầm đã ghi trước: nhận định đã giữ giới hạn, đứng cạnh đoạn mạnh hơn |
| A04 | qua | **bị loại 3/3** (`context_limit:E2`, câu về nhóm **chức năng thấp**) | Khác đối tượng nhưng bị coi là giới hạn |
| CR1, CR2 | bị loại (`not_supported`) | bị loại vì support mọi lần | CR1 còn bị gắn `context_limit:E1`, tức là chính đoạn chứa căn cứ bị gọi là "giới hạn" |

| Quy tắc | Trạng thái |
|---|---|
| R1 (phát hiện đúng câu) | Chưa xác định; đã có 1 lần F02 trượt vì đầu ra hỏng |
| **R2 (không báo nhầm)** | **Trượt**: P08 3/3, A04 3/3, CC3 1/3 |
| R3 (không được cứu) | Đạt trên dữ liệu đã có |
| R4 (hồi quy trong nhóm) | Chưa đo |
| **R5 (định dạng)** | **Trượt**: 1 đầu ra thiếu trường |
| R6 (độ dài) | Đạt trên dữ liệu đã có: ca đơn trung vị 256, lớn nhất 376 token (v0.5: 191, 289) |

## 3. Nhận xét

1. C **phát hiện được** lỗi bỏ mức thận trọng ở S05 đúng câu nguồn. CD1 là ca v0.5 lọt 5/5, nên phần này có giá trị.
2. Nhưng verifier **không phân biệt được** đoạn khác đối tượng (A04), đoạn mạnh hơn nằm cạnh nhận định đã giữ giới hạn (P08), và đoạn đồng ý (CC3) với một giới hạn thật. Prompt đã ghi rõ "khác đối tượng thì không phải vấn đề", vậy mà model vẫn báo nhầm 3/3.
3. Thêm một trường vào đầu ra lại gây lỗi schema. Đây là lần thứ ba trong ba thử nghiệm (v0.6, v0.7, C).

## 4. Theo tiêu chí đăng ký

Một quy tắc trượt là đủ để kích hoạt quyết định "dừng C theo thiết kế này". Ở đây đã có hai: R2 và R5. Hai kết quả này đã chắc chắn, chạy nốt 12 lượt còn lại không thể biến chúng thành "đạt". Bộ chấm vẫn ghi "chưa chấm" vì dữ liệu chưa đủ.
