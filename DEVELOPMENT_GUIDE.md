# Sectors Hackathon 2026 — Development Guide
## Single Source of Truth untuk AI Development

---

## 🎯 PROJECT OVERVIEW

**Project:** StockLens
**Hackathon:** Sectors Hackathon Indonesia 2026
**Track:** Track 03 - Market Intelligence
**Team:** Solo (Muhammad Salim)
**Deadline:** 30 September 2026, 23:59 WIB

**One-Sentence Problem Statement:**

"StockLens membantu investor retail Indonesia memahami kondisi, kinerja, valuasi, dan historical evidence saham secara lebih cepat melalui data dan analisis fundamental yang terstruktur."

---

## ✅ HACKATHON COMPLIANCE (NON-NEGOTIABLE)

### Track 03 Requirements

- ✅ Produce **derived insight** (valuation models, scoring, comparative analysis) — bukan sekadar data mentah
- ✅ AI/LLM optional dan **tidak digunakan sebagai fitur utama produk**
- ✅ Qualifies as market intelligence / comparative analysis / custom research logic

### General Requirements

- ✅ **Sectors API sebagai core production data source**
- ✅ Working prototype / MVP dengan end-to-end workflow
- ✅ Live deployment optional sampai tahap submission
- ✅ **NO automated trade execution**
- ✅ Current frontend stack: **Next.js + TypeScript + Tailwind**
- ✅ Project dibuat khusus untuk hackathon

### Product Positioning

StockLens adalah **information and analysis tool**.

Produk:
- menampilkan data
- menghitung derived metrics
- menyajikan valuation analysis
- menampilkan historical evidence / backtest
- membantu user melakukan research

Produk **bukan automated trading system**.

Gunakan bahasa penelitian / analysis seperti:
- analysis
- signal
- valuation
- historical evidence
- comparison
- growth
- financial performance

Hindari menjadikan UI sebagai sistem eksekusi trading.

### Build Period Rules

- ✅ Repository dibuat setelah 19 Agustus 2026
- ✅ No pre-event code
- ✅ Freeze setelah submit
- ✅ No commits setelah 30 September 2026, 23:59 WIB

### Submission Requirements

- ✅ Public GitHub repo
- ✅ 1-minute teaser video
- ✅ 3-minute judging video
- ✅ Social media post tagging @sectors
- ✅ Disclaimer:
  **"Information and analysis tool, bukan investment recommendation"**

---

# 🏗️ TECHNICAL ARCHITECTURE

## High-Level Architecture

### Current Frontend Development Architecture

```text
Template_Sample_data.md
        ↓
Frontend Data Model / Mock Data
        ↓
Next.js + TypeScript + Tailwind
        ↓
StockLens UI
Planned Production Architecture
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
Next.js + TypeScript + Tailwind
        ↓
StockLens UI
Important Architecture Principle

Frontend components must depend on the application data contract, not on the physical origin of the data.

The UI should not care whether the data ultimately comes from:

mock data
Sectors API
n8n
database
backend calculation engine

The UI should consume a stable application data shape.

🧠 FRONTEND DATA REFERENCE & RUNTIME SOURCES
Canonical Frontend Development Reference

The file:

D:\Stock Analyzer\Template_Sample_data.md

is the canonical frontend development reference for the data and metrics the UI is expected to be able to display.

It represents the sample frontend data coverage expected during development, including:

available metrics
financial periods
sample values
derived outputs
metric names
metric meanings
calculation-related context
intended frontend information coverage

Use this file to understand what the frontend should be capable of presenting.

It is especially important when deciding:

whether a metric exists
how a metric should be named
whether a metric is annual or quarterly
whether a metric is source data or derived data
which information belongs in a research tab
Distinct Roles of Data Sources
1. Template_Sample_data.md

Development reference for:

frontend data availability
metric definitions
metric terminology
sample values
data coverage
derived outputs

This is not a runtime source.

2. frontend/src/data/mock-stock-details.ts

Temporary runtime Single Source of Truth for the current frontend development phase.

This is the data model actually consumed by the frontend.

3. Production Backend / API

Future runtime source.

Production data will eventually flow from Sectors API → backend/data layer → frontend application contract.

Development Flow
Template_Sample_data.md
        ↓
Identify available frontend data
+ metric definitions
+ sample values
        ↓
Populate / update
mock-stock-details.ts
        ↓
Frontend UI
Production Flow
Sectors API
        ↓
n8n / ingestion
        ↓
Database / Canonical Data Store
        ↓
Calculation & Analysis Layer
        ↓
Frontend Application Data Contract
        ↓
Next.js Frontend
Rules for AI Development
Before declaring a metric unavailable, inspect Template_Sample_data.md.
Before adding or removing a metric from a research tab, cross-check Template_Sample_data.md.
Preserve metric names and meanings from the template unless the product specification explicitly changes them.

If a metric exists in Template_Sample_data.md but does not exist in mock-stock-details.ts, treat it as:
available in the frontend reference but not yet implemented in the mock data model.

Do NOT treat it as unavailable.

Distinguish:
direct/source metrics
derived metrics
presentation-only labels
Do not fabricate financial data.
Do not invent a new metric definition when the template already defines the metric.
If a calculation is required, verify its intended definition against the template or existing calculation logic before implementing it.
Do not make frontend components read Template_Sample_data.md directly.
Do not add runtime filesystem access to the frontend.
Do not read CSV files directly from frontend components.
Local CSV/reference files may be used during development to validate or populate the temporary mock data model, but the browser/frontend must not depend on those files.
Keep the frontend data-source independent.
For historical series:
use periods available in the canonical frontend data model
sort periods chronologically
avoid hardcoding specific periods when dynamic data is appropriate
if a UI needs "latest N periods", select them dynamically
if fewer than N periods exist, render the available periods
never invent missing values solely to fill a UI slot
Before implementing a major research tab:
inspect the current frontend implementation
inspect Template_Sample_data.md
map reference metrics to the frontend data model
identify missing implementation fields
define UI hierarchy
then implement
Temporary Frontend Runtime Source

During current frontend development, the temporary runtime Single Source of Truth is:

frontend/src/data/mock-stock-details.ts

This file represents the canonical data shape currently consumed by the frontend.

The goal is to keep the frontend UI independent from the physical source of the sample data.

📁 REPO STRUCTURE
sectors-hackathon-2026/
├── README.md
├── DEVELOPMENT_GUIDE.md
│
├── n8n-workflow/
│   ├── ingestion.json
│   └── analysis.json
│
├── backend/
│   └── data/
│       └── sectors_data.json
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── data/
│   │   └── ...
│   ├── public/
│   ├── package.json
│   └── tailwind.config.ts
│
├── scripts/
│   └── test_calculations.py
│
├── videos/
│   ├── teaser.mp4
│   └── judging.mp4
│
└── assets/
    ├── architecture.png
    └── mockup.png
🚀 DEVELOPMENT PHASES
PHASE 1: Template & Data Foundation ✅ COMPLETED
Goal

Build and validate the Excel analysis template using data retrieved from the Sectors API.

Completed
 Excel analysis template created
 Data retrieved from Sectors API
 Template populated with sample/company data
 Financial metrics established
 Valuation metrics established
 Growth metrics established
 Quality / supporting metrics established
 Template outputs converted into Template_Sample_data.md
 Sample data/reference structure prepared for frontend development
Status

Completed.

The Excel/template stage is the foundation for the frontend sample-data contract.

PHASE 2: UI/UX & FRONTEND PROTOTYPE ✅ CURRENT
Goal

Build and finalize the StockLens frontend using validated sample data from:

Template_Sample_data.md

Runtime frontend data source:

frontend/src/data/mock-stock-details.ts

Important
No live backend connection yet
No direct CSV/file access from frontend components
No production API dependency
UI must be built against the application data contract
Template_Sample_data.md is the reference for frontend data coverage and metric definitions
Frontend should not invent financial data
Frontend should preserve the intended semantics of the sample/template data
Current Scope
 Market Overview
 Stock Research Overview
 Financials
 Growth
 Valuation
 Backtest
 Shared component foundation
 Loading states
 Empty states
 Error states
 Final desktop UI refinement
 Responsive refinement
Success Criteria
 All primary research tabs implemented
 UI hierarchy and terminology locked
 Sample data correctly represented
 No fabricated metrics
 Production build passes
 Components remain data-source independent
Current Focus

Growth tab

PHASE 3: BACKEND & DATABASE
Goal

Build the production data and calculation backend behind the finalized frontend application contract.

Data Flow
Sectors API
      ↓
n8n ingestion
      ↓
Database / Canonical Data Store
      ↓
Calculation & Analysis Layer
      ↓
Backend API Contract
Scope
 Sectors API integration
 Database schema
 Company / master data
 Historical annual data
 Quarterly data
 Derived financial metrics
 Growth calculations
 Valuation calculations
 Backtest calculations
 API response contract
 Server-side/private calculation logic
 Data validation
 Missing-data handling
Success Criteria
 Data fetched reliably
 Data stored reliably
 Calculations match validated template outputs
 API returns stable application data contract
 Missing/invalid data handled safely
 Backend can support multiple tickers
PHASE 4: END-TO-END INTEGRATION
Goal

Connect the production backend and database to the finalized Next.js frontend.

Data Flow
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
Scope
 Replace mock data with backend/API data
 Connect ticker selection to backend
 Connect Overview
 Connect Financials
 Connect Growth
 Connect Valuation
 Connect Backtest
 Loading states
 Empty states
 Error states
 Multi-ticker testing
 Production data validation
Success Criteria
 End-to-end ticker workflow works
 Frontend displays production data correctly
 UI data contract remains stable
 Tested across multiple tickers
 No direct dependency on local sample/reference files
PHASE 5: SUBMISSION PREP
Goal

Prepare the final working product and hackathon submission.

Scope
 Deployment
 README
 Architecture documentation
 Teaser video
 Judging video
 Disclaimer
 Final compliance check
 Final repository cleanup
 Public GitHub verification
 Final submission
🎨 UI/UX SPECIFICATIONS
Product Direction

StockLens is designed as a beginner-friendly stock research / market intelligence application.

The UI should prioritize:

clarity
information hierarchy
consistent card structure
readable financial metrics
traceable analytical context
beginner-friendly terminology
professional financial-dashboard appearance

Avoid unnecessary visual complexity.

Current App Structure
Global App Shell
Fixed left sidebar
Main content independently scrollable
Desktop-first
No unnecessary top header duplication
Primary navigation:
Market
Profile
Research tabs live within /market/[ticker]
Stock Research Tabs

The current primary research tabs are:

Overview
Financials
Growth
Valuation
Backtest

Health is NOT a primary research tab.

Health-related raw data may remain in the data layer for future calculations.

Locked Sections
Market Overview

Do not redesign without explicit request.

Stock Research Overview

Current structure is considered locked unless explicitly requested otherwise.

Overview includes:

Research Summary
Company Profile
Price Chart
Current Valuation snapshot
Historical Evidence preview
Growth Summary
Dividend Snapshot
Financials

Financials focuses on historical financial performance.

Annual
3 large trend cards
6 supporting metric cards
historical financial table
Quarterly
3 large trend cards
6 supporting metric cards
quarterly historical financial table
Important Financials UI Rule

Large trend cards show:

actual metric
actual unit
historical series
performance indicator

Annual performance indicator:

CAGR (5Y)

Quarterly performance indicator:

latest-quarter YoY growth

Supporting cards follow:

metric title
main value
optional context

Do not use redundant period labels inside supporting cards.

GROWTH

Growth is the next research tab being implemented.

The Growth tab must be based on:

Template_Sample_data.md
current frontend data model
validated derived metrics

Do not assume that a metric is unavailable merely because it has not yet been added to the mock frontend model.

Planned Growth areas:

Historical Growth
Revenue CAGR
Net Income CAGR
EPS CAGR
Latest Growth
Revenue YoY
Net Income YoY
EPS Growth / Recovery where supported
Growth Momentum where its definition is validated
Growth Quality
Revenue Volatility / CoV
Asset Growth Gap
NWC / Revenue
NWC Intensity Change
OCF / Net Income
Revenue vs Earnings Growth
Quarterly Growth Check

Use available quarterly metrics and periods from the canonical frontend data model.

Potential metrics include:

Revenue YoY
Net Income YoY
Gross Margin
OCF / Net Income
Interest Expense
other verified quarterly growth / momentum indicators

Do not invent missing metrics.

HEALTH DATA

Health is no longer a primary research tab.

Health-related data may remain in the data layer, including:

financialHealth
debt / equity
current ratio
interest coverage
health score
related risk calculations

These may be used later by:

backend calculations
future research modules
derived metrics

Do not expose Health as a primary tab unless the product direction explicitly changes.

⚠️ CONSTRAINTS & GUARDRAILS
AI Coding Guidelines
Do not hallucinate API endpoints.
If the Sectors API schema is unknown, inspect the available documentation or ask before assuming.
Do not over-engineer.
This is a hackathon project. Prioritize a working, maintainable prototype.
Keep the frontend simple.
Use:
Next.js
TypeScript
Tailwind
existing components/patterns where possible
Always verify calculations.
Derived calculations should be cross-checked against the validated template/reference.
Comment complex logic.
Judges may inspect the repository.
Do not modify locked sections unnecessarily.
Do not add dependencies unless clearly necessary.
Prefer data-driven components over hardcoded period-specific UI.
Common Pitfalls to Avoid
❌ Do not hardcode arbitrary financial data.
❌ Do not invent financial metrics.
❌ Do not infer unavailable source values merely to fill a UI slot.
❌ Do not read CSV files directly from frontend components.
❌ Do not make browser/frontend code depend on local filesystem paths.
❌ Do not treat missing mock-model fields as proof that a metric does not exist.
❌ Do not silently change metric definitions.
❌ Do not create unnecessary abstractions.
❌ Do not redesign locked tabs without explicit instruction.
❌ Do not expose Health as a primary research tab.
❌ Do not create automated trade execution.
❌ Do not forget the financial-analysis disclaimer.
❌ Do not commit after hackathon submission freeze.
Development Data Usage
OK
✅ Frontend development may use validated sample data from Template_Sample_data.md through mock-stock-details.ts.
✅ Sample values may be manually populated into the temporary frontend SSOT.
✅ Template data may be used to validate UI coverage and metric definitions.
✅ Local reference CSVs may be used outside runtime to validate sample data.
NOT OK
❌ Frontend components importing CSV files
❌ Browser-side filesystem access
❌ Runtime parsing of Template_Sample_data.md
❌ Runtime dependency on local development paths
❌ Invented values presented as source-backed financial data
Production
✅ Production runtime data must come through the Sectors API/backend data flow.
🔄 DATA MODEL PRINCIPLES
Canonical Application Contract

The frontend should consume a stable application-level data contract.

Example concept:

Company
 ├── overview
 ├── financialHistory
 ├── growth
 ├── valuation
 ├── backtest
 └── supportingData

The physical data provider may change without forcing a UI redesign.

Historical Data Rules

When rendering historical data:

use periods available in the data model
sort periods chronologically
prefer dynamic period selection
if the UI requests latest N periods, select the latest N available
if fewer than N periods exist, render what is available
do not invent missing periods
do not infer missing values unless the metric definition explicitly requires a derived calculation
🔗 QUICK CONTEXT RESET

Use this block when starting a new AI coding conversation.

## QUICK CONTEXT — StockLens

Project: StockLens
Hackathon: Sectors Hackathon Indonesia 2026
Track: Track 03 — Market Intelligence

Stack:
- Next.js
- TypeScript
- Tailwind
- n8n
- Sectors API

Current Phase:
Phase 2 — UI/UX & Frontend Prototype

Current Focus:
Growth tab

Temporary frontend runtime Single Source of Truth:
frontend/src/data/mock-stock-details.ts

Canonical frontend development reference:
D:\Stock Analyzer\Template_Sample_data.md

Data rules:
- Template_Sample_data.md defines intended frontend data coverage and metric definitions.
- mock-stock-details.ts is the temporary runtime source for frontend development.
- Frontend must not read CSV/filesystem data directly.
- Do not fabricate financial data.
- If a metric exists in Template_Sample_data.md but not in mock-stock-details.ts, treat it as not yet implemented in the mock model, not as unavailable.
- Production data will later come from Sectors API → n8n → database/backend → application data contract → frontend.

Primary research tabs:
1. Overview
2. Financials
3. Growth
4. Valuation
5. Backtest

Health:
- not a primary research tab
- health-related raw data may remain in the data layer

Locked:
- Market Overview
- Stock Research Overview
- Financials unless explicitly requested

Development rule:
Audit current frontend + cross-check Template_Sample_data.md before implementing a major research tab.

Do not:
- invent metrics
- invent source values
- add unnecessary dependencies
- read local files from frontend
- redesign unrelated tabs
📊 CURRENT PROGRESS
Phase 1 — Template & Data Foundation

Status: ✅ COMPLETED

 Excel analysis template created
 Data retrieved from Sectors API
 Template populated
 Financial / valuation / growth / quality metrics established
 Template converted to Template_Sample_data.md
 Frontend sample-data reference prepared
Phase 2 — UI/UX & Frontend

Status: ✅ CURRENT

Completed / Locked
 App shell
 Market Overview
 Stock Research routing
 Stock Research Overview
 Financials structure
 Financials Annual/Quarterly data presentation
 Temporary frontend SSOT
 Frontend data reference guidance
Current Work
 Growth tab
 Growth data model expansion based on template sample
 Growth UI hierarchy
 Growth terminology cleanup
 Rename old "Health & Growth" tab to "Growth"
Remaining Phase 2
 Valuation
 Backtest
 Loading states
 Empty states
 Error states
 Desktop UI refinement
 Responsive refinement
 Final sample-data consistency pass
 Production build verification
Phase 3 — Backend & Database

Status: ⏳ NOT STARTED

 Sectors API integration
 Database schema
 Canonical data store
 Calculation layer
 Growth calculations
 Valuation calculations
 Backtest calculations
 Backend API contract
 Multi-ticker support
 Data validation
Phase 4 — End-to-End Integration

Status: ⏳ NOT STARTED

 Replace mock data
 Connect ticker selection
 Connect Overview
 Connect Financials
 Connect Growth
 Connect Valuation
 Connect Backtest
 Loading states
 Empty states
 Error states
 Multi-ticker testing
 Production validation
Phase 5 — Submission

Status: ⏳ NOT STARTED

 Deployment
 README
 Architecture documentation
 Teaser video
 Judging video
 Disclaimer
 Compliance check
 Final repository cleanup
 Public GitHub verification
 Final submission

Last Updated: 16 September 2026
Maintained by: Muhammad Salim
