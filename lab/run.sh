set -e
mkdir -p lab/out
(cd lab && python exports.py) > lab/out/exports_log.txt 2>&1 || echo failed >> lab/out/exports_log.txt
cp lab/exports_monthly.csv lab/out/ || true
