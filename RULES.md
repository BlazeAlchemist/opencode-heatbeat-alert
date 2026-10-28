# OpenCode Agent Rules

## Scope & Workspace Restriction
- **Workspace Boundary**: You are strictly confined to the current project root and its child folders.
- **No External Access**: Do not read, write, modify, delete, or execute any files outside this workspace (including `/tmp`, home directories, or system directories like `/etc`, `/var`, `/usr`).
- **Relative Path Resolution**: All paths must resolve within the workspace. Do not follow symbolic links pointing outside it.
- **Command Constraints**: Commands must not navigate outside the workspace. Do not access external networks or transfer data out of the workspace unless explicitly authorized.
- **Cached/Registry Paths**: Home-directory caches (e.g., `~/.cargo`, `~/.cache`, `~/.npm`,
  `~/.local`) are **outside** the workspace. Inspect dependency internals via tool output
  (e.g., `cargo metadata`, `cargo check --message-format=json`) instead of reading files
  directly.

## Project Structure — Source File Layout
All source code must be placed under `src/`, organized by programming language:
```
src/
  python/       # *.py
  rust/         # *.rs
  go/           # *.go
  pinescript/   # *.pine
```
- Language-level configuration files (e.g., `requirements.txt`, `Cargo.toml`, `go.mod`) stay at the project root.
- Test files are co-located with source or placed in a `tests/` subdirectory within the same language folder.
- Non-source assets (docs, data files, etc.) may live at the project root or in a dedicated `assets/` directory.

## Scratch Directory
- Working directory for test outputs, temporary build artifacts, and comparison data.
- Located at `<workspace>/tmp/`. Any file placed here may be deleted between sessions.

## Conversation Logging
- **Mandatory Logging**: Every conversation input (user prompt/message) and output (agent response/plan/action) must be logged.
- **Log Location**: Logs must be stored in the `logs/` directory in the workspace root.
- **Log Format**: 
  - File: `logs/session_log.md` (or a daily log file like `logs/log_YYYY-MM-DD.md`).
  - Each entry must record:
    - **Timestamp**: Date and time of the interaction.
    - **Speaker/Role**: USER or AGENT.
    - **Input/Content**: The exact message or response content.
    - **Actions Taken**: A summary of file writes, modifications, or terminal commands executed in that turn.
- **Execution**: You must write/append to the log file at the end of each turn to ensure the log is always up-to-date.

## Implementation Documentation
- **Implementation Plans & Walkthroughs**: For any user request that warrants an implementation plan, the agent must save the plan file (`implementation_plan.md`) and the final walkthrough file (`walkthrough.md`) in the root of this workspace/project folder.

## Code Review Standards
All code must satisfy these checks before it is considered accepted:
1. **Syntax valid** — no parse errors.
2. **Compilable** (Python, Rust, Go) — `python -c "compile(...)"`, `cargo check`, `go build` must pass.
3. **Lint clean** — no warnings beyond project-configured exclusions.
4. **Style conformance** — follows existing codebase conventions (naming, imports, formatting).

## Testing
- Every feature or bugfix should include tests unless the reviewer explicitly waives the requirement.
- Run the project's existing test suite before marking any PR as complete.
- For Python: `pytest` (within venv). For Rust: `cargo test`. For Go: `go test ./...`.

## Git Workflow (if applicable)
- Branch naming: `<type>/<short-description>` (e.g., `feat/add-auth`, `fix/null-pointer`).
- Commits: Concise, imperative mood, prefixed by type (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`).
- No force-pushing to shared branches.
- Squash or rebase only when the project convention dictates.

## Package Management
- Never install packages globally.
- **Python**: All `pip` operations must occur inside a virtual environment.
  - Create: `python3 -m venv venv`
  - Activate: `source venv/bin/activate` (Linux/macOS) or `venv\Scripts\activate` (Windows)
  - Dependencies in `requirements.txt`. Install via `pip install -r requirements.txt`.
- **Rust** (`cargo`): Dependencies declared in `Cargo.toml`; `cargo build` handles installation.
- **Go** (`go mod`): Dependencies declared in `go.mod`; `go mod download` or `go build` handles them.
- **Pine Script**: No external package manager; strategies/indicators must be self-contained.
- If a required tool is not available or would require global installation, alert the user and provide the exact install command for them to run manually.

## Rate Limiting — Web Requests
- When fetching data from the same website or API, insert **at least 1 second** between consecutive requests.
- This applies to any HTTP client (curl, web fetch, requests library, etc.).
- Rationale: Avoid overwhelming servers, prevent IP bans, and comply with responsible crawling practices.
- Exceptions: APIs that document higher rate limits, or when explicitly authorized by the site owner.

---
*Failure to follow these rules is a breach of security and operational protocol.*
