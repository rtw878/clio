# clio

A professional research platform for exploring The National Archives (TNA) catalogue — fast, reliable, and designed for rigorous scholarship.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset=".github/assets/logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset=".github/assets/logo.svg">
    <img alt="clio - National Archives Research Platform" src=".github/assets/logo.svg" width="400">
  </picture>
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

### Logo Assets

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset=".github/assets/logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset=".github/assets/logo.svg">
    <img alt="clio - National Archives Research Platform" src=".github/assets/logo.svg" width="400">
  </picture>
</p>

#### Available Logo Formats
- **Primary Logo**: `.github/assets/logo.svg` (light mode)
- **Dark Mode Logo**: `.github/assets/logo-dark.svg`
- **Icon/Mark**: `.github/assets/mark.svg`
- **Dark Mode Mark**: `.github/assets/mark-dark.svg`
- **Wordmark**: `.github/assets/wordmark.svg`
- **Dark Mode Wordmark**: `.github/assets/wordmark-dark.svg`

### Color Palette

**Dynamic Green Gradient** - The core brand identity:
- **Start**: `#A1D25B` (Dynamic Lime)
- **End**: `#428D42` (Tech Green)
- **CSS**: `linear-gradient(to right, #A1D25B, #428D42)`

### Complete Brand Kit

For complete brand guidelines, color specifications, and all asset variations including PNG formats, see:
- `BRAND IDENTITY KIT/` - Complete brand assets and manual
- `.github/assets/palette.md` - Detailed color specifications
- `.github/assets/` - All web-ready SVG assets

### Usage Guidelines
- **Gradient Direction**: Always horizontal from left to right
- **Logo Logic**: Light color starts on left/tail, transitions to dark color on right/point
- **Monochrome**: Use Tech Green (`#428D42`) for solid color elements

### Brand Attributes
Dynamic, Modern, Growth, Speed, Forward-thinking, Fresh, Energetic, Tech, Professional, Trustworthy, Vibrant

---

## License

MIT — see `LICENSE`.