---
name: specs-pull
description: Pull latest spec files from the spec service
---

# /specs-pull

Pull the latest spec documents from the Awolve Spec Service.

## Instructions

Run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/sync.py pull
```

If the user is not authenticated, tell them to run `/specs-login` first.

If there is no `.claude/specs.local.md` config file in the project, help them create one with:
```yaml
---
project: <project-name>
specs_path: ./specs
service_url: https://specs.awolve.ai
---
```

After pulling, briefly summarize what was synced.
