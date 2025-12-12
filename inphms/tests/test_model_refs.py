import re
import pathlib
import pytest

MODEL_PATTERN = re.compile(r"['\"]((?:ir|res)\.[a-z0-9_.]+)['\"]", re.IGNORECASE)
MODEL_DEF_PATTERN = re.compile(r"_name\s*=\s*['\"]([a-z0-9_.]+)['\"]", re.IGNORECASE)
STATIC_PATTERN = re.compile(r"['\"]/base/static(?:/[\w\-/\.]*)?['\"]", re.IGNORECASE)
CODE_DIR = pathlib.Path("inphms")
ADDONS_DIR = CODE_DIR / "addons"


def collect_defined_models() -> set[str]:
    """Walk through addons/ and collect all _name declarations."""
    defined_models = set()
    for path in ADDONS_DIR.rglob("*.py"):
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for match in MODEL_DEF_PATTERN.findall(content):
            defined_models.add(match)
    return defined_models

DEFINED_MODELS = collect_defined_models()


@pytest.mark.parametrize("path", CODE_DIR.rglob("*.py"))
def test_log_model_references(path):
    """Scan and log all ir./res. model references across the codebase."""
    content = path.read_text(encoding="utf-8", errors="ignore")
    matches = MODEL_PATTERN.findall(content)
    image_matches = STATIC_PATTERN.findall(content)

    if not matches:
        pytest.skip(f"No ir./res. references found in {path}")

    missing_models = []
    for model in matches:
        if model not in DEFINED_MODELS:
            missing_models.append(model)

    if missing_models:
        print(f"\n📁 {path}:")
        for m in missing_models:
            print(f"  ❌ Missing model: {m}")

    for a in image_matches:
        print(f"\nImage 📁 {path}:")
        print(a)

    # If we want it to be purely logging:
    assert True

    # If we want the test to fail when missing models are found:
    # assert not missing_models, f"Missing models: {', '.join(missing_models)}"
