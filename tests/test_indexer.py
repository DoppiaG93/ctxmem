from ctxmem import indexer


def test_extract_symbols_returns_named_python_blocks():
    text = """\
class MemoryStore:
    pass

def recall(query):
    return query
"""

    symbols = indexer.extract_symbols("sample.py", text)

    assert [name for name, _, _ in symbols] == ["MemoryStore", "recall"]
    assert symbols[0][1] == 1
    assert "class MemoryStore" in symbols[0][2]
    assert symbols[1][1] == 4
    assert "def recall" in symbols[1][2]


def test_extract_symbols_indexes_file_head_when_no_symbol_matches():
    symbols = indexer.extract_symbols("README.md", "first line\nsecond line\n")

    assert symbols == [("README.md", 1, "first line\nsecond line")]
