import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
HCX_SOURCE = PROJECT_ROOT / "backend" / "agents" / "diary_chatbot" / "hcx.py"


def test_hcx005_agent_does_not_directly_call_hcx007_agent() -> None:
    tree = ast.parse(HCX_SOURCE.read_text(encoding="utf-8"))
    hcx005 = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Hcx005MultimodalChatAgent"
    )

    referenced_names = {
        node.id for node in ast.walk(hcx005) if isinstance(node, ast.Name)
    }
    referenced_attributes = {
        node.attr for node in ast.walk(hcx005) if isinstance(node, ast.Attribute)
    }

    assert "Hcx007DiaryGenerationAgent" not in referenced_names
    assert "Hcx007DiaryGenerationAgent" not in referenced_attributes


def test_runtime_code_does_not_import_test_packages() -> None:
    forbidden_prefixes = ("tests", "backend.testing")
    runtime_files = [
        *PROJECT_ROOT.joinpath("backend").rglob("*.py"),
        *PROJECT_ROOT.joinpath("frontend").rglob("*.py"),
    ]

    violations = []
    for source_path in runtime_files:
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imported_modules = []
            if isinstance(node, ast.Import):
                imported_modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules = [node.module]
            for module in imported_modules:
                if module.startswith(forbidden_prefixes):
                    violations.append(f"{source_path.relative_to(PROJECT_ROOT)} -> {module}")

    assert violations == []
