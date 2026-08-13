from base import *


class MapProviderTests(PetJourneyApiTestBase):

    def test_amap_provider_is_selected_when_configured(self) -> None:
        settings = Settings(
            database_path=Path(self.tempdir.name) / "amap.sqlite3",
            upload_dir=Path(self.tempdir.name) / "amap-uploads",
            public_base_url="http://testserver",
            map_provider="amap",
            amap_api_key="test-amap-key",
        )
        client = TestClient(create_app(settings))
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["map_provider_mode"], "amap")
        self.assertEqual(payload["map_provider"], "amap-web-map-provider")
        self.assertEqual(payload["world_simulation_engine"], "world-simulation-engine")
        self.assertEqual(payload["weather_provider"], "amap-weather-provider")
        self.assertEqual(payload["amap_web_service"], "amap-web-service-client")
        self.assertEqual(payload["street_rank_engine"], "petsoul-street-rank-engine")

    def test_google_provider_is_selected_when_configured(self) -> None:
        settings = Settings(
            database_path=Path(self.tempdir.name) / "google.sqlite3",
            upload_dir=Path(self.tempdir.name) / "google-uploads",
            public_base_url="http://testserver",
            map_provider="google",
            google_maps_api_key="test-google-key",
        )
        client = TestClient(create_app(settings))
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["map_provider"], "google-maps-map-provider")
        self.assertEqual(payload["google_maps_service"], "google-maps-service-client")
        self.assertEqual(payload["weather_provider"], "google-weather-provider")

        config = client.get("/api/v1/google/config")
        self.assertEqual(config.status_code, 200)
        self.assertTrue(config.json()["routes_api"])

    def test_google_maps_service_parses_places_routes_and_regeo(self) -> None:
        class FakeGoogleMapsServiceClient(GoogleMapsServiceClient):
            def _post_json(self, url: str, payload: dict[str, object], headers: dict[str, str]) -> dict[str, object]:
                if "places:searchNearby" in url:
                    return {
                        "places": [
                            {
                                "id": "places/test-cafe",
                                "displayName": {"text": "星巴克京都二年坂茶屋店"},
                                "formattedAddress": "Kyoto",
                                "location": {"latitude": 35.0001, "longitude": 135.7801},
                                "rating": 4.4,
                                "userRatingCount": 1200,
                                "primaryType": "cafe",
                                "types": ["cafe", "food", "point_of_interest"],
                                "photos": [{"name": "places/test/photos/1"}],
                            }
                        ]
                    }
                if "directions/v2:computeRoutes" in url:
                    return {
                        "routes": [
                            {
                                "distanceMeters": 872,
                                "duration": "740s",
                                "polyline": {"encodedPolyline": "encoded-polyline"},
                            }
                        ]
                    }
                return {}

            def _get_json(self, url: str) -> dict[str, object]:
                return {
                    "status": "OK",
                    "results": [
                        {
                            "formatted_address": "488 Kamihonnōjimaechō, Nakagyo Ward, Kyoto, 604-8571日本",
                            "address_components": [
                                {"long_name": "Kyoto", "types": ["locality", "political"]},
                                {"long_name": "Kyoto Prefecture", "types": ["administrative_area_level_1", "political"]},
                                {"long_name": "Kamihonnōjimaechō", "types": ["route"]},
                            ],
                        }
                    ],
                }

        client = FakeGoogleMapsServiceClient(Settings(google_maps_api_key="test-google-key"))
        places = client.places_nearby(city_name="京都", lat=35.0116, lng=135.7681, theme="coffee", limit=3)
        self.assertEqual(len(places), 1)
        self.assertEqual(places[0].category, "cafe")
        self.assertEqual(places[0].source, "google-maps-service-client")
        self.assertEqual(places[0].rating, 4.4)

        route = client.route_between(
            mode=TravelMode.walk,
            origin_lng=135.7681,
            origin_lat=35.0116,
            destination_lng=135.7717,
            destination_lat=35.0159,
        )
        self.assertIsNotNone(route)
        self.assertEqual(route.distance_meters, 872)
        self.assertEqual(route.duration_seconds, 740)
        self.assertEqual(route.polyline, "encoded-polyline")

        regeo = client.reverse_geocode(lat=35.0116, lng=135.7681)
        self.assertIsNotNone(regeo)
        self.assertEqual(regeo.city, "Kyoto")
        self.assertEqual(regeo.source, "google-maps-service-client")

    def test_amap_web_service_parses_route_tips_and_regeo(self) -> None:
        class FakeAMapWebServiceClient(AMapWebServiceClient):
            def _get_json(self, path: str, params: dict[str, str]) -> dict[str, object]:
                if path == "/v3/direction/walking":
                    return {
                        "status": "1",
                        "route": {
                            "paths": [
                                {
                                    "distance": "1234",
                                    "duration": "900",
                                    "steps": [
                                        {"polyline": "118.1,24.4;118.2,24.5"},
                                        {"polyline": "118.2,24.5;118.3,24.6"},
                                    ],
                                }
                            ]
                        },
                    }
                if path == "/v3/assistant/inputtips":
                    return {
                        "status": "1",
                        "tips": [
                            {
                                "id": "B0TEST",
                                "name": "默迹咖啡馆",
                                "district": "福建省厦门市思明区",
                                "adcode": "350203",
                                "address": "测试路",
                                "typecode": "050500",
                                "location": "118.082,24.474",
                            }
                        ],
                    }
                if path == "/v3/geocode/regeo":
                    return {
                        "status": "1",
                        "regeocode": {
                            "formatted_address": "福建省厦门市思明区测试路",
                            "addressComponent": {
                                "province": "福建省",
                                "city": "厦门市",
                                "district": "思明区",
                                "township": "测试街道",
                                "adcode": "350203",
                                "streetNumber": {"street": "测试路", "number": "1号"},
                            },
                        },
                    }
                return {"status": "1"}

        client = FakeAMapWebServiceClient(Settings(amap_api_key="test-amap-key"))

        route = client.route_between(
            mode=TravelMode.walk,
            origin_lng=118.1,
            origin_lat=24.4,
            destination_lng=118.3,
            destination_lat=24.6,
        )
        self.assertIsNotNone(route)
        self.assertEqual(route.distance_meters, 1234)
        self.assertEqual(route.duration_seconds, 900)
        self.assertEqual(route.polyline, "118.1,24.4;118.2,24.5;118.3,24.6")

        tips = client.input_tips(keywords="咖啡", city="厦门")
        self.assertEqual(tips[0].name, "默迹咖啡馆")
        self.assertEqual(tips[0].lat, 24.474)
        self.assertEqual(tips[0].lng, 118.082)

        regeo = client.reverse_geocode(lat=24.474, lng=118.082)
        self.assertIsNotNone(regeo)
        self.assertEqual(regeo.formatted_address, "福建省厦门市思明区测试路")
        self.assertEqual(regeo.adcode, "350203")

    def test_amap_weather_provider_formats_and_caches_live_weather(self) -> None:
        class FakeAMapWeatherProvider(AMapWeatherProvider):
            calls = 0

            def _get_json(self, path: str, params: dict[str, str]) -> dict[str, object]:
                self.calls += 1
                self.assert_weather_path = path
                return {
                    "status": "1",
                    "lives": [
                        {
                            "weather": "多云",
                            "temperature": "29",
                            "winddirection": "东南",
                            "windpower": "3",
                            "humidity": "78",
                        }
                    ],
                }

        settings = Settings(amap_api_key="test-amap-key", map_provider="amap")
        provider = FakeAMapWeatherProvider(settings)
        city = JourneyCity(
            name="厦门",
            lat=24.4798,
            lng=118.0894,
            weather="海风很轻",
            phrases=("慢慢走",),
            thoughts=("汪",),
        )
        now = datetime(2026, 7, 3, 4, 0, tzinfo=timezone.utc)

        first = provider.city_with_weather(city, now=now)
        second = provider.city_with_weather(city, now=now + timedelta(seconds=30))

        self.assertEqual(first.weather, "多云，29°C，东南风3级，湿度78%")
        self.assertEqual(second.weather, first.weather)
        self.assertEqual(provider.calls, 1)

    def test_google_weather_provider_formats_and_caches_live_weather(self) -> None:
        class FakeGoogleWeatherProvider(GoogleWeatherProvider):
            calls = 0
            last_url = ""
            last_params: dict[str, str] = {}

            def _get_json(self, url: str, params: dict[str, str]) -> dict[str, object]:
                self.calls += 1
                self.last_url = url
                self.last_params = params
                return {
                    "weatherCondition": {
                        "description": {"text": "Sunny", "languageCode": "en"},
                        "type": "CLEAR",
                    },
                    "temperature": {"unit": "CELSIUS", "degrees": 23.8},
                    "feelsLikeTemperature": {"unit": "CELSIUS", "degrees": 25.2},
                    "relativeHumidity": 52,
                    "wind": {
                        "direction": {"degrees": 250, "cardinal": "WEST_SOUTHWEST"},
                        "speed": {"unit": "KILOMETERS_PER_HOUR", "value": 11.2},
                    },
                    "uvIndex": 7,
                }

        settings = Settings(google_maps_api_key="test-google-key", map_provider="google")
        provider = FakeGoogleWeatherProvider(settings)
        city = JourneyCity(
            name="洛杉矶",
            lat=34.0522,
            lng=-118.2437,
            weather="阳光很亮",
            phrases=("慢慢走",),
            thoughts=("汪",),
        )
        now = datetime(2026, 7, 3, 4, 0, tzinfo=timezone.utc)

        first = provider.city_with_weather(city, now=now)
        second = provider.city_with_weather(city, now=now + timedelta(seconds=30))

        self.assertEqual(first.weather, "Sunny，24°C，体感25°C，湿度52%，西南偏西风11km/h，UV 7")
        self.assertEqual(second.weather, first.weather)
        self.assertEqual(provider.calls, 1)
        self.assertIn("currentConditions:lookup", provider.last_url)
        self.assertEqual(provider.last_params["unitsSystem"], "METRIC")

