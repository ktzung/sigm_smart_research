# Hướng dẫn sử dụng Pipeline — SigM Research Platform

> Dành cho người mới bắt đầu. Tài liệu này giải thích từng bước trong quy trình tự động tạo bài báo khoa học.

---

## Tổng quan — Pipeline làm gì?

Hệ thống tự động hóa toàn bộ quy trình viết bài báo khoa học (survey/review) từ đầu đến cuối:

```
Bạn nhập chủ đề
      ↓
[1] Lập kế hoạch tìm kiếm
      ↓
[2] Tìm bài báo từ nhiều nguồn
      ↓
[3] Lọc bài liên quan
      ↓
[4] Tải nội dung PDF
      ↓
[5] Trích xuất kiến thức
      ↓
[6] Tổng hợp so sánh
      ↓
[7] Phân loại phương pháp
      ↓
[8] Phân tích khoảng trống
      ↓
[9] Viết bản thảo
      ↓
[10] Đánh giá chất lượng
      ↓
[11-15] Hoàn thiện & Xuất file
```

**Thời gian ước tính:** 30-90 phút tùy số lượng bài báo và model sử dụng.

---

## Trước khi bắt đầu — Cấu hình API Key

Vào **Admin → Config → LLM Provider** để cấu hình. Bạn cần ít nhất **1 trong các key sau**:

| Provider | Đăng ký tại | Chi phí | Ghi chú |
|---|---|---|---|
| **Gemini** ⭐ Khuyến nghị | [aistudio.google.com](https://aistudio.google.com/app/apikey) | Miễn phí (có giới hạn) | Tốt nhất cho hầu hết stages |
| **Perplexity** | [perplexity.ai/settings/api](https://www.perplexity.ai/settings/api) | ~$5/tháng | Tốt nhất cho tìm kiếm |
| **Anthropic** | [console.anthropic.com](https://console.anthropic.com) | Trả theo dùng | Tốt nhất cho viết lách |
| **OpenAI** | [platform.openai.com](https://platform.openai.com) | Trả theo dùng | Phổ biến, đa năng |

> 💡 **Gợi ý tiết kiệm:** Dùng Gemini (miễn phí) cho hầu hết stages, Perplexity cho Stage 1-2 (tìm kiếm).

---

## Chi tiết từng Stage

---

### 🔍 Stage 1 — Query Plan (Lập kế hoạch tìm kiếm)

**Làm gì?** AI phân tích chủ đề của bạn và tạo ra 10-15 câu truy vấn tìm kiếm đa dạng — giống như một thủ thư chuyên nghiệp lập danh sách từ khóa.

**Ví dụ:** Chủ đề "Federated Learning" → tạo ra các query như:
- "federated learning non-IID data" (tìm trực tiếp)
- "distributed machine learning privacy" (tìm liên quan)
- "stochastic gradient descent convergence" (tìm nền tảng)

**Model tốt nhất:**
- 🥇 **Perplexity `sonar-pro`** — có khả năng tìm kiếm web thời gian thực, biết các paper mới nhất
- 🥈 Gemini `gemini-3.1-pro-preview` — nếu không có Perplexity

**Chạy kiểu:** Đồng bộ (kết quả ngay lập tức, ~10 giây)

**Yêu cầu:** Không có

---

### 📚 Stage 2 — Discover (Tìm bài báo)

**Làm gì?** Thực thi các query từ Stage 1 để tìm bài báo từ nhiều nguồn:
- **Semantic Scholar** — 200M+ bài báo
- **arXiv** — preprints mới nhất, có PDF
- **IEEE Xplore** — nếu có API key
- **CrossRef** — journal papers có DOI
- **OpenAlex** — 250M+ works
- **GitHub Awesome-lists** — danh sách curated từ cộng đồng (nếu có GitHub token)

**Model tốt nhất:** Không dùng AI — chỉ gọi API

**Chạy kiểu:** Đồng bộ (~30-60 giây tùy số query)

**Yêu cầu:** Stage 1 phải xong

**Kết quả:** Thấy số bài trong tab **Papers**

---

### ✅ Stage 3 — Screen (Lọc bài liên quan)

**Làm gì?** Đọc abstract từng bài và quyết định có đưa vào nghiên cứu không. Gán nhãn:
- **direct** — liên quan trực tiếp (điểm cao)
- **adjacent** — liên quan gián tiếp
- **foundational** — nền tảng lý thuyết
- **exclude** — không liên quan

**Model tốt nhất:**
- 🥇 **Gemini `gemini-3.1-flash-lite-preview`** — nhanh, rẻ, đủ tốt cho việc lọc
- Không cần model mạnh vì chỉ đọc abstract ngắn

**Chạy kiểu:** Background (~5-15 phút tùy số bài)

**Yêu cầu:** Stage 2 phải xong

**Mẹo:** Sau khi chạy xong, vào tab **Papers** để xem kết quả. Có thể override thủ công nếu AI lọc sai.

---

### 📥 Stage 4 — Ingest (Tải nội dung)

**Làm gì?** Cố gắng tải PDF của từng bài đã được chấp nhận. Nếu không tải được (paywall), dùng abstract làm nội dung.

**Model tốt nhất:** Không dùng AI

**Chạy kiểu:** Background (~10-30 phút)

**Yêu cầu:** Stage 3 phải xong

**Lưu ý:** Nhiều bài sẽ chỉ có abstract vì PDF bị paywall (Springer, ACM, IEEE...). Đây là bình thường. Dùng nút **+ Enrich** để cố tìm bản open-access.

---

### 🔬 Stage 5 — Extract (Trích xuất kiến thức)

**Làm gì?** AI đọc nội dung từng bài và trích xuất thông tin có cấu trúc:
- Phương pháp đề xuất là gì?
- Dataset nào được dùng?
- Điểm mạnh/yếu?
- Liên quan đến chủ đề như thế nào?

**Model tốt nhất:**
- 🥇 **Gemini `gemini-3.1-flash-lite-preview`** — nhanh, xử lý được nhiều bài
- 🥈 Gemini `gemini-2.0-flash` — thay thế tốt

**Chạy kiểu:** Background (~15-45 phút)

**Yêu cầu:** Stage 4 phải xong

> ⚠️ **Quan trọng:** Stage 6 (Synthesize) sẽ **fail** nếu Stage 5 chưa chạy!

---

### 🧩 Stage 6 — Synthesize (Tổng hợp)

**Làm gì?** AI so sánh tất cả bài báo với nhau và tạo ra:
- Bảng so sánh các phương pháp
- Các pattern lặp lại trong field
- Mâu thuẫn giữa các nghiên cứu
- Benchmark nào được dùng nhiều nhất

**Model tốt nhất:**
- 🥇 **Gemini `gemini-3.1-pro-preview`** — context window lớn, lý luận tốt
- 🥈 **Claude `claude-opus-4-5`** — nếu muốn chất lượng cao hơn (đắt hơn)

**Chạy kiểu:** Background (~5-15 phút)

**Yêu cầu:** Stage 5 phải xong (ít nhất 1 bài có extraction)

---

### 🗂️ Stage 7 — Taxonomy (Phân loại)

**Làm gì?** Xây dựng hệ thống phân loại đa chiều cho các phương pháp trong field. Ví dụ với Federated Learning:
- Chiều "aggregation": FedAvg, FedProx, SCAFFOLD
- Chiều "privacy": DP, SecAgg, None
- Chiều "data": IID, Non-IID

**Model tốt nhất:**
- 🥇 **Gemini `gemini-3.1-pro-preview`**
- 🥈 **Claude `claude-opus-4-5`**

**Chạy kiểu:** Background (~5-10 phút)

---

### 🔎 Stage 8 — Gap Analysis (Phân tích khoảng trống)

**Làm gì?** Tìm ra những gì **chưa được nghiên cứu** — đây là phần quan trọng nhất của một bài survey tốt. Ví dụ: "Chưa có benchmark thống nhất cho non-IID với label noise".

**Model tốt nhất:**
- 🥇 **Gemini `gemini-3.1-pro-preview`**
- 🥈 **Claude `claude-opus-4-5`** — phân tích sâu hơn

**Chạy kiểu:** Background (~5-10 phút)

---

### ✍️ Stage 9 — Draft (Viết bản thảo)

**Làm gì?** Viết từng section của bài báo dựa trên toàn bộ dữ liệu đã thu thập. Các section mặc định cho survey:
- Introduction, Background, Problem Formulation
- Taxonomy, Literature Review, Critical Analysis
- Future Directions, Conclusion

**Model tốt nhất:**
- 🥇 **Claude `claude-sonnet-4-5`** — viết học thuật tốt nhất
- 🥈 **Gemini `gemini-3.1-pro-preview`** — thay thế tốt, rẻ hơn
- 🥉 **GPT-4o** — nếu có OpenAI key

**Chạy kiểu:** Background (~15-30 phút)

**Mẹo:** Xem kết quả trong tab **Drafts**

---

### 📋 Stage 10 — Review (Đánh giá)

**Làm gì?** AI đóng vai peer reviewer để đánh giá bản thảo, chỉ ra:
- Điểm yếu lớn cần sửa
- Vấn đề nhỏ (format, citation)
- Thứ tự ưu tiên sửa chữa
- Điểm tổng thể: `strong_accept` → `accept` → `weak_accept` → `borderline` → `weak_reject` → `reject`

**Model tốt nhất:**
- 🥇 **Claude `claude-opus-4-5`** — reviewer nghiêm khắc và chi tiết nhất
- 🥈 **Gemini `gemini-3.1-pro-preview`**

**Chạy kiểu:** Background (~5-10 phút)

**Kỳ vọng thực tế:** Draft đầu tiên thường nhận `borderline` hoặc `weak_reject` — đây là **bình thường**. Dùng nút **🔄 Auto R&R** để tự động chạy Review → Revision nhiều vòng.

---

## Các Stage Chất lượng (chạy sau Stage 10)

---

### 📊 Stage 11 — PRISMA

**Làm gì?** Tạo biểu đồ PRISMA flow (chuẩn systematic review) và viết section Methodology.

**Khi nào dùng:** Khi viết systematic review hoặc meta-analysis.

**Model:** Gemini `gemini-3.1-flash-lite-preview`

---

### 🕸️ Stage 12 — Citation Network

**Làm gì?** Phân tích mạng lưới trích dẫn — tìm bài nào được trích dẫn nhiều nhất, phân bố theo năm, venue phổ biến.

**Model:** Không dùng AI (chỉ gọi Semantic Scholar API)

---

### 🔄 Stage 13 — Revision (Sửa bản thảo)

**Làm gì?** Viết lại từng section dựa trên feedback từ Review.

**Model tốt nhất:**
- 🥇 **Claude `claude-sonnet-4-5`** — sửa theo feedback tốt nhất
- 🥈 **Gemini `gemini-3.1-pro-preview`**

**Mẹo:** Dùng nút **🔄 Auto R&R** thay vì chạy Review và Revision riêng lẻ — tự động lặp lại đến khi đạt `weak_accept`.

---

### 🔍 Stage 14 — QA Check

**Làm gì?** Kiểm tra 3 lớp:
1. **LanguageTool** — ngữ pháp, chính tả (miễn phí)
2. **LLM** — viết lại câu nghe "AI-generated"
3. **Grammarly** — kiểm tra đạo văn (cần Business plan)

**Model:** Gemini `gemini-3.1-flash-lite-preview`

---

### 📄 Stage 15 — LaTeX Export

**Làm gì?** Tạo file LaTeX hoàn chỉnh sẵn sàng nộp journal:
- `main.tex` — bản thảo chính
- `references.bib` — danh sách tài liệu tham khảo
- Figures — PRISMA flow, year distribution, taxonomy heatmap

**Templates:** IEEEtran, ACM, Elsevier, Springer

**Model:** Không dùng AI

---

## Các Stage Mở rộng — Extended Pipeline (Remote Execution)

> Dành cho **PhD student và Professor** — chạy thí nghiệm ML thực tế trên server từ xa.
> Yêu cầu: Đã cấu hình SSH Server trong tab **🔌 SSH**.

---

### 🖥️ Stage 16 — Hybrid Design

**Làm gì?** Tạo tài liệu thiết kế thí nghiệm kết hợp insights từ literature review với code analysis của GitHub repo đã link. Đề xuất architecture, baseline methods, experimental setup.

**Yêu cầu:** Synthesize + Taxonomy + Gaps đã xong. GitHub repo đã link và analyze (tùy chọn nhưng nên có).

**Model:** Gemini `gemini-3.1-pro-preview` hoặc Claude `claude-opus-4-5`

**API:** `POST /api/v1/topics/{id}/remote/stage16`

---

### 💻 Stage 17 — Code Synthesis

**Làm gì?** Tạo code thí nghiệm hoàn chỉnh dựa trên Hybrid Design:
- `train.py` — training script
- `config.yaml` — hyperparameter configuration
- `requirements.txt` — dependencies

**Yêu cầu:** Stage 16 phải xong

**Model:** Gemini `gemini-3.1-pro-preview`

**API:** `POST /api/v1/topics/{id}/remote/stage17`

---

### ⚙️ Stage 18 — Env Architect

**Làm gì?** Tạo environment setup files cho server từ xa:
- Conda/pip environment file (tự động detect CUDA)
- SSH setup commands
- Hỗ trợ standalone (nohup/tmux) và Slurm scheduler

**Yêu cầu:** Stage 17 phải xong

**Model:** Gemini `gemini-3.1-flash-lite-preview`

**API:** `POST /api/v1/topics/{id}/remote/stage18`

---

### 🚀 Stage 19 — Remote Deploy

**Làm gì?** Tạo deployment script để upload code lên server SSH và cài đặt môi trường.

**Yêu cầu:** Stage 18 + SSH Server đã cấu hình

**API:** `POST /api/v1/topics/{id}/remote/stage19`

---

### ▶️ Stage 20 — Execution

**Làm gì?** Tạo execution script để chạy thí nghiệm trên server (standalone hoặc Slurm sbatch).

**Yêu cầu:** Stage 19 phải xong

**API:** `POST /api/v1/topics/{id}/remote/stage20`

---

### 📥 Stage 21 — Harvest Results

**Làm gì?** Tạo script để thu thập kết quả thí nghiệm (CSV metrics) từ server về local.

**Yêu cầu:** Stage 20 đã chạy xong trên server

**API:** `POST /api/v1/topics/{id}/remote/stage21`

---

### 📊 Stage 22 — Analytics

**Làm gì?** Đọc CSV kết quả thí nghiệm và viết section **Experiments** bằng LaTeX — bảng số liệu, so sánh baseline, ablation study.

**Yêu cầu:** Stage 21 đã harvest kết quả vào `storage/results/topic_{id}/`

**Model:** Gemini `gemini-3.1-pro-preview`

**API:** `POST /api/v1/topics/{id}/remote/stage22`

---

### Cách sử dụng Extended Pipeline

1. Vào tab **🖥️ Remote** của topic
2. Chọn SSH Server đã cấu hình
3. Chạy từng stage theo thứ tự 16 → 17 → 18 → 19 → 20 → 21 → 22
4. Download artefacts (code, scripts) tại `GET /api/v1/topics/{id}/remote/artefacts/{section_name}`

**Lưu ý:** Extended Pipeline chỉ dành cho **PhD student** và **Professor** trong lab. Undergraduate student không có quyền truy cập.

---

Vào **🤖 Models** trên topic view để cấu hình per-stage.

### Cấu hình tiết kiệm (chỉ cần Gemini free):
| Stage | Model |
|---|---|
| Tất cả | Gemini `gemini-3.1-flash-lite-preview` |
| Synthesize, Taxonomy, Gaps, Draft, Review, Revision | Gemini `gemini-3.1-pro-preview` |

### Cấu hình chất lượng cao:
| Stage | Model | Lý do |
|---|---|---|
| Query Plan | Perplexity `sonar-pro` | Tìm kiếm web thời gian thực |
| Screen, Extract | Gemini `flash-lite` | Nhanh, rẻ, đủ tốt |
| Synthesize, Taxonomy, Gaps | Gemini `3.1-pro` hoặc Claude `opus-4-5` | Cần lý luận sâu |
| Draft, Revision | Claude `sonnet-4-5` | Viết học thuật tốt nhất |
| Review | Claude `opus-4-5` | Đánh giá nghiêm khắc nhất |

---

## Câu hỏi thường gặp

**Q: Synthesize báo lỗi "No extracted papers"?**
→ Chạy Stage 5 (Extract) trước. Stage 5 cần Stage 4 (Ingest) đã xong.

**Q: Review cho kết quả "reject" liên tục?**
→ Dùng nút **🔄 Auto R&R** — tự động chạy Review → Revision 3 vòng. Kết quả `weak_accept` là đủ tốt cho draft AI-generated.

**Q: Nhiều bài chỉ có abstract, không có PDF?**
→ Bình thường — nhiều journal có paywall. Nhấn **+ Enrich** để tìm bản open-access. Bài có arXiv version thường tải được.

**Q: Chạy bao lâu?**
→ Toàn bộ pipeline: 45-90 phút. Stage nặng nhất là Ingest (tải PDF) và Draft (viết).

**Q: Có thể chạy lại một stage không?**
→ Có — nhấn **↺ Re-run** trên stage card bất kỳ lúc nào.

**Q: Kết quả lưu ở đâu?**
→ Database PostgreSQL. PDF lưu tại `storage/pdfs/topic_{id}/`. LaTeX tại `storage/latex/topic_{id}/`.

---

*Cập nhật: Tháng 4/2026*
