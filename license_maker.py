#!/usr/bin/env python
# -*- coding: utf-8 -*-
# license_maker.py - Generate activation key for PipeAgent (CLI)

import os
import sys
import hmac
import hashlib
import base64
import uuid
import argparse
from datetime import datetime, date, timedelta

# Must match the SECRET_KEY in services/license.py
SECRET_KEY = b'PipeAgent2026!SecureKeyForLicenseSigning'


def get_machine_id() -> str:
    try:
        mac = uuid.getnode()
        if mac == 0:
            raise OSError
        return f"mac-{mac:012x}"
    except Exception:
        fallback_path = os.path.join(os.path.expanduser("~"), ".pipeagent_machine_id")
        if os.path.exists(fallback_path):
            with open(fallback_path, "r") as f:
                return f.read().strip()
        mid = str(uuid.uuid4())
        os.makedirs(os.path.dirname(fallback_path) or ".", exist_ok=True)
        with open(fallback_path, "w") as f:
            f.write(mid)
        return mid


def generate_activation_key(license_type: str, expiry_date_str: str = None) -> str:
    machine_id = get_machine_id()

    if expiry_date_str:
        try:
            expiry = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError("Expiry date must be YYYY-MM-DD")
    else:
        today = date.today()
        if license_type == "3month":
            expiry = today + timedelta(days=90)
        elif license_type == "6month":
            expiry = today + timedelta(days=180)
        elif license_type == "1year":
            expiry = today + timedelta(days=365)
        elif license_type == "unlimited":
            expiry = date(2099, 12, 31)
        else:
            raise ValueError("Invalid license type")
        expiry_date_str = expiry.isoformat()

    issued_date = date.today().isoformat()
    msg = f"{machine_id}|{license_type}|{expiry_date_str}|{issued_date}"
    signature = hmac.new(SECRET_KEY, msg.encode(), hashlib.sha256).hexdigest()
    full = f"{msg}|{signature}"
    return base64.urlsafe_b64encode(full.encode()).decode()


def main():
    parser = argparse.ArgumentParser(
        description="Generate activation key for PipeAgent"
    )
    parser.add_argument(
        "--type",
        choices=["3month", "6month", "1year", "unlimited"],
        default="1year",
        help="License type"
    )
    parser.add_argument(
        "--expiry",
        help="Expiry date in YYYY-MM-DD format (optional)"
    )
    parser.add_argument(
        "--machine-id",
        action="store_true",
        help="Show machine ID and exit"
    )
    args = parser.parse_args()

    if args.machine_id:
        print(get_machine_id())
        return

    try:
        key = generate_activation_key(args.type, args.expiry)
        print("\n" + "=" * 60)
        print("ACTIVATION KEY:")
        print("=" * 60)
        print(f"\n{key}\n")
        print("=" * 60)
        print(f"License type : {args.type}")
        if args.expiry:
            print(f"Expiry date  : {args.expiry}")
        else:
            print("Expiry date  : (auto-calculated)")
        print(f"Machine ID   : {get_machine_id()}")
        print("=" * 60)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()