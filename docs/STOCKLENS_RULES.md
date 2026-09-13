StockLens Frontend Development Rules

PROJECT:
StockLens is a beginner-friendly Indonesian stock market intelligence web application.

CURRENT DEVELOPMENT PHASE:
Frontend only.
Do not implement backend integrations unless explicitly requested.

TECH STACK:
- Next.js
- TypeScript
- Tailwind CSS
- shadcn/ui

DESIGN:
- Desktop-first
- Primary viewport: 1440x900
- Secondary viewport: 1280x800
- Mobile optimization is postponed
- Clean fintech research interface
- Beginner-friendly
- Calm, trustworthy, analytical
- Avoid excessive visual density
- Avoid unnecessary animations
- Avoid excessive popups
- Avoid dashboard clutter

APPLICATION SHELL:
- Header is fixed
- Left navigation is fixed
- Main content area is independently scrollable
- Header and sidebar must not scroll with main content
- Keep the application shell consistent across all pages

NAVIGATION:
Primary navigation contains only:
- Market
- Profile

STOCK RESEARCH:
Stock detail pages are part of Market, not separate top-level navigation.

Tabs:
- Overview
- Financials
- Health & Growth
- Valuation
- Historical Evidence

DESIGN CONSISTENCY:
- Reuse existing components
- Do not create duplicate components for the same purpose
- Do not introduce a new visual language for individual pages
- Preserve established spacing, typography, colors, and component behavior

FINANCIAL LANGUAGE:
Use neutral analytical language.
Do not use investment recommendation language such as:
- BUY
- SELL
- STRONG BUY
- STRONG SELL

Prefer:
- Current Valuation
- Historical Evidence
- Historical Result
- Current Condition
- Undervalued
- Overvalued

CODE QUALITY:
- Keep components small and reusable
- Prefer readable code over clever abstractions
- Avoid unnecessary dependencies
- Do not refactor unrelated files
- Do not change architecture without explicit instruction
- Do not implement features outside the requested scope

IMPORTANT:
Before making large changes, inspect the existing project structure and reuse existing components.

When a reference screenshot is provided:
- Treat it as the primary visual reference
- Match layout hierarchy, spacing, proportions, and visual relationships
- Do not invent a different design unless explicitly requested

When uncertain:
- Ask for clarification rather than inventing a new product behavior.