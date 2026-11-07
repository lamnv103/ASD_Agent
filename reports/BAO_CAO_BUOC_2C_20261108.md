# Bước 2 (vòng hẹp): verifier hai nhãn (v0.7), kết quả **không đạt, dừng hướng bảng**

**Ngày:** 08/11/2026. **Mã thử nghiệm:** `b6b6196` (`answer_contract_v0.7`, tag `answer-g-v0.7-rejected-trial`). **Baseline:** v0.5 (`b98486f`, lượt chạy `f8bbd35`).
**Tiêu chí đăng ký trước:** `evaluation/trials/verifier_v0.7_small/criteria.json`, commit `38fb6e7`, trước lượt gọi NIM đầu tiên và không sửa sau khi có kết quả. Bộ chấm: `scripts/evaluation/check_trial.py`.
**Phạm vi:** nguyên mẫu nội bộ, `chua_duyet`. Không đổi nhãn nào.

## 1. Đã thử gì

Verifier v0.5 được giữ nguyên và chỉ thêm `checks` gồm đúng hai nhãn, không trích nguyên văn:

- `certainty`: `same` / `weaker` / `stronger`;
- `conclusion_topic`: `same` / `narrower` / `changed`.

Chỉ `stronger` và `changed` thêm lý do loại; mọi kiểm tra của v0.5 giữ nguyên. Không có `question_fit` và `population_scope`. Giải thích tối đa 20 từ. Ví dụ trong prompt lấy từ các quy tắc đã có trong prompt generator.

Generator, sửa, chốt dược lý, thuật ngữ, A và giới hạn 3.072 token đều không đổi.

**Chạy:** 27 lượt gọi NIM theo kế hoạch đăng ký, mỗi lần lặp có cache riêng và không dùng lại cache. **Chi phí tính cả lượt mất: 37 lượt gọi NIM** (27 có bằng chứng, 10 mất). Phân tích nội dung chỉ dùng 27 lượt có bằng chứng. Lần chạy đầu bị lỗi đường dẫn (ký tự `\r` trong tên thư mục) nên mất 10 lượt gọi: phản hồi không được ghi và không ai xem, sau đó đã chạy lại toàn bộ. Mọi lần đo phát lại được bằng `measure_verifier.py --check`.

## 2. Kết quả theo tiêu chí

| Quy tắc | Kết quả | Chi tiết |
|---|---|---|
| R1: F01, A01 bị loại vì nhãn bảng, mọi lần lặp (ca đơn) | **Trượt** | Model gán `same/same` cho **F01 3/3 và A01 3/3**. A01 **qua** cả 3 lần. F01 bị loại cả 3 lần nhưng chỉ vì `span_not_in_cited_evidence` (đoạn trích không khớp), là lý do kỹ thuật nên không tính |
| R2: như trên, trong nhóm (G1, GA1) | **Trượt** | F01 trong G1 qua 2/2. A01 trong GA1: một lần qua, một lần nhóm lỗi định dạng |
| R3: ca sạch không bị loại | **Trượt** | **A06 bị loại 3/3**, với `certainty:stronger` cộng cờ v0.5 `certainty_changed`, `condition_dropped`. P03, A02, A04 qua mọi lần đơn. Ca sạch trong G8 và một lần GA1 bị loại do nhóm lỗi |
| R4: không có đầu ra hỏng | **Trượt** | **3/6 lượt gọi nhóm hỏng** (G8 2/2, GA1 1/2): model chép tên khía cạnh `conclusion_topic` vào danh sách `flags` |
| R5: mọi lượt gọi ≤ 2.048 token | Đạt | Ca đơn trung vị 192, lớn nhất 197 (v0.5: 209). G8 tối đa 906. Độ trễ ca đơn trung vị 3,8 giây |

Ghi chú báo cáo riêng, không thuộc tiêu chí:

- **A07** qua 3/3 (vẫn lọt như v0.5), được báo cáo riêng.
- Trong G1, **F02 và F03 qua** cả 2 lần.
- A03 trong GA1 bị loại với lý do nội dung ở lần không lỗi.

**Quyết định theo tiêu chí đã đăng ký: dừng hướng bảng đối chiếu và chuyển sang C với verifier v0.5.** Không sửa thêm prompt, không thêm khía cạnh.

## 3. Nhận xét

1. Ở dạng hai nhãn ngắn, model **không thấy** lỗi của F01 và A01 (`same/same` 9/9 lần). Ở v0.6, các lần bắt được F01 đến từ `population_scope` và `conclusion_topic:narrowed`, không phải từ hai nhãn này. Đúng như dự báo trước khi chạy.
2. Model nhất quán đánh A06 là "mạnh hơn nguồn" (3/3 lần ở v0.6, 3/3 lần ở v0.7, kể cả cờ v0.5). Đây là **câu hỏi về nhãn của A06**, được ghi nhận riêng ở đây và **không sửa nhãn**. Dù câu trả lời là gì, theo tiêu chí đây vẫn là loại oan.
3. Prompt dài thêm vẫn làm **lệch phần kiểm tra cũ** (cờ v0.5 trên A06) và **gây lẫn schema** khi gọi theo nhóm (tên khía cạnh lọt vào `flags`). Độ dài đầu ra không phải nguyên nhân (R5 đạt).
4. Hai vòng (v0.6, v0.7) cho thấy: với model verifier hiện tại, thêm bảng nhãn vào cùng lượt gọi **không đáng tin cho các lỗi diễn giải tinh**. Đổi model verifier là thí nghiệm riêng về sau, không làm bây giờ.

## 4. Tiếp theo

- HEAD được đưa về hành vi v0.5 bằng một commit mới. Lịch sử v0.7 giữ ở tag `answer-g-v0.7-rejected-trial`.
- Chuyển sang **C**: verifier được xem các đoạn khác trong catalog **chỉ để phát hiện giới hạn hoặc mâu thuẫn**, không bao giờ dùng làm căn cứ cho nhận định không trích. Cần thiết kế và tiêu chí đăng ký trước, rồi trình duyệt trước khi chạy.
- F01, A01, A07, F10 vẫn là ca theo dõi, lọt ở v0.5.
- Lỗi làm mất 10 lượt đã được đóng trong công cụ đo trước lượt gọi kế tiếp: kiểm tra trước đường dẫn và khả năng ghi cache, sổ lượt gọi ghi trước mỗi lượt, lưu trạng thái chạy dở, dừng ngay khi lỗi (`docs/answer_layer/THIET_KE_C.md`, mục 4).
