set -e
mkdir -p lab/out
(cd lab/old && python kospi_bottom_model.py) > lab/out/old_log.txt 2>&1 || echo old failed
(cd lab/new && python kospi_bottom_model.py) > lab/out/new_log.txt 2>&1 || echo new failed
cp lab/new/report.md lab/out/new_report.md; cp lab/old/report.md lab/out/old_report.md
python lab/compare.py
