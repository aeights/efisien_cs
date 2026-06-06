from app.models.user import User
from app.repositories.lead_repo import LeadRepository


def _user(session, phone="0812"):
    u = User(name="Budi", phone=phone)
    session.add(u)
    session.flush()
    return u


def test_upsert_creates_new_lead(session):
    user = _user(session)
    lead = LeadRepository(session).upsert(
        user.id, project_type="POS", requirements="3 cabang"
    )
    assert lead.id is not None
    assert lead.status == "new"
    assert lead.project_type == "POS"
    assert lead.requirements == {"text": "3 cabang"}


def test_upsert_updates_open_lead_without_clobbering(session):
    repo = LeadRepository(session)
    user = _user(session)
    first = repo.upsert(user.id, project_type="POS")
    again = repo.upsert(user.id, budget="20 juta")
    assert again.id == first.id            # same open lead updated
    assert again.project_type == "POS"     # None argument did not clobber
    assert again.budget == "20 juta"


def test_new_lead_created_once_open_lead_is_closed(session):
    repo = LeadRepository(session)
    user = _user(session)
    a = repo.upsert(user.id, project_type="POS")
    a.status = "qualified"
    session.flush()
    b = repo.upsert(user.id, project_type="Website")
    assert b.id != a.id
    assert repo.get_latest(user.id).id == b.id
    assert repo.get_open(user.id).id == b.id


def test_set_proposal_stores_and_qualifies(session):
    user = _user(session, phone="0815")
    repo = LeadRepository(session)
    lead = repo.upsert(user.id, project_type="POS")
    proposal = {
        "scope": "POS 3 cabang",
        "timeline": "6-8 minggu",
        "cost": "Rp 25 juta",
        "deliverables": ["Aplikasi POS Android", "Dashboard web"],
    }
    repo.set_proposal(lead, proposal)
    assert lead.proposal == proposal
    assert lead.status == "qualified"
