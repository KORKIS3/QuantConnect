"""run_fred.py

Unified launcher for Fred — switches between brokers with a single flag.

Usage
-----
    # Interactive Brokers (default)
    python run_fred.py
    python run_fred.py --broker ib

    # TradeStation simulated
    python run_fred.py --broker ts --sim

    # TradeStation live
    python run_fred.py --broker ts

    # Dry run (any broker)
    python run_fred.py --broker ib --dry-run
    python run_fred.py --broker ts --dry-run

    # Full day session
    python run_fred.py --duration 450

    # First-time TradeStation auth
    python run_fred.py --broker ts --auth

Common options
--------------
    --broker    ib | ts          (default: ib)
    --duration  minutes          (default: 105)
    --dry-run                    log signals, no orders
    --no-plot                    headless, no chart window
    --sim                        TradeStation sim environment (ts only)
    --auth                       first-time OAuth flow (ts only)

IB-specific options
-------------------
    --port      4002 (paper) | 4001 (live)
    --host      127.0.0.1

TradeStation credentials (set as environment variables)
-------------------------------------------------------
    TS_CLIENT_ID
    TS_CLIENT_SECRET
    TS_REFRESH_TOKEN
"""

import argparse
import os
import sys


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Fred — YM futures trading bot. Switch brokers with --broker.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--broker",   choices=["ib", "ts"], default="ib",
                   help="Broker to use: ib=Interactive Brokers, ts=TradeStation (default: ib)")
    p.add_argument("--duration", type=int, default=105,
                   help="Session duration in minutes (default: 105 = ~9:30-11:15)")
    p.add_argument("--dry-run",  action="store_true", dest="dry_run",
                   help="Log signals without placing orders")
    p.add_argument("--no-plot",  action="store_false", dest="show_plot",
                   help="Disable live chart window")
    p.add_argument("--sim",      action="store_true",
                   help="[ts only] Use TradeStation simulated environment")
    p.add_argument("--auth",     action="store_true",
                   help="[ts only] Run first-time OAuth flow")
    # IB-specific
    p.add_argument("--port",     type=int, default=4002,
                   help="[ib only] IB Gateway port (default: 4002 = paper)")
    p.add_argument("--host",     default="127.0.0.1",
                   help="[ib only] IB Gateway host (default: 127.0.0.1)")
    p.add_argument("--client-id", type=int, default=1, dest="client_id",
                   help="[ib only] IB client ID (default: 1)")
    p.add_argument("--start-time", default=None, dest="start_time",
                   help="[ib only] Fixed session start HH:MM ET (e.g. --start-time 18:00 for night session)")
    p.add_argument("--test",     action="store_true",
                   help="[ib only] Connection test only")
    p.set_defaults(show_plot=True)
    return p


def run_ib(args) -> None:
    from InteractiveBrokers import IBDataBridge, run_connection_test
    from ib_insync import IB
    import time

    if args.test:
        run_connection_test(args.host, args.port, args.client_id)
        return

    bridge = IBDataBridge(
        host=args.host,
        port=args.port,
        client_id=args.client_id,
        dry_run=args.dry_run,
        show_plot=args.show_plot,
        session_duration_minutes=args.duration,
        start_time=args.start_time or "09:30",
    )

    max_retries = 20
    retry_delay = 30

    for attempt in range(1, max_retries + 1):
        try:
            print(f"[Fred] Connecting (attempt {attempt}/{max_retries}) ...")
            bridge.connect()
            bridge.start()
            break  # clean session end
        except KeyboardInterrupt:
            print("[Fred] Stopped by user.")
            break
        except Exception as exc:
            print(f"[Fred] Connection lost: {exc}")
            if attempt < max_retries:
                print(f"[Fred] Reconnecting in {retry_delay}s ...")
                time.sleep(retry_delay)
                try:
                    bridge._ib.disconnect()
                except Exception:
                    pass
                bridge._ib = IB()
                bridge._window_set = False
            else:
                print("[Fred] Max retries reached. Giving up.")


def run_ts(args) -> None:
    import os
    from TradeStation import TSAuth, TSDataBridge, first_time_auth

    client_id     = os.environ.get("TS_CLIENT_ID", "")
    client_secret = os.environ.get("TS_CLIENT_SECRET", "")
    refresh_token = os.environ.get("TS_REFRESH_TOKEN", "")

    if args.auth:
        if not client_id or not client_secret:
            print("Set TS_CLIENT_ID and TS_CLIENT_SECRET environment variables first.")
            sys.exit(1)
        first_time_auth(client_id, client_secret)
        return

    if not all([client_id, client_secret, refresh_token]):
        print("TradeStation credentials not set. Add to your environment:")
        print("  TS_CLIENT_ID=your_client_id")
        print("  TS_CLIENT_SECRET=your_client_secret")
        print("  TS_REFRESH_TOKEN=your_refresh_token")
        print("\nRun with --auth to get your refresh token.")
        sys.exit(1)

    auth = TSAuth(client_id, client_secret, refresh_token, sim=args.sim)
    bridge = TSDataBridge(
        auth=auth,
        dry_run=args.dry_run,
        sim=args.sim,
        show_plot=args.show_plot,
        session_duration_minutes=args.duration,
    )
    bridge.start()


if __name__ == "__main__":
    args = _build_parser().parse_args()

    print(f"\n{'='*50}")
    print(f"  Fred — YM Futures Trading Bot")
    print(f"  Broker:   {'Interactive Brokers' if args.broker == 'ib' else 'TradeStation'}")
    print(f"  Mode:     {'DRY RUN' if args.dry_run else ('SIM' if getattr(args,'sim',False) else 'LIVE')}")
    print(f"  Duration: {args.duration} min")
    print(f"{'='*50}\n")

    if args.broker == "ib":
        run_ib(args)
    elif args.broker == "ts":
        run_ts(args)
