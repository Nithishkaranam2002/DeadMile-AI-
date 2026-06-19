# Documentation Assets

## Screenshots

After running the app (`make setup`), capture screenshots for the README:

1. **hero-screenshot.png** — Full dashboard with map, load cards, and chat panel
   ```bash
   # macOS: Cmd+Shift+4, select the browser window
   # Save to docs/hero-screenshot.png
   ```

2. **architecture.png** — Optional; the Mermaid diagram in README renders on GitHub automatically

## Placeholder

`hero-screenshot.svg` is a placeholder graphic until you capture a real screenshot.
Update README.md to use `hero-screenshot.png` once captured.

## Data Files

Load data files are not committed (see `.gitignore`). Download from the hackathon Google Drive and place in:

```
data/text/   # loads_part_000.txt – loads_part_012.txt
data/pdf/    # broker_load_sheet_001.pdf – 012.pdf
```

Then run `make seed` to ingest.
