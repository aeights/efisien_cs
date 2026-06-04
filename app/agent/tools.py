import json
import uuid

from app.integrations.calendar import fmt_slot, now_wib, parse_slot
from app.llm.base import ToolCall, ToolSpec
from app.repositories.lead_repo import LeadRepository
from app.repositories.meeting_repo import MeetingRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.ticket_repo import TicketRepository

TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="search_knowledge_base",
        description=(
            "Cari informasi resmi perusahaan (layanan, harga, profil, portofolio, FAQ) "
            "dari knowledge base. Gunakan untuk pertanyaan tentang perusahaan."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Pertanyaan atau kata kunci pencarian",
                }
            },
            "required": ["query"],
        },
    ),
    ToolSpec(
        name="create_lead",
        description=(
            "Simpan atau perbarui lead (kebutuhan calon klien) setelah menggali "
            "kebutuhan lewat percakapan. Panggil saat sudah ada cukup informasi; "
            "boleh dipanggil ulang untuk melengkapi data yang sama."
        ),
        parameters={
            "type": "object",
            "properties": {
                "project_type": {
                    "type": "string",
                    "description": "Jenis proyek, mis. POS, Website, Mobile App",
                },
                "platform": {
                    "type": "string",
                    "description": "Platform target, mis. Web, Android, iOS",
                },
                "requirements": {
                    "type": "string",
                    "description": "Ringkasan kebutuhan utama klien",
                },
                "budget": {
                    "type": "string",
                    "description": "Estimasi budget, mis. '20-30 juta' atau 'belum ada'",
                },
            },
        },
    ),
    ToolSpec(
        name="get_lead",
        description=(
            "Ambil ringkasan lead terbaru milik user saat ini "
            "(kebutuhan yang sudah dicatat sebelumnya)."
        ),
        parameters={"type": "object", "properties": {}},
    ),
    ToolSpec(
        name="get_available_slots",
        description=(
            "Lihat slot jadwal konsultasi yang masih tersedia (hari kerja, jam kerja). "
            "Panggil saat user ingin booking meeting/konsultasi."
        ),
        parameters={"type": "object", "properties": {}},
    ),
    ToolSpec(
        name="create_meeting",
        description=(
            "Pesan jadwal konsultasi pada slot yang dipilih user. Panggil setelah user "
            "memilih salah satu slot dari get_available_slots."
        ),
        parameters={
            "type": "object",
            "properties": {
                "slot": {
                    "type": "string",
                    "description": "Slot terpilih, format 'YYYY-MM-DD HH:MM' (WIB)",
                }
            },
            "required": ["slot"],
        },
    ),
    ToolSpec(
        name="send_invitation",
        description=(
            "Kirim undangan konsultasi (berisi waktu & link) ke kontak user, "
            "untuk meeting terbaru yang sudah dibuat."
        ),
        parameters={"type": "object", "properties": {}},
    ),
    ToolSpec(
        name="get_project_status",
        description=(
            "Lihat status dan progres proyek milik klien yang sedang chat. "
            "Panggil saat klien existing menanyakan perkembangan proyeknya."
        ),
        parameters={"type": "object", "properties": {}},
    ),
    ToolSpec(
        name="create_ticket",
        description=(
            "Buat tiket support untuk klien existing yang melaporkan masalah atau "
            "permintaan. Tentukan category (bug/feature/question) dan priority "
            "(low/med/high) dari isi keluhan. Panggil setelah deskripsi masalah jelas."
        ),
        parameters={
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Ringkasan masalah atau permintaan klien",
                },
                "category": {
                    "type": "string",
                    "enum": ["bug", "feature", "question"],
                    "description": "Jenis tiket",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "med", "high"],
                    "description": "Tingkat prioritas",
                },
            },
            "required": ["description"],
        },
    ),
    ToolSpec(
        name="assign_developer",
        description=(
            "Tugaskan tiket terbaru milik klien ke tim developer (ubah status "
            "menjadi 'assigned'). Panggil setelah create_ticket berhasil."
        ),
        parameters={"type": "object", "properties": {}},
    ),
]


def _meeting_link() -> str:
    return f"https://meet.efisien.id/{uuid.uuid4().hex[:8]}"


_CATEGORIES = {"bug", "feature", "question"}
_PRIORITIES = {"low", "med", "high"}


def dispatch(
    tool_call: ToolCall, *, retriever=None, session=None, user=None, calendar=None, email=None
) -> str:
    """Execute a tool call and return a JSON string result to feed back to the LLM."""
    try:
        if tool_call.name == "search_knowledge_base":
            query = tool_call.args.get("query", "")
            hits = retriever.search(query, k=4)
            if not hits:
                return json.dumps(
                    {"result": "Tidak ada informasi relevan di knowledge base."},
                    ensure_ascii=False,
                )
            return json.dumps(
                {"results": [{"text": h["text"], "source": h["source"]} for h in hits]},
                ensure_ascii=False,
            )

        if tool_call.name == "create_lead":
            lead = LeadRepository(session).upsert(
                user.id,
                project_type=tool_call.args.get("project_type"),
                platform=tool_call.args.get("platform"),
                requirements=tool_call.args.get("requirements"),
                budget=tool_call.args.get("budget"),
            )
            return json.dumps(
                {
                    "lead_id": lead.id,
                    "status": lead.status,
                    "project_type": lead.project_type,
                    "platform": lead.platform,
                    "budget": lead.budget,
                },
                ensure_ascii=False,
            )

        if tool_call.name == "get_lead":
            lead = LeadRepository(session).get_latest(user.id)
            if lead is None:
                return json.dumps({"result": "Belum ada lead."}, ensure_ascii=False)
            return json.dumps(
                {
                    "lead_id": lead.id,
                    "project_type": lead.project_type,
                    "platform": lead.platform,
                    "requirements": (lead.requirements or {}).get("text"),
                    "budget": lead.budget,
                    "status": lead.status,
                },
                ensure_ascii=False,
            )

        if tool_call.name == "get_available_slots":
            booked = MeetingRepository(session).scheduled_times()
            slots = calendar.available_slots(booked, now=now_wib())
            return json.dumps(
                {"slots": [fmt_slot(s) for s in slots[:8]]}, ensure_ascii=False
            )

        if tool_call.name == "create_meeting":
            lead = LeadRepository(session).get_latest(user.id)
            if lead is None:
                return json.dumps(
                    {"result": "Belum ada lead. Gali kebutuhan klien dulu sebelum booking."},
                    ensure_ascii=False,
                )
            chosen = tool_call.args.get("slot", "")
            booked = MeetingRepository(session).scheduled_times()
            available = {fmt_slot(s) for s in calendar.available_slots(booked, now=now_wib())}
            if chosen not in available:
                return json.dumps(
                    {"error": f"Slot '{chosen}' tidak tersedia. Tawarkan slot lain."},
                    ensure_ascii=False,
                )
            meeting = MeetingRepository(session).create(
                lead.id, parse_slot(chosen), _meeting_link()
            )
            return json.dumps(
                {
                    "meeting_id": meeting.id,
                    "meeting_time": chosen,
                    "meeting_link": meeting.meeting_link,
                    "status": meeting.status,
                },
                ensure_ascii=False,
            )

        if tool_call.name == "send_invitation":
            meeting = MeetingRepository(session).get_latest_for_user(user.id)
            if meeting is None:
                return json.dumps(
                    {"result": "Belum ada meeting untuk dikirimi undangan."},
                    ensure_ascii=False,
                )
            to = user.email or user.phone
            email.send(
                to,
                "Undangan Konsultasi - PT Efisien Integrasi Indonesia",
                f"Jadwal: {fmt_slot(meeting.meeting_time)} WIB\nLink: {meeting.meeting_link}",
            )
            return json.dumps({"result": f"Undangan terkirim ke {to}."}, ensure_ascii=False)

        if tool_call.name == "get_project_status":
            projects = ProjectRepository(session).list_for_user(user.id)
            if not projects:
                return json.dumps(
                    {"result": "Belum ada proyek terdaftar atas nama Anda."},
                    ensure_ascii=False,
                )
            return json.dumps(
                {
                    "projects": [
                        {
                            "name": p.name,
                            "type": p.type,
                            "progress": p.progress,
                            "status": p.status,
                            "details": p.details,
                        }
                        for p in projects
                    ]
                },
                ensure_ascii=False,
            )

        if tool_call.name == "create_ticket":
            description = tool_call.args.get("description", "")
            category = tool_call.args.get("category")
            if category not in _CATEGORIES:
                category = "question"
            priority = tool_call.args.get("priority")
            if priority not in _PRIORITIES:
                priority = "med"
            projects = ProjectRepository(session).list_for_user(user.id)
            project_id = projects[-1].id if projects else None
            ticket = TicketRepository(session).create(
                user.id,
                description=description,
                category=category,
                priority=priority,
                project_id=project_id,
            )
            return json.dumps(
                {
                    "ticket_id": ticket.id,
                    "category": ticket.category,
                    "priority": ticket.priority,
                    "status": ticket.status,
                    "project_id": ticket.project_id,
                },
                ensure_ascii=False,
            )

        if tool_call.name == "assign_developer":
            ticket = TicketRepository(session).get_latest_for_user(user.id)
            if ticket is None:
                return json.dumps(
                    {"result": "Belum ada tiket untuk ditugaskan."}, ensure_ascii=False
                )
            TicketRepository(session).assign(ticket)
            print(
                f"[ASSIGN] Tiket #{ticket.id} ({ticket.priority}/{ticket.category}) "
                f"ditugaskan ke {ticket.assigned_developer}"
            )
            return json.dumps(
                {
                    "ticket_id": ticket.id,
                    "status": ticket.status,
                    "assigned_developer": ticket.assigned_developer,
                },
                ensure_ascii=False,
            )

        return json.dumps(
            {"error": f"Tool tidak dikenal: {tool_call.name}"}, ensure_ascii=False
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
