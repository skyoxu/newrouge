# Main branch knowledge catalog publication

The repository keeps local publication available through:

```powershell
py -3 scripts/python/publish_knowledge_catalog.py --publish
py -3 scripts/python/publish_knowledge_catalog.py --check
```

After a merge to `main`, `.github/workflows/publish-knowledge-catalog.yml` runs on a Windows runner with full Git history. It publishes against the actual `main` commit, validates the generated layers, and opens a pull request containing only derived `knowledge/**` state when changes are required.

The workflow uses a dedicated automation branch and never writes directly to protected `main`. Merging that pull request creates a new `main` commit; the workflow runs again and verifies that the generated state is bound to the resulting commit. The local commands remain the portable path for repositories without GitHub Actions.
