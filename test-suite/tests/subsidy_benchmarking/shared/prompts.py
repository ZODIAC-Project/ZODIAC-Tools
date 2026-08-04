ADMIN = "Admin"


def build_routing_task(operation_desc: str, result_topic: str) -> str:
    return (
        f"Du erhältst eine Nachricht mit einer Zahl auf deinem abonnierten Topic. "
        f"{operation_desc} Veröffentliche ausschließlich das numerische Ergebnis als "
        f"reinen Text (keine weiteren Wörter) auf Topic '{result_topic}'. "
    )


def build_instruction(base_task: str, vector_purpose: str | None, mcp_purpose: str | None) -> str:
    parts = [base_task]
    if vector_purpose:
        parts.append(f"Nutze für RAG-Zugriffe ausschließlich den Purpose '{vector_purpose}'.")
    if mcp_purpose:
        parts.append(f"Nutze für Tool-Aufrufe (MCP) ausschließlich den Purpose '{mcp_purpose}'.")
    parts.append("Falls ein Zugriff wegen des Purpose abgelehnt wird, antworte exakt mit 'ACCESS_DENIED_PURPOSE_ISSUE'.")
    return " ".join(parts)

def build_matching_task(result_topic: str, allow_no_match: bool = False) -> str:
    no_match_clause = (
        "Wenn für eine Subsidy kein passender Customer existiert, lasse sie in der "
        "Ergebnisliste weg (erstelle KEINEN erzwungenen Match)."
        if allow_no_match else ""
    )
    return (
        "Du erhältst eine Nachricht mit zwei Listen: 'customers' und 'subsidies', "
        "jeweils mit 'id' und 'text'. Ordne jeder Subsidy einen passenden Customer zu, "
        f"basierend auf den Beschreibungen. {no_match_clause} "
        "Sende das Ergebnis als reines JSON (Liste von Objekten mit 'customer_id' und "
        f"'subsidy_id', keine weiteren Wörter, keine Markdown-Codeblöcke) an Topic '{result_topic}'."
    )

def build_multi_message_matching_task(result_topic: str) -> str:
    return (
        "Du erhältst zwei separate Nachrichten: eine mit einer Liste 'customers', eine mit "
        "einer Liste 'subsidies' (jeweils Objekte mit 'id' und 'text'). Warte, bis du BEIDE "
        "Nachrichten erhalten hast, bevor du antwortest. Ordne danach jeder Subsidy einen "
        "passenden Customer zu und sende das Ergebnis als reines JSON (Liste von Objekten mit "
        f"'customer_id' und 'subsidy_id', keine weiteren Wörter, keine Markdown-Codeblöcke) an Topic '{result_topic}'."
    )