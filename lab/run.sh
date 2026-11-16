set -e
mkdir -p lab/out
python lab/new_highs.py | tee lab/out/highs_log.txt
cp highs/list.json lab/out/highs_list.json
