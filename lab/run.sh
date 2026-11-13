set -e
python kospi_bottom_model.py
mkdir -p lab/out
cp report.md signals_daily.csv lab/out/
