# Thiết kế C: verifier xem các đoạn không trích để tìm giới hạn (bản nháp chờ duyệt)

**Ngày:** 08/11/2026. **Trạng thái:** `chua_duyet`, chưa gọi API.

**Baseline:** v0.5 (`b98486f`, lượt chạy `f8bbd35`). v0.5 có lỗi đã biết: đây là baseline nghiên cứu, chưa phải bản đạt chất lượng.

**Mã:** `rag/answer_verify_context.py` (`verifier_context_v0.1`). Module chỉ được dùng khi `deployments/answer_layer.json` có `"verifier_context": {"enabled": true}`. Hiện **chưa bật**, nên verifier vẫn đúng từng byte của v0.5 (prompt sha `fd7c1477…`; có kiểm thử khẳng định). Module chưa nối vào pipeline của `rag/answer_layer.py`; trước hết chỉ đo qua `measure_verifier.py`.

## 1. Phạm vi (theo quyết định ngày 08/11)

| Phần | Quy tắc | Bảo đảm bằng |
|---|---|---|
| Bằng chứng được trích | Dùng để kiểm tra nhận định có căn cứ hay không | Parser v0.5 chạy nguyên trạng; `evidence_span` phải nằm nguyên văn trong đoạn **được trích**. **Không bảo đảm tất định** rằng model không dựa vào đoạn không trích khi chấm `supported` (xem mục 2) |
| Các đoạn khác trong catalog | Chỉ tìm giới hạn, điều kiện hoặc mâu thuẫn bị bỏ qua | Prompt; trường `other_passage_issue` không thể xóa lý do loại của parser v0.5, chỉ có thể **thêm** lý do |
| Khi phát hiện vấn đề | Thu hẹp, sửa hoặc loại nhận định; không tự thêm căn cứ chưa trích | Lý do `context_limit:<Ex>` đi vào vòng sửa như mọi lý do khác. Nếu generator dùng Ex, nó phải trích Ex và qua lại toàn bộ kiểm tra |
| Đoạn khác đối tượng hoặc kết quả | Không mặc định coi là mâu thuẫn | Prompt; đo bằng các ca chống báo nhầm (CC2, CC3, A04, P08, G6) |
| Thay đổi khác | Giữ nguyên generator, model, chốt tất định, thuật ngữ, ngân sách sửa | Không đổi file nào trong số đó |

## 2. Cơ chế

- **Payload:** giữ nguyên payload v0.5 và thêm `context_passages`, là toàn bộ đoạn trong catalog. Mỗi nhận định vẫn chỉ có `cited` là các đoạn nó trích.
- **Đầu ra:** mỗi verdict thêm `other_passage_issue`, có giá trị `null` hoặc `{"id": <đoạn KHÔNG trích>, "span": <một câu nguyên văn>}`.
- **Kiểm tra tất định**, sau khi tách trường này ra và chạy parser v0.5:
  - `id` là đoạn được trích hoặc không tồn tại → lý do kỹ thuật `context_id_invalid`;
  - `span` không nằm nguyên văn trong đoạn đó hoặc quá ngắn → lý do kỹ thuật `context_span_not_verbatim`;
  - `span` nguyên văn nhưng **không phải câu trọn vẹn** (không bắt đầu ở đầu câu hoặc không kết thúc ở cuối câu; được phép thiếu dấu chấm cuối, được phép nhiều câu liên tiếp) → lý do kỹ thuật `context_span_not_whole_sentence`. Lý do giữ yêu cầu trọn câu: ở B, các mảnh câu ngắn đã làm rơi điều kiện (F06);
  - hợp lệ → lý do nội dung `context_limit:<id>`.

  Các lý do kỹ thuật vẫn loại nhận định (cách làm thận trọng như v0.5), nhưng **được báo riêng và không bao giờ tính là bắt đúng lỗi**.
- **Lỗi schema:** thiếu trường, sai kiểu hoặc có khóa lạ → `verifier_output_invalid` (lỗi hệ thống, báo riêng).
- **Giới hạn chưa có bảo đảm tất định:** model thấy toàn bộ catalog, nên vẫn có thể chấm `supported` nhờ một đoạn **không trích**, rồi chọn một câu có thật nhưng không đủ sức chứng minh trong đoạn được trích làm `evidence_span`. Parser không phát hiện được lỗi ngữ nghĩa này. Nguy cơ được **đo** bằng CR1/CR2 (R3) chứ không được ngăn chặn.
- **Không đặt kỳ vọng sửa F01 hay A01:** các đoạn liên quan đã nằm trong phần được trích nhưng verifier vẫn hiểu sai. Hai ca này tiếp tục là ca theo dõi và kiểm tra hồi quy.

**Rủi ro đã biết:**

- Prompt dài thêm có thể làm lệch phần kiểm tra cũ hoặc gây lẫn schema, như đã thấy ở v0.6 và v0.7. Vì vậy có R4, R5 và đo nhóm 5 đến 6 nhận định.
- Ca sạch P08 nằm cạnh E1 "mạnh hơn" là nguy cơ báo nhầm lớn nhất.
- Chỉ có 2 ca phát hiện (F02, CD1), cùng một câu hỏi và gần như cùng một lỗi. Nếu đạt, kết quả chỉ chứng minh trong phạm vi hẹp đó.

## 3. Đo: tiêu chí ở `evaluation/trials/verifier_c_small/criteria.json` (bản nháp)

**Chặng baseline** (v0.5, 20 lượt): các ca C chạy đơn ×3 và GC1 ×2. Chặng này chỉ để kiểm tra nhãn và để quy kết quả, không dùng để chấm.

**Chặng thử nhỏ** (contract v0.8 bật C, 37 lượt):

- ca đơn ×3: F02, P08, A04, CD1, CC1–CC3, CR1, CR2;
- nhóm ×2: G1, G5 (đầy đủ và sau chốt), G6, GC1.

| Quy tắc | Điều kiện đạt |
|---|---|
| R1 | F02 và CD1 bị loại ở **mọi** lần, cả đơn lẫn nhóm (G1, GC1), **đúng đoạn và đúng câu**: lý do đúng chính xác `context_limit:E2`; câu được trích chứa một trong hai câu E2 đã đăng ký trước ("these conclusions are still premature…", hoặc "studies have failed to provide conclusive evidence … low-functioning…"); **không** kèm lý do kỹ thuật nào. Trích đúng ID nhưng sai câu thì không tính |
| R2 | CC1, CC2, CC3, P08, A04 và các ca sạch trong G1, G5, G5 sau chốt, G6, GC1 **không bao giờ** bị loại |
| R3 | CR1, CR2 bị loại với lý do support khớp chính xác (`support_not_supported` / `partially_supported` / `contradicted`) |
| R4 | F16, F17 (G5, G5 sau chốt) và F12–F14 (G6) vẫn bị bắt vì lý do nội dung |
| R5 | Không có đầu ra hỏng hoặc bị cắt, **và** không có ID đoạn sai, câu trích không nguyên văn hoặc không trọn câu (`context_*`). `span_not_in_cited_evidence` của v0.5 được báo riêng |
| R6 | Mọi lượt gọi ≤ 2.048 token |

`check_trial.py` **từ chối chấm** nếu thiếu bất kỳ ca, nhóm hay lần lặp nào.

**Phạm vi kết luận:** nếu đạt hết, đây chỉ là cải thiện hẹp trên lỗi bỏ mức thận trọng ở S05 (2 ca phát hiện), chưa phải verifier đạt chất lượng chung.

**Quyết định:**

- Đạt hết → đo đầy đủ.
- Trượt bất kỳ quy tắc nào → dừng C theo thiết kế này, không sửa prompt nhiều vòng. Hướng kế tiếp là cải thiện sinh/sửa, mỗi việc là một thử nghiệm riêng được duyệt.

## 4. An toàn khi chạy (đóng lỗi làm mất 10 phản hồi ngày 08/11)

- `measure_verifier.py` kiểm tra `--out` trước mọi lượt gọi: không có ký tự điều khiển hay khoảng trắng thừa, nằm dưới `reports/`, thư mục mới. Sau đó nó tạo `cache/` và ghi thử, đọc lại, xóa một file bằng đúng hàm ghi mà client dùng.
- **Sổ lượt gọi** `calls.jsonl` được ghi và `fsync` **trước** mỗi lượt gọi. Nếu không ghi được sổ thì không gọi. Tóm tắt báo riêng từng loại:
  - `started`: số lượt đã bắt đầu;
  - `saved_responses`: phản hồi đã lưu (chắc chắn tính phí, biết số token);
  - `cache_hits`: lấy từ cache, không gọi nhà cung cấp;
  - `errors` kèm `error_codes`: lượt lỗi;
  - `unresolved`: lượt bắt đầu mà không có phản hồi lẫn dòng lỗi;
  - `cost_unknown` = `errors` + `unresolved`: không coi là chắc chắn tính phí, cũng không coi là miễn phí.

  Ví dụ: lỗi ghi cache sau khi nhà cung cấp đã trả lời giờ hiện thành `started=1, saved_responses=0, errors=1, cost_unknown=1`.
- Gặp lỗi giữa chừng: ghi `results.partial.json` (bản ghi đã có, lỗi, tóm tắt sổ), dừng ngay và trả mã lỗi. Thư mục có file này không bao giờ được dùng lại tự động.
- `run_trial.py` chạy kế hoạch của file tiêu chí:
  - từ chối nếu `status` khác `registered`;
  - kiểm tra mọi lần chạy và contract của mã đang checkout trước lượt gọi đầu tiên;
  - gọi tiến trình con bằng danh sách tham số, không qua shell;
  - dừng ở lần chạy lỗi đầu tiên và ghi `trial_state.json` gồm done, failed, pending và tổng số lượt gọi.
