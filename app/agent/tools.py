import json

from app.llm.base import ToolCall, ToolSpec
from app.repositories.lead_repo import LeadRepository

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
]


def dispatch(tool_call: ToolCall, *, retriever=None, session=None, user=None) -> str:
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

        return json.dumps(
            {"error": f"Tool tidak dikenal: {tool_call.name}"}, ensure_ascii=False
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
