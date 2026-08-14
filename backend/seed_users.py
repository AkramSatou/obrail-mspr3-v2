"""
seed_users.py — création des comptes applicatifs de démonstration.

Idempotent : peut être relancé sans créer de doublon ni écraser un mot de passe
existant. Appelé automatiquement au démarrage du conteneur backend
(voir scripts/entrypoint.sh), après le seed des trajets.

Les mots de passe sont lus depuis l'environnement afin de ne jamais figurer
dans le code source. Les valeurs par défaut ne servent qu'à la démonstration locale.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import User  # noqa: E402
from app.security import ROLE_ADMIN, ROLE_VIEWER, hash_password  # noqa: E402

DEMO_USERS = [
    {
        "username": os.getenv("OBRAIL_VIEWER_USER", "viewer"),
        "password": os.getenv("OBRAIL_VIEWER_PASSWORD", "viewer123"),
        "role": ROLE_VIEWER,
    },
    {
        "username": os.getenv("OBRAIL_ADMIN_USER", "admin"),
        "password": os.getenv("OBRAIL_ADMIN_PASSWORD", "admin123"),
        "role": ROLE_ADMIN,
    },
]


def seed_users() -> None:
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    created = 0
    try:
        for entry in DEMO_USERS:
            exists = session.query(User).filter(User.username == entry["username"]).first()
            if exists:
                print(f"[seed_users] '{entry['username']}' existe déjà — ignoré")
                continue
            session.add(
                User(
                    username=entry["username"],
                    hashed_password=hash_password(entry["password"]),
                    role=entry["role"],
                    is_active=True,
                )
            )
            created += 1
            print(f"[seed_users] compte '{entry['username']}' créé (rôle {entry['role']})")
        session.commit()
        print(f"[seed_users] terminé — {created} compte(s) créé(s)")
    finally:
        session.close()


if __name__ == "__main__":
    seed_users()
