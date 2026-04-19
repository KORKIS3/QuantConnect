"""Download 5 years of YM data from IB live account."""
import argparse
from Backtest2Year import download_all

p = argparse.ArgumentParser()
p.add_argument("--port", type=int, default=4001)
args = p.parse_args()
download_all(args.port)
print("Done. Run: python Backtest2Year.py --skip-download")
