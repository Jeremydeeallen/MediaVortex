# directive: path-property-and-fuzz | # see path.C1
from hypothesis import HealthCheck, settings


settings.register_profile(
    "million",
    max_examples=1_000_000,
    deadline=None,
    suppress_health_check=[
        HealthCheck.too_slow,
        HealthCheck.data_too_large,
        HealthCheck.filter_too_much,
    ],
)
settings.register_profile("dev", max_examples=200, deadline=None)


# directive: path-performance-budget | # see path.C1
def pytest_configure(config):
    """Register the 'perf' marker so @pytest.mark.perf does not emit unknown-mark warnings."""
    config.addinivalue_line("markers", "perf: opt-in performance benchmark; run with -m perf")
