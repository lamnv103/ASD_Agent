> **ĐÍNH CHÍNH 07/11/2026 — đọc trước.** Một số số liệu trong tài liệu này đã được kiểm định lại và sửa trong [KIEM_DINH_DOC_LAP_VA_UU_TIEN.md](KIEM_DINH_DOC_LAP_VA_UU_TIEN.md):
> - Chỉ số truy xuất ở A2 thiếu 27 câu của retrieval_v1 và đếm lặp H05. Số đúng: hit@5 0,964, MRR 0,779 trên 55 câu duy nhất; hit@1 khoảng 0,66 (xem `.	asks.ps1 diag`).
> - "Vector trung bình nhiều chủ đề" là giả thuyết, chưa được chứng minh.
> - 22/156 lỗi (14%) là lịch sử phát triển, không phải độ tin cậy khi phục vụ. Độ trễ đã có telemetry: tổng các stage NIM mỗi câu có trung vị khoảng 27 giây.
> - Tổng số test là 149 (nay 157), không phải 133. Con số "35% hoàn thành" không có cơ sở tính.
> - Kế hoạch 8 tuần ở Phần C được thay bằng thứ tự ưu tiên trong bản kiểm định độc lập và [docs/MVP_SCOPE_DRAFT.md](../../docs/MVP_SCOPE_DRAFT.md).

# ASD_AGENT — Đánh giá hiện trạng và kế hoạch hoàn thiện RAG Agent

Ngày đánh giá: 06/11/2026. Người đánh giá: rà soát kỹ thuật bằng AI (không phải thẩm định lâm sàng).
Phạm vi: mã nguồn `rag/`, `scripts/`, `tests/`, dữ liệu `knowledge/`, `evaluation/`, các báo cáo bàn giao tới 02/11/2026, PostgreSQL `deployments-rag-db-1` (pgvector, cổng 5433).

---

## Phần A — Kết quả kiểm tra thực tế hôm nay

### A1. Tái lập nghiệm thu (DB đang chạy, không gọi API)

| Hạng mục | Kết quả | Ghi chú |
|---|---|---|
| `retriever.health()` | OK — 33 tài liệu, 33 vector, 1536 chiều, read-only | Collection `asd_fulltext_33_20261030_26eb017efca5` |
| `tests/` (unittest) | **115/115 đạt** | Bắt buộc `PYTHONPATH=.`; không có lệnh chuẩn được ghi lại |
| `scripts/embedding` tests | 8/8 và 9/9 đạt | |
| `scripts/source_library` test | **Lỗi import** `bs4` | Pipeline nguồn phụ thuộc venv cũ `E:\AI4LIFE\Carobud_ASD_2026\.venv-rag` không còn tồn tại |
| `verify_evidence_context.py` | VERIFIED — 30 truy vấn giữ nguyên thứ hạng/khoảng cách | |
| `verify_semantic_reader.py` | Đạt kỹ thuật; 16/20 khớp nhãn sơ bộ (v2) | |
| `verify_reader_v3.py` | Đạt — 23 trace phát lại, 44 span hợp lệ, 0 API call | Script ghi đè `final_tests.txt` trong thư mục báo cáo cũ (tác dụng phụ) |

**Kết luận A1:** phần đã làm *tái lập được* khi DB chạy. Pipeline dữ liệu nguồn *không* tái lập được trên máy hiện tại.

### A2. Chẩn đoán truy xuất độc lập (mới, offline)

Script: `scripts/evaluation/diagnose_retrieval_offline.py` — dùng 73 vector câu hỏi đã cache, xếp hạng **toàn bộ 33 tài liệu**, đối chiếu với nhãn nguồn của 5 bộ đánh giá reader. Kết quả đầy đủ: `retrieval_diagnostics.txt`.

| Chỉ số (34 câu có nguồn kỳ vọng) | Giá trị |
|---|---|
| hit@1 | **0.647** |
| hit@3 | 0.853 |
| hit@5 | 0.912 |
| hit@10 | 0.912 (không cải thiện từ 5 → 10) |
| MRR (toàn bộ xếp hạng) | 0.758 |
| Ca trượt | H05 (hạng **19/33**), N02 (hạng **20/33**) — cả hai đều là `NIH-NIMH-ASD-2025` |
| Khoảng cách cosine hạng 1 → hạng 5 (trung vị) | 0.099 (min 0.010) — rất sát, xếp hạng dễ dao động |

**Hiện tượng "hub" (tài liệu chiếm top-5):**

| Tài liệu | Có mặt trong top-5 | Độ dài |
|---|---|---|
| ASD-OA-PMC6487529 | 44% số câu | 73k ký tự |
| ASD-OA-PMC13005892 | 40% | 110k |
| ASD-CSV-002 | 38% | 100k |
| ASD-CSV-091 | 30% | 129k |
| CDC-ASD-TREATMENT, ASD-OA-PMC10018050 | **0% — không bao giờ vào top-5 trong 73 câu** | |

Tương quan độ dài tài liệu ↔ tần suất vào top-5: 0.32.

**Diễn giải:** vector toàn văn của bài nghiên cứu dài là "trung bình" của nhiều chủ đề, nên gần với mọi câu hỏi chung về tự kỷ, đẩy các trang tổng quan ngắn và chính xác hơn (NIMH, CDC) xuống dưới. Con số hit@5 = 1.0 trong báo cáo retrieval_v1 *lạc quan hơn thực tế*: trên các bộ câu reader, hit@1 chỉ ~0.65. **Đây là điểm nghẽn số 1 của dự án**, và tăng top_k không giải quyết được (hit@10 = hit@5).

### A3. Chất lượng bộ đánh giá

- 23 câu cuối, 18 câu đã dùng để sửa lỗi → thực chất là bộ hồi quy.
- "Final holdout" 5 câu: 4/5 câu ghi tên nguồn trong câu hỏi ("Theo NIMH…", "Theo NIDCD…", "CDC mô tả…") → không đại diện cho người dùng thật; 2/5 lỗi schema ở lần chạy đầu rồi chạy lại.
- S05 và S08 được chấm `sufficient` nhưng không dùng đoạn tham chiếu (`reference_span_overlap_used=False`) → cần người đọc lại; có thể đúng, có thể là reader "đủ" quá dễ.
- 5 câu ngoài phạm vi khớp nhãn `insufficient` là hiển nhiên; tỷ lệ khớp trên câu có nội dung ≈ 15/18.
- 100% nhãn do AI gán; 0 câu được chuyên gia duyệt; không có đo đồng thuận giữa người chấm.

### A4. Độ tin cậy vận hành (từ 23 thư mục run)

- 156 lượt câu hỏi, **22 lỗi (14%)**: `reader_no_context` 6, `v3_verifier_schema` 5, `nim_http` (503) 4, `nim_network` (timeout) 4, `v3_plan_schema` 2, `v3_selection_schema` 1.
- Mỗi câu mới: 1 Cohere embed + 3–4 lượt Nemotron-3-Ultra 550B. Độ trễ thật **chưa được đo** (số 1–2 giây trong CSV là phát lại cache).

### A5. Kỹ thuật & bảo trì

| Vấn đề | Bằng chứng | Mức |
|---|---|---|
| Không có git | Thư mục không phải repo; phiên bản cũ lưu trong `previous_files.json` | Cao |
| Đường dẫn E: cứng | `supplement_20261030.py:263` chặn mọi thư mục khác `E:\AI4LIFE\ASD_AGENT`; README, audit script | Cao |
| Bí mật | `.env` là YAML Continue chứa khóa NVIDIA thô; tên file gây nhầm với dotenv | Cao |
| Mã dồn nén | Dòng 517 ký tự, nhiều câu lệnh/dòng bằng `;` (v3: 43 dòng) | Trung bình |
| v2 và v3 song song | ~700 dòng trùng chức năng | Trung bình |
| Phụ thuộc | Ghim theo khoảng, không lockfile; venv dựa trên miniconda base; `bs4` thiếu | Trung bình |
| Dung lượng | `reports/` 107 MB, tokenizer 17 MB nằm trong cây mã | Thấp |
| Tài liệu | Lỗi mã hóa ký tự ("c?u ph?t tri?n") trong bàn giao v3 và README v3 | Thấp |

### A6. Điểm mạnh cần giữ

- Truy nguyên nguồn chặt: ID đoạn, offset, hash, đối chiếu DB; model không thể tự tạo trích dẫn.
- Thiết kế fail-closed: tách lỗi mạng khỏi "thiếu bằng chứng", giới hạn lượt sửa schema, chặn yêu cầu kê liều/chẩn đoán cá nhân.
- Kỷ luật đánh giá: đóng băng input, fingerprint code/config, giữ run lỗi, không sửa nhãn.
- Giao thức v3 (mệnh đề cố định cho câu có/không, annotation riêng mỗi cặp đoạn–nhu cầu) là thiết kế tốt, hiếm thấy.

### A7. Ước lượng tiến độ

| Thành phần của RAG Agent hoàn chỉnh | Trạng thái | % |
|---|---|---|
| Kho nguồn & giấy phép | 33 tài liệu, 7 chờ duyệt, chưa có nguồn tiếng Việt | 60% |
| Chỉ mục & truy xuất | Chỉ 1 vector/tài liệu, không hybrid, không rerank | 30% |
| Đọc bằng chứng / context | v3 tốt | 75% |
| Vòng lặp agent (tìm lại, đọc sâu) | Chưa có | 0% |
| Sinh câu trả lời tiếng Việt có trích dẫn | Chưa có | 0% |
| Đánh giá (bộ câu, nhãn người, chỉ số đầu cuối) | Nhỏ, AI-gán, chưa có holdout sạch | 25% |
| An toàn & quản trị lâm sàng | Guard intent có; chưa red-team, chưa chuyên gia | 20% |
| Vận hành (API, retry, quan sát, SLO) | Chưa có | 5% |
| **Tổng thể (có trọng số)** | | **≈ 35%** |

---

## Phần B — Mục tiêu "xuất sắc" (Definition of Done)

Một RAG Agent tư vấn thông tin ASD đạt mức xuất sắc khi **đo được** trên bộ test sạch, có chuyên gia duyệt:

| Tầng | Chỉ số | Hiện tại | Mục tiêu |
|---|---|---|---|
| Truy xuất | hit@5 cấp tài liệu | 0.91 | ≥ 0.97 |
| | hit@1 cấp tài liệu | 0.65 | ≥ 0.85 |
| | recall@10 cấp đoạn tham chiếu | chưa đo | ≥ 0.90 |
| | tỉ lệ hub (tài liệu top-5 nhiều nhất) | 44% | ≤ 25% |
| Đọc / đủ bằng chứng | khớp nhãn sufficiency (người duyệt) | ~83% (AI) | ≥ 90% |
| Trả lời | độ đúng nội dung (chuyên gia chấm 1–5) | — | trung bình ≥ 4.3, không câu nào ≤ 2 về an toàn |
| | citation precision (câu có trích dẫn được nguồn hỗ trợ) | — | ≥ 0.95 |
| | citation recall (câu nội dung có trích dẫn) | — | ≥ 0.95 |
| | giữ giới hạn nguồn (tuổi, quốc gia, thiết kế nghiên cứu) | — | ≥ 0.95 |
| An toàn | từ chối đúng (chẩn đoán/liều cá nhân, khẩn cấp) | — | 100% trên bộ red-team |
| | từ chối sai (câu hợp lệ bị từ chối) | — | ≤ 5% |
| | prompt injection qua câu hỏi/nguồn thành công | — | 0 |
| Vận hành | tỉ lệ lỗi đầu cuối ở chế độ người dùng | 14% (chế độ eval) | ≤ 1% |
| | độ trễ p50 / p95 câu mới | chưa đo | ≤ 10 s / ≤ 25 s (streaming bắt đầu ≤ 3 s) |
| | chi phí / câu | chưa đo | được ghi và có ngưỡng |
| Kỹ thuật | tái lập từ máy sạch bằng 1 lệnh | không | có |

---

## Phần C — Kế hoạch chi tiết (8 tuần, 7 giai đoạn)

Nguyên tắc xuyên suốt: mỗi giai đoạn có **cổng nghiệm thu** đo được; giữ kỷ luật hiện có (đóng băng input, fingerprint, không sửa nhãn); mọi thay đổi chỉ mục tạo **collection mới**, collection 33 vector giữ làm baseline.

### Giai đoạn 0 — Nền móng kỹ thuật (2–3 ngày) — ƯU TIÊN NGAY

| # | Việc | Chi tiết | Nghiệm thu |
|---|---|---|---|
| 0.1 | Git | `git init`; `.gitignore` thêm `reports/**/run_*`, `reports/**/traces`, `reports/*cache*`, `deployments/tokenizers/`, `*.env`, `continue*.yaml`; commit baseline có tag `baseline-v3-20261102` | `git log` có tag |
| 0.2 | Bí mật | Đổi tên `.env` (YAML Continue) → `continue.config.yaml` ngoài repo; tạo `.env.example` dotenv chuẩn (`NVIDIA_API_KEY`, `COHERE_API_KEY`, `RAG_DATABASE_URL`); **đổi khóa NVIDIA** vì đã hiện trong log phiên rà soát | không có chuỗi `nvapi-` trong repo (`git grep`) |
| 0.3 | Đường dẫn | Thay mọi `E:\...` bằng `ROOT` tương đối; bỏ kiểm tra cứng ở `supplement_20261030.py:263` (thay bằng kiểm tra marker file) | grep `E:` = 0 trong mã |
| 0.4 | Môi trường | `pyproject.toml` + lockfile (`uv lock` hoặc `pip-compile`); gộp yêu cầu của `source_library` (bs4, lxml…) | `uv sync` trên máy sạch chạy được mọi test |
| 0.5 | Lệnh chuẩn | `tasks.ps1` (hoặc `Makefile`): `db-up`, `test`, `verify`, `diag`, `eval`; thêm `conftest`/`PYTHONPATH` | `./tasks.ps1 test` chạy toàn bộ 133 test |
| 0.6 | Format | ruff + ruff-format; chạy một lần cho `rag/`, `scripts/`, `tests/` (commit riêng, chỉ format) | ruff sạch, test vẫn 100% |
| 0.7 | Tác dụng phụ | `verify_*` chỉ ghi vào thư mục run mới, không ghi đè báo cáo cũ | hash báo cáo cũ không đổi sau verify |
| 0.8 | Tài liệu | Sửa lỗi mã hóa ký tự; README gốc ngắn gọn: kiến trúc, cách chạy, trạng thái | đọc được, không còn `?` lỗi |

### Giai đoạn 1 — Truy xuất thế hệ 2 (tuần 1–2) — ĐIỂM NGHẼN SỐ 1

Mục tiêu: sửa đúng lỗi đã đo ở A2 mà **không vi phạm nguyên tắc "không cắt rời điều kiện khỏi kết luận"**: chia đoạn chỉ để *tìm*; khi *đọc* vẫn lấy nguyên đơn vị/mục cha từ toàn văn.

1. **Chỉ mục phân cấp (hierarchical / parent-document)**
   - Cấp 0: giữ 33 vector toàn văn (baseline).
   - Cấp 1: mục theo heading Markdown (tận dụng `sections()`/`passage_units` đã có), 300–900 token, kèm `parent_section_id`, `source_id`, offset, hash, tiêu đề đường dẫn (breadcrumb: "Tài liệu › Mục › Mục con") gắn vào văn bản nhúng (contextual chunk header).
   - Ước tính: ~2–4k đơn vị cho 2.3M ký tự; Cohere embed-v4 đa ngôn ngữ nên câu hỏi tiếng Việt khớp nguồn tiếng Anh.
   - Collection mới, ví dụ `asd_sections_33_<hash>`; migration chỉ thêm bảng, không sửa bảng cũ.
2. **Hybrid search**
   - Dense (pgvector, HNSW hoặc exact vì quy mô nhỏ) trên cấp 1.
   - Lexical: Postgres full-text (`tsvector` tiếng Anh) hoặc BM25 trên cấp 1, dùng `search_terms` tiếng Anh mà planner v3 đã sinh (đã có sẵn — tận dụng làm query translation).
   - Hợp nhất bằng Reciprocal Rank Fusion (k=60).
3. **Rerank**: cross-encoder đa ngôn ngữ (Cohere `rerank-v3.5` hoặc NVIDIA `nv-rerankqa`) trên top-50 → top-12 đơn vị; gộp về tài liệu bằng max-score.
4. **Chống hub**: chuẩn hóa điểm theo tài liệu (giới hạn tối đa N đơn vị/tài liệu trong top-k), MMR cho đa dạng nguồn.
5. **Metadata filter / boost**: loại nguồn (hướng dẫn chính thức, tổng quan, RCT, nghiên cứu nhỏ), nhóm tuổi, quốc gia — lấy từ `core_catalog.jsonl`; boost nguồn tổng quan chính thức cho câu hỏi định nghĩa/khái quát.
6. **Đánh giá riêng tầng truy xuất** (mở rộng `diagnose_retrieval_offline.py`): hit@k cấp tài liệu, recall@k cấp span tham chiếu, MRR, nDCG@10, hub share, so sánh A/B với baseline trên cùng câu.

Cổng nghiệm thu G1: trên bộ dev hiện có + bộ mới (G2): hit@1 ≥ 0.85, hit@5 ≥ 0.97, H05/N02 có NIMH-ASD-2025 trong top-5, hub share ≤ 25%, CDC-ASD-TREATMENT xuất hiện khi câu hỏi về điều trị; 30 truy vấn cũ vẫn chạy được trên baseline.

### Giai đoạn 2 — Bộ đánh giá v2 có người duyệt (song song tuần 1–3)

1. **Phân loại câu hỏi (taxonomy)** — 14 nhóm, mỗi nhóm 6–10 câu, tổng ~120 câu:
   định nghĩa/khái niệm · dấu hiệu sớm theo tuổi · sàng lọc & quy trình chẩn đoán · can thiệp hành vi/giao tiếp/AAC · can thiệp sớm · thuốc & an toàn thuốc (giáo dục chung) · trường học & giáo viên · gia đình & chăm sóc · đồng mắc (ADHD, lo âu, trầm cảm, giấc ngủ, ăn uống) · vị thành niên · so sánh nhiều nguồn (multi-hop) · tiền đề sai / phủ định · ngoài phạm vi kho · yêu cầu cá nhân hóa (chẩn đoán, liều, khẩn cấp, tự hại).
2. **Cách viết câu**: giọng phụ huynh/giáo viên Việt Nam, **không ghi tên nguồn**, có câu viết tắt, không dấu, lỗi chính tả, câu dài nhiều ý; 10% câu tấn công (prompt injection, yêu cầu bỏ qua quy tắc).
3. **Chia tập**: dev 40 (được xem, dùng để sửa) / test 80 (đóng băng bằng hash, *không ai xem output trước khi chạy cuối*; mỗi vòng sửa lớn chỉ chạy test một lần và ghi lại).
4. **Nhãn**: AI soạn nháp (nguồn, span, sufficiency, ý chính bắt buộc của câu trả lời, giới hạn phải nêu) → **chuyên gia (bác sĩ nhi/tâm lý lâm sàng/âm ngữ trị liệu) duyệt toàn bộ test 80**; 20 câu do hai người chấm độc lập, báo cáo Cohen's κ (mục tiêu ≥ 0.7).
5. **Rubric chấm câu trả lời** (dùng ở G4): đúng nội dung, đầy đủ ý bắt buộc, trích dẫn đúng, giữ giới hạn, an toàn, dễ hiểu cho phụ huynh — mỗi tiêu chí 1–5, có ví dụ neo.

Cổng G2: 120 câu, test đóng băng có hash, ≥ 80 câu có chữ ký người duyệt, κ báo cáo.

### Giai đoạn 3 — Vòng lặp agent (tuần 3–4)

Biến pipeline tuyến tính thành **máy trạng thái có giới hạn** (tự viết hoặc LangGraph; giữ trace đầy đủ):

```
ROUTE(intent, an toàn) ─┬─ personal/emergency → ABSTAIN_WITH_REFERRAL
                        └─ general → PLAN(needs, propositions, EN search terms)
PLAN → RETRIEVE(hybrid+rerank) → READ(v3 select) → VERIFY(v3)
VERIFY ─┬─ sufficient → ANSWER
        ├─ partial/insufficient & lý do = retrieval_gap → REFORMULATE (≤2 vòng: tách nhu cầu thiếu, đổi thuật ngữ, lọc metadata)
        ├─ đúng tài liệu nhưng thiếu đoạn → DEEP_READ (mở rộng mục cha/mục lân cận trong cùng nguồn, ≤1 vòng)
        └─ vẫn thiếu → ANSWER_PARTIAL (nói rõ phần chưa có căn cứ) hoặc ABSTAIN
```

- Ngân sách cứng: tối đa 8 lượt LLM, 2 vòng tìm lại, 40k token đầu vào / câu.
- Mỗi vòng lưu query thực tế, kết quả, lý do chuyển trạng thái; đánh giá **tách riêng** "top-k ban đầu" và "sau vòng bổ sung" (như bàn giao v3 đã đề xuất).
- Giảm chi phí: dùng model nhỏ hơn (ví dụ Nemotron Super/Nano) cho ROUTE/PLAN/SELECT; giữ model lớn cho VERIFY/ANSWER; đo ảnh hưởng chất lượng trên dev trước khi đổi.
- Gộp v2 vào v3: sau khi v3 đạt parity, chuyển v2 sang `legacy/` và chỉ giữ để phát lại trace.

Cổng G3: trên dev, tỉ lệ `insufficient` do retrieval_gap giảm ≥ 50% so với G1; không câu nào vượt ngân sách; trace phát lại tất định từ cache.

### Giai đoạn 4 — Sinh câu trả lời tiếng Việt có trích dẫn (tuần 4–6)

1. **Đầu vào duy nhất** là context v3 (đoạn chứng minh + phạm vi + giới hạn); generator không thấy gì khác.
2. **Định dạng đầu ra có cấu trúc** (JSON → render): danh sách câu, mỗi câu nội dung có `citations: [passage_id]`; trường `limitations`, `when_to_see_professional`, `unanswered_needs`.
3. **Kiểm tra sau sinh (fail-closed)**:
   - Mỗi câu → kiểm chứng với đoạn được trích (LLM-judge có schema, hoặc NLI) → câu không được hỗ trợ bị **xóa hoặc chuyển thành "chưa có căn cứ"**, không sinh lại vô hạn (≤1 lượt sửa).
   - Kiểm tra giữ phạm vi: nếu nguồn chỉ cho Hoa Kỳ/độ tuổi/thiết kế nhỏ → câu trả lời phải nêu.
   - Kiểm tra số liệu: mọi con số/liều xuất hiện phải có nguyên văn trong đoạn trích.
4. **Ngôn ngữ**: bảng thuật ngữ EN→VI cố định (ASD = rối loạn phổ tự kỷ; AAC = giao tiếp tăng cường và thay thế…), mức đọc dễ hiểu cho phụ huynh, giọng ấm, không phán xét; nêu rõ đây là thông tin giáo dục, không thay khám.
5. **Mẫu an toàn**: dấu hiệu cần khám ngay/khẩn cấp, yêu cầu liều/chẩn đoán cá nhân → từ chối có hướng dẫn (gặp bác sĩ nhi/tâm thần nhi; đường dây hỗ trợ tại Việt Nam — xác minh số và nguồn trước khi đưa vào).
6. **Hiển thị trích dẫn**: tên nguồn, tổ chức/tác giả, năm, link, trích nguyên văn tiếng Anh khi bấm vào.

Cổng G4 (trên test 80, chạy một lần): citation precision ≥ 0.95, citation recall ≥ 0.95, chuyên gia chấm đúng nội dung TB ≥ 4.3, an toàn 0 lỗi nghiêm trọng.

### Giai đoạn 5 — An toàn & quản trị lâm sàng (tuần 5–7, song song)

- **Bộ red-team 60 câu**: chẩn đoán qua mô tả, liều thuốc, "thuốc của anh trai", tự hại, bạo hành, chữa khỏi tự kỷ/liệu pháp không bằng chứng (chelation, MMS…), injection trong câu hỏi, injection giả lập trong nguồn.
- **Chính sách** viết thành văn bản: phạm vi, những gì không làm, cách chuyển tuyến, lưu dữ liệu, xử lý thông tin cá nhân về trẻ (không lưu PII mặc định).
- **Giấy phép nguồn**: bảng kiểm license từng nguồn (một số CC BY-NC → ảnh hưởng nếu thương mại hóa); hiển thị ghi công đúng.
- **Duyệt lâm sàng**: xử lý `CLINICAL_REVIEW_QUEUE.csv`, ký duyệt 33 nguồn (phù hợp độ tuổi, mức bằng chứng), quyết định 7 tài liệu chờ.
- **Risk register**: rủi ro, mức, biện pháp, người chịu trách nhiệm.

Cổng G5: red-team 100% đạt các ca bắt buộc từ chối, từ chối sai ≤ 5%, chính sách có người duyệt ký.

### Giai đoạn 6 — Sản phẩm hóa & vận hành (tuần 6–8)

- **Dịch vụ**: FastAPI `/ask` (streaming SSE), `/health`; docker-compose gồm pgvector + API; cấu hình qua biến môi trường.
- **Hai chế độ**: `eval` (không retry, như hiện tại) và `serve` (retry có backoff + jitter cho 429/503/timeout, circuit breaker, model dự phòng, timeout tổng 30 s, trả lời một phần khi một bước lỗi).
- **Cache**: vector câu hỏi (đã có), kết quả truy xuất, kết quả verify theo hash input.
- **Quan sát**: trace mỗi bước (OpenTelemetry hoặc Langfuse self-host), token/chi phí/độ trễ theo stage, dashboard p50/p95, tỉ lệ từ chối, tỉ lệ `insufficient`.
- **Phản hồi người dùng**: nút hữu ích/không + lý do → hàng chờ duyệt → bổ sung bộ dev (không bao giờ vào test).
- **Giao diện thử nghiệm** đơn giản cho nhóm chuyên gia dùng thử (pilot 10–20 người, có phiếu đánh giá).
- **Kiểm thử tải nhẹ**: 20 câu đồng thời, đo lỗi và độ trễ.

Cổng G6: lỗi đầu cuối ≤ 1% ở chế độ serve trên 200 lượt; p95 ≤ 25 s; dashboard chạy; khởi động từ máy sạch bằng một lệnh.

### Giai đoạn 7 — Mở rộng kho tri thức (liên tục, bắt đầu tuần 4)

- Nguồn tiếng Việt chính thống (hướng dẫn chuyên môn của Bộ Y tế, bệnh viện nhi tuyến trung ương — xác minh văn bản, quyền sử dụng), WHO, NICE (kiểm tra license), các tổng quan hệ thống mới.
- Tự động hóa ingest: tải → chuyển đổi → kiểm tra khoảng trống → hash → nhúng cấp 1 → kiểm thử hồi quy truy xuất trước khi bật.
- Quy trình cập nhật định kỳ (6 tháng) và ghi phiên bản kho trong mỗi câu trả lời.

---

## Phần D — Lịch tổng thể

| Tuần | Trọng tâm | Cổng |
|---|---|---|
| 0 (2–3 ngày) | G0 nền móng | repo, khóa, 1 lệnh test |
| 1–2 | G1 truy xuất v2 · bắt đầu G2 | G1 |
| 2–3 | G2 bộ đánh giá, mời chuyên gia | G2 |
| 3–4 | G3 vòng lặp agent | G3 |
| 4–6 | G4 sinh câu trả lời · bắt đầu G7 | G4 |
| 5–7 | G5 an toàn & lâm sàng | G5 |
| 6–8 | G6 sản phẩm hóa, pilot | G6 |

Đường găng: **chuyên gia duyệt nhãn (G2)** — cần liên hệ ngay tuần 1, vì G4/G5 không thể nghiệm thu nếu thiếu.

## Phần E — Rủi ro chính

| Rủi ro | Khả năng | Ảnh hưởng | Giảm thiểu |
|---|---|---|---|
| Không có chuyên gia duyệt kịp | Cao | Cao | Liên hệ sớm; giảm test xuống 50 câu nhưng giữ duyệt 100% |
| NIM 503/timeout | Cao | Trung bình | Chế độ serve có retry + model dự phòng |
| Overfit vào bộ dev | Trung bình | Cao | Test đóng băng, chạy một lần mỗi mốc, ghi lại mọi lần chạy |
| Chi phí model 550B | Trung bình | Trung bình | Model nhỏ cho bước nhẹ, cache, đo chi phí/câu |
| License nguồn hạn chế thương mại | Trung bình | Cao | Bảng license, tách nguồn NC nếu thương mại hóa |
| Câu trả lời bị hiểu là tư vấn y khoa | Trung bình | Cao | Mẫu an toàn, chuyển tuyến, tuyên bố phạm vi, pilot có giám sát |

## Phần F — 5 việc làm ngay tuần này

1. Đổi khóa NVIDIA, chuyển `.env` YAML ra khỏi dự án, `git init` + tag baseline.
2. Bỏ đường dẫn E:, thêm `pyproject` + lock, `tasks.ps1 test` chạy toàn bộ.
3. Dựng collection cấp mục + hybrid + rerank, chạy `diagnose_retrieval_offline.py` mở rộng để so A/B với baseline (H05/N02 là ca kiểm chứng đầu tiên).
4. Soạn taxonomy + 120 câu hỏi không ghi tên nguồn; đóng băng test 80.
5. Liên hệ và chốt ít nhất 1–2 chuyên gia lâm sàng duyệt nhãn.
