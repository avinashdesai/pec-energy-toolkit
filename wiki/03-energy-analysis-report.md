# Energy Analysis Report

## Purpose

`energy_analysis_report.py` generates a standalone HTML report from a Green Button XML export.

The report combines:

- actual interval usage from the XML
- PEC TOU pricing from the shared rate model
- a flat-rate comparison
- charts for hourly, daily, weekday, and TOU-period patterns

## Input

- one XML file containing Green Button interval readings

The script reads only the kWh interval series. It ignores non-kWh series such as instantaneous power.

## Output

- a standalone HTML file named `<xml stem>_report.html` by default

The report includes:

- total usage
- TOU total
- flat total
- TOU vs flat difference
- source and snapshot details
- usage mix by TOU period and season
- Plotly charts

## Main Calculations

### XML Parsing

The script:

- loads the XML
- finds `IntervalBlock` entries with `uom` value `72`
- extracts interval start time, duration, and energy value
- converts using `powerOfTenMultiplier` when present

### TOU Costing

Each interval is expanded minute by minute so usage can be assigned accurately across TOU boundaries.

This matters when an interval crosses boundaries such as:

- `5:01 p.m.`
- `9:01 p.m.`

### Flat Comparison

The flat comparison uses the shared rate configuration:

- flat base power charge
- delivery charge
- transmission charge
- fixed service charge

## Charts Included

- Hourly Energy Usage
- Daily Usage and Total Cost Comparison
- Total Bill Comparison
- Usage Split Under TOU Periods
- Usage by Day of Week

## CLI Options

```bash
python energy_analysis_report.py <xml_file> [options]
```

Supported options:

- `-o`, `--output`
- `--timezone`
- `--rate-source`
- `--snapshot-file`
- `--service-charge`
- `--delivery-charge`
- `--transmission-charge`
- `--flat-rate`

## Examples

Generate a report using the local snapshot:

```bash
python energy_analysis_report.py april_bill_data.xml
```

Try a live PEC fetch first:

```bash
python energy_analysis_report.py april_bill_data.xml --rate-source auto
```

Override the flat base rate:

```bash
python energy_analysis_report.py april_bill_data.xml --flat-rate 0.070
```

## Report Styling

The generated report currently uses:

- dark mode page styling
- dark Plotly charts
- cents per kWh display with one decimal place for rate labels
- dollars for totals and fixed charges

## Notes

- The report is static after generation.
- It does not call the local dashboard API.
- If PEC live fetch fails, the script can still use the local or cached snapshot path.

## Related Pages

- [Rate Snapshot and Refresh Model](./05-rate-snapshot-and-refresh.md)
- [XML Utilities](./06-xml-utilities.md)

