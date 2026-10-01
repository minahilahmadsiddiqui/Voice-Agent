"""Place an outbound call. The server (python -m app.main) must already be running.

Examples:
  python scripts/place_call.py --to +13035550100                    # the real verification call
  python scripts/place_call.py --to +13035550100 --mode chat        # free chat test
  python scripts/place_call.py --to +13035550100 --mode tts_test    # read IDs aloud
  python scripts/place_call.py --ivr                                # call the fake payer menu
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.telephony import start_call  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--to", help="Number to call, E.164 (+1...)")
    p.add_argument("--mode", default="verify", choices=["verify", "chat", "ivr_test", "tts_test"])
    p.add_argument("--scenario", default="lana_kane")
    p.add_argument("--voice", help="Cartesia voice id (overrides CARTESIA_VOICE_ID)")
    p.add_argument("--ivr", action="store_true", help="Call TWILIO_IVR_TEST_NUMBER in ivr_test mode")
    args = p.parse_args()

    if args.ivr:
        if not settings.twilio_ivr_test_number:
            sys.exit("Set TWILIO_IVR_TEST_NUMBER in .env first.")
        args.to, args.mode = settings.twilio_ivr_test_number, "ivr_test"
    if not args.to:
        sys.exit("Pass --to +1... or --ivr")

    print(start_call(args.to, args.mode, args.scenario, args.voice))


if __name__ == "__main__":
    main()
