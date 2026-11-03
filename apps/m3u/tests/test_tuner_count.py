"""calculate_tuner_count(): profile sums, custom streams, and optional limits."""
from django.test import TestCase

from apps.channels.models import Stream
from apps.m3u.models import M3UAccount, M3UAccountProfile
from apps.m3u.utils import calculate_tuner_count

SLATE_URL = "http://127.0.0.1:9721/slate.ts"


class CalculateTunerCountTests(TestCase):
    def setUp(self):
        # Isolate from accounts/streams created by data migrations.
        M3UAccount.objects.update(is_active=False)
        Stream.objects.filter(is_custom=True).delete()
        self.account = M3UAccount.objects.create(
            name="Tuner Account",
            server_url="http://example.com/playlist.m3u",
            max_streams=4,
        )
        self.profile = M3UAccountProfile.objects.get(
            m3u_account=self.account, is_default=True
        )

    def _add_custom_streams(self, count, url=SLATE_URL):
        for i in range(count):
            Stream.objects.create(
                name=f"Could Not Dispatch {i}", url=url, is_custom=True
            )

    def test_limited_profiles_without_custom_streams(self):
        self.assertEqual(calculate_tuner_count(), 4)

    def test_default_behaviour_counts_every_custom_stream(self):
        self._add_custom_streams(5)
        self.assertEqual(calculate_tuner_count(), 9)

    def test_unlimited_profile_uses_unlimited_default_plus_custom(self):
        self.profile.max_streams = 0
        self.profile.save()
        self._add_custom_streams(2)
        self.assertEqual(calculate_tuner_count(unlimited_default=10), 12)
        self.assertEqual(calculate_tuner_count(unlimited_default=50), 52)

    def test_custom_streams_can_be_excluded(self):
        self._add_custom_streams(5)
        self.assertEqual(calculate_tuner_count(count_custom_streams=False), 4)

    def test_identical_custom_urls_counted_once_when_deduped(self):
        self._add_custom_streams(30)
        Stream.objects.create(
            name="Other", url="http://example.com/other.ts", is_custom=True
        )
        Stream.objects.create(name="No URL A", url=None, is_custom=True)
        Stream.objects.create(name="No URL B", url="", is_custom=True)
        # 4 profile tuners + 2 distinct URLs + 2 streams without URL
        self.assertEqual(calculate_tuner_count(dedupe_custom_urls=True), 8)
        # Without de-duplication every custom stream counts.
        self.assertEqual(calculate_tuner_count(), 4 + 33)

    def test_maximum_caps_the_result(self):
        self._add_custom_streams(299)
        self.assertEqual(calculate_tuner_count(maximum=20), 20)

    def test_maximum_above_count_has_no_effect(self):
        self._add_custom_streams(2)
        self.assertEqual(calculate_tuner_count(maximum=20), 6)

    def test_maximum_none_or_invalid_means_no_limit(self):
        self._add_custom_streams(2)
        for value in (None, 0, -5, True):
            self.assertEqual(calculate_tuner_count(maximum=value), 6)

    def test_minimum_still_applies(self):
        self.account.is_active = False
        self.account.save()
        self.assertEqual(calculate_tuner_count(minimum=1), 1)
        self.assertEqual(calculate_tuner_count(minimum=3, maximum=2), 2)
