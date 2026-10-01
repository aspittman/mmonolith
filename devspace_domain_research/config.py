MIN_BUY_SCORE = 75
MIN_REVIEW_SCORE = 45
MAX_ALERTS_OR_INGESTS = 5

MARKET_DATA_DEFAULTS = {
    "market_data_enabled": True,
    "sales_data_path": "data/domain_merchant/domain_sales.json",
    "sales_sources": {
        "deduplication_date_tolerance_days": 14,
        "namebio": {
            "enabled": True,
            "import_type": "csv",
            "path": "data/domain_merchant/namebio_sales.csv",
            "column_mapping": {},
        },
        "dnjournal": {
            "enabled": False,
            "import_type": "csv_or_json",
            "path": "data/domain_merchant/dnjournal_sales.csv",
            "column_mapping": {},
        },
    },
    "minimum_comparable_similarity": 0.45,
    "minimum_comparable_count": 3,
    "high_confidence_comparable_count": 8,
    "comparable_max_age_days": 1825,
    "sales_trend_window_days": 730,
    "liquidity_window_days": 1095,
    "valuation_percentiles": [0.25, 0.75],
    "minimum_source_quality_tier": 3,
    "source_quality_weights": {"tier_1": 1.0, "tier_2": 0.8, "tier_3": 0.45, "tier_4": 0.1},
    "valuation_currency": "USD",
    "component_score_weights": {
        "quality": 0.35,
        "comparable_sales": 0.20,
        "market": 0.12,
        "liquidity": 0.12,
        "buyer_market": 0.13,
        "timing": 0.08,
    },
    "minimum_buy_score": 75,
    "minimum_review_score": 55,
    "maximum_purchase_price": 250,
    "minimum_expected_margin": 100,
    "annual_renewal_cost": 12,
    "expected_holding_years": 2,
    "marketplace_commission_rate": 0.15,
    "expected_negotiation_discount": 0.10,
    "estimated_sale_probability": 0.12,
    "domain_score_snapshot_path": "data/domain_merchant/domain_score_snapshots.jsonl",
    "grammar_report_path": "data/domain_merchant/grammar_report.json",
    "control_data_path": None,
    "minimum_grammar_support": 2,
    "availability": {
        "enabled": True,
        "provider": "static_file",
        "path": "data/domain_merchant/domain_availability.csv",
        "require_available_for_buy": True,
    },
    "dry_run": False,
}


def market_config(config=None) -> dict:
    supplied = config or {}
    merged = {**MARKET_DATA_DEFAULTS, **supplied}
    merged["component_score_weights"] = {
        **MARKET_DATA_DEFAULTS["component_score_weights"],
        **(supplied.get("component_score_weights") or {}),
    }
    merged["availability"] = {
        **MARKET_DATA_DEFAULTS["availability"],
        **(supplied.get("availability") or {}),
    }
    return merged

STATE_TERMS = [
    "utah", "arizona", "colorado", "nevada", "texas", "florida",
    "california", "oregon", "washington", "idaho", "montana",
    "georgia", "tennessee", "carolina", "ohio", "michigan",
]

CITY_TERMS = [
    "phoenix", "denver", "vegas", "saltlake", "provo", "orem",
    "boise", "austin", "dallas", "houston", "orlando", "tampa",
    "miami", "atlanta", "nashville", "charlotte", "columbus",
    "detroit", "portland", "seattle", "spokane", "reno",
]
