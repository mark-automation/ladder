"""Static mirror generator: running Ladder server -> docs/ (GitHub Pages root).

Follows the proven mirror technique: fetch rendered pages, rewrite root-absolute
paths by output depth, degrade backend-only features client-side, verify zero
root-absolute refs remain. Regenerate any time with:  python gen_static.py
(requires the dev server on :8600).
"""
import json, os, re, shutil, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
ORIGIN = os.environ.get("LADDER_ORIGIN", "http://127.0.0.1:8600")
OUT = os.path.join(BASE, "docs")
FEATURED = [1, 3, 4, 8, 14, 18, 21, 23]          # applicant ids to mirror feed views for


def fetch(path: str) -> str:
    with urllib.request.urlopen(ORIGIN + path, timeout=20) as r:
        return r.read().decode("utf-8")


def rewrite(html: str, depth: int) -> str:
    pre = "./" if depth == 0 else "../" * depth
    html = re.sub(r'(href|src|action)="(/(?!/))',
                  lambda m: f'{m.group(1)}="{pre}', html)
    return html


def static_mode(html: str, depth: int, variant_map: dict) -> str:
    """Inject static-mode flag + variant navigation for the applicant selector."""
    pre = "./" if depth == 0 else "../" * depth
    vmap = {str(k): pre + v for k, v in variant_map.items()}
    inject = ("<script>window.LADDER_STATIC=true;"
              "function goVariant(v){var m=" + json.dumps(vmap) + ";"
              "location.href=(m[v]||'./');}</script>")
    html = html.replace("<body>", "<body>" + inject, 1)
    html = html.replace("location.href='/jobs?applicant='+this.value",
                        "goVariant(this.value)")
    return html


def write(path: str, html: str) -> None:
    full = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(html)


def main() -> None:
    # clean previous mirror (architecture/ is source-controlled, keep it)
    for entry in os.listdir(OUT):
        if entry not in ("architecture", ".nojekyll"):
            p = os.path.join(OUT, entry)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)

    variant_map = {1: "jobs/"}
    for aid in FEATURED[1:]:
        variant_map[aid] = f"jobs-a{aid}/"

    pages = [
        ("/", "index.html", 0),
        ("/explorer", "explorer/index.html", 1),
        ("/methodology", "methodology/index.html", 1),
    ]
    for aid in FEATURED:
        rel = "jobs/index.html" if aid == 1 else f"jobs-a{aid}/index.html"
        pages.append((f"/jobs?applicant={aid}", rel, rel.count("/")))

    n_applicants = 24
    for aid in range(1, n_applicants + 1):
        pages.append((f"/profile/{aid}", f"profile/{aid}/index.html", 2))

    for slug in ["northwind-labs", "halcyon-ai", "datatide", "verdant", "cobre", "gigantorp"]:
        pages.append((f"/company/{slug}", f"company/{slug}/index.html", 2))

    for src, rel, depth in pages:
        html = fetch(src)
        html = rewrite(html, depth)
        if "goVariant" not in html and "jobs" in rel:      # feed pages only
            pass
        if rel.startswith(("jobs", "index.html")):
            html = static_mode(html, depth, variant_map if rel.startswith("jobs") else {})
        write(rel, html)
        print("mirrored", src, "->", rel)

    # static assets + jekyll bypass
    shutil.copytree(os.path.join(BASE, "static"), os.path.join(OUT, "static"),
                    dirs_exist_ok=True)
    open(os.path.join(OUT, ".nojekyll"), "w").close()

    # verify: zero root-absolute refs anywhere
    bad = []
    for root, _, files in os.walk(OUT):
        for fn in files:
            if not fn.endswith(".html"):
                continue
            full = os.path.join(root, fn)
            body = open(full, encoding="utf-8").read()
            for m2 in re.finditer(r'(href|src|action)="(/(?!/))', body):
                bad.append((os.path.relpath(full, OUT), m2.group(0)))
    if bad:
        raise SystemExit(f"ROOT-ABSOLUTE REFS REMAIN: {bad[:5]}")
    print(f"OK — {len(pages)} pages mirrored to docs/ with zero root-absolute refs")


if __name__ == "__main__":
    main()
