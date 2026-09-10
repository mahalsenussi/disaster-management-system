"""
Marine module: sea surface currents, sea surface height, and vessel-capsize risk.
Data sources: Copernicus Marine (copernicusmarine package) via MEDSEA analysis/forecast
product MEDSEA_ANALYSISFORECAST_PHY_006_013; UNESCO-IOC sea level gauges.

Per product decision (2026-09-10): build with mock fallback initially; real CMEMS
downloads activate automatically once credentials are available (see collector.login_hint()).
"""