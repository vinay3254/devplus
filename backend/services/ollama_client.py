import requests


class OllamaError(Exception):
    pass


def summarize_and_tag(text, api_url, model):
    prompt = (
        "Summarize the following text in 1-2 sentences, then suggest one "
        "category (a single word) and up to 3 tags (comma-separated, lowercase). "
        "Respond in exactly this format:\n"
        "SUMMARY: <summary>\n"
        "CATEGORY: <category>\n"
        "TAGS: <tag1, tag2, tag3>\n\n"
        f"TEXT:\n{text}"
    )
    try:
        resp = requests.post(
            f"{api_url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise OllamaError(str(e))

    raw = resp.json().get("response", "")
    return _parse_summary_response(raw)


def _parse_summary_response(raw):
    summary, category, tags = None, None, []
    for line in raw.splitlines():
        line = line.strip()
        if line.upper().startswith("SUMMARY:"):
            summary = line.split(":", 1)[1].strip()
        elif line.upper().startswith("CATEGORY:"):
            category = line.split(":", 1)[1].strip()
        elif line.upper().startswith("TAGS:"):
            tags = [t.strip() for t in line.split(":", 1)[1].split(",") if t.strip()]
    return summary, category, tags


def embed(text, api_url, model):
    try:
        resp = requests.post(
            f"{api_url}/api/embeddings",
            json={"model": model, "prompt": text},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise OllamaError(str(e))
    return resp.json()["embedding"]
