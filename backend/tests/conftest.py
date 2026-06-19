import os
from hypothesis import settings, HealthCheck

# Register the profile for PBT
settings.register_profile(
    "rag_pbt",
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)

# Load profile
settings.load_profile("rag_pbt")
