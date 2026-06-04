import pathlib
import sys

# Allow running as `python scripts/seed_projects.py` from the project root.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.repositories.project_repo import ProjectRepository  # noqa: E402
from app.repositories.user_repo import UserRepository  # noqa: E402

DEMO_PHONE = "081234567890"


def main() -> None:
    with SessionLocal() as session:
        user = UserRepository(session).get_or_create(name="Klien Demo", phone=DEMO_PHONE)
        session.flush()
        repo = ProjectRepository(session)
        if repo.list_for_user(user.id):
            print(f"Proyek demo untuk {DEMO_PHONE} sudah ada, lewati.")
            return
        repo.create(
            user.id,
            name="Aplikasi POS Toko Maju",
            type="POS",
            progress=75,
            status="in_progress",
            details={"backend": "done", "frontend": 80, "testing": "in progress"},
        )
        repo.create(
            user.id,
            name="Website Company Profile",
            type="Website",
            progress=100,
            status="completed",
        )
        session.commit()
        print(f"Seed selesai: 2 proyek untuk user id={user.id} ({DEMO_PHONE}).")


if __name__ == "__main__":
    main()
