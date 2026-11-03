"""HDHR discover.json / device.xml identity and tuner count."""
import json
import re
import xml.etree.ElementTree as ET
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.channels.models import Stream
from apps.hdhr.models import HDHRDevice
from apps.m3u.models import M3UAccount
from apps.m3u.utils import calculate_tuner_count
from core.models import CoreSettings, HDHR_IDENTITY_KEY, STREAM_SETTINGS_KEY

DEVICE_ID_RE = re.compile(r"^dispatcharr-[a-z0-9]{8}$")


class HDHRTestBase(TestCase):
    def setUp(self):
        self._network_patch = patch(
            "apps.hdhr.api_views.network_access_allowed", return_value=True
        )
        self._network_patch.start()
        self.addCleanup(self._network_patch.stop)
        # Settings groups are cached in Redis, which is not rolled back with
        # the test transaction.
        for key in (STREAM_SETTINGS_KEY, HDHR_IDENTITY_KEY):
            CoreSettings.invalidate_group_cache(key)
            self.addCleanup(CoreSettings.invalidate_group_cache, key)

        M3UAccount.objects.update(is_active=False)
        Stream.objects.filter(is_custom=True).delete()
        HDHRDevice.objects.all().delete()
        CoreSettings.objects.filter(key=HDHR_IDENTITY_KEY).delete()
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

    def _device_xml(self):
        response = self.client.get("/hdhr/device.xml")
        self.assertEqual(response.status_code, 200)
        return ET.fromstring(response.content)


class HDHRDeviceIdTests(HDHRTestBase):
    def test_default_device_id_has_random_instance_part(self):
        device_id = self._discover()["DeviceID"]
        self.assertRegex(device_id, DEVICE_ID_RE)
        self.assertNotEqual(device_id, "12345678")

    def test_device_id_is_persisted_and_stable(self):
        first = self._discover()["DeviceID"]
        CoreSettings.invalidate_group_cache(HDHR_IDENTITY_KEY)
        self.assertEqual(self._discover()["DeviceID"], first)
        stored = CoreSettings.objects.get(key=HDHR_IDENTITY_KEY).value
        self.assertEqual(f"dispatcharr-{stored['instance_id']}", first)

    def test_regenerating_changes_device_id(self):
        first = self._discover()["DeviceID"]
        CoreSettings.regenerate_hdhr_instance_id()
        second = self._discover()["DeviceID"]
        self.assertRegex(second, DEVICE_ID_RE)
        self.assertNotEqual(first, second)

    def test_invalid_stored_instance_id_is_replaced(self):
        CoreSettings._update_group(
            HDHR_IDENTITY_KEY, "HDHR Identity", {"instance_id": "12345678"[:3]}
        )
        self.assertRegex(self._discover()["DeviceID"], DEVICE_ID_RE)

    def test_device_xml_matches_discover_without_device(self):
        root = self._device_xml()
        data = self._discover()
        self.assertEqual(root.findtext("DeviceID"), data["DeviceID"])
        self.assertEqual(root.findtext("FriendlyName"), data["FriendlyName"])

    def test_profile_urls_extend_the_instance_id(self):
        base = self._discover()["DeviceID"]
        self.assertEqual(
            self._discover("/hdhr/Sports/discover.json")["DeviceID"], f"{base}-Sports"
        )
        self.assertEqual(
            self._discover("/hdhr/output_profile/3/discover.json")["DeviceID"],
            f"{base}-3",
        )
        self.assertEqual(
            self._discover("/hdhr/Sports/output_profile/3/discover.json")["DeviceID"],
            f"{base}-Sports-3",
        )

    def test_existing_device_id_is_kept_everywhere(self):
        HDHRDevice.objects.create(friendly_name="Living Room", device_id="12345678")
        self.assertEqual(self._discover()["DeviceID"], "12345678")
        self.assertEqual(
            self._discover("/hdhr/Sports/tuners/5/discover.json")["DeviceID"],
            "12345678",
        )
        self.assertEqual(self._device_xml().findtext("DeviceID"), "12345678")

    def test_device_xml_escapes_values(self):
        HDHRDevice.objects.create(friendly_name="A & B <tv>", device_id="dev-1")
        self.assertEqual(self._device_xml().findtext("FriendlyName"), "A & B <tv>")


class HDHRTunerCountTests(HDHRTestBase):
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


class HDHRTunerUrlTests(HDHRTestBase):
    def test_url_tuner_limit_sets_count_and_base_url(self):
        data = self._discover("/hdhr/tuners/5/discover.json")
        self.assertEqual(data["TunerCount"], 5)
        self.assertTrue(data["BaseURL"].endswith("/hdhr/tuners/5"))
        self.assertTrue(data["LineupURL"].endswith("/hdhr/tuners/5/lineup.json"))

    def test_url_tuner_limit_does_not_change_device_id(self):
        base = self._discover()["DeviceID"]
        self.assertEqual(
            self._discover("/hdhr/tuners/5/discover.json")["DeviceID"], base
        )
        data = self._discover("/hdhr/Sports/output_profile/3/tuners/7/discover.json")
        self.assertEqual(data["DeviceID"], f"{base}-Sports-3")
        self.assertEqual(data["TunerCount"], 7)
        self.assertTrue(
            data["BaseURL"].endswith("/hdhr/Sports/output_profile/3/tuners/7")
        )

    def test_url_tuner_limit_overrides_global_maximum(self):
        self._set_stream_settings(hdhr_max_tuner_count=20)
        self.assertEqual(self._discover("/hdhr/tuners/50/discover.json")["TunerCount"], 50)
        self.assertEqual(self._discover("/hdhr/tuners/2/discover.json")["TunerCount"], 2)

    def test_url_tuner_limit_is_capped_by_automatic_count(self):
        self._set_stream_settings(hdhr_count_custom_streams=False)
        self.assertEqual(self._discover("/hdhr/tuners/10/discover.json")["TunerCount"], 4)

    def test_zero_tuner_limit_falls_back_to_settings(self):
        self._set_stream_settings(hdhr_max_tuner_count=20)
        data = self._discover("/hdhr/tuners/0/discover.json")
        self.assertEqual(data["TunerCount"], 20)
        self.assertTrue(data["BaseURL"].endswith("/hdhr"))

    def test_lineup_endpoints_accept_tuner_segment(self):
        for path in (
            "/hdhr/tuners/5/lineup.json",
            "/hdhr/tuners/5/lineup_status.json",
            "/hdhr/output_profile/3/tuners/5/lineup_status.json",
            "/hdhr/Sports/tuners/5/lineup_status.json",
        ):
            self.assertEqual(self.client.get(path).status_code, 200, path)


class HDHRIdentityAPITests(HDHRTestBase):
    url = "/api/hdhr/identity/"

    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="hdhr-admin", password="pw", user_level=10
        )
        self.standard = User.objects.create_user(
            username="hdhr-user", password="pw", user_level=1
        )
        self.api = APIClient()

    def test_requires_admin(self):
        self.assertIn(self.api.get(self.url).status_code, (401, 403))
        self.api.force_authenticate(self.standard)
        self.assertEqual(self.api.get(self.url).status_code, 403)
        self.assertEqual(self.api.post(self.url).status_code, 403)

    def test_get_and_regenerate(self):
        self.api.force_authenticate(self.admin)
        first = self.api.get(self.url).json()
        self.assertRegex(first["device_id"], DEVICE_ID_RE)
        self.assertEqual(first["device_id"], f"dispatcharr-{first['instance_id']}")
        self.assertFalse(first["device_override"])
        self.assertEqual(self._discover()["DeviceID"], first["device_id"])

        second = self.api.post(self.url).json()
        self.assertNotEqual(second["instance_id"], first["instance_id"])
        self.assertEqual(self._discover()["DeviceID"], second["device_id"])

    def test_reports_device_override(self):
        HDHRDevice.objects.create(friendly_name="Living Room", device_id="fixed-id")
        self.api.force_authenticate(self.admin)
        data = self.api.get(self.url).json()
        self.assertEqual(data["device_id"], "fixed-id")
        self.assertTrue(data["device_override"])
