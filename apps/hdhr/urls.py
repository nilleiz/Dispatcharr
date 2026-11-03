from django.urls import path
from rest_framework.routers import DefaultRouter
from .api_views import (
    HDHRDeviceViewSet,
    DiscoverAPIView,
    LineupAPIView,
    LineupStatusAPIView,
    HDHRDeviceXMLAPIView,
)

app_name = 'hdhr'

router = DefaultRouter()
router.register(r'devices', HDHRDeviceViewSet, basename='hdhr-device')

# HDHR endpoints exist under every combination of the optional path prefixes
#   /hdhr[/<channel_profile>][/output_profile/<id>][/tuners/<n>]/
# The tuner segment is last so a base URL (as entered in Plex) can carry it and
# Plex appends discover.json / lineup.json behind it.
_HDHR_PREFIXES = [
    ("<str:channel_profile>/output_profile/<int:output_profile_id>/", "with_profile_and_output"),
    ("output_profile/<int:output_profile_id>/", "with_output"),
    ("<str:channel_profile>/", "with_profile"),
    ("", "no_profile"),
]
_HDHR_ENDPOINTS = [
    ("discover.json", DiscoverAPIView, "discover"),
    ("lineup.json", LineupAPIView, "lineup"),
    ("lineup_status.json", LineupStatusAPIView, "lineup_status"),
]

urlpatterns = []

# Tuner-limited variants first: "tuners/<n>/discover.json" must not be read as
# channel profile "tuners".
for _prefix, _suffix in _HDHR_PREFIXES:
    for _file, _view, _name in _HDHR_ENDPOINTS:
        urlpatterns.append(
            path(f"{_prefix}tuners/<int:tuner_limit>/{_file}", _view.as_view(), name=f"{_name}_{_suffix}_with_tuners")
        )
for _prefix, _suffix in _HDHR_PREFIXES:
    for _file, _view, _name in _HDHR_ENDPOINTS:
        urlpatterns.append(path(f"{_prefix}{_file}", _view.as_view(), name=f"{_name}_{_suffix}"))

urlpatterns.append(path('device.xml', HDHRDeviceXMLAPIView.as_view(), name='device_xml'))

urlpatterns += router.urls
