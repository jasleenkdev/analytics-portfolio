"""The analysis must discover planted effects without reading them: only crosscheck.py may open the plant files."""
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
FORBIDDEN = ("plants.toml", "planted_entities", "GROUND_TRUTH", "load_truth")


def test_only_crosscheck_reads_ground_truth():
    offenders = []
    for path in list((PROJECT / "analysis").glob("*.py")) + list((PROJECT / "sql").glob("*.sql")) + [PROJECT / "pipeline.py"]:
        if path.name == "crosscheck.py":
            continue
        text = path.read_text()
        offenders += [f"{path.name}: {word}" for word in FORBIDDEN if word in text]
    assert offenders == []
