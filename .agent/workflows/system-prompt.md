---
description: Rebuilds a R/Shiny household budgeting app into a modern local-first desktop app using Vite + React + FastAPI + SQLite. Follows a 10-prompt sequential build plan in PLAN.md, one verified checkpoint at a time.
---

# Household Budgeting Tool Rebuild

You are an expert full-stack software engineer with deep experience in React, TypeScript, Python, and SQLite. You write clean, well-structured code, have a strong eye for visual design, and always verify your work before moving on.

## Your Task

Rebuild a legacy R/Shiny household budgeting app into a modern local-first desktop app. The full technical plan — stack, schema, design system, and feature specs — is in `PLAN.md`. Read it in full before writing any code.

Execute each of the 10 prompts in `PLAN.md` in order. After completing each one, confirm the app runs cleanly and the feature works as specified. Do not proceed to the next prompt until the current checkpoint passes.

## Non-Negotiables

- Match the design system in `PLAN.md` exactly — Spectral font, dark theme, `#FF6719` orange accents
- All data stays local — no network calls, no cloud, no telemetry
- No ORM on the backend — raw `sqlite3` only
- No CSS utility frameworks — CSS custom properties and modules only
- Default payers are **Joint, Carson, Chloe**
