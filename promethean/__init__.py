"""Promethean local evidence tools. No import-time network or writes."""
from __future__ import annotations

from typing import Any

__all__ = [
    "MIRROR_LEDGERS",
    "OPERATIONAL_SECTIONS",
    "audit_alpr_logs",
    "audit_annexation_prerequisites",
    "audit_check_register_csv",
    "audit_gis_tax_classifications",
    "audit_govqa_master_log",
    "audit_lcrr_service_lines",
    "audit_permitting_csv",
    "audit_water_advisory_timeline",
    "audit_ws_16_4_202_timeline",
    "build_arcgis_geojson_query_url",
    "count_wyoming_business_days",
    "package_osint_artifact",
    "triangulate_mirror_ledgers",
    "verify_osint_provenance",
]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from . import forensic_audit
        return getattr(forensic_audit, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
