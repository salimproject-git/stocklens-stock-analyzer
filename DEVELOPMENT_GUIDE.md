# Sectors Hackathon 2026 — Development Guide
## Single Source of Truth untuk AI Development

---

## 🎯 PROJECT OVERVIEW

**Hackathon:** Sectors Hackathon Indonesia 2026  
**Track:** Track 03 - Market Intelligence  
**Team:** Solo (Muhammad Salim)  
**Deadline:** 30 September 2026, 23:59 WIB  

**One-Sentence Problem Statement:**  
"Membantu investor retail Indonesia melakukan valuasi saham fundamental dengan cepat menggunakan multi-metode valuation dan health check terintegrasi untuk identifikasi saham undervalued"

---

## ✅ HACKATHON COMPLIANCE (NON-NEGOTIABLE)

### Track 03 Requirements
- ✅ Produce **derived insight** (valuation models, scoring, recommendations) — bukan data mentah
- ✅ AI/LLM optional (tidak digunakan di produk)
- ✅ Qualifies as: custom screener dengan logic sendiri, comparative analysis

### General Requirements (All Tracks)
- ✅ **Sectors API sebagai core data source** — tanpa Sectors, produk tidak berfungsi
- ✅ Working prototype/MVP dengan end-to-end workflow
- ✅ Live deployment optional (video demo sufficient)
- ✅ **NO automated trade execution** — hanya analysis & recommendation
- ✅ Stack unrestricted (n8n + Streamlit + Python valid)
- ✅ Proyek eksklusif untuk hackathon (tidak ada code dari previous projects)

### Build Period Rules
- ✅ Repository dibuat **setelah 19 Agustus 2026** (cek commit history!)
- ✅ No pre-event code (semua commit dalam build period)
- ✅ Freeze setelah submit (no commits setelah 30 Sep 23:59 WIB)

### Submission Requirements
- ✅ Public GitHub repo (tetap public 90 hari setelah winners announced)
- ✅ 1-minute teaser video (screen recording produk bekerja)
- ✅ 3-minute judging video (walkthrough problem, audience, workflow)
- ✅ Social media post tagging @sectors
- ✅ **Disclaimer wajib:** "Information and analysis tool, bukan investment recommendation"

---

## 🏗️ TECHNICAL ARCHITECTURE

### High-Level Architecture
```
┌─────────────────────────────────────────────────────────────┐
│  DATA LAYER                                                  │
│  Sectors API → n8n Ingestion (once/quarter) → JSON Storage   │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  BACKEND LAYER (n8n Workflow)                                │
│  Webhook Trigger → Read Cached Data → Calculate → JSON Response │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  FRONTEND LAYER (Streamlit)                                  │
│  User Input (Ticker) → Call n8n Webhook → Display Dashboard  │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow Detail
1. **Ingestion (Once per Quarter):**
   - n8n workflow fetch data dari Sectors API
   - Simpan ke `backend/data/sectors_data.json`
   - Fields: ticker, company_name, sector, subsector, revenue, cogs, interest_expense, net_income, ocf, dps, accounts_receivable, inventory, current_assets, current_liabilities, total_liabilities, total_equity, shares, stock_price

2. **Analysis (On-Demand):**
   - User input ticker di Streamlit
   - Streamlit call n8n webhook (POST `/webhook/analysis` dengan body `{ticker: "BIRD"}`)
   - n8n read cached data → calculate semua metrik → return JSON
   - Streamlit display results


---

## 📁 REPO STRUCTURE

```
sectors-hackathon-2026/
├── README.md
├── DEVELOPMENT_GUIDE.md          # This file
├── n8n-workflow/
│   ├── ingestion.json            # n8n: Sectors API → JSON storage
│   └── analysis.json             # n8n: Webhook → Calculate → Response
├── backend/
│   └── data/
│       └── sectors_data.json     # Cached financial data
├── frontend/
│   └── app.py                    # Streamlit dashboard
├── scripts/
│   └── test_calculations.py      # Verify calculations match Excel
├── videos/
│   ├── teaser.mp4
│   └── judging.mp4
└── assets/
    ├── architecture.png
    └── mockup.png
```

---

## 🚀 DEVELOPMENT PHASES

### PHASE 1: Template & Data Validation (CURRENT)
**Goal:** Pastikan data dari Sectors API bisa ditarik, template terisi, dan semua perhitungan backtest works.

**Success Criteria:**
- [ ] n8n ingestion workflow bisa fetch data dari Sectors API
- [ ] Data tersimpan di `backend/data/sectors_data.json` (min. 5 emiten, 5 tahun)
- [ ] Excel template terisi penuh dengan data dari JSON
- [ ] Semua valuation models hitung benar (cross-check manual dengan Excel)
- [ ] Health score, market mood, quality adjustment = match Excel
- [ ] Test script (`test_calculations.py`) all assertions pass

**Deliverables:**
- `n8n-workflow/ingestion.json` (export n8n workflow)
- `backend/data/sectors_data.json` (cached data)
- `scripts/test_calculations.py` (all tests pass)
- Screenshot: Excel output vs Script output (side-by-side match)

**Timeline:** 3-5 hari

---

### PHASE 2: UI/UX Design & Frontend Prototype
**Goal:** UI/UX mockup + Streamlit frontend dengan dummy data (tanpa backend connection).

**Success Criteria:**
- [ ] Mockup UI/UX (Figma atau sketsa manual) — semua panel ada
- [ ] Streamlit app (`frontend/app.py`) bisa render semua panel dengan dummy data
- [ ] Layout responsive (desktop + mobile)
- [ ] Color scheme, typography sesuai reference (clean, professional, data-dense)
- [ ] Optional: Simple login page (hardcoded auth)

**Deliverables:**
- Mockup screenshot (Figma/sketsa)
- `frontend/app.py` (Streamlit dengan dummy data)
- Screenshot semua panel

**Timeline:** 3-5 hari

---

### PHASE 3: Backend Integration & Deployment
**Goal:** Connect frontend ke n8n backend, deploy, end-to-end works.

**Success Criteria:**
- [ ] n8n analysis workflow deployed dan webhook accessible
- [ ] Streamlit call n8n webhook → receive JSON → display results (end-to-end works)
- [ ] Error handling: handle ticker tidak ada, API error, malformed data
- [ ] Deploy Streamlit di Streamlit Cloud (public URL)
- [ ] Test dengan 5-10 ticker berbeda → semua works

**Deliverables:**
- `n8n-workflow/analysis.json` (export n8n workflow)
- `frontend/app.py` (connected to n8n webhook)
- Deployed URL (Streamlit Cloud)
- Test results (5-10 tickers, screenshot)

**Timeline:** 3-5 hari

---

### PHASE 4: Submission Prep
**Goal:** Semua materi submit ready, compliance check pass.

**Deliverables:**
- [ ] `README.md` lengkap (overview, architecture, how-to-run, disclaimer)
- [ ] GitHub repo public (all files uploaded)
- [ ] 1-minute teaser video (screen recording produk bekerja)
- [ ] 3-minute judging video (walkthrough problem, audience, workflow)
- [ ] Social media post (Twitter/LinkedIn/IG) tagging @sectors
- [ ] Final compliance check (all requirements ✅)

**Timeline:** 2-3 hari

---

## 🎨 UI/UX SPECIFICATIONS

### Layout Structure
```
┌─────────────────────────────────────────────────────────────┐
│  HEADER: Logo + Ticker Search + Analysis Date               │
├─────────────────────────────────────────────────────────────┤
│  PANEL 1: Company Info + Current Price + Quick Metrics      │
├─────────────────────────────────────────────────────────────┤
│  PANEL 2: Valuation Breakdown (Table) + Consensus Badge     │
├─────────────────────────────────────────────────────────────┤
│  PANEL 3: Health Vital Signs (Score + Diagnosis)            │
├─────────────────────────────────────────────────────────────┤
│  PANEL 4: Market Checklist + Strategic Execution            │
├─────────────────────────────────────────────────────────────┤
│  FOOTER: Disclaimer                                         │
└─────────────────────────────────────────────────────────────┘
```

### Color Palette
- **Primary:** Navy Blue `#1E3A8A`
- **Success:** Green `#10B981`
- **Warning:** Yellow `#F59E0B`
- **Danger:** Red `#EF4444`
- **Neutral:** Gray `#6B7280`
- **Background:** White `#FFFFFF` / Light Gray `#F9FAFB`

### Typography
- **Font:** Inter / Roboto / System sans-serif
- **Heading:** Bold, 24-32px
- **Body:** Regular, 14-16px
- **Metrics:** Bold, 18-20px

### Reference
- Macrotrends.net
- Simply Wall St
- TIKR Terminal

---

## ⚠️ CONSTRAINTS & GUARDRAILS

### AI Coding Guidelines
1. **Jangan hallucinate API endpoints** — jika tidak tahu Sectors API schema, tanya user atau asumsikan format umum
2. **Jangan over-engineer** — hackathon, bukan production. Prioritize working prototype over perfect code
3. **Keep it simple** — Streamlit > React untuk speed. n8n > custom backend untuk automation
4. **Always verify calculations** — setiap formula yang di-code, cross-check dengan Excel template
5. **Comment code** — judges akan inspect repo. Jelaskan logic kompleks dengan komentar

### Common Pitfalls to Avoid
- ❌ Jangan buat repo sebelum 19 Agustus 2026 (violate build period rules)
- ❌ Jangan hardcode data — harus dari Sectors API (via ingestion)
- ❌ Jangan lupa disclaimer financial advice (code of conduct violation)
- ❌ Jangan commit setelah submit (freeze violation)
- ❌ Jangan buat video private tanpa link sharing (inaccessible = tidak dinilai)

### When in Doubt
- Hackathon Rules: https://hackathon.sectors.app/rules
- Ask di Slack #discussion channel
- Refer back to this DEVELOPMENT_GUIDE.md

---

## 🔗 QUICK CONTEXT RESET (Paste di Setiap Chat Baru)

```
## QUICK CONTEXT — Sectors Hackathon 2026

**Project:** Stock Analysis Dashboard (Track 03: Market Intelligence)  
**Stack:** n8n (backend) + Streamlit (frontend) + Sectors API (data)  
**Deadline:** 30 September 2026  
**Current Phase:** [Phase 1/2/3/4]  
**Next Task:** [task spesifik berikutnya]

**Key Requirements:**
- Sectors API = core data source (cached once/quarter)
- Derived insight (valuation, scoring) — bukan data mentah
- NO automated trade execution
- Disclaimer wajib: "bukan investment recommendation"

**Full context:** See DEVELOPMENT_GUIDE.md

**Constraints:**
- Jangan hallucinate API schema — tanya jika tidak sure
- Keep it simple — working prototype > perfect code
- Cross-check calculations dengan Excel template
```

---

## 📊 PROGRESS TRACKER

### Phase 1: Template & Data Validation
- [ ] n8n ingestion workflow created
- [ ] Sectors API credentials obtained
- [ ] Data fetched for 5 emiten (min. 5 years each)
- [ ] Cached data saved to `backend/data/sectors_data.json`
- [ ] Excel template filled with fetched data
- [ ] Valuation calculations verified (match Excel)
- [ ] Health score calculations verified
- [ ] Test script (`test_calculations.py`) all pass
- [ ] Screenshot comparison: Excel vs Script output

### Phase 2: UI/UX & Frontend
- [ ] UI/UX mockup completed (Figma/sketsa)
- [ ] Streamlit app structure created
- [ ] Company info panel implemented
- [ ] Valuation breakdown panel implemented
- [ ] Health vital signs panel implemented
- [ ] Market checklist panel implemented
- [ ] Strategic execution panel implemented
- [ ] System judgement panel implemented
- [ ] Dummy data integration
- [ ] Responsive layout tested

### Phase 3: Backend Integration
- [ ] n8n analysis workflow created
- [ ] Webhook endpoint tested (Postman/curl)
- [ ] Streamlit connected to n8n webhook
- [ ] End-to-end test (input ticker → output results)
- [ ] Error handling implemented
- [ ] Deployed to Streamlit Cloud
- [ ] Tested with 5-10 tickers

### Phase 4: Submission
- [ ] README.md completed
- [ ] GitHub repo public
- [ ] 1-minute teaser video recorded
- [ ] 3-minute judging video recorded
- [ ] Social media post published
- [ ] Final compliance check passed
- [ ] Submitted via hackathon portal

---

**Last Updated:** 8 September 2026  
**Maintained by:** Muhammad Salim