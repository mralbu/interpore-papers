# List available recipes
default:
    @just --list

# Install/sync the Python environment
setup:
    uv sync

# Download the Indico exports (2018 on) and the 2016/2017 books of abstracts into data/raw/ (cached). Args: --refresh (re-download Indico, e.g. while a meeting's programme changes), --force
fetch *args:
    uv run interpore fetch {{args}}

# Re-download the Indico exports and rebuild everything
update: (fetch "--refresh") build

# Parse the raw sources into data/records.json (report in data/records-report.txt). Args: record IDs to print
records *args:
    uv run interpore records {{args}}

# Embeddings of title + abstract -> data/embeddings/<model>/ (resumable). Args: --model M
embed *args:
    uv run interpore embed {{args}}

# 2D map + topics -> data/topics/topics.json (hand overrides in topics.yaml). Args: --model M, --force
topics *args:
    uv run interpore topics {{args}}

# Export site/data/ (papers, abstracts, topics, history, charts) and llms.txt; commit it to publish
site-data:
    uv run interpore site

# Run every stage after fetch, in order (each is cached/resumable)
build: records embed topics site-data

# Serve the site on all interfaces (port 8000) and print the LAN URL
serve port="8000":
    #!/usr/bin/env bash
    set -euo pipefail
    # LAN IP: macOS (default-route interface) or Linux (hostname -I).
    ip=""
    if command -v ipconfig >/dev/null 2>&1; then
        iface=$(route -n get default 2>/dev/null | awk '/interface:/ {print $2}')
        [ -n "$iface" ] && ip=$(ipconfig getifaddr "$iface" 2>/dev/null || true)
    fi
    [ -z "$ip" ] && ip=$(hostname -I 2>/dev/null | awk '{print $1}' || true)
    echo "Local:   http://localhost:{{port}}"
    echo "Network: http://${ip:-unknown-ip}:{{port}}"
    # no-cache: browsers revalidate on every load, so edits to site/ show up on a normal reload.
    exec python3 -c 'import functools, http.server as h, sys
    class H(h.SimpleHTTPRequestHandler):
        def end_headers(self):
            self.send_header("Cache-Control", "no-cache")
            super().end_headers()
    h.ThreadingHTTPServer(("0.0.0.0", int(sys.argv[1])), functools.partial(H, directory="site")).serve_forever()' {{port}}

# Run tests and lint
check:
    uv run pytest -q
    uv run ruff check src tests
    uv run ruff format --check src tests
