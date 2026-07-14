import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from services.ollama_client import _parse_summary_response


def test_parse_summary_response_extracts_all_fields():
    raw = "SUMMARY: A short summary.\nCATEGORY: dsa\nTAGS: arrays, sorting, search"
    summary, category, tags = _parse_summary_response(raw)
    assert summary == "A short summary."
    assert category == "dsa"
    assert tags == ["arrays", "sorting", "search"]
    print("PASS: parses summary/category/tags from well-formed response")


def test_parse_summary_response_handles_missing_fields():
    raw = "SUMMARY: Only a summary, nothing else."
    summary, category, tags = _parse_summary_response(raw)
    assert summary == "Only a summary, nothing else."
    assert category is None
    assert tags == []
    print("PASS: missing CATEGORY/TAGS lines default to None/[]")


if __name__ == "__main__":
    test_parse_summary_response_extracts_all_fields()
    test_parse_summary_response_handles_missing_fields()
    print("All ollama_client tests passed.")
