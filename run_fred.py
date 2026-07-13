"""run_fred.py

Launcher for Fred — Interactive Brokers YM futures trading bot.

Usage
-----
    python run_fred.py
    python run_fred.py --dry-run
    python run_fred.py --duration 450
    python run_fred.py --port 4001          # live account
    python run_fred.py --no-plot            # headless
    python run_fred.py --test               # connection test only

Options
-------
    --duration  minutes          (default: 105)
    --dry-run                    log signals, no orders
    --no-plot                    headless, no chart window
    --port      4002 (paper) | 4001 (live)
    --host      127.0.0.1
    --client-id IB client ID     (default: 1)
    --start-time HH:MM ET       (default: 09:30)
    --test                       connection test only
"""

import argparse
import sys
import time


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Fred — YM futures trading bot (Interactive Brokers).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--duration", type=int, default=105,
                   help="Session duration in minutes (default: 105 = ~9:30-11:15)")
    p.add_argument("--dry-run",  action="store_true", dest="dry_run",
                   help="Log signals without placing orders")
    p.add_argument("--no-plot",  action="store_false", dest="show_plot",
                   help="Disable live chart window")
    p.add_argument("--port",     type=int, default=4002,
                   help="IB Gateway port (default: 4002 = paper)")
    p.add_argument("--host",     default="127.0.0.1",
                   help="IB Gateway host (default: 127.0.0.1)")
    p.add_argument("--client-id", type=int, default=1, dest="client_id",
                   help="IB client ID (default: 1)")
    p.add_argument("--start-time", default=None, dest="start_time",
                   help="Fixed session start HH:MM ET (e.g. --start-time 18:00 for night session)")
    p.add_argument("--test",     action="store_true",
                   help="Connection test only")
    p.set_defaults(show_plot=True)
    return p


def main() -> None:
    args = _build_parser().parse_args()

    from InteractiveBrokers import IBDataBridge, run_connection_test
    from ib_async import IB

    print(f"\n{'='*50}")
    print(f"  Fred — YM Futures Trading Bot")
    print(f"  Mode:     {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"  Duration: {args.duration} min")
    print(f"  Port:     {args.port}")
    print(f"{'='*50}\n")

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
                try:
                    from Emailer import send_disconnect_alert
                    send_disconnect_alert(attempt, max_retries, str(exc))
                except Exception:
                    pass
                time.sleep(retry_delay)
                time.sleep(retry_delay)
                try:
                    bridge._ib.disconnect()
                except Exception:
                    pass
                bridge._ib = IB()
                bridge._window_set = False
            else:
                print("[Fred] Max retries reached. Giving up.")
                try:
                    from Emailer import send_disconnect_alert
                    send_disconnect_alert(attempt, max_retries, f"Max retries reached. Fred has stopped. Last error: {exc}")
                except Exception:
                    pass


if __name__ == "__main__":
    main()
