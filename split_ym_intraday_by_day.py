import csv
from collections import defaultdict
import os

# Input and output paths
input_path = '/Users/orkiskevin/Desktop/YM_intraday_last30_0930-1000.csv'
output_dir = '/Users/orkiskevin/PycharmProjects/QuantConnect'

# Read the CSV and group rows by date
data_by_date = defaultdict(list)
header = []

with open(input_path, 'r', newline='') as infile:
    reader = csv.reader(infile)
    rows = list(reader)
    # Find the header row (skip any metadata rows)
    for i, row in enumerate(rows):
        if row and row[0] == 'Price':
            header = row
            data_start = i + 1
            break
    # Skip any non-data rows after header
    for row in rows[data_start:]:
        if len(row) < 7 or not row[0] or row[0] == 'Datetime':
            continue
        date = row[-1]
        data_by_date[date].append(row)

# Write each day's data to a separate CSV file
for date, rows in data_by_date.items():
    outname = f'YM_intraday_{date}_0930-1000.csv'
    outpath = os.path.join(output_dir, outname)
    with open(outpath, 'w', newline='') as outfile:
        writer = csv.writer(outfile)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)

print(f"Split complete. {len(data_by_date)} files written to {output_dir}")
