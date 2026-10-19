"""Load the demo's survey responses into BigQuery, as Capital Bank of Australia's internal feedback warehouse.

Usage (from the repository root, signed in to Google Cloud, for example `gcloud auth application-default login`):
  python3 demo/load_warehouse.py <gcp project> [--location US]

Reads profiles/demo/data/survey.csv (run demo/make_data.py first, so the dates fall in the current window) and writes
  <project>.capital_bank.survey      a table, replaced on every load
  <project>.capital_bank.survey_v    the view a warehouse connection reads
Then prints the connection to add during setup.
"""
import argparse, csv, json, os, sys, time, urllib.request, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
from readers.bigquery import token, call  # noqa: E402

DATASET, TABLE, VIEW, BQ = "capital_bank", "survey", "survey_v", "https://bigquery.googleapis.com/bigquery/v2"
SCHEMA = [("response_id", "STRING"), ("submitted_at", "TIMESTAMP"), ("score", "INT64"), ("comment", "STRING"), ("city", "STRING")]

ap = argparse.ArgumentParser()
ap.add_argument("project"); ap.add_argument("--location", default="US")
a = ap.parse_args()
path = os.path.join(ROOT, "profiles", "demo", "data", "survey.csv")
if not os.path.exists(path):
    sys.exit("run python3 demo/make_data.py first")
rows = [{"response_id": r["response_id"], "submitted_at": f"{r['submitted_at']}T12:00:00Z", "score": int(r["score"]),
         "comment": r["comment"], "city": r["city"]} for r in csv.DictReader(open(path))]

tok = token()
if "_error" in call(f"{BQ}/projects/{a.project}/datasets/{DATASET}", tok):
    r = call(f"{BQ}/projects/{a.project}/datasets", tok, {"datasetReference": {"projectId": a.project, "datasetId": DATASET},
                                                          "location": a.location, "description": "Capital Bank of Australia demo warehouse (fictional, generated)."})
    if "_error" in r:
        sys.exit(f"could not create dataset: {r}")
meta = {"configuration": {"load": {"destinationTable": {"projectId": a.project, "datasetId": DATASET, "tableId": TABLE},
                                   "schema": {"fields": [{"name": n, "type": t} for n, t in SCHEMA]},
                                   "sourceFormat": "NEWLINE_DELIMITED_JSON", "writeDisposition": "WRITE_TRUNCATE"}}}
b = uuid.uuid4().hex
body = (f"--{b}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta)}\r\n--{b}\r\nContent-Type: application/octet-stream\r\n\r\n").encode() \
    + "\n".join(json.dumps(r) for r in rows).encode() + f"\r\n--{b}--".encode()
req = urllib.request.Request(f"https://bigquery.googleapis.com/upload/bigquery/v2/projects/{a.project}/jobs?uploadType=multipart", data=body,
                             method="POST", headers={"Authorization": f"Bearer {tok}", "Content-Type": f"multipart/related; boundary={b}"})
job = json.load(urllib.request.urlopen(req, timeout=120))["jobReference"]
loc = job.get("location", a.location)
while (st := call(f"{BQ}/projects/{a.project}/jobs/{job['jobId']}?location={loc}", tok)).get("status", {}).get("state") != "DONE":
    time.sleep(1)
if st["status"].get("errorResult"):
    sys.exit(f"load failed: {st['status']['errorResult']}")
r = call(f"{BQ}/projects/{a.project}/queries", tok, {"useLegacySql": False, "location": loc,
         "query": f"CREATE OR REPLACE VIEW `{a.project}.{DATASET}.{VIEW}` AS SELECT * FROM `{a.project}.{DATASET}.{TABLE}`"})
if "_error" in r:
    sys.exit(f"could not create view: {r}")
print(f"loaded {len(rows)} survey responses; view ready: {a.project}.{DATASET}.{VIEW}")
print("connection for setup:\n" + json.dumps({"id": "survey", "type": "warehouse", "engine": "bigquery", "label": "In-app survey (warehouse)",
      "project": a.project, "dataset": DATASET, "table": VIEW, "location": loc,
      "columns": {"id": "response_id", "date": "submitted_at", "text": "comment", "rating": "score"}, "ratingScale": 10}, indent=2))
