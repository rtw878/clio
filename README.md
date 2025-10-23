# clio

A professional research platform for exploring The National Archives (TNA) catalogue — fast, reliable, and designed for rigorous scholarship.

<p align="center">
  <img src="web/static/images/logo.png" alt="clio" height="80" />
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green" alt="License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.8%2B-3776AB" alt="Python"></a>
  <a href="https://github.com/rtw878/clio"><img src="https://img.shields.io/badge/GitHub-rtw878%2Fclio-black" alt="Repo"></a>
</p>

---

## Vision

clio provides a refined, local-first experience for working with archival metadata from TNA Discovery. It adds a modern web UI, fast local search (FTS5), optional semantic search, and strong provenance and validation — optimized for historians, archivists, and digital humanities teams.

---

## Features

- Search at research speed (SQLite + FTS5, optional semantic search)
- Clean, accessible web interface (FastAPI + Jinja2)
- Respectful API usage with strict rate limiting and logging
- Data validation, referential integrity, and provenance tracking
- Streaming operations, backups, and professional export formats

---

## Quick start

```bash
# Clone
git clone https://github.com/rtw878/clio.git
cd clio

# Install
pip install -r requirements.txt

# Configure (if required)
copy config.env.example config.env

# Run
python main.py serve --port 8080
# Open http://localhost:8080
```

---

## Architecture

- `web/`: FastAPI app, Jinja templates, premium CSS
- `api/`: Discovery client with retries, backoff, and rate limiting
- `storage/`: SQLite + FTS5, schema migration, cache
- `search/`: optional semantic search engine
- `validation/`: validators and reporting
- `utils/`: exporters, streaming, backup/recovery, provenance

---

## Brand identity

- Primary logo: `web/static/images/logo.png`
- Symbol: `web/static/images/logo-symbol.png`
- Favicon: `web/static/images/favicon.png`
- Additional assets: `logos/`

For color, typography, and components, see `BRAND_KIT.md` and `web/static/css/main.css`.

---

## License

MIT — see `LICENSE`.