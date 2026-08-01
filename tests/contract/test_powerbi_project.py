from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path("powerbi/Libra")
MODEL = ROOT / "Libra.SemanticModel/definition"
REPORT = ROOT / "Libra.Report/definition"
EXPECTED_MEASURES = {
    "Total Revenue",
    "Total Operational Cost",
    "Gross Profit",
    "Gross Margin Percentage",
    "Shipment Count",
    "Revenue per Shipment",
    "Cost per Shipment",
    "Budget Amount",
    "Actual Cost",
    "Budget Variance Amount",
    "Budget Variance Percentage",
    "FX Impact",
    "Failed Quality Rows",
    "Latest Successful Refresh",
}


def test_pbip_has_real_model_and_report_bindings() -> None:
    project = json.loads((ROOT / "Libra.pbip").read_text(encoding="utf-8"))
    report = json.loads((ROOT / "Libra.Report/definition.pbir").read_text(encoding="utf-8"))
    assert project["version"] == "1.0"
    assert report["version"] == "4.0"
    assert report["datasetReference"]["byPath"]["path"] == "../Libra.SemanticModel"


def test_model_has_expected_tables_relationships_and_approved_measures() -> None:
    table_files = list((MODEL / "tables").glob("*.tmdl"))
    model = (MODEL / "model.tmdl").read_text(encoding="utf-8")
    relationships = (MODEL / "relationships.tmdl").read_text(encoding="utf-8")
    measures = (MODEL / "tables/FinanceMeasures.tmdl").read_text(encoding="utf-8")
    table_names = {
        re.search(r"^table (.+)$", path.read_text(encoding="utf-8"), re.MULTILINE).group(1)
        for path in table_files
    }
    assert len(table_files) == 12
    assert "Measures" not in table_names
    assert "FinanceMeasures" in table_names
    assert "ref table Measures" not in model
    assert "ref table FinanceMeasures" in model
    assert len(re.findall(r"^relationship ", relationships, re.MULTILINE)) == 22
    assert "isActive: false" not in relationships
    assert "bothDirections" not in relationships
    assert set(re.findall(r"^\s*measure '([^']+)' =", measures, re.MULTILINE)) == EXPECTED_MEASURES
    assert "FactInvoice[AmountEUR]" in measures
    assert "FactShipment[AmountEUR]" not in measures


def test_report_has_seven_ordered_data_bound_pages() -> None:
    pages = json.loads((REPORT / "pages/pages.json").read_text(encoding="utf-8"))
    assert len(pages["pageOrder"]) == 7
    visual_files = []
    for page_name in pages["pageOrder"]:
        page_path = REPORT / "pages" / page_name
        assert (page_path / "page.json").is_file()
        visuals = list((page_path / "visuals").glob("*/visual.json"))
        assert len(visuals) >= 2
        visual_files.extend(visuals)
    visual_definitions = "\n".join(visual.read_text(encoding="utf-8") for visual in visual_files)
    assert len(visual_files) == 30
    assert all('"query"' in visual.read_text(encoding="utf-8") for visual in visual_files)
    assert '"Entity":"Measures"' not in visual_definitions
    assert '"queryRef":"Measures.' not in visual_definitions
    assert '"Entity":"FinanceMeasures"' in visual_definitions


def test_snowflake_parameters_are_non_secret_placeholders() -> None:
    expressions = (MODEL / "expressions.tmdl").read_text(encoding="utf-8")
    assert "Snowflake.Databases" in expressions
    assert "LIBRA" in expressions
    assert "REPORTING" in expressions
    assert "password" not in expressions.lower()


def test_snowflake_parameter_metadata_is_inline_for_power_bi_desktop() -> None:
    expressions = (MODEL / "expressions.tmdl").read_text(encoding="utf-8")
    expected = [
        'expression SnowflakeServer = "configure-in-power-bi-desktop" meta '
        '[IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]',
        'expression SnowflakeWarehouse = "configure-in-power-bi-desktop" meta '
        '[IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]',
    ]
    assert expressions.splitlines()[:4] == [expected[0], "", expected[1], ""]
