import json
from pathlib import Path

from devspace_domain_research.market_data import load_sales
from devspace_domain_research.sales_sources import DNJournalImporter, NameBioCsvImporter, canonicalize_sales


def import_sales(source_path, output_path=None, quarantine_path=None) -> dict:
    result = load_sales(source_path)
    if output_path:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps({"sales": result["records"]}, indent=2), encoding="utf-8")
    if quarantine_path and result["quarantined"]:
        destination = Path(quarantine_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result["quarantined"], indent=2), encoding="utf-8")
    return result


def import_configured_sources(namebio_file=None, dnjournal_file=None, output_path=None, quarantine_path=None, config=None) -> dict:
    config = config or {}
    source_config = config.get("sales_sources") or config
    adapters = []
    namebio = source_config.get("namebio") or {}
    dnjournal = source_config.get("dnjournal") or {}
    namebio_path = namebio_file or namebio.get("path")
    dnjournal_path = dnjournal_file or dnjournal.get("path")
    if namebio_path and namebio.get("enabled", True):
        adapters.append(NameBioCsvImporter(namebio_path, namebio.get("column_mapping")))
    if dnjournal_path and dnjournal.get("enabled", True):
        adapters.append(DNJournalImporter(dnjournal_path, dnjournal.get("column_mapping")))
    all_records, quarantined, warnings = [], [], []
    for adapter in adapters:
        loaded = adapter.load()
        all_records.extend(loaded["records"])
        quarantined.extend(loaded["quarantined"])
        if loaded.get("error"):
            warnings.append(loaded["error"])
    merged = canonicalize_sales(all_records, int(source_config.get("deduplication_date_tolerance_days", 14)))
    result = {**merged, "quarantined": quarantined, "warnings": warnings, "sources_attempted": [adapter.source_name for adapter in adapters]}
    if output_path:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps({"sales": result["records"]}, indent=2), encoding="utf-8")
    if quarantine_path and quarantined:
        destination = Path(quarantine_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(quarantined, indent=2), encoding="utf-8")
    return result
