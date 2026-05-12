"""Send multi-account end-of-day comparison email.

Compares trades from both accounts (CSVs and IB Gateway logs) and sends
a side-by-side comparison to harvell1972@gmail.com and orkiskevin2@gmail.com.
"""

import os
import sys
import pandas as pd
from datetime import datetime
import pytz
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import glob

def parse_ib_log(log_path):
    """Parse IB Gateway log to extract trades."""
    trades = []
    if not os.path.exists(log_path):
        return trades
    
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if '[ORDER placed]' in line or '[ORDER filled]' in line:
                trades.append(line.strip())
    return trades

def send_multi_account_summary(date_str=None):
    """Send end-of-day comparison email for both accounts."""
    
    if date_str is None:
        date_str = datetime.now(pytz.timezone("US/Eastern")).strftime("%Y-%m-%d")
    
    sender    = os.environ.get("IB_EMAIL_FROM", "orkiskevin2@gmail.com")
    recipient = "harvell1972@gmail.com,orkiskevin2@gmail.com"
    password  = os.environ.get("IB_EMAIL_PASS")
    host      = os.environ.get("IB_EMAIL_HOST", "smtp.gmail.com")
    port      = int(os.environ.get("IB_EMAIL_PORT", "587"))
    
    if not password:
        print("ERROR: IB_EMAIL_PASS not set")
        return
    
    # Find tracking CSVs for both accounts
    tracking_root = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "tracking")
    csv1_pattern = os.path.join(tracking_root, f"YM_tracking_DUO158495_{date_str}_*.csv")
    csv2_pattern = os.path.join(tracking_root, f"YM_tracking_DUQ921172_{date_str}_*.csv")
    
    csv1_files = glob.glob(csv1_pattern)
    csv2_files = glob.glob(csv2_pattern)
    
    csv1_path = csv1_files[0] if csv1_files else None
    csv2_path = csv2_files[0] if csv2_files else None
    
    # Find IB Gateway logs for both accounts
    log_root = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "logs")
    log1_pattern = os.path.join(log_root, f"fred_ib_DUO158495_{date_str.replace('-', '')}_*.log")
    log2_pattern = os.path.join(log_root, f"fred_ib_DUQ921172_{date_str.replace('-', '')}_*.log")
    
    log1_files = glob.glob(log1_pattern)
    log2_files = glob.glob(log2_pattern)
    
    log1_path = log1_files[0] if log1_files else None
    log2_path = log2_files[0] if log2_files else None
    
    # Build email body
    body = f"Multi-Account Trading Summary\n"
    body += f"{'=' * 70}\n"
    body += f"Date: {date_str}\n"
    body += f"{'=' * 70}\n\n"
    
    # Account 1 Summary
    body += f"ACCOUNT 1: DUO158495\n"
    body += f"{'-' * 70}\n"
    if csv1_path and os.path.exists(csv1_path):
        df1 = pd.read_csv(csv1_path)
        if 'session_pl' in df1.columns and len(df1) > 0:
            final_pl1 = df1['session_pl'].iloc[-1]
            body += f"Final P/L: {final_pl1:+.0f} points (${final_pl1*5:.0f})\n"
            body += f"Total Bars: {len(df1)}\n"
        else:
            body += f"No trades recorded\n"
    else:
        body += f"CSV not found\n"
    
    if log1_path and os.path.exists(log1_path):
        trades1 = parse_ib_log(log1_path)
        body += f"IB Log Trades: {len(trades1)}\n"
    else:
        body += f"IB Log not found\n"
    body += "\n"
    
    # Account 2 Summary
    body += f"ACCOUNT 2: DUQ921172\n"
    body += f"{'-' * 70}\n"
    if csv2_path and os.path.exists(csv2_path):
        df2 = pd.read_csv(csv2_path)
        if 'session_pl' in df2.columns and len(df2) > 0:
            final_pl2 = df2['session_pl'].iloc[-1]
            body += f"Final P/L: {final_pl2:+.0f} points (${final_pl2*5:.0f})\n"
            body += f"Total Bars: {len(df2)}\n"
        else:
            body += f"No trades recorded\n"
    else:
        body += f"CSV not found\n"
    
    if log2_path and os.path.exists(log2_path):
        trades2 = parse_ib_log(log2_path)
        body += f"IB Log Trades: {len(trades2)}\n"
    else:
        body += f"IB Log not found\n"
    body += "\n"
    
    # Comparison
    body += f"{'=' * 70}\n"
    body += f"COMPARISON\n"
    body += f"{'=' * 70}\n"
    if csv1_path and csv2_path and os.path.exists(csv1_path) and os.path.exists(csv2_path):
        df1 = pd.read_csv(csv1_path)
        df2 = pd.read_csv(csv2_path)
        if 'session_pl' in df1.columns and 'session_pl' in df2.columns and len(df1) > 0 and len(df2) > 0:
            pl1 = df1['session_pl'].iloc[-1]
            pl2 = df2['session_pl'].iloc[-1]
            diff = abs(pl1 - pl2)
            if diff < 1.0:
                body += f"✓ Accounts are SYNCHRONIZED (diff: {diff:.1f} pts)\n"
            else:
                body += f"⚠ Accounts DIFFER by {diff:.0f} points\n"
                body += f"  Account 1: {pl1:+.0f} pts\n"
                body += f"  Account 2: {pl2:+.0f} pts\n"
    else:
        body += f"Cannot compare - missing CSV files\n"
    
    body += f"\nAttachments:\n"
    attachments = []
    if csv1_path and os.path.exists(csv1_path):
        body += f"  - {os.path.basename(csv1_path)}\n"
        attachments.append(csv1_path)
    if csv2_path and os.path.exists(csv2_path):
        body += f"  - {os.path.basename(csv2_path)}\n"
        attachments.append(csv2_path)
    if log1_path and os.path.exists(log1_path):
        body += f"  - {os.path.basename(log1_path)}\n"
        attachments.append(log1_path)
    if log2_path and os.path.exists(log2_path):
        body += f"  - {os.path.basename(log2_path)}\n"
        attachments.append(log2_path)
    
    # Create email
    subject = f"Fred Multi-Account Summary - {date_str}"
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    
    # Attach files
    for file_path in attachments:
        try:
            with open(file_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(file_path)}")
            msg.attach(part)
        except Exception as e:
            print(f"Failed to attach {file_path}: {e}")
    
    # Send email
    try:
        with smtplib.SMTP(host, port) as server:
            server.ehlo()
            server.starttls()
            server.login(sender, password)
            recipients = [r.strip() for r in recipient.split(",")]
            server.sendmail(sender, recipients, msg.as_string())
        print(f"✓ Multi-account summary sent to {recipient}")
    except Exception as e:
        print(f"✗ Failed to send email: {e}")

if __name__ == "__main__":
    date_str = sys.argv[1] if len(sys.argv) > 1 else None
    send_multi_account_summary(date_str)
