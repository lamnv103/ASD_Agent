# Thiết kế: hướng dẫn thuật ngữ trong phản hồi sửa lỗi (bản nháp chờ duyệt)

**Ngày:** 08/11/2026. **Trạng thái:** `chua_duyet`, chưa gọi API.

**Baseline:** v0.5 (`b98486f`, lượt chạy `f8bbd35`). Đây là baseline nghiên cứu, còn lỗi đã biết.

**Câu hỏi hẹp:** hướng dẫn thuật ngữ cụ thể có giúp vòng sửa khắc phục lỗi dịch, mà vẫn giữ đúng bằng chứng hay không?

## 1. Thay đổi duy nhất

Với mỗi mục `problems` của vòng sửa có lý do `known_term_error:<cụm sai>`, nhánh B thêm:

`term_guidance: [{"wrong": "du lượn", "source_term": "passive swinging", "use": "đu đưa thụ động"}]`

Nội dung hướng dẫn nằm trong `deployments/answer_term_guidance.json` (`term_guidance_v0.1`), được cố định trước lượt gọi đầu tiên; khóa của nó trùng với `known_term_errors`. Mã: `rag/answer_repair_terms.py`.

"Nguyên tắc bảo đảm thực hiện đúng phương pháp" (fidelity: mức độ thực hiện can thiệp đúng các nguyên tắc của phương pháp) là **lựa chọn dịch của dự án** cho bản thử dành cho phụ huynh, chưa phải thuật ngữ tiếng Việt đã được chuyên gia duyệt.

- **Giữ nguyên mã lỗi** để truy vết.
- **Không diễn giải lại các mã khác** (ví dụ `flag_condition_dropped`), để không trộn sửa thuật ngữ với sửa phạm vi. Có kiểm thử khẳng định.
- **Không thay chữ trực tiếp vào câu trả lời.** Generator tự viết lại, và nhận định mới đi qua **toàn bộ** kiểm tra v0.5: K1, chốt, thuật ngữ, verifier **trên câu chữ mới**, trạng thái.
- `rag/answer_layer.py`, prompt, model, chốt và ngân sách sửa (1 lượt) **không đổi**. Hướng dẫn chưa được nối vào pipeline.

## 2. Đối chứng trên cùng đầu vào

`scripts/evaluation/measure_repair.py` chạy pipeline v0.5 thật qua một client trung gian:

- **Vòng đầu** (sinh + kiểm tra) được phát lại offline từ bundle lượt chạy 2 (`reports/answer_eval_20261107_v0.5`). Nếu request vòng đầu không có trong bundle, lần chạy dừng trước khi gọi API (`FirstRoundMismatch`).
- **Vòng sửa** gọi thật. Nhánh A gửi `problems` của v0.5; nhánh B gửi `problems` có thêm `term_guidance`. Mọi thứ khác giống hệt.

**Điều kiện tiên quyết đã kiểm offline** (có kiểm thử):

| Câu | Nhánh A | Nhánh B |
|---|---|---|
| S05, S07, H03 | Tái tạo **từng byte** lượt chạy 2 | Tái tạo **từng byte** lượt chạy 2 |
| S08 | Tái tạo đúng lượt chạy 2, kể cả vòng sửa viết lại hai cụm sai | **Chỉ** request vòng sửa khác (thêm hướng dẫn cho c2, c3) |

H03 đạt ngay vòng đầu và không bị đưa vào sửa ở nhánh nào. S05 và S07 không có lỗi thuật ngữ, nên không gọi model cho chúng.

## 3. Đơn vị đo (`evaluation/answer_repair_terms_v1/units.jsonl`)

| Đơn vị | Vai trò | Gọi API |
|---|---|---|
| U1 | Ca đích: vòng đầu thật của S08 (c2 "nguyên tắc trung thực", c3 "du lượn") | Có |
| U2 | Biến thể giữ lại, chưa dùng để chỉnh thông báo: c3 vừa sai thuật ngữ **vừa khẳng định hiệu quả vượt quá bằng chứng được cung cấp** ("đã được chứng minh hiệu quả hơn ASI"; không suy ra rằng khoa học đã chứng minh điều ngược lại). Sửa được từ mà vẫn hiển thị nội dung đó thì **tính là trượt**. Bỏ riêng phần so sánh sai hoặc loại cả nhận định đều chấp nhận được, nhưng được báo riêng | Có (vòng đầu trùng U1 nên phát lại được) |
| U3 | Biến thể giữ lại: dùng thuật ngữ đúng ngay từ đầu. Không có `known_term_error`, nên request nhánh B trùng nhánh A theo cách xây dựng (đã kiểm offline) | Không (gọi API ở đây chỉ đo lại v0.5) |

**Kế hoạch:** 2 đơn vị × 2 nhánh × 3 lần lặp = 12 lần chạy, mỗi lần tối đa 2 lượt gọi (sửa, kiểm tra sau sửa), **tối đa 24 lượt**. Hai nhánh xen kẽ nhau trong từng lần lặp.

24 là trần, không phải chỉ tiêu: nếu mọi nhận định sửa đều trượt kiểm tra tất định, pipeline không gọi verifier. Không gọi bù để đủ 24; một lần chạy hoàn tất hợp lệ với ít lượt hơn vẫn có giá trị.

## 4. Đánh giá

**Đánh giá: hai bản chấm độc lập, rồi phân xử khi vẫn ẩn nhánh.**

1. **Phiếu mù:** các nhận định được hiển thị được xáo trộn với seed cố định; nhánh và đơn vị bị ẩn. Khóa giữ cả hash câu chữ của từng nhận định.
2. **Nhóm chấm trước, độc lập.** Người chấm đọc nguyên văn đoạn trích cho từng dòng; đây là phần đối chiếu thủ công duy nhất dựa trên nguồn. Các trường cần ghi:
   - khái niệm thể hiện;
   - `term_correct` (y/n/na);
   - `faithful` (y/n): giữ nghĩa, phạm vi, mức chắc chắn, không thêm thông tin;
   - `contains_known_wrong_content` (y/n).
3. **Đánh giá nháp bằng model** (Claude), làm riêng, không đọc bản chấm của nhóm.
4. **Giữ cả hai bản.** Bất đồng do nhóm phân xử khi nhánh vẫn ẩn (`review_adjudicated.json`). Báo cáo ghi mức đồng thuận và từng bất đồng.

Bộ chấm chỉ dùng bản đã phân xử, và **từ chối chấm** nếu bất kỳ bản nào trong ba bản (nhóm, model, phân xử):
- thiếu dòng cho một nhận định hiển thị, hoặc có dòng trùng;
- có dòng không khớp khóa, hoặc khớp sai lần chạy, nhánh hay câu chữ;
- có giá trị ngoài danh sách cho phép.

**Giới hạn của việc làm mù:** người thiết kế thử nghiệm có thể nhận ra nhánh qua câu chữ.

`supported` của verifier hay trạng thái `du` **không bao giờ** được dùng làm phán quyết chất lượng. Kết quả verifier của câu cũ không được dùng thay cho câu mới.

**Khái niệm đăng ký trước** (S08):

| Khái niệm | Nội dung | Thuật ngữ đúng |
|---|---|---|
| K_ANSWER | Câu trả lời trực tiếp (c1) | — |
| K_FIDELITY | Nguyên tắc ASI | "nguyên tắc bảo đảm thực hiện đúng phương pháp" hoặc cùng nghĩa |
| K_SWING | Ví dụ đầu vào thụ động | "đu đưa thụ động" |
| K_REVIEWS | Các tổng quan trước đây (chỉ báo cáo) | — |

**Quy tắc** (nhánh B, đủ 3 lần lặp):

| Quy tắc | Điều kiện đạt |
|---|---|
| R1 | U1: cả K_SWING và K_FIDELITY được hiển thị với thuật ngữ đúng (`term_correct = y`; "na" không tính là sửa) **và** trung thành với nguồn. Bỏ nhận định không được tính là sửa |
| R2 | U1: K_ANSWER vẫn hiển thị và trung thành (không mất nhận định đúng) |
| R3 | U1: không có nhận định nào về hai khái niệm trên mà sai nghĩa hoặc giữ thuật ngữ sai |
| R4 | U2: nội dung sai về hiệu quả **không bao giờ** được hiển thị |
| R5 | U2: nhận định về K_SWING nếu hiển thị thì phải trung thành, với thuật ngữ đúng |
| Quy kết | Chỉ ghi nhận "có lợi **trong thử nghiệm nhỏ này**" khi nhánh B sửa được cả hai khái niệm ở 3/3 lần **và** nhánh A ở ít hơn 3/3. Điều đó chưa chứng minh cải thiện ổn định nói chung; ví dụ A 2/3 so với B 3/3 được trình bày đúng ở mức đó. Nếu nhánh A cũng 3/3 thì "không chứng minh được lợi ích", không nhận |

**Báo cáo riêng:**

- số lỗi thuật ngữ đã sửa;
- số nhận định thực sự chấp nhận được, theo từng lần chạy và từng nhánh;
- sổ lượt gọi (bắt đầu, đã lưu, lỗi, chi phí chưa xác định).

Thiếu lần chạy hoặc thiếu dòng đánh giá thì bộ chấm từ chối chấm.

**Phạm vi kết luận:** một câu hỏi (S08) và hai lỗi dịch đã biết; chưa phải kết quả chung về chất lượng vòng sửa.

**Quyết định:**

- Đạt hết → đề xuất nối hướng dẫn vào pipeline thành một thay đổi riêng, được duyệt riêng, rồi chạy 4 câu trên một phiên bản cố định.
- Trượt → dừng dạng phản hồi này. Không viết lại hướng dẫn trên các đơn vị này. Hướng kế tiếp là tách phạm vi hoặc nhận định tự đủ nghĩa, mỗi hướng một thử nghiệm riêng.

## 5. An toàn khi chạy

Dùng lại cơ chế đã có:

- kiểm tra `--out` trước khi gọi, ghi thử cache, sổ lượt gọi ghi trước mỗi lượt;
- `results.partial.json` và dừng ngay khi lỗi; nếu vòng sửa trả `system_error` thì cũng dừng;
- `run_trial.py` chạy kế hoạch bằng danh sách tham số và từ chối bản nháp.

Các lần chạy phát lại được bằng `measure_repair.py --check`, kể cả theo commit cũ.
