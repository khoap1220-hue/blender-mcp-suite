# Master Orchestration Plan: Blender MCP Production Suite

## Overview
Transform existing Blender bridge prototypes into an industrial-grade Model Context Protocol (MCP) server suite integrated with Blender 4.1+, meeting all acceptance criteria in `ORIGINAL_REQUEST.md`.

## Workflow Phases

### Phase 0: Survey & Scope Formulation
- [ ] Dispatch 3 parallel exploratory agents:
  - Agent 1: `teamwork_preview_explorer` — Analyze existing codebase architecture, bridge scripts, addon, and protocol gaps.
  - Agent 2: `teamwork_preview_spec_miner` — Extract full functional requirements and specifications for R1-R4 from `ORIGINAL_REQUEST.md`.
  - Agent 3: `teamwork_preview_explorer` — Investigate Blender 4.1 runtime environment on Windows, daemon lifecycle, socket auto-recovery, and process handling.
- [ ] Synthesize findings into root `PROJECT.md` with comprehensive Architecture, Feature Inventory, Milestones, and Interface Contracts.

### Phase 1: Dual-Track Dispatch
- [ ] Track A: E2E Testing Track
  - Design opaque-box test runner and test cases (Tiers 1-4) in `tests/test_blender_mcp_e2e.py`.
  - Produce `TEST_INFRA.md` and declare `TEST_READY.md`.
- [ ] Track B: Implementation Track
  - Milestone 1 (M1): Blender Daemon Lifecycle & Resilient Socket Auto-Recovery (R1).
  - Milestone 2 (M2): Full-Spectrum 3D MCP Tools Suite (R2).
  - Milestone 3 (M3): Structured Error Handling & Zero-Crash Boundary (R3).
  - Milestone 4 (M4): E2E Test Suite Execution (Tiers 1-4 pass 100%) and Adversarial Hardening (Tier 5).
  - Milestone 5 (M5): Documentation, 1-Click Launchers, and AI Client Configs (Antigravity/Cursor/Claude Desktop).

### Phase 2: Final Gate & Delivery Synthesis
- [ ] Verify 100% test pass on `tests/test_blender_mcp_e2e.py`.
- [ ] Forensic audit verification (binary veto).
- [ ] Final handoff report to parent.
