"""HDHR discover.json / device.xml identity and tuner count."""
import json
import xml.etree.ElementTree as ET
from unittest.mock import patch

from django.test import TestCase

from apps.channels.models import Stream
from apps.hdhr.api_views import DEFAULT_HDHR_DEVICE_ID
from apps.hdhr.models import HDHRDevice
from apps.m3u.models import M3UAccount
from apps.m3u.utils import calculate_tuner_count
from core.models import CoreSettings, STREAM_SETTINGS_KEY


class HDHRDiscoveryTests(TestCase):
    def setUp(self):
        self._network_patch = patch(
            "apps.hdhr.api_views.network_access_allowed", return_value=True
        )
        self._network_patch.start()
        self.addCleanup(self._network_patch.stop)
        # Settings groups are cached in Redis, which is not rolled back with
        # the test transaction.
        CoreSettings.invalidate_group_cache(STREAM_SETTINGS_KEY)
        self.addCleanup(CoreSettings.invalidate_group_cache, STREAM_SETTINGS_KEY)

        M3UAccount.objects.update(is_active=False)
        Stream.objects.filter(is_custom=True).delete()
        HDHRDevice.objects.all().delete()
        M3UAccount.objects.create(
            name="HDHR Account",
            server_url="http://example.com/playlist.m3u",
            max_streams=4,
        )
        for i in range(299):
            Stream.objects.create(
                name=f"Could Not Dispatch {i}",
                url="http://127.0.0.1:9721/slate.ts",
                is_custom=True,
            )

    def _set_stream_settings(self, **values):
        CoreSettings._update_group(STREAM_SETTINGS_KEY, "Stream Settings", values)

    def _discover(self, path="/hdhr/discover.json"):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content)

    def _device_xml_id(self):
        response = self.client.get("/hdhr/device.xml")
        self.assertEqual(response.status_code, 200)
        return ET.fromstring(response.content).findtext("DeviceID")

    # --- DeviceID -----------------------------------------------------------

    def test_default_device_id_is_not_numeric(self):
        self.assertEqual(DEFAULT_HDHR_DEVICE_ID, "dispatcharr")
        self.assertEqual(self._discover()["DeviceID"], "dispatcharr")

    def test_device_xml_matches_discover_without_device(self):
        self.assertEqual(self._device_xml_id(), self._discover()["DeviceID"])

    def test_existing_device_id_is_kept_in_discover_and_xml(self):
        HDHRDevice.objects.create(friendly_name="Living Room", device_id="12345678")
        self.assertEqual(self._discover()["DeviceID"], "12345678")
        self.assertEqual(self._device_xml_id(), "12345678")

    def test_profile_device_id_unchanged(self):
        data = self._discover("/hdhr/Sports/discover.json")
        self.assertEqual(data["DeviceID"], "dispatcharr-hdhr-Sports")

    def test_device_xml_escapes_values(self):
        HDHRDevice.objects.create(friendly_name="A & B <tv>", device_id="dev-1")
        response = self.client.get("/hdhr/device.xml")
        root = ET.fromstring(response.content)
        self.assertEqual(root.findtext("FriendlyName"), "A & B <tv>")

    # --- TunerCount ---------------------------------------------------------

    def test_tuner_count_defaults_to_previous_behaviour(self):
        self.assertEqual(self._discover()["TunerCount"], 4 + 299)

    def test_max_tuner_count_limits_discover(self):
        self._set_stream_settings(hdhr_max_tuner_count=20)
        self.assertEqual(self._discover()["TunerCount"], 20)
        self.assertEqual(
            self._discover("/hdhr/Sports/discover.json")["TunerCount"], 20
        )

    def test_empty_max_tuner_count_is_automatic(self):
        self._set_stream_settings(hdhr_max_tuner_count="")
        self.assertEqual(self._discover()["TunerCount"], 303)

    def test_custom_streams_can_be_excluded(self):
        self._set_stream_settings(hdhr_count_custom_streams=False)
        self.assertEqual(self._discover()["TunerCount"], 4)

    def test_identical_custom_urls_counted_once(self):
        self._set_stream_settings(hdhr_dedupe_custom_stream_urls=True)
        self.assertEqual(self._discover()["TunerCount"], 5)

    def test_hdhr_settings_do_not_change_xtream_count(self):
        self._set_stream_settings(
            hdhr_max_tuner_count=20, hdhr_count_custom_streams=False
        )
        # Xtream Codes calls calculate_tuner_count() without the HDHR options.
        self.assertEqual(
            calculate_tuner_count(minimum=1, unlimited_default=50), 303
        )
