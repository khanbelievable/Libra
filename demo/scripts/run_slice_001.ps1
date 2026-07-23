$ErrorActionPreference = "Stop"

libra generate healthy --output data/generated
libra run healthy --input data/generated --output data/processed
libra generate broken --output data/generated

# Broken scenarios intentionally return exit code 2. Run separately so evidence is retained.
foreach ($scenario in @("duplicate_invoices", "missing_gbp_fx", "incomplete_germany", "invalid_operational_costs")) {
    libra run-batch --batch-dir "data/generated/$scenario" --output "data/processed/$scenario"
    if ($LASTEXITCODE -notin @(0, 2)) {
        throw "Scenario $scenario failed with infrastructure exit code $LASTEXITCODE"
    }
}

libra generate correction --output data/generated
libra run correction --input data/generated --output data/processed

pytest tests/demo -q
