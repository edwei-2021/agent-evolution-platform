# Ollama Bridge Verification (Ollama 橋接驗證)

Date: October 11, 2026. Version: 0.4.1.

The user has independently established metadata connectivity from Windows 10 Ollama to WSL2 on port 11435. The project incorporates that evidence without rerunning target-host tests. The attachment diagnostic is preserved byte-for-byte and covered by its recorded SHA-256.

Development environment: Ubuntu 24.04.3, Python 3.12.14, Linux Node 24.19.0; no WSL kernel, Python 3.11 interpreter or Windows host access. The project `.venv` is available. The WSL installer's APT checks report missing packages in this container; the actual executable tools needed for development tests are present. No APT installation was performed here. The new integration uses Python standard-library modules only; WSL installation now checks `iproute2` explicitly.

| Verification | Scope |
| --- | --- |
| Offline configuration and restart | Saved host/port/model/timeouts survive provider restart; configuration reads issue no HTTP requests |
| NAT discovery | Uses current WSL IPv4 route; changes are resolved dynamically; ambiguous/non-WSL routes require an override |
| Export generation | Shell-quoted exports survive spaces and shell metacharacters; existing proxy exclusions retained |
| Mock metadata and inference | Exact endpoint/payload, model ID, non-streaming request and separate pass states |
| Proxy bypass | Successful mock requests with deliberately unusable HTTP proxy variables |
| Failure evidence | HTTP error, malformed model listing and empty answer are failures; no automatic retry |
| Concurrent/revision guards | Duplicate operation and outdated configuration revision cannot dispatch another request |
| Local HTTP security | Settings round-trip, CSRF/Origin rejection and optimistic revision checks |
| Original diagnostic | Attachment hash matches; mock API-only run sends no inference |
| Web controller/rendering | No automatic probe, session token, explicit request, failure display, escaped output and earlier-revision labeling |

New regression coverage: 8 Python and 4 JavaScript tests. Full regression: **47 JavaScript + 46 Python tests passed (93 total)**. Python regression includes actual local role processes and the existing Skill evidence/approval/rollback flow; elapsed time was 47.303 seconds. JavaScript regression includes polling and Skill controls. `git diff --check`, Bash syntax and changed Python/JavaScript syntax checks also passed. All provider HTTP tests use a local mock; they do not establish real model loading or quality. Windows PowerShell remains preserved attachment code and was not executed in this container. Browser visual/full DOM QA is not claimed.
