import os


def _as_bool(val: str | None, default: bool = True) -> bool:
    if val is None:
        return default
    v = val.strip().lower()
    return v in {"1", "true", "yes", "on"}


class DashboardFeatures:
    alerts: bool
    trends: bool
    drilldown: bool
    export: bool
    scorecards: bool

    def __init__(self) -> None:
        self.alerts = _as_bool(os.getenv("FEATURE_DASHBOARD_ALERTS"), True)
        self.trends = _as_bool(os.getenv("FEATURE_DASHBOARD_TRENDS"), True)
        self.drilldown = _as_bool(os.getenv("FEATURE_DASHBOARD_DRILLDOWN"), True)
        self.export = _as_bool(os.getenv("FEATURE_DASHBOARD_EXPORT"), True)
        self.scorecards = _as_bool(os.getenv("FEATURE_DASHBOARD_SCORECARDS"), True)


features = DashboardFeatures()

