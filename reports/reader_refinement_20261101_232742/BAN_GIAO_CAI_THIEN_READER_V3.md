# Bàn giao cải thiện reader v3 — 02/11/2026

Đã hoàn tất triển khai và nghiệm thu kỹ thuật reader v3 tại E:/AI4LIFE/ASD_AGENT. Bản này lập kế hoạch câu hỏi, đọc nguyên văn nguồn, xác minh ID đoạn chứng minh và chuẩn bị context. Chưa bật model sinh câu trả lời cho người dùng; chưa có thẩm định lâm sàng độc lập.

## Xem nhanh

- [Hướng dẫn từng file, kiến trúc, cấu hình và cách chạy](../../rag/README_READER_V3.md).
- [Nghiệm thu máy đọc được](verification.json), [log kiểm thử](final_tests.txt).
- [Kết quả 23 câu cuối](results_latest_23.csv).
- [So sánh 6 ca trước/sau](comparison_development.csv).
- [Các ca cần đọc lại](review_queue.jsonl).
- [Danh sách ba run được nghiệm thu](evaluation_selection.json).

## Những thay đổi chính

**Câu hỏi phủ định.** Nhu cầu giải thích tách khỏi mệnh đề cần kiểm chứng. Với câu hỏi có/không, verifier đánh giá cùng một mệnh đề cố định; bác bỏ mệnh đề có thể là một câu trả lời có đủ căn cứ. Không đổi chiều nhận định chỉ để tăng điểm.

**Nguồn thực sự làm bằng chứng.** Ghi chú biên soạn về tuổi/chất lượng/giới hạn đã được loại khỏi payload chọn và kiểm tra nguồn. Model phải khai báo support_passage_ids có thật trong gói nguồn. Tên, tác giả/tổ chức, đường dẫn và ngày vẫn được giữ nguyên trong dữ liệu và gắn lại khi truy nguyên.

**Ngữ cảnh và so sánh.** Bộ chọn xét cả phần mở đầu mục cha và mục con, giữ đơn vị nguyên vẹn. Hai mục cùng nguồn phục vụ một nhu cầu so sánh được gộp rõ ràng; ngữ cảnh bổ sung được giữ trong context cuối và đếm token. Thứ tự văn bản cố định theo vị trí nguồn để phát lại ổn định.

**Mức hỗ trợ.** Trực tiếp nhưng mới đáp ứng một phần vẫn được tính một phần. Nhu cầu chưa có căn cứ vẫn bắt buộc. Liên kết model tự thêm không được cộng điểm; nhận định thiếu trích dẫn đoạn chính bị loại khỏi bằng chứng. Không dùng ghi chú quản lý hoặc tài liệu chưa thực sự truy xuất để nâng điểm.

**Lỗi và sửa schema.** HTTP/timeout được tách khỏi thiếu bằng chứng. Có tối đa một lượt yêu cầu sửa schema kế hoạch và một lượt chọn lại ID; không fuzzy-map ID nguồn, không tự thử lại lỗi mạng. Neo câu hỏi phối hợp có thể được đối chiếu theo thứ tự từ thực, giữ toàn bộ khoảng văn bản gốc và các điều kiện xen giữa; quy tắc này không áp dụng cho trích dẫn nguồn.

## Kết quả

| Bộ câu hỏi | Trace hợp lệ | Trạng thái khớp nhãn AI sơ bộ |
|---|---:|---:|
| 6 câu phát triển | 6/6 | 5/6 |
| 12 câu hồi quy mở rộng | 12/12 | 11/12 |
| 5 câu bổ sung cuối | 5/5 | 4/5 |

Tổng cộng 23/23 trace hợp lệ và 20/23 trạng thái khớp nhãn sơ bộ. Nguồn tham chiếu xuất hiện trong top 5 ở 16/18 câu có nguồn dự kiến.

Đây không phải độ chính xác y khoa. Nhãn do AI đọc nguồn, không phải bộ đáp án được bác sĩ duyệt; bộ nguồn tham chiếu chưa đầy đủ. Nhãn và source ID dự kiến không được gửi cho model. Các lần chạy lại dùng cache không phải các mẫu đánh giá độc lập.

Sáu câu phát triển và 12 câu mở rộng đã được dùng phát hiện lỗi nên được coi là hồi quy. Năm câu F được chốt sau khi siết đầu vào nguồn, trước lần chạy đầu: lần đầu có 3/5 trace hợp lệ, hai lỗi schema; kết quả cuối là bản đã sửa/phát lại. Không gọi kết quả cuối là một holdout chưa từng quan sát.

## Sáu ca trước và sau

| Ca | V2 cuối | V3 cuối |
|---|---|---|
| S05 | insufficient | sufficient |
| S07 | insufficient | partially_sufficient |
| S08 | insufficient | sufficient |
| H03 | insufficient | sufficient |
| H04 | sufficient | sufficient |
| H05 | sufficient | insufficient |

H03 hiện đọc được đoạn NIH-NIMH-MEDICATIONS từng bị bỏ qua. H04 có các định nghĩa nguyên văn về ba nhóm biểu hiện. S07 giữ mức một phần khi chưa có đoạn trực tiếp đủ cho toàn bộ câu hỏi; không bảo đảm tăng lời nói từ một kết quả nghiên cứu chung.

Các ca cần tiếp tục xử lý:

- **H05 và N02:** nguồn NIMH phù hợp có trong kho nhưng chưa ở top 5 của các câu này. Không dùng việc đọc thêm nguồn đó để nâng điểm run. Đây là ưu tiên cho truy xuất bổ sung.
- **F02:** tài liệu NIDCD đã được tìm thấy, nhưng một nhận định của model trỏ không đúng đoạn chính nên bị loại; kết quả giữ mức một phần. Cần cải thiện việc chọn/căn cứ trích dẫn.
- **N04:** nội dung phương pháp được đọc; phần giới hạn chưa được hỗ trợ đủ trong ngữ cảnh được chọn. Cần đọc sâu thêm phần phù hợp trong chính nguồn.
- **S07:** cần duyệt riêng căn cứ về phối hợp AAC với lời nói và căn cứ về kết quả phát triển lời nói.

Các quan sát này là rà soát kỹ thuật/nội dung bằng AI, chưa phải kết luận lâm sàng độc lập. Không sửa nhãn để làm kết quả đẹp hơn.

## Nghiệm thu và dữ liệu được giữ nguyên

- 115 kiểm thử đạt, không lỗi hoặc bỏ qua.
- 23 trace v3 phát lại từ cache, khớp assessment/policy/context; các trích dẫn và đoạn hỗ trợ được đối chiếu vị trí với PostgreSQL.
- 20 trace v2 phát lại giống trước; 30 truy vấn cũ giữ nguyên thứ hạng và cosine_distance.
- Snapshot database, 33 tài liệu/33 vector và 132 tệp nguồn không đổi. Không tạo lại embedding tài liệu, không chia vector theo đoạn, không thay collection/profile.
- Có tạo cache vector cho 17 câu hỏi mới; đó là vector truy vấn, không phải vector tài liệu trong database.
- Lượt audit không gọi API. Các mẫu request hoàn thành dùng trong nghiệm thu có delta token local/provider bằng 0; không suy thành bảo đảm cho mọi request tương lai.

Các run lỗi, phản hồi model bị chặn và cache thành công được giữ nguyên. Đã gặp HTTP 503/timeout, lỗi ID và các lỗi schema. Có phát hiện model viện dẫn ghi chú quản lý nguồn trong run trước siết đầu vào; kết quả đó bị chặn và không thuộc nghiệm thu cuối. Mỗi run có fingerprint code/config; không trộn số liệu trước/sau sửa.

## File và cách dùng

Các file mới chính: rag/semantic_reader_v3.py, deployments/semantic_reader_v3.json, hai script evaluate_reader_v3.py / verify_reader_v3.py và tests/test_semantic_reader_v3.py. Evidence/context được mở rộng riêng cho giao thức v3; mã/config retriever và reader v2 giữ nguyên. Bản trước sửa nằm trong previous_files.json; manifest bàn giao ghi hash artifact hiện tại.

CLI mặc định v3; thêm --reader-version v2 để đối chiếu. Không truyền adapter mới thì EvidencePipeline vẫn giữ luồng review tường minh trước đó. Chatbot cũ chưa được chuyển sang sinh câu trả lời.

Lệnh nghiệm thu chỉ dùng cache, với PostgreSQL đang chạy:

```powershell
.\.venv-embedding\Scripts\python.exe -B scripts/evaluation/verify_reader_v3.py
```

Lệnh dừng nếu cache thiếu, nguồn/config đổi hoặc kết quả không khớp. Xem hướng dẫn v3 để chạy câu mới và cấu hình khóa; không đưa khóa vào báo cáo.

## Bước tiếp theo

1. Thêm nhánh agent tìm kiếm bổ sung khi thiếu nguồn và đọc sâu thêm mục khi đã có đúng tài liệu. Lưu truy vấn thực tế và kết quả từng lượt; chấm riêng top 5 ban đầu với ngữ cảnh bổ sung.
2. Cải thiện/kiểm tra lại căn cứ trích dẫn ở F02, đối chiếu hàng chờ với người có chuyên môn và bộ câu hỏi mới.
3. Nối tầng trả lời tiếng Việt có dẫn nguồn ở chế độ thử nghiệm. Chấm riêng độ đúng, đầy đủ, câu–nguồn, giữ giới hạn và từ chối; chưa coi đây là ứng dụng tư vấn y khoa đã kiểm nghiệm.

Kho nguồn đã đối chiếu phục vụ nghiên cứu; chưa có thẩm định lâm sàng độc lập.
