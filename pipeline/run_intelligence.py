"""
FlightPulse Flight Delay Intelligence Engine CLI Runner.
Executes deterministic causal attribution for individual or batch flights.
"""

import argparse
import json
import logging
import sys

from pipeline.config import config
from pipeline.database import get_db_connection
from pipeline.intelligence.analyzer import analyze_all_flights, analyze_flight_delay

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("flightpulse.intelligence.cli")


def main():
    parser = argparse.ArgumentParser(description="FlightPulse Flight Delay Intelligence Engine")
    parser.add_argument(
        "--flight",
        help="Flight Number (e.g. UA415) or Flight ID to analyze",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Analyze all flights in the database",
    )
    parser.add_argument(
        "--delayed-only",
        action="store_true",
        help="When running with --all, only analyze flights delayed > 15 minutes",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON instead of formatted text",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform evaluation without persisting or updating state",
    )

    args = parser.parse_args()

    if not args.flight and not args.all:
        parser.print_help()
        print("\nError: Please specify either --flight <FLIGHT_NUMBER> or --all.")
        sys.exit(1)

    try:
        conn = get_db_connection()
    except Exception as exc:
        logger.error("Failed to connect to PostgreSQL database: %s", exc)
        sys.exit(1)

    try:
        if args.flight:
            result = analyze_flight_delay(args.flight, conn=conn)
            if not result:
                print(f"Error: Flight '{args.flight}' not found in database.")
                sys.exit(1)

            if args.json:
                print(json.dumps(result.to_dict(), indent=2))
            else:
                print("\n" + "=" * 80)
                print(result.format_display())
                print("=" * 80 + "\n")

        elif args.all:
            results = analyze_all_flights(conn=conn, delayed_only=args.delayed_only)
            if args.json:
                print(json.dumps([r.to_dict() for r in results], indent=2))
            else:
                print("\n" + "=" * 80)
                print(f"FLIGHTPULSE DELAY INTELLIGENCE REPORT ({len(results)} Flights Analyzed)")
                print("=" * 80)
                for idx, r in enumerate(results, 1):
                    print(f"\n--- [{idx}/{len(results)}] Flight {r.flight_number} ---")
                    print(r.format_display())
                print("\n" + "=" * 80 + "\n")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
