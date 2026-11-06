# Bổ sung nguồn theo bốn chủ đề còn thiếu

Ngày đối chiếu: 30/10/2026. Kho đích: E:/AI4LIFE/ASD_AGENT.

Giữ nguyên 27 tài liệu; thêm 6 tài liệu đạt kiểm tra chuyển đổi. Tập chính hiện có **33 tài liệu, 2,307,606 ký tự**, tăng 399,532 ký tự. Đã lưu thêm 7 bản gốc và bản chuyển đổi chờ xử lý, không cộng chúng vào tập chính. Chưa thực hiện embedding, gọi LLM hoặc thay database.

**Đây là kho nguồn nghiên cứu chưa có thẩm định lâm sàng độc lập.** Các nhận xét dưới đây là metadata biên tập/đối chiếu, không phải văn bản nguồn hay quyết định điều trị.

## Kết quả theo yêu cầu

| Nhóm | Đã thêm vào tập chính | Đã lấy bản gốc nhưng còn chờ | Phần chưa đáp ứng |
|---|---|---|---|
| Can thiệp sớm | CDC Early Intervention; CDC Treatment; tổng quan nền tảng NDBI | Project AIM cập nhật | Chưa có toàn văn AAP được xác minh quyền; NDBI 2015 không phải guideline hiện hành. |
| Ngôn ngữ/trị liệu ngôn ngữ | NDBI có phần dạy ngôn ngữ và giao tiếp; CDC có phần can thiệp ngôn ngữ | Tổng quan NDBI + AAC; tổng quan giao tiếp ở trẻ ít lời | Chưa có ASHA Practice Portal được xác minh quyền; chưa coi độ sâu speech-language therapy là hoàn tất. |
| OT/can thiệp cảm giác | Tổng quan ASI 2019; tổng quan SBI 2025 | Phân tích phương pháp SI/SP; báo cáo SenITA 2022 đầy đủ PDF | Chưa có toàn văn AOTA được xác minh quyền. Cần giữ bằng chứng không đồng nhất và giới hạn quần thể. |
| Kỹ năng xã hội/PEERS/SST | Thử nghiệm Social Stories ASSSIST-2 và phụ lục | RCT PEERS Ba Lan; tổng quan SST vị thành niên | Chưa nhận PEERS/SST vào tập chính do còn biểu đồ; không có giáo trình PEERS được cấp phép. |

Bốn nhóm đã được bổ sung tài liệu thực chất, nhưng chưa thể công bố tất cả đều đạt độ phủ đầy đủ hoặc chuẩn thực hành lâm sàng.

## Sáu tài liệu được nhận về mặt chuyển đổi

| Tài liệu / nguồn | Loại và ngày nguồn | Ký tự nội dung | Giới hạn cần giữ |
|---|---|---:|---|
| [ASD-SUP-PMC4513196](../../knowledge/rag/source_library/documents/ASD-SUP-PMC4513196.md) — [Naturalistic Developmental Behavioral Interventions: Empirically Validated Treatments for Autism Spectrum Disorder](https://pmc.ncbi.nlm.nih.gov/articles/PMC4513196/) | research; 2015-3-4 | 100,426 | NDBI nền tảng, trẻ nhỏ. Bài bình luận 2022 về cách đơn giản hóa ngôn ngữ đầu vào được ghi ở metadata; không đưa ra đơn thuốc ngôn ngữ cố định. |
| [ASD-SUP-PMC6590432](../../knowledge/rag/source_library/documents/ASD-SUP-PMC6590432.md) — [A systematic review of ayres sensory integration intervention for children with autism](https://pmc.ncbi.nlm.nih.gov/articles/PMC6590432/) | research; 2018-12-12 online; số báo 2019 | 87,015 | ASI có tiêu chí fidelity, kết luận cho trẻ 4–12 trong phạm vi chọn nghiên cứu; khác mọi hoạt động cảm giác. Cần đối chiếu nghiên cứu SenITA mới hơn. |
| [ASD-SUP-PMC12658592](../../knowledge/rag/source_library/documents/ASD-SUP-PMC12658592.md) — [Systematic review of sensory-based interventions for children and youth (2015–2024)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12658592/) | research; 2025-11-13 | 98,175 | SBI, tiêu chí tuổi 0–21 và nhiều chẩn đoán; không suy thành bằng chứng cho mọi trẻ ASD hoặc an toàn cho trẻ sơ sinh. |
| [ASD-SUP-PMC11754701](../../knowledge/rag/source_library/documents/ASD-SUP-PMC11754701.md) — [Autism Spectrum Social Stories in Schools Trial 2 (ASSSIST‐2): a pragmatic randomised controlled trial of the Social Stories™ intervention to address the social and emotional health of autistic children in UK primary schools](https://pmc.ncbi.nlm.nih.gov/articles/PMC11754701/) | research; 2024-12-17 online; số báo 2025 | 101,974 | Trẻ 4–11 tại Anh. Kết quả chính ITT không có ý nghĩa thống kê; cải thiện mục tiêu cá nhân không đồng nghĩa cải thiện xã hội toàn diện. |
| [CDC-EARLY-INTERVENTION](../../knowledge/rag/source_library/documents/CDC-EARLY-INTERVENTION.md) — [Early Intervention](https://www.cdc.gov/act-early/early-intervention/) | official_health_education; 2025-09-04 | 3,478 | Hướng dẫn tiếp cận dịch vụ Hoa Kỳ; không áp quyền lợi/điều kiện dịch vụ vào Việt Nam. |
| [CDC-ASD-TREATMENT](../../knowledge/rag/source_library/documents/CDC-ASD-TREATMENT.md) — [Treatment and Intervention for Autism Spectrum Disorder](https://www.cdc.gov/autism/treatment/index.html) | official_health_education; Ngày hiển thị 2024-05-16 | 8,464 | Tổng quan giáo dục sức khỏe, không phải guideline AAP/ASHA/AOTA; các cách can thiệp được nêu không có nghĩa hiệu quả ngang nhau. |

Các nghiên cứu giữ phương pháp, kết quả, thảo luận, hạn chế, tài liệu tham khảo và phần bổ sung đã chuyển đổi trong cùng tệp. Hai trang CDC là toàn bộ văn bản bài qua bản đọc web, không phải bản HTML gốc; giới hạn kỹ thuật/ảnh minh họa được ghi trong hồ sơ.

## Bảy tài liệu đã lấy bản gốc, chưa nhận bản chữ vào tập chính

| ID / tài liệu | Phần còn chờ | Bản gốc |
|---|---|---|
| [ASD-SUP-PMC9399988 — Effects of Social Skills Training for Adolescents on the Autism Spectrum: a Randomized Controlled Trial of the Polish Adaptation of the PEERS® Intervention via Hybrid and In-Person Delivery](../../knowledge/rag/source_library/pending_documents/ASD-SUP-PMC9399988.md) | graphic: asset_not_transcribed; media: asset_not_transcribed; supplementary-material: external_supplement_not_transcribed | [Bản gốc](../../knowledge/rag/source_library/originals/ASD-SUP-PMC9399988/snapshot-2026-10-30-79b838660c2a.xml) |
| [ASD-CSV-017 — The Effect of Naturalistic Developmental Behavioral Interventions and Aided AAC on the Language Development of Children on the Autism Spectrum with Minimal Speech: A Systematic Review and Meta-analysis](../../knowledge/rag/source_library/pending_documents/ASD-CSV-017.md) | graphic: asset_not_transcribed | [Bản gốc](../../knowledge/rag/source_library/originals/ASD-CSV-017/snapshot-2026-10-30-5781aa3d9598.xml) |
| [ASD-SUP-PMC7726187 — Evaluating Sensory Integration/Sensory Processing Treatment: Issues and Analysis](../../knowledge/rag/source_library/pending_documents/ASD-SUP-PMC7726187.md) | graphic: asset_not_transcribed | [Bản gốc](../../knowledge/rag/source_library/originals/ASD-SUP-PMC7726187/snapshot-2026-10-30-f6af3509a3df.xml) |
| [ASD-SUP-PMC10981608 — The Methodological Quality and Intervention Fidelity of Randomised Controlled Trials Evaluating Social Skills Group Programs in Autistic Adolescents: A Systematic Review and Meta-analysis](../../knowledge/rag/source_library/pending_documents/ASD-SUP-PMC10981608.md) | graphic: asset_not_transcribed | [Bản gốc](../../knowledge/rag/source_library/originals/ASD-SUP-PMC10981608/snapshot-2026-10-30-61e6a123a480.xml) |
| [ASD-SUP-PMC13414371 — Interventions to Promote Communication in Minimally Verbal Autistic Children: A Systematic Review](../../knowledge/rag/source_library/pending_documents/ASD-SUP-PMC13414371.md) | graphic: asset_not_transcribed; media: asset_not_transcribed; supplementary-material: external_supplement_not_transcribed | [Bản gốc](../../knowledge/rag/source_library/originals/ASD-SUP-PMC13414371/snapshot-2026-10-30-d59a3ead99f5.xml) |
| [ASD-SUP-PMC10783429 — Autism intervention meta-analysis of early childhood studies (Project AIM): updated systematic review and secondary analysis](../../knowledge/rag/source_library/pending_documents/ASD-SUP-PMC10783429.md) | bibliographic_version: needs_relationship_review; graphic: asset_not_transcribed; media: asset_not_transcribed; supplementary-material: external_supplement_not_transcribed | [Bản gốc](../../knowledge/rag/source_library/originals/ASD-SUP-PMC10783429/snapshot-2026-10-30-863bcee24be9.xml) |
| [NIHR-SENITA-2022 — Sensory integration therapy for children with autism and sensory processing difficulties: the SenITA RCT](../../knowledge/rag/source_library/pending_documents/NIHR-SENITA-2022.md) | figures: needs_complete_visual_transcription; pdf_layout: needs_table_order_and_symbol_review | [Bản gốc](../../knowledge/rag/source_library/originals/NIHR-SENITA-2022/snapshot-2026-10-30-f29fad003271.pdf) |

ASD-CSV-017 đã có trong danh mục trước đây nên dùng lại ID, không tạo một nguồn thứ hai. Với Project AIM, quan hệ phiên bản/DOI gần giống nhau còn chờ xác minh; không cộng như hai bằng chứng độc lập. SenITA có đủ **172 trang PDF vật lý**, gồm phần đầu/cuối và phụ lục; không nhầm số trang PDF với trang nội dung đánh số của báo cáo. Bản Markdown SenITA là văn bản trích từng trang, chưa xác nhận thứ tự bảng/ký hiệu/hình.

## Hồ sơ chỉ có thông tin và link, chưa sao chép toàn văn

| Nguồn | Trạng thái và lý do |
|---|---|
| [AAP-ASD-CLINICAL-2020 — Identification, Evaluation, and Management of Children With Autism Spectrum Disorder](https://publications.aap.org/pediatrics/article/145/1/e20193447/36917/Identification-Evaluation-and-Management-of) | Free to read is not verified permission to reproduce full content for this AI corpus. Publisher PDF says copyrighted AAP property; reaffirmed October 2025. |
| [ASHA-AUTISM-PORTAL — Autism and Autism Spectrum Disorder](https://www.asha.org/practice-portal/clinical-topics/autism/) | Practice Portal consulted; no explicit corpus/AI reuse permission established. Metadata/link only, no copied full-text substitute. |
| [AOTA-ASD-SERVICES-2022 — Autism Spectrum Disorders Across the Life Course and Occupational Therapy Services](https://doi.org/10.5014/ajot.2022.76S3002) | Official AOTA document; copyright reserved. General AOTA terms restrict reproduction; no separate AI reuse permission established. |
| [ASD-SUP-PMC8862714 — Understanding the Effects of Naturalistic Developmental Behavioral Interventions: A Project AIM Meta-analysis](https://pmc.ncbi.nlm.nih.gov/articles/PMC8862714/) | No recognized permitted OA reuse license established by the OAI/license gate; do not add full article to accepted corpus. |

Miễn phí đọc không tự động đồng nghĩa được phép sao chép toàn văn cho kho AI. Không gửi yêu cầu xin phép, thanh toán hoặc tự gán giấy phép. Các nguồn PMC được lấy qua OAI-PMH, có kiểm tra quyền từng bài và metadata phiên bản; kiểm tra đính chính/rút bài là snapshot, không bảo đảm đầy đủ mọi cập nhật trong tương lai.

## Các chi tiết y khoa đã giữ giới hạn

- ASI khác SBI và khác toàn bộ hoạt động trị liệu nghề nghiệp; không suy ra chỉ dẫn ép sâu/chăn nặng tại nhà.
- Tổng quan ASI tìm trong 2006–2017 có ba nghiên cứu cuối cùng. SenITA 2022 không thấy lợi ích có ý nghĩa ở kết quả chính so với chăm sóc thường lệ; không dùng tổng quan cũ để khẳng định đồng thuận hiện tại. Khác biệt kết quả/thiết kế cần chuyên gia đánh giá.
- ASSSIST-2: giữ khoảng tin cậy có dấu âm (−4.18 đến 0.96), p=.220 cho kết quả chính; không đổi thành thử nghiệm chứng minh hiệu quả toàn diện.
- PEERS Ba Lan: tiêu chí tuổi 11–18 nhưng mẫu thực tế 11.8–16.1; không đổi thành bằng chứng cho mọi trẻ 0–18.
- Các tổng quan có thể dùng chung nghiên cứu. Chưa có đánh giá độc lập để coi chúng là các khối bằng chứng không trùng.
- Chưa dịch/biên soạn lại để thay văn bản gốc; agent giải thích tiếng Việt là bước sau.

## Kiểm tra và bước tiếp theo

verification.json ghi kết quả kiểm tra thực tế: 17 kiểm thử, hash nguồn/tài sản/Markdown, khớp JSON, giữ nguyên 27 hồ sơ và tệp nguồn ban đầu, tách tập chờ và kiểm tra lại phép chuyển đổi. Cache chứa một số trang báo lỗi HTTP 200; chúng được ghi vào invalid_cache_inputs.json và không nhận làm dữ liệu nguồn.

Bước tiếp theo ưu tiên đối chiếu hình/bảng/phụ lục và quan hệ phiên bản của bảy tài liệu chờ, tìm nguồn speech-language therapy có quyền phù hợp hoặc xác minh quyền ASHA/AAP/AOTA, rồi nhờ chuyên gia thẩm định các nhận định. Chỉ sau đó chốt tập đem thử embedding; chưa thể coi việc nhúng là bước còn thiếu duy nhất.

DATA_TRANSFER_MANIFEST.json được giữ làm lịch sử sao chép ban đầu. SUPPLEMENT_20261030_MANIFEST.json là snapshot hash mới; index_preview.jsonl vẫn chỉ có 183 mục của 27 tài liệu cũ.
