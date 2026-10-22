"""Assemble the site: src/app.html -> site/index.html, data.json beside it (fetched fresh on every visit),
plus the app manifest, icons and offline worker.

Usage: python3 scripts/build.py data/data.json site            # hosted site
       python3 scripts/build.py data/data.json out --single    # one self-contained HTML file with data inside
"""
import json, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
data_path, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)

app = (ROOT / "src/app.html").read_text()
single = "--single" in sys.argv
data = data_path.read_text().replace("</", "<\\/") if single else ""
meta = json.loads(data_path.read_text())["meta"]

head = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#1D5A39">
<meta name="description" content="Weekly NFL fantasy rankings, start/sit, trades, waivers and mock drafts. No betting data.">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="icons/icon-192.png" type="image/png">
<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Butler FF">
<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>
"""
sw = """<script>
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
}
</script>
"""
# The app template starts with its <title>, font links and <style>; those belong in <head>.
split = app.index('<header class="top">')
page = head + app[:split] + "</head><body>\n" + app[split:].replace("__DATA__", data) + sw + "</body></html>\n"
(out / "index.html").write_text(page)
if single:
    (out / "butler-ff.html").write_text(page.replace(sw, ""))
    (out / "index.html").unlink()
    print(f"Built self-contained Week {meta['week']} → {out/'butler-ff.html'}")
    sys.exit(0)
shutil.copyfile(data_path, out / "data.json")
shutil.copytree(ROOT / "public", out, dirs_exist_ok=True)
# Bump the worker's cache name each build so installed apps pick up new projections.
swp = out / "sw.js"
swp.write_text(swp.read_text().replace("__BUILD__", meta["built"].replace(" ", "_")))
print(f"Built Week {meta['week']} ({meta.get('weekDates','')}) → {out/'index.html'} ({len(page)//1024} KB)")
