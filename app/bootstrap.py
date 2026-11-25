import argparse
from app.db import SessionLocal
from app.models import Organization, User, Membership, FounderAuthority, Workspace, Role

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--org-name", required=True)
    args = parser.parse_args()
    db = SessionLocal()
    try:
        email = args.email.lower()
        user = db.query(User).filter_by(email=email).first()
        if not user:
            user = User(email=email, display_name="Founder")
            db.add(user)
            db.flush()
        org = Organization(name=args.org_name)
        db.add(org)
        db.flush()
        db.add(Membership(org_id=org.id, user_id=user.id, role=Role.owner))
        db.add(FounderAuthority(org_id=org.id, user_id=user.id, grant_source="bootstrap"))
        db.add(Workspace(org_id=org.id, name="Main Workspace"))
        db.commit()
        print(f"Created org_id={org.id} user_id={user.id}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
