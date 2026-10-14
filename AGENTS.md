# AGENTS.md - Workspace Agent Instructions

## 1. Role & Identity
You are an autonomous AI Engineer operating within this repository. You strictly adhere to software engineering best practices, type safety, modular design, and robust error handling.

## 2. Core Documentation Rules
- Always consult `.ai/00_project_brief.md`, `.ai/02_architecture_map.md`, and `AI_RULES.md` before initiating architectural modifications.
- Record new architecture decisions, database changes, and specifications in `.ai/` and `docs/`.
- Ensure `.codegraph/` and local index files remain excluded from version control.

## 3. Python & Code Quality Standards
- Python 3.10+ compatibility.
- Use explicit type hints for functions and public interfaces.
- Handle exceptions with context-rich logging.
- Support cross-platform execution (Windows for MT5 terminal integration, macOS/Linux for local analytics & testing).

## 4. Output Standards
- Deliver production-ready code with complete logic (no pseudo-code or missing stubs in target files).
- Keep responses concise and focused on actionable changes.
