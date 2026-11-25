"""Trusted local CLI for provisioning explicit Founder Authority.

This is intentionally not exposed as an HTTP endpoint. Run only from a trusted
administrative shell with access to the configured Agency OS database.
"""
import argparse
import sys

from app.db import AdminSessionLocal
from app.models import FounderAuthority, Organization, User


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage explicit Agency OS Founder Authority")
    parser.add_argument("action", choices=("grant", "revoke"))
    parser.add_argument("--org-id", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument(
        "--confirm",
        required=True,
        help="Must exactly equal the target email to confirm the authority change",
    )
    args = parser.parse_args()
    email = args.email.strip().lower()
    if args.confirm.strip().lower() != email:
        parser.error("--confirm must exactly match --email")

    db = AdminSessionLocal()
    try:
        org = db.query(Organization).filter_by(id=args.org_id).first()
        user = db.query(User).filter_by(email=email, active=True).first()
        if org is None:
            print("Organization not found", file=sys.stderr)
            return 2
        if user is None:
            print("Active user not found", file=sys.stderr)
            return 2

        grant = db.query(FounderAuthority).filter_by(
            org_id=org.id, user_id=user.id
        ).first()

        if args.action == "grant":
            if grant is None:
                grant = FounderAuthority(
                    org_id=org.id,
                    user_id=user.id,
                    active=True,
                    grant_source="cli_provisioning",
                )
                db.add(grant)
            else:
                grant.active = True
                grant.grant_source = "cli_provisioning"
            db.commit()
            print(f"Founder Authority granted: org={org.id} user_id={user.id}")
            return 0

        if grant is None or not grant.active:
            print("No active Founder Authority grant exists")
            return 0
        grant.active = False
        db.commit()
        print(f"Founder Authority revoked: org={org.id} user_id={user.id}")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
