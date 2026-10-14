# MASTER AI RULES & WORKSPACE GUIDELINES

## 1. Core Operating Principles
- **Read First, Code Later:** Before implementing any feature or refactoring code, inspect existing workspace documentation in `.ai/` and `AGENTS.md`.
- **Maintain Workspace Structure:** Ensure all new architecture decisions, API designs, and test cases are recorded in `.ai/` and `docs/`.
- **Token Efficiency:** Keep explanations concise. Prefer diffs over re-printing entire files. Avoid non-essential prose.

## 2. Directory & Documentation Standards
- **.ai/ Folder:** Memory bank for AI agents. Do not delete or rename directories within `.ai/`.
- **docs/ Folder:** Human-readable technical specifications (BA, SA, TEST, USER_GUIDE, DEVOPS, ADR).
- **.gitignore Enforcement:** Never commit `.codegraph/`, temporary snapshots, `.env`, or `.db` files to git.

## 3. Code Generation & Quality Control
- **Strict Typing:** Use typing / type hints consistently.
- **Architecture Compliance:** Follow SOLID, DRY, and clean modular architecture.
- **Error Handling:** Standardized error handling, try-catch blocks, and structured logging.
