import json

from app.llm.base import ToolCall, ToolSpec

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
    )
]


def dispatch(tool_call: ToolCall, *, retriever) -> str:
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
        return json.dumps(
            {"error": f"Tool tidak dikenal: {tool_call.name}"}, ensure_ascii=False
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
