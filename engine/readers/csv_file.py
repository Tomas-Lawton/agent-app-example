import csv, os


def fetch(src, since, limit, profile_dir, timeout=None):
    path = os.path.normpath(os.path.join(profile_dir, src["file"]))
    if not path.startswith(os.path.normpath(profile_dir) + os.sep):
        raise ValueError(f"{src['file']} is outside the profile folder; files must live inside it")
    if not os.path.exists(path):
        raise FileNotFoundError(f"{os.path.relpath(path)} not found; export it again or ask setup to refresh it")
    cols = src.get("columns") or {}
    c = lambda row, k: (row.get(cols.get(k, k)) or "").strip()
    items = []
    with open(path, newline="", encoding="utf8") as f:
        for n, row in enumerate(csv.DictReader(f)):
            date, text = c(row, "date")[:10], c(row, "text")
            if not text or not date or date < since:
                continue
            r = c(row, "rating")
            items.append(
                {
                    "id": f"{src['id']}:{c(row, 'id') or n}",
                    "url": c(row, "url") or None,
                    "date": date,
                    "title": c(row, "title"),
                    "text": text,
                    "rating": float(r) if r else None,
                    "ratingScale": src.get("ratingScale") if r else None,
                }
            )
            if len(items) >= limit:
                break
    oldest = min((i["date"] for i in items), default=None)
    return items, {"coverageFrom": oldest, "limitReached": len(items) >= limit}
