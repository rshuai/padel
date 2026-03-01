# Padel Payment Tracker

Simple web app for tracking shared padel session costs and settlements.

## Pages
- `/padel.html`: editable tracker
- `/padel-view.html`: view-only tracker

## Cost Model
- Session total: `£48`
- Players per session: `4`
- Share per player: `£12`

## Run Locally (Static)
From repo root:

```bash
python3 -m http.server 8765 --directory frontend
```

Open:
- `http://localhost:8765/`
- `http://localhost:8765/padel.html`
- `http://localhost:8765/padel-view.html`

## Deployment
Netlify publish directory is configured in [netlify.toml](/Users/rshuai/Desktop/Codex/netlify.toml):

```toml
[build]
  publish = "frontend"
```
