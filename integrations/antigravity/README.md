# Antigravity Integration

Antigravity integration is slash-commands only.

Install command templates to user directory:

```bash
python -m maestro_flow.cli install --target antigravity --scope user
```

Install command templates to project directory:

```bash
python -m maestro_flow.cli install --target antigravity --scope project
```

Included commands:
- `maestro-spec`
- `maestro-run`

If your Antigravity build uses a custom command path:

```bash
python -m maestro_flow.cli install --target antigravity --scope user --dest "<your-command-path>"
```
