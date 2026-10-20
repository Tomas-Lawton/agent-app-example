import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # engine/
import glob, json
from core import config

try:
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA, TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import normalize
except ImportError:
    sys.exit("scikit-learn is missing; install it with: python3 -m pip install -r requirements.txt")

cfg, info = config.open_run(config.key_arg())
c = cfg["scope"]["cluster"]
items = json.load(open("items.json"))["items"]
texts = [f"{i.get('title') or ''} {i['text']}" for i in items]

if len(items) < 12:  # too few to cluster: one group, in order
    labels, xy, terms = [0] * len(items), [(0.0, 0.0)] * len(items), [[]]
else:
    tfidf = TfidfVectorizer(stop_words="english", max_df=0.6, min_df=2, sublinear_tf=True)
    X = tfidf.fit_transform(texts)
    lsa = TruncatedSVD(n_components=max(2, min(60, X.shape[1] - 1, len(items) - 1)), random_state=0)
    V = normalize(lsa.fit_transform(X))
    k = max(2, min(c["k"], len(items) // 10))
    km = KMeans(n_clusters=k, n_init=10, random_state=0).fit(V)
    labels = km.labels_.tolist()
    xy = [(round(float(a), 4), round(float(b), 4)) for a, b in PCA(n_components=2, random_state=0).fit_transform(V)]
    words = tfidf.get_feature_names_out()
    centres = lsa.inverse_transform(km.cluster_centers_)
    terms = [[words[j] for j in centre.argsort()[::-1][:8]] for centre in centres]

clusters = []
for g in sorted(set(labels), key=lambda g: -labels.count(g)):
    clusters.append(
        {
            "id": len(clusters) + 1,
            "size": labels.count(g),
            "terms": terms[g],
            "items": [items[n]["id"] for n in range(len(items)) if labels[n] == g],
        }
    )
json.dump(
    {"clusters": clusters, "positions": {items[n]["id"]: xy[n] for n in range(len(items))}},
    open("clusters.json", "w"),
    indent=1,
)

by_id = {i["id"]: i for i in items}
# carry tags from the previous run for items seen before (same connection and original id), so only new items need tagging
carried = {}
if info.get("previous"):
    prev = os.path.join(config.ROOT, info["previous"])
    if os.path.exists(os.path.join(prev, "items.json")):
        old_ids = {
            (i["source"], str(i.get("nativeId"))): i["id"]
            for i in json.load(open(os.path.join(prev, "items.json")))["items"]
        }
        old_tags = {}
        for p_ in glob.glob(os.path.join(prev, "tags", "*.json")):
            old_tags.update(json.load(open(p_)))
        for i in items:
            old = old_ids.get((i["source"], str(i.get("nativeId"))))
            if old in old_tags:
                carried[i["id"]] = old_tags[old]
os.makedirs("tags", exist_ok=True)
json.dump(carried, open("tags/carried.json", "w"), indent=1)
lines = []
for cl in clusters:
    lines.append(f"## Cluster {cl['id']} ({cl['size']} items): {', '.join(cl['terms'])}")
    for iid in cl["items"]:
        i = by_id[iid]
        rating = f"{i['rating']:g}/{i['ratingScale']}" if i.get("rating") is not None else "-"
        text = (f"{i['title']}: " if i.get("title") else "") + i["text"]
        was = f" | tagged last run: {', '.join(carried[iid]) or 'none'}" if iid in carried else ""
        lines.append(
            f"{iid} | {i['date']} | {rating}{' | private' if i.get('private') else ''}{was} | {text[:c['textChars']]}"
        )
os.makedirs("reading", exist_ok=True)
for f in os.listdir("reading"):
    os.remove(os.path.join("reading", f))
part, count, n = [], 0, 1
for line in lines:
    part.append(line)
    count += not line.startswith("## ")
    if count >= c["readingChunk"]:
        open(f"reading/part_{n:02d}.txt", "w").write("\n".join(part) + "\n")
        part, count, n = [], 0, n + 1
if count or part:
    open(f"reading/part_{n:02d}.txt", "w").write("\n".join(part) + "\n")
parts = sorted(os.listdir("reading"))
for cl in clusters:
    print(f"cluster {cl['id']}: {cl['size']:>4} items  {', '.join(cl['terms'][:6])}")
print(
    f"{len(items)} items in {len(clusters)} clusters -> clusters.json, reading/ ({len(parts)} parts); "
    f"{len(carried)} keep their tags from the previous run (tags/carried.json)"
)
print(
    f"next: read every part in reading/, write themes.json, tag every item in tags/, then run: python3 engine/steps/summarise.py {cfg['key']}"
)
