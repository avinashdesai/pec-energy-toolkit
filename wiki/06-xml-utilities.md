# XML Utilities

## Purpose

In addition to the main report and dashboard workflow, this folder includes smaller utilities for direct XML inspection and chart output.

## `hourly_usage_chart.py`

This script builds a simpler hourly usage visualization from a Green Button XML file.

### What It Does

- parses kWh interval readings from XML
- groups usage into hourly buckets
- writes either:
  - an SVG chart without extra dependencies
  - a matplotlib-based chart when supported by the output type and environment

### Typical Usage

```bash
source .venv/bin/activate
python hourly_usage_chart.py green_button_data_1776194255990.xml --timezone America/Chicago
```

### Arguments

- `xml_file`
- `-o`, `--output`
- `--timezone`
- `--title`

### Notes

- The default output file is `hourly_usage_chart.svg`.
- The script is narrower in scope than `energy_analysis_report.py`.
- It is useful when you only want a quick hourly profile instead of the full HTML report.

## `parse_energy.py`

This is a simple direct-inspection script for a specific XML file path.

### What It Prints

- number of interval readings
- multiplier values seen in the XML
- raw sum of values
- total energy in kWh
- total interval cost
- selected summary fields from `ElectricPowerUsageSummary`
- a sample interval duration

### Notes

- It is not parameterized.
- It is best treated as a lightweight debugging or validation script.
- The main supported workflow is still the report generator.

## When to Use These Utilities

Use `hourly_usage_chart.py` when:

- you want a quick visual
- you do not need TOU costing
- you want a lightweight artifact

Use `parse_energy.py` when:

- you want to inspect raw XML values
- you are validating totals or multipliers
- you are debugging an unfamiliar XML export

## Related Pages

- [Energy Analysis Report](./03-energy-analysis-report.md)
- [Testing and Maintenance](./07-testing-and-maintenance.md)

