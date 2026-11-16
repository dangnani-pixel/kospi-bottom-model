set -e
python lab/new_highs.py
mkdir -p lab/out
cp highs/list.json lab/out/highs_list.json
ls highs | head -3 > lab/out/highs_files.txt
head -3 "highs/$(ls highs | grep csv | head -1)" >> lab/out/highs_files.txt || true
