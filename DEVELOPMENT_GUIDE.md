# StockLens — Development Guide
## Single Source of Truth untuk AI Development

---

## 🎯 PROJECT OVERVIEW

**Project:** StockLens
**Hackathon:** Sectors Hackathon Indonesia 2026  
**Track:** Track 03 - Market Intelligence  
**Team:** Solo  
**Deadline:** 30 September 2026, 23:59 WIB  

**One-Sentence Product Statement:**  
StockLens adalah information and analysis tool untuk membantu investor retail Indonesia memahami kondisi perusahaan, financial history, growth, valuation, dan historical evidence secara terstruktur.

**Important Product Positioning:**
- StockLens adalah **information and analysis tool**, bukan investment recommendation engine.
- UI tidak menggunakan bahasa BUY / SELL sebagai keputusan produk.
- User tetap membuat keputusan investasinya sendiri berdasarkan informasi yang ditampilkan.

---

## ✅ HACKATHON COMPLIANCE (NON-NEGOTIABLE)

### Track 03 Requirements
- ✅ Produce **derived insight** (valuation models, scoring, comparative analysis) — bukan sekadar data mentah.
- ✅ AI/LLM optional dan bukan bagian wajib dari produk.
- ✅ Qualifies as a market intelligence / comparative analysis product.

### General Requirements
- ✅ **Sectors API sebagai core production data source** — tanpa Sectors, produk tidak berfungsi dalam production architecture.
- ✅ Working prototype / MVP dengan end-to-end workflow.
- ✅ Live deployment optional sesuai hackathon requirements.
- ✅ **NO automated trade execution.**
- ✅ Current frontend stack: **Next.js + TypeScript + Tailwind**.
- ✅ Project dibuat khusus untuk hackathon.

### Build Period Rules
- ✅ Repository dibuat setelah 19 Agustus 2026.
- ✅ No pre-event code.
- ✅ Freeze setelah submit sesuai deadline hackathon.

### Submission Requirements
- ✅ Public GitHub repo.
- ✅ 1-minute teaser video.
- ✅ 3-minute judging video.
- ✅ Social media post sesuai requirement hackathon.
- ✅ Disclaimer: **"Information and analysis tool, bukan investment recommendation."**

---

## 🏗️ TECHNICAL ARCHITECTURE

### High-Level Production Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│ DATA LAYER                                                  │
│ Sectors API → n8n Ingestion → Canonical Data Store         │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ BACKEND / CALCULATION LAYER                                 │
│ Read Canonical Data → Calculate → Application API Contract  │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ FRONTEND LAYER                                              │
│ Next.js + TypeScript + Tailwind                             │
│ User Input → Application Data Contract → StockLens UI      │
└─────────────────────────────────────────────────────────────┘
```

### Current Frontend Development Architecture

```text
Template_Sample_data.md
        ↓
Identify available frontend metrics + definitions
        ↓
frontend/src/data/mock-stock-details.ts
        ↓
StockLens frontend UI
```

### Future Production Architecture

```text
Sectors API
    ↓
n8n ingestion
    ↓
Database / Canonical Data Store
    ↓
Calculation & Analysis Layer
    ↓
Backend API Contract
    ↓
Next.js Frontend
```

---

## 🧠 FRONTEND DATA REFERENCE & RUNTIME SOURCES

### Canonical Frontend Development Reference

`D:\Stock Analyzer\Template_Sample_data.md` is the canonical frontend development reference for the data and metrics that the UI is expected to be able to display.

It represents the **sample frontend data coverage** expected during development, including:
- available metrics
- available periods
- sample values
- derived outputs
- metric terminology
- metric definitions
- intended organization / grouping of information

Use this file to understand what data the frontend should be capable of representing.

### Roles of the Data Sources

The roles are intentionally distinct:

- `Template_Sample_data.md` → **frontend data availability and presentation reference**.
- `frontend/src/data/mock-stock-details.ts` → **temporary runtime Single Source of Truth** for the current frontend development phase.
- Production backend/API data → **future runtime source**.

### Development Flow

```text
Template_Sample_data.md
        ↓
Identify available frontend data + metric definitions
        ↓
Populate / update mock-stock-details.ts
        ↓
Frontend UI
```

### Production Flow

```text
Sectors API
        ↓
n8n / ingestion
        ↓
Canonical Data Store
        ↓
Application / Backend Data Contract
        ↓
Frontend UI
```

### Rules for AI Development

- Before declaring a metric unavailable, inspect `Template_Sample_data.md`.
- Before adding or removing a metric from a research tab, cross-check `Template_Sample_data.md`.
- Preserve the metric names and meanings from the template unless the product specification explicitly changes them.
- If a metric exists in `Template_Sample_data.md` but not in `mock-stock-details.ts`, treat it as **available in the frontend reference but not yet implemented in the mock data model** — not as unavailable.
- Distinguish **direct/source metrics** from **derived metrics**.
- Do not invent a metric definition when an existing template definition is available.
- Do not fabricate missing values.
- Do not silently infer missing source values merely to fill a UI slot.
- If a UI requires a limited number of periods, select periods dynamically from the available data rather than hardcoding specific quarter/year labels.
- If fewer periods are available, render fewer periods.
- Do not hardcode a specific ticker's period structure into reusable UI logic.
- Do not make frontend components read `Template_Sample_data.md` directly.
- Do not add runtime filesystem access for the frontend.
- Do not read CSV files directly from frontend components.
- Keep frontend components data-source independent.

### Temporary Frontend Runtime Source

During the current frontend development phase, the temporary runtime Single Source of Truth is:

`frontend/src/data/mock-stock-details.ts`

This file represents the canonical data shape consumed by the frontend.

### Important Development Principle

The frontend should not care whether data ultimately comes from:
- CSV
- local files
- Sectors API
- n8n
- Supabase / database
- another backend source

The frontend should consume the application data contract only.

---

## 📁 REPO STRUCTURE

```text
stocklens-stock-analyzer/
├── README.md
├── DEVELOPMENT_GUIDE.md
├── docs/
│   ├── STOCKLENS_RULES.md
│   └── STOCKLENS_PRODUCT.md
├── frontend/
│   ├── src/
│   │   ├── app/                  # Next.js routes
│   │   ├── components/           # UI + research components
│   │   └── data/                 # Temporary frontend SSOT / mock data
│   ├── public/
│   ├── package.json
│   └── tailwind.config.ts
├── Data/                         # Development/reference data; not read directly by frontend
├── n8n-workflow/                 # Production/integration workflows when implemented
├── backend/                      # Future backend/calculation layer
└── scripts/                      # Validation / testing scripts
```

---

## 🚀 DEVELOPMENT PHASES

### PHASE 1: Template & Data Foundation ✅ COMPLETED

**Goal:** Build and validate the Excel analysis template using data retrieved from the Sectors API, then prepare the validated sample data as the frontend development reference.

**Completed:**
- [x] Excel analysis template created.
- [x] Data retrieved from Sectors API.
- [x] Template populated with sample/company data.
- [x] Financial, valuation, growth, quality, and supporting metrics established.
- [x] Template outputs converted into `Template_Sample_data.md`.
- [x] Sample data/reference structure prepared for frontend development.

**Status:**
Completed. The Excel/template stage is the foundation for the frontend sample-data contract.

---

### PHASE 2: UI/UX & Frontend Prototype ✅ CURRENT

**Goal:** Build and finalize the StockLens frontend using validated sample data from `Template_Sample_data.md`.

**Runtime data source during this phase:**

`frontend/src/data/mock-stock-details.ts`

**Important:**
- No live backend connection yet.
- No direct CSV/file access from frontend components.
- UI must be built against the application data contract.
- `Template_Sample_data.md` is the reference for available frontend data and metric definitions.
- Do not expand backend architecture inside frontend tasks unless explicitly requested.

**Current Scope:**
- [x] Market Overview
- [x] Stock Research Overview
- [x] Financials
- [ ] Growth
- [ ] Valuation
- [ ] Backtest
- [x] Shared component system / visual language
- [ ] Loading / empty / error states refinement
- [ ] Desktop UI refinement
- [ ] Responsive behavior refinement

**Success Criteria:**
- [ ] All primary research tabs implemented.
- [ ] UI hierarchy and terminology locked.
- [ ] Sample data correctly represented.
- [ ] No fabricated metrics.
- [ ] Frontend production build passes.
- [ ] Frontend remains independent of local reference files.

**Current Focus:**
Growth tab.

---

### PHASE 3: Backend & Database

**Goal:** Build the production data, database, and calculation backend behind the finalized frontend data contract.

**Production data flow:**

```text
Sectors API
    ↓
n8n ingestion
    ↓
Database / Canonical Data Store
    ↓
Calculation & Analysis Layer
    ↓
Backend API Contract
```

**Scope:**
- [ ] Sectors API integration.
- [ ] Database schema.
- [ ] Company/master data.
- [ ] Historical annual data.
- [ ] Historical quarterly data.
- [ ] Derived financial metrics.
- [ ] Growth calculations.
- [ ] Valuation calculations.
- [ ] Backtest calculations.
- [ ] Server-side/private calculation logic where appropriate.
- [ ] Stable application API response contract.
- [ ] Error handling for missing or malformed data.

**Success Criteria:**
- [ ] Data can be fetched and stored reliably.
- [ ] Calculations match the validated template outputs.
- [ ] API returns stable application data contract.
- [ ] Missing/invalid data handled safely.
- [ ] Production calculations are separated from frontend presentation logic.

---

### PHASE 4: End-to-End Integration

**Goal:** Connect the production backend and database to the finalized Next.js frontend.

**Data flow:**

```text
Sectors API
    ↓
n8n
    ↓
Database
    ↓
Backend/API
    ↓
Next.js
    ↓
StockLens UI
```

**Scope:**
- [ ] Replace mock data with backend/API data.
- [ ] Connect ticker selection to backend.
- [ ] Connect Overview.
- [ ] Connect Financials.
- [ ] Connect Growth.
- [ ] Connect Valuation.
- [ ] Connect Backtest.
- [ ] Loading states.
- [ ] Empty states.
- [ ] Error states.
- [ ] Multi-ticker testing.

**Success Criteria:**
- [ ] End-to-end ticker workflow works.
- [ ] Frontend displays production data correctly.
- [ ] UI data contract remains stable.
- [ ] Tested across multiple tickers.
- [ ] No direct dependency on local sample/reference files.

---

### PHASE 5: Submission Prep

**Goal:** Prepare the final working product and hackathon submission.

**Scope:**
- [ ] Deployment.
- [ ] README.
- [ ] Architecture documentation.
- [ ] Teaser video.
- [ ] Judging video.
- [ ] Disclaimer.
- [ ] Final compliance check.
- [ ] Final repository cleanup.
- [ ] Final freeze / submit.

---

## 🎨 UI/UX SPECIFICATIONS

### Core Layout Principles

- Desktop-first during the current frontend phase.
- Fixed left sidebar.
- Main content scrolls independently.
- No unnecessary top header.
- Primary navigation: Market Overview and Profile; stock research is accessed through Market → ticker.
- Use consistent card hierarchy, spacing, typography, and semantic colors across research tabs.
- Prefer information hierarchy over decorative complexity.
- Do not add UI elements solely to fill empty space.
- Do not create duplicate information when the same information is already clearly visible elsewhere.

### Stock Research Tab Structure

The current primary research tabs are:

1. Overview
2. Financials
3. Growth
4. Valuation
5. Backtest

There is **no primary Health tab**.

Health-related raw data may remain in the data layer for future calculations, but it is not a primary research section unless explicitly requested later.

### Financials Structure

Financials uses:
- Annual / Quarterly toggle.
- Three large trend cards.
- Six supporting metric cards.
- Historical financial table.

Trend-card principle:
- Chart = actual financial series.
- Annual performance indicator = CAGR (5Y) where appropriate.
- Quarterly performance indicator = latest-quarter YoY growth where available.

Supporting-card principle:
- Metric title.
- Main value.
- Optional useful context.
- Do not show redundant period labels such as `2025 annual` or `Q2 2026` inside every card when the active period is already obvious.
- Do not fabricate interpretation merely to fill a card.

### Growth Tab Naming

The research tab is named exactly:

**Growth**

Do not use:
- Health
- Health & Growth
- Financial Health as a primary tab

### General Metric Card Rule

A metric card should answer:
1. What is the metric?
2. What is the current/latest value?
3. Is there a useful context or interpretation?

If a verified context exists, show it.
If no useful context exists, use the correct unit/context rather than inventing a narrative.

---

## ⚠️ CONSTRAINTS & GUARDRAILS

### AI Coding Guidelines

1. **Do not hallucinate API endpoints.** If the Sectors API schema is unknown, inspect available documentation or ask before implementing.
2. **Do not over-engineer.** This is a hackathon project; prioritize a working prototype and clean architecture over unnecessary abstraction.
3. **Keep it simple.** Use Next.js + TypeScript + Tailwind for frontend; use n8n for integration/automation where appropriate.
4. **Always verify calculations.** Any formula or derived metric must be cross-checked against the validated template data where applicable.
5. **Comment complex logic.** Judges may inspect the repository.
6. **Make the smallest clean change.** Avoid unrelated refactors.
7. **Do not modify locked sections without explicit instruction.**
8. **Respect the application data contract.** UI components should not depend on CSV files or local reference files.

### Common Pitfalls to Avoid

- ❌ Do not hardcode arbitrary data.
- ❌ Do not invent missing financial values.
- ❌ Do not infer missing source values just to make a chart or card look complete.
- ❌ Do not read CSV files directly from frontend components.
- ❌ Do not add frontend filesystem access.
- ❌ Do not treat absence from `mock-stock-details.ts` as proof that a metric is unavailable; cross-check `Template_Sample_data.md` first.
- ❌ Do not duplicate metrics unnecessarily across sections.
- ❌ Do not rename or redefine a metric without checking the template/product specification.
- ❌ Do not reintroduce Health as a primary research tab.
- ❌ Do not touch Market Overview / locked Overview unnecessarily.
- ❌ Do not add dependencies for a small UI change unless clearly necessary.

### OK FOR DEVELOPMENT

- ✅ Frontend development may use validated sample data derived from `Template_Sample_data.md` through `mock-stock-details.ts`.
- ✅ The frontend can use mock/sample data during Phase 2.
- ✅ Production runtime data must come through the Sectors API/backend data flow.

### Data Selection Rules

For historical or quarterly series:
- Use the periods actually present in the application data model.
- Sort periods chronologically for display.
- If the UI requests a maximum number of recent periods, take the latest available periods dynamically.
- If fewer periods are available, render fewer periods.
- Never hardcode a specific quarter as if it were universally available.

### When in Doubt

- Refer back to `DEVELOPMENT_GUIDE.md`.
- Cross-check `Template_Sample_data.md`.
- Inspect the current data model before changing components.
- Prefer asking for clarification over inventing assumptions.

---

## 🔗 QUICK CONTEXT RESET

Paste this block into a new AI coding session when needed:

```text
## QUICK CONTEXT — StockLens

Project: StockLens
Hackathon: Sectors Hackathon Indonesia 2026
Track: Track 03 — Market Intelligence
Stack: n8n (backend/integration) + Next.js + TypeScript + Tailwind (frontend) + Sectors API (production data)
Deadline: 30 September 2026

Current Phase: Phase 2 — UI/UX & Frontend Prototype
Current Focus: Growth tab

Frontend development data reference:
D:\Stock Analyzer\Template_Sample_data.md

Temporary frontend runtime Single Source of Truth:
frontend/src/data/mock-stock-details.ts

Important architecture rules:
- Template_Sample_data.md = frontend data availability / definition / sample coverage reference.
- mock-stock-details.ts = temporary runtime SSOT for the frontend development phase.
- Frontend components MUST NOT read CSVs or local reference files directly.
- Production flow will be Sectors API → n8n → database/canonical data → backend API contract → Next.js.
- Do not fabricate data.
- Cross-check Template_Sample_data.md before declaring a metric unavailable.
- Preserve metric definitions and terminology from the template unless product requirements explicitly change them.
- No primary Health tab; the research tab is named Growth.
- Do not modify locked Market Overview / Overview unnecessarily.

Product positioning:
- Information and analysis tool.
- Not an investment recommendation engine.
- No automated trade execution.

Before coding:
1. Inspect the current implementation.
2. Cross-check Template_Sample_data.md.
3. Inspect mock-stock-details.ts.
4. Make the smallest clean change.
5. Verify TypeScript, lint, and build where practical.
```

---

## 📊 PROGRESS TRACKER

### Phase 1: Template & Data Foundation
- [x] Excel analysis template created.
- [x] Data retrieved from Sectors API.
- [x] Template populated with sample/company data.
- [x] Financial / valuation / growth / quality structures established.
- [x] Template converted into `Template_Sample_data.md`.
- [x] Sample data prepared for frontend development.

### Phase 2: UI/UX & Frontend
- [x] Market Overview implemented / baseline locked.
- [x] Stock Research Overview implemented / structure locked.
- [x] Financials implemented / current structure locked.
- [ ] Growth tab implemented and refined.
- [ ] Valuation tab implemented and refined.
- [ ] Backtest tab implemented and refined.
- [x] Shared component / visual language established.
- [ ] Loading / empty / error states refined.
- [ ] Desktop UI final pass.
- [ ] Responsive behavior final pass.

### Phase 3: Backend & Database
- [ ] Sectors API integration.
- [ ] Database schema.
- [ ] Historical annual data.
- [ ] Historical quarterly data.
- [ ] Company/master data.
- [ ] Derived metric calculations.
- [ ] Growth calculations.
- [ ] Valuation calculations.
- [ ] Backtest calculations.
- [ ] Stable API response contract.
- [ ] Server-side/private calculation logic.

### Phase 4: End-to-End Integration
- [ ] Replace mock data with production API data.
- [ ] Ticker-driven backend request flow.
- [ ] Overview connected.
- [ ] Financials connected.
- [ ] Growth connected.
- [ ] Valuation connected.
- [ ] Backtest connected.
- [ ] Loading states.
- [ ] Empty states.
- [ ] Error states.
- [ ] Multi-ticker testing.

### Phase 5: Submission
- [ ] Deployment.
- [ ] README completed.
- [ ] Architecture documentation completed.
- [ ] Teaser video recorded.
- [ ] Judging video recorded.
- [ ] Disclaimer verified.
- [ ] Final compliance check passed.
- [ ] Final repository cleanup.
- [ ] Submitted.

---

**Last Updated:** 16 September 2026  
**Maintained by:** StockLens project owner
