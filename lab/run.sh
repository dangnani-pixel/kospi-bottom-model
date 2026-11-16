set -e
mkdir -p lab/out
python lab/new_highs.py | tee lab/out/highs_log2.txt
