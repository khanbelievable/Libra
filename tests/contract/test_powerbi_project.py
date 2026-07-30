from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path("powerbi/Libra")
MODEL = ROOT / "Libra.SemanticModel/definition"
REPORT = ROOT / "Libra.Report/definition"


def test_pbip_has_real_model_and_report_bindings() -> None:
    project = json.loads((ROOT / "Libra.pbip").read_text(encoding="utf-8"))
    report = json.loads((ROOT / "Libra.Report/definition.pbir").read_text(encoding="utf-8"))
    assert project["version"] == "1.0"
    assert report["version"] == "4.0"
    assert report["datasetReference"]["byPath"]["path"] == "../Libra.SemanticModel"


def test_model_has_expected_tables_relationships_and_approved_measures() -> None:
    table_files = list((MODEL / "tables").glob("*.tmdl"))
    relationships = (MODEL / "relationships.tmdl").read_text(encoding="utf-8")
    measures = (MODEL / "tables/Measures.tmdl").read_text(encoding="utf-8")
    assert len(table_files) == 12
    assert len(re.findall(r"^relationship ", relationships, re.MULTILINE)) == 22
    assert len(re.findall(r"^\s*measure ", measures, re.MULTILINE)) == 14
    assert "bothDirections" not in relationships
    assert "FactInvoice[AmountEUR]" in measures
    assert "FactShipment[AmountEUR]" not in measures


def test_report_has_seven_ordered_data_bound_pages() -> None:
    pages = json.loads((REPORT / "pages/pages.json").read_text(encoding="utf-8"))
    assert len(pages["pageOrder"]) == 7
    for page_name in pages["pageOrder"]:
        page_path = REPORT / "pages" / page_name
        assert (page_path / "page.json").is_file()
        visuals = list((page_path / "visuals").glob("*/visual.json"))
        assert len(visuals) >= 2
        assert all('"query"' in visual.read_text(encoding="utf-8") for visual in visuals)


def test_snowflake_parameters_are_non_secret_placeholders() -> None:
    expressions = (MODEL / "expressions.tmdl").read_text(encoding="utf-8")
    assert "Snowflake.Databases" in expressions
    assert "LIBRA" in expressions
    assert "REPORTING" in expressions
    assert "password" not in expressions.lower()
