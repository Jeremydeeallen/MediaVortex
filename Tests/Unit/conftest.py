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
