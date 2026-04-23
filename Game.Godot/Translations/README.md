Place translation resources here.

Current M1 policy:
- `en.csv` and `zh-CN.csv` are project-local key/value source tables.
- Runtime UI first tries `TranslationServer.Translate(key)`, then falls back to these CSV files when the translation server returns a raw key or empty value.
- Do not register the current source CSV files directly in `project.godot` until they are converted to a Godot-verified `.translation`, `.po`, or standard CSV translation resource.
- `SettingsLoader` applies `settings.language` via `TranslationServer.SetLocale(...)` at startup.

Authoritative strategy:
- `docs/gdd/m1-translation-loading-strategy.zh-CN.md`

