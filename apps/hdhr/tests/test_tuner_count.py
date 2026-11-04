"""HDHR TunerCount: global maximum, custom stream counting, per-URL tuner count."""
import json
from unittest.mock import patch

from django.test import TestCase

from apps.channels.models import Stream
from apps.hdhr.models import HDHRDevice
from apps.m3u.models import M3UAccount
from apps.m3u.utils import calculate_tuner_count
from core.models import CoreSettings, STREAM_SETTINGS_KEY


class HDHRTunerTestBase(TestCase):
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
        # e.g. one fallback custom stream per channel, all with the same URL
        for i in range(299):
            Stream.objects.create(
                name=f"Fallback {i}",
                url="http://127.0.0.1:9721/slate.ts",
                is_custom=True,
            )

    def _set_stream_settings(self, **values):
        CoreSettings._update_group(STREAM_SETTINGS_KEY, "Stream Settings", values)

    def _discover(self, path="/hdhr/discover.json"):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content)


class HDHRTunerCountTests(HDHRTunerTestBase):
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


class HDHRTunerUrlTests(HDHRTunerTestBase):
    def test_url_tuner_count_sets_count_and_base_url(self):
        data = self._discover("/hdhr/tuners/5/discover.json")
        self.assertEqual(data["TunerCount"], 5)
        self.assertTrue(data["BaseURL"].endswith("/hdhr/tuners/5"))
        self.assertTrue(data["LineupURL"].endswith("/hdhr/tuners/5/lineup.json"))

    def test_url_tuner_count_does_not_change_device_id(self):
        self.assertEqual(
            self._discover("/hdhr/tuners/5/discover.json")["DeviceID"],
            self._discover()["DeviceID"],
        )
        with_tuners = self._discover(
            "/hdhr/Sports/output_profile/3/tuners/7/discover.json"
        )
        without = self._discover("/hdhr/Sports/output_profile/3/discover.json")
        self.assertEqual(with_tuners["DeviceID"], without["DeviceID"])
        self.assertEqual(with_tuners["TunerCount"], 7)
        self.assertTrue(
            with_tuners["BaseURL"].endswith("/hdhr/Sports/output_profile/3/tuners/7")
        )

    def test_url_tuner_count_cannot_exceed_global_maximum(self):
        self._set_stream_settings(hdhr_max_tuner_count=20)
        self.assertEqual(self._discover("/hdhr/tuners/50/discover.json")["TunerCount"], 20)
        self.assertEqual(self._discover("/hdhr/tuners/2/discover.json")["TunerCount"], 2)

    def test_url_tuner_count_is_explicit_below_global_maximum(self):
        # Automatic count is 4 here; an explicit count up to the global
        # maximum is reported as is.
        self._set_stream_settings(
            hdhr_max_tuner_count=20, hdhr_count_custom_streams=False
        )
        self.assertEqual(self._discover("/hdhr/tuners/10/discover.json")["TunerCount"], 10)
        self.assertEqual(self._discover()["TunerCount"], 4)

    def test_url_tuner_count_capped_by_automatic_count_without_maximum(self):
        self._set_stream_settings(hdhr_count_custom_streams=False)
        self.assertEqual(self._discover("/hdhr/tuners/10/discover.json")["TunerCount"], 4)

    def test_zero_tuner_count_falls_back_to_settings(self):
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
