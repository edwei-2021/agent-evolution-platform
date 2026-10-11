# Validation Record（驗證紀錄）

Date: October 11, 2026. Environment: the current Linux workspace, not the user's Windows host.

| Check | Result | Interpretation |
| --- | --- | --- |
| Python syntax compilation | PASS | `check-ollama.py` parses under Python 3.12 |
| Bash syntax | PASS | `wsl-connect.sh` parses with `bash -n` |
| Native and compatible HTTP probes | PASS with local mock | The client checks version and both model listings |
| Chat request and response handling | PASS with local mock | Correct model ID, non-streaming request, nonempty reply |
| Proxy bypass | PASS with deliberately unusable proxy environment | Direct HTTP client does not use HTTP proxy variables |
| Export file with spaces and Bash sourcing | PASS | Variables load correctly from generated shell-safe exports |
| Missing model | PASS negative case | Nonzero exit; existing exports retained |
| Malformed model-list API | PASS negative case | Nonzero exit; existing exports retained |
| Inference without model ID | PASS negative case | Argument rejected |
| Windows PowerShell execution | PENDING on target | PowerShell is unavailable in this workspace; code reviewed only |
| Actual Windows firewall/NAT path | PENDING on target | Requires the user's Windows 10 and WSL2 virtual network |
| Real model loading and generation | PENDING on target | Requires the Windows Ollama installation/model |

The earlier experiment used a Windows Ollama endpoint on port 11435. These scripts are a focused reconstruction of that connection approach, not recovered copies of all historical scripts. Local mock QA does not establish that the new package has already run on the target Windows host.

On-target acceptance: run Windows `check`, refresh `firewall`, and run WSL `--model <exact ID> --infer`. Confirm both metadata APIs and a real generated answer. Preserve the printed server version, current endpoint, and model ID.
