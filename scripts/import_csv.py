import csv, sys, requests
# Usage: python scripts/import_csv.py sample_data/jobs.csv
API='http://localhost:8000/api/jobs'
with open(sys.argv[1], newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        payload={k:row.get(k) or None for k in ['company','title','location','posted_at','description','source_url']}
        r=requests.post(API,json=payload,timeout=20);print(r.status_code,row['company'],row['title'])
