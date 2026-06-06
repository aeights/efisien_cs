import json
import uuid

from app.integrations.calendar import fmt_slot, now_wib, parse_slot
from app.llm.base import ToolCall, ToolSpec
from app.repositories.lead_repo import LeadRepository
from app.repositories.meeting_repo import MeetingRepository
from app.repositories.client_fact_repo import ClientFactRepository
from app.repositories.notification_repo import NotificationRepository
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
    ToolSpec(
        name="remember_fact",
        description=(
            "Simpan fakta durable tentang user (mis. nama, perusahaan, peran, preferensi) "
            "agar diingat di percakapan berikutnya. Panggil saat user menyebutkan info "
            "tentang dirinya yang layak diingat."
        ),
        parameters={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Label fakta, mis. 'nama', 'perusahaan'"},
                "value": {"type": "string", "description": "Isi fakta"},
            },
            "required": ["key", "value"],
        },
    ),
    ToolSpec(
        name="notify_sales",
        description=(
            "Teruskan ke tim sales saat ada peluang/permintaan komersial yang butuh "
            "manusia (mis. negosiasi harga, penawaran khusus). Isi 'reason' yang jelas."
        ),
        parameters={
            "type": "object",
            "properties": {"reason": {"type": "string", "description": "Alasan eskalasi ke sales"}},
            "required": ["reason"],
        },
    ),
    ToolSpec(
        name="notify_manager",
        description=(
            "Eskalasi ke manajer saat user minta bicara dengan manusia, ada komplain "
            "pembayaran/kontrak, atau kegagalan berulang. Isi 'reason' yang jelas."
        ),
        parameters={
            "type": "object",
            "properties": {"reason": {"type": "string", "description": "Alasan eskalasi ke manajer"}},
            "required": ["reason"],
        },
    ),
    ToolSpec(
        name="generate_proposal",
        description=(
            "Susun proposal awal (scope, timeline, biaya, deliverables) dari kebutuhan "
            "lead yang sudah digali. Panggil saat user meminta penawaran/proposal atau "
            "setelah kebutuhan cukup lengkap. Isi argumen secara realistis."
        ),
        parameters={
            "type": "object",
            "properties": {
                "scope": {"type": "string", "description": "Ringkasan lingkup pekerjaan"},
                "timeline": {"type": "string", "description": "Estimasi waktu, mis. '6-8 minggu'"},
                "cost": {"type": "string", "description": "Estimasi biaya, mis. 'Rp 25-30 juta'"},
                "deliverables": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Daftar hasil yang diserahkan",
                },
            },
            "required": ["scope", "timeline", "cost"],
        },
    ),
]


def _meeting_link() -> str:
    return f"https://meet.efisien.id/{uuid.uuid4().hex[:8]}"


_CATEGORIES = {"bug", "feature", "question"}
_PRIORITIES = {"low", "med", "high"}


def _notify(session, user, role: str, reason: str) -> str:
    payload = {"name": user.name, "phone": user.phone, "email": user.email}
    notif = NotificationRepository(session).create(role, reason=reason, payload=payload)
    print(f"[NOTIFY:{role}] {reason} | user={user.name or user.phone or user.email}")
    return json.dumps(
        {
            "notification_id": notif.id,
            "target_role": notif.target_role,
            "status": notif.status,
            "result": f"Diteruskan ke tim {role}; akan menindaklanjuti.",
        },
        ensure_ascii=False,
    )


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

        if tool_call.name == "remember_fact":
            key = tool_call.args.get("key", "")
            value = tool_call.args.get("value", "")
            ClientFactRepository(session).upsert(user.id, key, value)
            return json.dumps(
                {"key": key, "value": value, "result": "Fakta disimpan."},
                ensure_ascii=False,
            )

        if tool_call.name == "notify_sales":
            return _notify(session, user, "sales", tool_call.args.get("reason", ""))

        if tool_call.name == "notify_manager":
            return _notify(session, user, "manager", tool_call.args.get("reason", ""))

        if tool_call.name == "generate_proposal":
            lead = LeadRepository(session).get_latest(user.id)
            if lead is None:
                return json.dumps(
                    {"result": "Belum ada lead. Gali kebutuhan klien dulu sebelum membuat proposal."},
                    ensure_ascii=False,
                )
            proposal = {
                "scope": tool_call.args.get("scope", ""),
                "timeline": tool_call.args.get("timeline", ""),
                "cost": tool_call.args.get("cost", ""),
                "deliverables": tool_call.args.get("deliverables", []),
            }
            LeadRepository(session).set_proposal(lead, proposal)
            return json.dumps(
                {"lead_id": lead.id, "proposal": proposal, "status": lead.status},
                ensure_ascii=False,
            )

        return json.dumps(
            {"error": f"Tool tidak dikenal: {tool_call.name}"}, ensure_ascii=False
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
