from base import *


class PhotoPipelineApiTests(PetJourneyApiTestBase):

    def test_image_provider_supports_pet_and_place_references(self) -> None:
        class FakeImageProvider(OpenAICompatibleImageProvider):
            def __init__(self, settings: Settings):
                super().__init__(settings)
                self.captured_files: list[ImageReference] = []
                self.captured_path = ""

            def _post_multipart(
                self,
                path: str,
                *,
                fields: dict[str, str],
                files: list[ImageReference],
            ) -> dict[str, object]:
                self.captured_path = path
                self.captured_files = files
                return {
                    "model": self.settings.image_model,
                    "data": [
                        {
                            "b64_json": (
                                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
                                "AAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
                            )
                        }
                    ],
                }

        provider = FakeImageProvider(Settings(image_api_key="image-key"))
        image = provider.generate_image_with_references(
            "Generate a photo with pet identity and place environment references.",
            references=[
                ImageReference(
                    image_bytes=b"pet-bytes",
                    mime_type="image/png",
                    filename="pet.png",
                    role="pet_identity",
                ),
                ImageReference(
                    image_bytes=b"place-bytes",
                    mime_type="image/jpeg",
                    filename="place.jpg",
                    role="place_environment",
                ),
            ],
        )

        self.assertEqual(provider.captured_path, "/images/edits")
        self.assertEqual([item.role for item in provider.captured_files], ["pet_identity", "place_environment"])
        self.assertEqual(image.provider, "openai-compatible-image-provider")
        self.assertEqual(image.mime_type, "image/png")

    def test_non_dog_cat_pet_uses_species_signal_and_photo_subject(self) -> None:
        dna = {
            "owner_title": "姐姐",
            "personality": "会学人说话，很爱观察窗外",
            "favorite_places": ["窗边", "有光的小店"],
            "hobby": ["看人来人往"],
            "catchphrase": "啾啾，我看到啦",
            "emoji_pref": "soft",
            "voice_style": "像一只小鹦鹉发来的短句和啾啾声",
        }
        response = self.client.post(
            "/api/v1/create_pet",
            data={
                "pet_name": "小青",
                "pet_type": "parrot",
                "dna": json.dumps(dna, ensure_ascii=False),
            },
        )
        self.assertEqual(response.status_code, 200)
        pet_id = response.json()["pet_id"]

        status = self.client.get(f"/api/v1/agent_status/{pet_id}")
        self.assertEqual(status.status_code, 200)
        latest = status.json()["agent_state"]["latest_thought"]
        self.assertEqual(latest["language_style"], "parrot_chirp_with_hidden_translation")
        self.assertIn("啾", latest["text"])

        mission = self.client.get(f"/api/v1/pets/{pet_id}/photo_mission")
        self.assertEqual(mission.status_code, 200)
        self.assertIn("beloved parrot", mission.json()["image_prompt"])

    def test_pet_photo_prompt_builder_formats_reference_contract_and_quality_check(self) -> None:
        builder = PetPhotoPromptBuilder()
        pet = PetRecord(
            pet_id="PJ-PROMPT",
            name="小福",
            pet_type=PetType.cat,
            dna=PetDNA(personality="胆子小但很爱观察窗外的光"),
            created_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
            photo_path="pet-reference.png",
        )
        place = PlaceSignal(
            id="place-cafe",
            name="默迹咖啡馆",
            category="cafe",
            city="厦门",
            lat=24.48,
            lng=118.08,
            activity_hint="窗边有咖啡香和柔和灯光",
            detail_hint="街边小咖啡馆的玻璃窗和小桌",
            source="test-map-provider",
            photo_url="https://example.com/place.jpg",
        )

        prompt = builder.build_prompt(
            pet=pet,
            place=place,
            perspective=PhotoPerspective.first_person_selfie,
            weather="多云，29°C",
            time_of_day="morning",
            landmark_hints=["街边小咖啡馆的玻璃窗"],
            local_detail_hints=["咖啡杯", "窗边小桌"],
            has_pet_reference=True,
            has_place_reference=True,
        )

        self.assertIn("pet_identity reference", prompt)
        self.assertIn("place_environment reference", prompt)
        self.assertIn("first-person pet selfie", prompt)
        self.assertIn("No cutout", prompt)
        self.assertIn("No watermark", prompt)
        report = builder.quality_check(
            prompt,
            expected_roles={"pet_identity", "place_environment"},
            place=place,
        )
        self.assertTrue(report.passed, report.summary)

        appended = builder.append_reference_contract("base prompt", roles={"pet_identity", "place_environment"})
        self.assertIn("preserve the exact pet identity", appended)
        self.assertIn("location layout", appended)

    def test_credential_prompt_builder_formats_pet_specific_documents(self) -> None:
        builder = PetCredentialPromptBuilder()
        pet = PetRecord(
            pet_id="PJ-CAT-42",
            name="奶糖",
            pet_type=PetType.cat,
            dna=PetDNA(owner_title="姐姐", personality="安静、爱趴窗台、会认真观察人"),
            created_at=datetime(2026, 7, 4, tzinfo=timezone.utc),
            photo_path="pet-reference.png",
        )

        prompts = builder.build_wallet_prompts(
            pet=pet,
            issue_date=datetime(2026, 7, 4, tzinfo=timezone.utc).date(),
            current_location="厦门",
            has_pet_reference=True,
        )

        self.assertEqual(
            [prompt.kind for prompt in prompts],
            [
                PetCredentialKind.identity,
                PetCredentialKind.passport,
                PetCredentialKind.health_record,
                PetCredentialKind.driver_license,
                PetCredentialKind.boarding_pass,
                PetCredentialKind.hotel_key,
            ],
        )
        identity = next(prompt for prompt in prompts if prompt.kind == PetCredentialKind.identity)
        driver = next(prompt for prompt in prompts if prompt.kind == PetCredentialKind.driver_license)
        health = next(prompt for prompt in prompts if prompt.kind == PetCredentialKind.health_record)
        self.assertIn("奶糖", identity.image_prompt)
        self.assertIn("beloved cat", identity.image_prompt)
        self.assertIn("pet_identity reference", identity.image_prompt)
        self.assertIn("do not copy or imitate any real government", identity.image_prompt.lower())
        self.assertIn("All other document memories", identity.image_prompt)
        self.assertIn("Do not synchronize", identity.image_prompt)
        self.assertNotIn("Current location context: 厦门", identity.image_prompt)
        self.assertIn("姐姐", identity.fields["守护人 / Guardian"])
        self.assertIn("PAW DRIVER LICENSE", driver.title)
        self.assertIn("Cloud Cart", driver.image_prompt)
        self.assertIn("Fictional keepsake only", driver.fields["状态 / Status"])
        self.assertIn("fictional PetSoul care stamp", health.fields["疫苗记录 / Vaccine"])

    def test_credentials_prompt_endpoint_returns_pet_wallet_documents(self) -> None:
        pet_id = self.create_pet(pet_type="rabbit")

        response = self.client.get(f"/api/v1/pets/{pet_id}/credentials/prompts")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            [item["kind"] for item in payload],
            ["identity", "passport", "health_record", "driver_license", "boarding_pass", "hotel_key"],
        )
        self.assertTrue(all(item["image_prompt"] for item in payload))
        self.assertTrue(any("beloved rabbit" in item["image_prompt"] for item in payload))
        self.assertTrue(all("Do not synchronize" in item["image_prompt"] for item in payload))
        self.assertTrue(all("Fictional PetSoul document only" in item["safety_notes"][0] for item in payload))

    def test_image_provider_reports_relay_configuration(self) -> None:
        settings = Settings(
            database_path=Path(self.tempdir.name) / "image.sqlite3",
            upload_dir=Path(self.tempdir.name) / "image-uploads",
            public_base_url="http://testserver",
            image_api_key="test-image-key",
            image_base_url="https://api.austinsapi.com/v1",
            image_model="gpt-image-2",
        )
        client = TestClient(create_app(settings))
        response = client.get("/api/v1/image_provider/config")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["provider"], "openai-compatible-image-provider")
        self.assertEqual(payload["image_model"], "gpt-image-2")
        self.assertEqual(payload["base_url"], "https://api.austinsapi.com/v1")
        self.assertTrue(payload["remote_configured"])
        self.assertTrue(payload["remote_call_active"])
        self.assertTrue(payload["remote_call_enabled"])
        self.assertTrue(payload["reference_image_supported"])

