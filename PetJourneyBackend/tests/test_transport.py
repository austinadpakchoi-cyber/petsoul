from base import *


class TransportApiTests(PetJourneyApiTestBase):

    def test_web_search_transport_schedule_parses_reference_only_candidate(self) -> None:
        class FakeWebSearchTransportScheduleProvider(OpenAIWebSearchTransportScheduleProvider):
            captured_payload: dict[str, object] | None = None

            def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
                self.captured_payload = payload
                return {
                    "output_text": json.dumps(
                        {
                            "found": True,
                            "mode": "flight",
                            "carrier": "Qatar Airways",
                            "service_number": "QR881",
                            "origin_name": "Xiamen Gaoqi International Airport",
                            "destination_name": "Doha Hamad International Airport",
                            "scheduled_departure": "18:40 CST",
                            "scheduled_arrival": "22:30 +03",
                            "terminal_or_platform": "T3",
                            "source_urls": ["https://example.com/flight/qr881"],
                            "confidence": "medium",
                            "notes": "Reference schedule only; no booking data.",
                        }
                    )
                }

        settings = Settings(
            openai_api_key="test-key",
            transport_schedule_provider="openai",
            transport_web_search_enabled=True,
        )
        provider = FakeWebSearchTransportScheduleProvider(settings)
        pet = self.sample_pet()
        request = TransportScheduleRequest(
            pet=pet,
            mode=TravelMode.flight,
            origin=self.place("xiamen", "厦门", "厦门", 24.544, 118.127, "city"),
            destination=self.place("doha", "多哈哈马德国际机场", "多哈", 25.2609, 51.6138, "airport"),
            depart_after=datetime(2026, 6, 15, 0, 0, tzinfo=timezone.utc),
            now=datetime(2026, 6, 14, 8, 0, tzinfo=timezone.utc),
            context="World Cup travel reference only.",
        )

        candidate = provider.best_candidate(request)

        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.service_number, "QR881")
        self.assertEqual(candidate.mode, TravelMode.flight)
        self.assertAlmostEqual(
            (candidate.scheduled_arrival - candidate.scheduled_departure).total_seconds() / 3600,
            8.83,
            places=1,
        )
        self.assertEqual(candidate.source_urls, ("https://example.com/flight/qr881",))
        self.assertEqual(candidate.reality_level, "web_reference_schedule")
        self.assertTrue(candidate.is_simulated)
        self.assertIsNotNone(provider.captured_payload)
        assert provider.captured_payload is not None
        self.assertEqual(provider.captured_payload["tools"], [{"type": "web_search_preview"}])
        prompt = provider.captured_payload["input"][0]["content"]
        self.assertIn("Do not collect", prompt)
        self.assertIn("prices", prompt)
        self.assertIn("seat availability", prompt)
        self.assertIn("booking", prompt)
        self.assertIn("ticketing websites", prompt)

    def test_web_search_transport_schedule_parses_connecting_itinerary(self) -> None:
        class FakeConnectingWebSearchProvider(OpenAIWebSearchTransportScheduleProvider):
            def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
                return {
                    "output_text": json.dumps(
                        {
                            "found": True,
                            "mode": "flight",
                            "itinerary_summary": "厦门经香港中转前往多哈。",
                            "confidence": "medium",
                            "notes": "公开时刻表参考，不含票价或余票。",
                            "segments": [
                                {
                                    "mode": "flight",
                                    "carrier": "Cathay Pacific",
                                    "service_number": "CX973",
                                    "origin_name": "厦门高崎国际机场",
                                    "origin_city": "厦门",
                                    "destination_name": "香港国际机场",
                                    "destination_city": "香港",
                                    "scheduled_departure": "12:20",
                                    "scheduled_arrival": "13:55",
                                    "terminal_or_platform": None,
                                    "source_urls": ["https://example.com/cx973"],
                                    "confidence": "medium",
                                    "notes": "第一段中转航班。",
                                },
                                {
                                    "mode": "flight",
                                    "carrier": "Qatar Airways",
                                    "service_number": "QR817",
                                    "origin_name": "香港国际机场",
                                    "origin_city": "香港",
                                    "destination_name": "多哈哈马德国际机场",
                                    "destination_city": "多哈",
                                    "scheduled_departure": "19:10 HKT",
                                    "scheduled_arrival": "23:05 +03",
                                    "terminal_or_platform": None,
                                    "source_urls": ["https://example.com/qr817"],
                                    "confidence": "medium",
                                    "notes": "第二段中转航班。",
                                },
                            ],
                        }
                    )
                }

        settings = Settings(
            openai_api_key="test-key",
            transport_schedule_provider="openai",
            transport_web_search_enabled=True,
        )
        provider = FakeConnectingWebSearchProvider(settings)
        pet = self.sample_pet()
        request = TransportScheduleRequest(
            pet=pet,
            mode=TravelMode.flight,
            origin=self.place("xiamen", "厦门", "厦门", 24.544, 118.127, "city"),
            destination=self.place("doha", "多哈哈马德国际机场", "多哈", 25.2609, 51.6138, "airport"),
            depart_after=datetime(2026, 6, 15, 0, 0, tzinfo=timezone.utc),
            now=datetime(2026, 6, 14, 8, 0, tzinfo=timezone.utc),
            context="World Cup connecting flight reference only.",
        )

        itinerary = provider.best_itinerary(request)

        self.assertEqual([item.service_number for item in itinerary], ["CX973", "QR817"])
        self.assertEqual(itinerary[0].destination_name, "香港国际机场")
        self.assertEqual(itinerary[1].origin_name, "香港国际机场")
        self.assertGreater(itinerary[1].scheduled_departure, itinerary[0].scheduled_arrival)
        self.assertTrue(all(item.source_urls for item in itinerary))

    def test_transport_reality_uses_reference_schedule_when_available(self) -> None:
        class FakeScheduleProvider:
            provider_name = "fake-web-reference-schedule-provider"

            def best_candidate(self, search: TransportScheduleRequest) -> TransportScheduleCandidate | None:
                return TransportScheduleCandidate(
                    mode=TravelMode.flight,
                    carrier="Qatar Airways",
                    service_number="QR881",
                    origin_name="Xiamen Gaoqi International Airport",
                    destination_name="Doha Hamad International Airport",
                    scheduled_departure=datetime(2026, 6, 15, 0, 5, tzinfo=timezone.utc),
                    scheduled_arrival=datetime(2026, 6, 15, 9, 15, tzinfo=timezone.utc),
                    terminal_or_platform="T3",
                    source_urls=("https://example.com/flight/qr881",),
                    confidence="high",
                    search_query="xiamen doha flight schedule number departure arrival",
                    notes="公开网页只作为时间线参考。",
                )

        pet = self.sample_pet(created_at=datetime(2026, 6, 14, 8, 0, tzinfo=timezone.utc))
        provider = MockTransportRealityProvider(schedule_provider=FakeScheduleProvider())
        origin = self.place("xiamen", "厦门街角", "厦门", 24.4798, 118.0894, "street")
        airport = self.place("doha", "多哈哈马德国际机场", "多哈", 25.2609, 51.6138, "airport")
        cafe = self.place("cafe", "赛场附近咖啡店", "多哈", 25.265, 51.505, "cafe")
        stadium = self.place("stadium", "世界杯赛场", "多哈", 25.263, 51.485, "stadium")

        legs = provider.worldcup_legs(
            pet=pet,
            origin=origin,
            airport=airport,
            cafe=cafe,
            stadium=stadium,
            now=datetime(2026, 6, 14, 8, 0, tzinfo=timezone.utc),
        )

        flight_leg = next(item for item in legs if item.mode == TravelMode.flight)
        self.assertEqual(flight_leg.service_number, "QR881")
        self.assertEqual(flight_leg.carrier, "Qatar Airways")
        self.assertEqual(flight_leg.provider, "fake-web-reference-schedule-provider")
        self.assertEqual(flight_leg.reality_level, "web_reference_schedule")
        self.assertEqual(flight_leg.source_urls, ["https://example.com/flight/qr881"])
        self.assertEqual(flight_leg.confidence, "high")
        self.assertIn("QR881", flight_leg.timeline_note or "")
        drive_leg = next(item for item in legs if item.mode == TravelMode.drive)
        self.assertGreater(drive_leg.scheduled_departure, flight_leg.scheduled_arrival)

    def test_transport_reality_expands_connecting_schedule(self) -> None:
        class FakeConnectingScheduleProvider:
            provider_name = "fake-connecting-schedule-provider"

            def best_itinerary(self, search: TransportScheduleRequest) -> list[TransportScheduleCandidate]:
                return [
                    TransportScheduleCandidate(
                        mode=TravelMode.flight,
                        carrier="Cathay Pacific",
                        service_number="CX973",
                        origin_name="厦门高崎国际机场",
                        destination_name="香港国际机场",
                        scheduled_departure=datetime(2026, 6, 15, 4, 20, tzinfo=timezone.utc),
                        scheduled_arrival=datetime(2026, 6, 15, 5, 55, tzinfo=timezone.utc),
                        source_urls=("https://example.com/cx973",),
                        confidence="medium",
                        notes="中转第一段。",
                    ),
                    TransportScheduleCandidate(
                        mode=TravelMode.flight,
                        carrier="Qatar Airways",
                        service_number="QR817",
                        origin_name="香港国际机场",
                        destination_name="多哈哈马德国际机场",
                        scheduled_departure=datetime(2026, 6, 15, 11, 10, tzinfo=timezone.utc),
                        scheduled_arrival=datetime(2026, 6, 15, 20, 5, tzinfo=timezone.utc),
                        source_urls=("https://example.com/qr817",),
                        confidence="medium",
                        notes="中转第二段。",
                    ),
                ]

            def best_candidate(self, search: TransportScheduleRequest) -> TransportScheduleCandidate | None:
                itinerary = self.best_itinerary(search)
                return itinerary[0] if itinerary else None

        pet = self.sample_pet(created_at=datetime(2026, 6, 14, 8, 0, tzinfo=timezone.utc))
        provider = MockTransportRealityProvider(schedule_provider=FakeConnectingScheduleProvider())
        origin = self.place("xiamen", "厦门街角", "厦门", 24.4798, 118.0894, "street")
        airport = self.place("doha", "多哈哈马德国际机场", "多哈", 25.2609, 51.6138, "airport")
        cafe = self.place("cafe", "赛场附近咖啡店", "多哈", 25.265, 51.505, "cafe")
        stadium = self.place("stadium", "世界杯赛场", "多哈", 25.263, 51.485, "stadium")

        legs = provider.worldcup_legs(
            pet=pet,
            origin=origin,
            airport=airport,
            cafe=cafe,
            stadium=stadium,
            now=datetime(2026, 6, 14, 8, 0, tzinfo=timezone.utc),
        )

        flight_legs = [item for item in legs if item.mode == TravelMode.flight]
        self.assertEqual([item.service_number for item in flight_legs], ["CX973", "QR817"])
        self.assertIn("中转第 1/2 段", flight_legs[0].timeline_note or "")
        self.assertIn("中转第 2/2 段", flight_legs[1].timeline_note or "")
        drive_leg = next(item for item in legs if item.mode == TravelMode.drive)
        self.assertGreater(drive_leg.scheduled_departure, flight_legs[-1].scheduled_arrival)

