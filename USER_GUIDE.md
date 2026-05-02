# Hướng dẫn Sử dụng Chi tiết — SigM Research Platform

> Hướng dẫn từng bước cho người dùng, bao gồm: làm gì, nhấp vào đâu, kết quả trông như thế nào.

---

## Bắt đầu nhanh

1. Mở trình duyệt → `http://localhost:8000`
2. Nhấp **Login** → đăng nhập bằng email/password
3. Nhấp **Research** trên thanh menu → vào trang Topics
4. Nhấp **+ Create First Topic** → nhập tiêu đề nghiên cứu → **Create**
5. Nhấp vào topic vừa tạo → thấy giao diện Pipeline với các Stage cards

---

## Giao diện Pipeline — Tổng quan

Sau khi chọn topic, bạn thấy:

```
[Topic Title]
[▶ Run Full Pipeline] [Export MD] [Export JSON] [🤖 Models]

CORE PIPELINE
[1 Query Plan] [2 Discover] [3 Screen] [4 Ingest] [5 Extract] [5b Code Discovery]

MAIN ANALYSIS
[6 Synthesize] [7 Taxonomy] [8 Gap Analysis] [9 Draft] [10 Review]

QUALITY STAGES
[11 PRISMA] [12 Citation Net] [13 Revision] [14 QA Check] [15 LaTeX Export]
```

Mỗi **Stage Card** có:
- **Số thứ tự** (góc trên)
- **Tên stage**
- **Trạng thái**: `pending` (xám) → `running` (vàng nhấp nháy) → `done` (xanh) / `failed` (đỏ)
- **Dropdown chọn model** (AI model sẽ dùng)
- **▶ Run with model** — chọn model và chạy ngay
- **👁 View** — xem kết quả
- **↺ Re-run** — chạy lại
- Các nút đặc biệt tùy stage

---

## Chi tiết từng Stage

---

### Stage 1 — Query Plan 🔍

**Làm gì:** AI phân tích tiêu đề topic và tạo 10-15 câu truy vấn tìm kiếm đa dạng.

**Cách chạy:**
1. Nhấp **▶ Run with model** trên card "Query Plan"
2. Chờ ~10 giây (chạy đồng bộ, kết quả ngay)
3. Card chuyển sang màu xanh `done`

**Xem kết quả:**
- Nhấp **👁 View** → thấy danh sách bundles với label (direct/adjacent/foundational), source (S2/arXiv/IEEE), query text

**Nếu thất bại:**
- Nhấp **↺ Re-run** → thử lại
- Hoặc đổi model sang `gpt-4o` trong dropdown → **▶ Run with model**

**Mẹo:** Tiêu đề topic càng cụ thể → queries càng chính xác. Ví dụ: "Federated Learning under Concept Drift" tốt hơn "Machine Learning".

---

### Stage 2 — Discover 📚

**Làm gì:** Thực thi các queries từ Stage 1, tìm bài báo từ Semantic Scholar, arXiv, IEEE, CrossRef, OpenAlex, và GitHub Awesome-lists.

**Cách chạy:**
1. Đảm bảo Stage 1 đã `done`
2. Nhấp **▶ Run with model** trên card "Discover"
3. Chờ 30-90 giây
4. Card chuyển `done`

**Xem kết quả:**
- Nhấp **👁 View** → thấy tổng số papers, breakdown theo source (Semantic Scholar/arXiv/...), top 10 papers
- Hoặc nhấp tab **Papers** → xem toàn bộ danh sách

**Nút đặc biệt:**
- **🔗 Snowball** — tìm thêm papers từ references của papers đã có (citation snowballing)

**Nếu thất bại:**
- Lỗi "No query plan" → chạy Stage 1 trước
- Lỗi network → thử lại sau vài phút

---

### Stage 3 — Screen ✅

**Làm gì:** AI đọc abstract từng bài và gán nhãn: `direct` / `adjacent` / `foundational` / `exclude`.

**Cách chạy:**
1. Nhấp **▶ Run with model**
2. Chờ 5-15 phút (tùy số papers)
3. Card chuyển `done`

**Xem kết quả:**
- Nhấp **👁 View** → thấy biểu đồ số lượng theo label + sample decisions với % score
- Tab **Papers** → xem chi tiết từng bài với score và lý do

**Override thủ công:**
- Trong tab Papers → tìm bài muốn sửa → nhấp vào label → chọn label mới
- Hữu ích khi AI screen sai

**Nút đặc biệt:**
- Không có nút đặc biệt — chỉ Re-run

**Mẹo:** Sau khi screen xong, vào tab Papers kiểm tra kết quả trước khi chạy Ingest.

---

### Stage 4 — Ingest 📥

**Làm gì:** Tải PDF của các bài được chấp nhận. Nếu không tải được (paywall), dùng abstract.

**Cách chạy:**
1. Nhấp **▶ Run with model**
2. Chờ 10-30 phút
3. Card chuyển `done`

**Xem kết quả:**
- Nhấp **👁 View** → thấy: Included / PDF Downloaded / Parsed / Abstract Only

**Nút đặc biệt:**
- **+ Enrich** — cố tìm bản open-access cho các bài chỉ có abstract (qua arXiv/S2)

**Lưu ý:** Nhiều bài sẽ chỉ có abstract (PDF bị paywall) — đây là bình thường. Nhấp **+ Enrich** để cải thiện.

---

### Stage 5 — Extract 🔬

**Làm gì:** AI đọc nội dung từng bài và trích xuất: method_type, datasets, strengths, limitations, relevance.

**Cách chạy:**
1. Nhấp **▶ Run with model**
2. Chờ 15-45 phút
3. Card chuyển `done`

**Xem kết quả:**
- Nhấp **👁 View** → thấy 6 papers đầu với method, setting, datasets

**⚠️ Quan trọng:** Stage 6 (Synthesize) sẽ **fail** nếu Stage 5 chưa chạy!

---

### Stage 5b — Code Discovery 💻

**Làm gì:** Tìm GitHub repo của từng bài báo qua Papers With Code API.

**Cách chạy:**
1. Nhấp **▶ Run with model**
2. Chờ 5-10 phút
3. Card chuyển `done`

**Xem kết quả:**
- Nhấp **👁 View** → danh sách papers có GitHub repo với link, stars, framework
- Tab Papers → cột Code hiển thị badge "GitHub ✓" với link

---

### Stage 6 — Synthesize 🧩

**Làm gì:** AI so sánh tất cả papers và tạo: comparison table, recurring patterns, contradictions, method clusters, benchmark coverage, prioritized opportunities.

**Cách chạy:**
1. Đảm bảo Stage 5 đã `done`
2. Nhấp **▶ Run with model** (nên dùng `gpt-4o`)
3. Chờ 5-15 phút

**Xem kết quả:**
- Nhấp **👁 View** → thấy recurring patterns, contradictions, benchmark coverage

---

### Stage 7 — Taxonomy 🗂️

**Làm gì:** Xây dựng phân loại đa chiều cho các phương pháp trong corpus.

**Cách chạy:**
1. Nhấp **▶ Run with model**
2. Chờ 5-10 phút

**Xem kết quả:**
- Nhấp **👁 View** → thấy dimensions với categories dạng badge màu tím

---

### Stage 8 — Gap Analysis 🔎

**Làm gì:** Tìm khoảng trống nghiên cứu với priority, actionable direction, difficulty.

**Cách chạy:**
1. Nhấp **▶ Run with model**
2. Chờ 5-10 phút

**Xem kết quả:**
- Nhấp **👁 View** → danh sách gaps với priority badge
- Tab **Gaps** → xem đầy đủ

---

### Stage 9 — Draft ✍️

**Làm gì:** Viết từng section của bài báo (introduction, background, taxonomy, literature_review, critical_analysis, future_directions, conclusion).

**Cách chạy:**
1. Nhấp **▶ Run with model** (nên dùng `gpt-4o`)
2. Chờ 15-30 phút

**Xem kết quả:**
- Nhấp **👁 View** → danh sách sections với word count + preview 800 chars
- Tab **Drafts** → xem đầy đủ từng section

**Nút đặc biệt:**
- **📝 Abstract** — tạo abstract (150-250 từ) và contributions list từ draft hiện có
- **🛡️ Anti-Fab** — kiểm tra và xóa citations giả, claims không có evidence

**Mẹo:** Sau khi Draft xong, nhấp **🛡️ Anti-Fab** để làm sạch trước khi Review.

---

### Stage 10 — Review 📋

**Làm gì:** AI đóng vai peer reviewer Q1, đánh giá draft và cho điểm.

**Cách chạy:**
1. Nhấp **▶ Run with model** (nên dùng `gpt-4o`)
2. Chờ 5-10 phút

**Xem kết quả:**
- Nhấp **👁 View** → thấy score màu + major weaknesses + minor issues + revision priorities
- Tab **Review** → xem đầy đủ

**Nút đặc biệt:**
- **🎯 Decision** — xem quyết định PROCEED / REFINE / PIVOT dựa trên score
  - `PROCEED` (score ≥ 60%) → tiếp tục sang Quality Stages
  - `REFINE` (30-60%) → cần revise, chạy Stage 13
  - `PIVOT` (<30%) → vấn đề cơ bản, cần xem lại từ Stage 8
- **🔄 Auto R&R** — tự động chạy Review → Revision → Review lặp lại (tối đa 3 vòng) cho đến khi đạt `weak_accept`

**Workflow khuyến nghị:**
1. Chạy Review → nhấp **🎯 Decision**
2. Nếu `REFINE` → nhấp **🔄 Auto R&R** → chờ tự động
3. Nếu `PROCEED` → tiếp tục Stage 11

---

### Stage 11 — PRISMA 📊

**Làm gì:** Tạo PRISMA flow diagram data và viết section Methodology theo chuẩn systematic review.

**Cách chạy:**
1. Nhấp **▶ Run with model**
2. Chờ 3-5 phút

**Xem kết quả:**
- Nhấp **👁 View** → thấy số papers identified/screened/included

---

### Stage 12 — Citation Network 🕸️

**Làm gì:** Phân tích mạng lưới trích dẫn — authority papers, year distribution, top venues.

**Cách chạy:**
1. Nhấp **▶ Run with model**
2. Chờ 5-10 phút (gọi Semantic Scholar API)

**Xem kết quả:**
- Nhấp **👁 View** → authority papers count + internal citations count

---

### Stage 13 — Revision 🔄

**Làm gì:** Viết lại từng section dựa trên feedback từ Review.

**Cách chạy:**
1. Đảm bảo Stage 10 (Review) đã `done`
2. Nhấp **▶ Run with model** (nên dùng `gpt-4o`)
3. Chờ 15-30 phút

**Xem kết quả:**
- Nhấp **👁 View** → sections với version tăng (v2, v3...) + word count

**Nút đặc biệt:**
- **🛡️ Anti-Fab** — kiểm tra lại sau revision
- **🔄 Auto R&R** — tự động lặp Review → Revision

---

### Stage 14 — QA Check 🔍

**Làm gì:** Kiểm tra 3 lớp: LanguageTool (ngữ pháp), LLM paraphrase (giảm AI-sounding), Grammarly plagiarism (nếu có key).

**Cách chạy:**
1. Nhấp **▶ Run with model**
2. Chờ 10-20 phút

**Xem kết quả:**
- Nhấp **👁 View** → grammar issues count, sections improved, originality score

---

### Stage 15 — LaTeX Export 📄

**Làm gì:** Tạo gói LaTeX hoàn chỉnh: main.tex, references.bib, figures/, README.md.

**Cách chạy:**
1. Nhấp **▶ Run with model**
2. Chờ 5-10 phút
3. Nếu có pdflatex → tự động compile PDF

**Xem kết quả:**
- Nhấp **👁 View** → thấy templates + PDF size + nút **⬇ Download PDF**

**Nút đặc biệt:**
- **✅ Verify Cites** — chạy 4-layer citation verification (arXiv + DOI + S2 + LLM relevance)

**Templates hỗ trợ:**
- `IEEEtran` — IEEE Transactions (mặc định)
- `acmart` — ACM Computing Surveys
- `elsarticle` — Elsevier
- `svjour3` — Springer

---

## Các nút toàn cục

### ▶ Run Full Pipeline
Chạy tất cả stages theo thứ tự tự động. Nhấp 1 lần → chờ 45-90 phút.

### 🤖 Models
Mở Model Settings để cấu hình model cho từng stage:
- Tab **Per Stage** — chọn model riêng cho từng stage
- Tab **By Category** — chọn model cho cả nhóm (fast_screen / deep_analysis / writing)
- Nhấp **Save** → lưu vào DB, áp dụng cho topic này

### Export MD / Export JSON
Xuất toàn bộ kết quả (papers, synthesis, taxonomy, gaps, drafts, review) ra file.

---

## Tab Papers — Tìm kiếm và Lọc

Nhấp tab **Papers** để xem danh sách bài báo:

**Tìm kiếm:**
- Gõ vào ô **"Search by title, author, venue..."** → lọc ngay lập tức

**Lọc:**
- **Status**: All / Direct / Adjacent / Foundational / Excluded / Pending
- **Type**: All / Conference / Journal / Preprint
- **Source**: All / Semantic Scholar / arXiv / IEEE Xplore
- **Has GitHub**: chỉ hiện bài có code

**Sắp xếp:**
- Nhấp header **Title**, **Year**, **Score** để sort (nhấp lại để đảo chiều)

**Phân trang:** 20 papers/trang, nút `‹ Prev` / `Next ›`

---

## Admin — Cấu hình hệ thống

Nhấp **Manage** trên menu (chỉ admin/professor):

### Tab Config
- **LLM Provider Configuration** — chọn provider (OpenAI/Groq/Gemini/MiniMax...), nhập API key, chọn model
- **Stage Routing Overrides** — override model cho từng stage toàn hệ thống
  - Chọn stage → chọn provider → nhập model → nhấp **Apply**
  - Thay đổi được lưu vào `storage/routing_overrides.json` → persist qua restart
  - Nhấp **↺ Reset All to Default** để xóa tất cả overrides

### Tab 💰 Cost
- Xem chi phí API đã dùng: tổng, theo provider, theo stage, theo model
- Giúp theo dõi và tối ưu chi phí

---

## Lỗi thường gặp

| Lỗi | Nguyên nhân | Giải pháp |
|---|---|---|
| Stage 6 fail "No extracted papers" | Stage 5 chưa chạy | Chạy Stage 5 trước |
| Stage 2 fail "No query plan" | Stage 1 chưa chạy | Chạy Stage 1 trước |
| Stage fail "Invalid model ID" | Model không tồn tại | Đổi sang `gpt-4o` hoặc `gpt-4o-mini` |
| Trang trắng | JS error | Ctrl+F5 để reload, hoặc restart uvicorn |
| Login 401 | Sai password | Reset password hoặc tạo user mới |
| Stage stuck ở `running` | Server restart | Server tự mark `failed` khi restart |

---

## Workflow khuyến nghị cho bài báo Q1

```
1. Tạo topic với tiêu đề cụ thể
2. Stage 1 (Query Plan) → Stage 2 (Discover)
3. Kiểm tra tab Papers → Stage 3 (Screen)
4. Review kết quả screening → Stage 4 (Ingest) → + Enrich
5. Stage 5 (Extract) → Stage 5b (Code Discovery)
6. Stage 6 → 7 → 8 (Synthesize → Taxonomy → Gaps)
7. Stage 9 (Draft) → 📝 Abstract → 🛡️ Anti-Fab
8. Stage 10 (Review) → 🎯 Decision
   - Nếu REFINE: 🔄 Auto R&R (tự động 3 vòng)
   - Nếu PROCEED: tiếp tục
9. Stage 11 → 12 (PRISMA → Citation Network)
10. Stage 14 (QA Check)
11. Stage 15 (LaTeX Export) → ✅ Verify Cites → ⬇ Download PDF
```

**Thời gian ước tính:** 45-90 phút cho toàn bộ pipeline với ~50-100 papers.

---

*Cập nhật: Tháng 4/2026 — SigM Research Platform*
