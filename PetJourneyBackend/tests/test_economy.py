from base import *


class EconomyApiTests(PetJourneyApiTestBase):

    def test_economy_collect_is_idempotent_and_sell_uses_item_version(self) -> None:
        pet_id = self.create_pet()
        quest_response = self.client.post(
            f"/api/v1/pets/{pet_id}/travel_quests",
            json={
                "message": "小星，去鼓浪屿慢慢玩，回来带一点小东西。",
                "destination": "鼓浪屿",
            },
        )
        self.assertEqual(quest_response.status_code, 200)
        quest_id = quest_response.json()["id"]

        first_collect = self.client.post(f"/api/v1/pets/{pet_id}/travel_quests/{quest_id}/souvenirs/collect")
        self.assertEqual(first_collect.status_code, 200)
        first_payload = first_collect.json()
        first_ids = [item["id"] for item in first_payload["items"]]
        first_tx_ids = [tx["tx_id"] for tx in first_payload["transactions"]]
        self.assertGreaterEqual(len(first_ids), 3)
        self.assertEqual(first_payload["snapshot"]["owned_item_count"], len(first_ids))
        self.assertTrue(all(item["template_id"] for item in first_payload["items"]))
        self.assertTrue(all(item["value_breakdown"]["final_market_value"] == item["market_value"] for item in first_payload["items"]))

        for _ in range(9):
            repeated = self.client.post(f"/api/v1/pets/{pet_id}/travel_quests/{quest_id}/souvenirs/collect")
            self.assertEqual(repeated.status_code, 200)
            repeated_payload = repeated.json()
            self.assertEqual([item["id"] for item in repeated_payload["items"]], first_ids)
            self.assertEqual([tx["tx_id"] for tx in repeated_payload["transactions"]], first_tx_ids)

        economy = self.client.get(f"/api/v1/pets/{pet_id}/economy")
        self.assertEqual(economy.status_code, 200)
        self.assertEqual(len(economy.json()["recent_transactions"]), 1)
        self.assertEqual(economy.json()["recent_transactions"][0]["type"], "item_acquired")

        sellable = next(item for item in first_payload["items"] if item["trade_policy"] == "tradable")
        sell = self.client.post(
            f"/api/v1/pets/{pet_id}/items/{sellable['id']}/sell",
            json={"client_request_id": "sell-once", "expected_item_version": sellable["version"]},
        )
        self.assertEqual(sell.status_code, 200)
        sell_payload = sell.json()
        self.assertEqual(sell_payload["item"]["status"], "sold")
        self.assertEqual(sell_payload["item"]["version"], sellable["version"] + 1)
        self.assertEqual(sell_payload["wallet"]["travel_coin"], sellable["market_value"] // 2)

        repeated_sell = self.client.post(
            f"/api/v1/pets/{pet_id}/items/{sellable['id']}/sell",
            json={"client_request_id": "sell-once", "expected_item_version": sellable["version"]},
        )
        self.assertEqual(repeated_sell.status_code, 200)
        self.assertEqual(repeated_sell.json()["transaction"]["tx_id"], sell_payload["transaction"]["tx_id"])

        stale_sell = self.client.post(
            f"/api/v1/pets/{pet_id}/items/{sellable['id']}/sell",
            json={"client_request_id": "sell-again", "expected_item_version": sellable["version"]},
        )
        self.assertEqual(stale_sell.status_code, 409)

    def test_economy_derived_state_can_be_rebuilt_from_transactions(self) -> None:
        pet_id = self.create_pet()
        quest_response = self.client.post(
            f"/api/v1/pets/{pet_id}/travel_quests",
            json={"message": "小星，去泉州走走，回来带一点小收藏。", "destination": "泉州"},
        )
        self.assertEqual(quest_response.status_code, 200)
        quest_id = quest_response.json()["id"]
        collect = self.client.post(f"/api/v1/pets/{pet_id}/travel_quests/{quest_id}/souvenirs/collect")
        self.assertEqual(collect.status_code, 200)
        sellable = next(item for item in collect.json()["items"] if item["trade_policy"] == "tradable")
        sell = self.client.post(
            f"/api/v1/pets/{pet_id}/items/{sellable['id']}/sell",
            json={"client_request_id": "replay-sell", "expected_item_version": sellable["version"]},
        )
        self.assertEqual(sell.status_code, 200)

        expected = self.client.get(f"/api/v1/pets/{pet_id}/economy").json()
        storage = self.client.app.state.storage
        storage.clear_economy_derived_state(pet_id)
        self.assertIsNone(storage.get_wallet(pet_id))
        self.assertIsNone(storage.get_economy_snapshot(pet_id))

        rebuilt = self.client.app.state.economy_engine.rebuild_derived_state(pet_id).model_dump(mode="json", by_alias=True)
        self.assertEqual(rebuilt["wallet"]["travel_coin"], expected["wallet"]["travel_coin"])
        self.assertEqual(rebuilt["wallet"]["star_dust"], expected["wallet"]["star_dust"])
        self.assertEqual(rebuilt["wallet"]["merit"], expected["wallet"]["merit"])
        for key in (
            "total_display_value",
            "sellable_value",
            "collection_value",
            "honor_value",
            "owned_item_count",
            "sellable_item_count",
            "archived_item_count",
            "sold_item_count",
        ):
            self.assertEqual(rebuilt["snapshot"][key], expected["snapshot"][key])
        self.assertEqual([tx["type"] for tx in rebuilt["recent_transactions"]], ["item_sold", "item_acquired"])

    def test_economy_read_endpoints_do_not_create_rewards_or_transactions(self) -> None:
        pet_id = self.create_pet()
        quest_response = self.client.post(
            f"/api/v1/pets/{pet_id}/travel_quests",
            json={"message": "小星，去京都看看会带回什么。", "destination": "京都"},
        )
        self.assertEqual(quest_response.status_code, 200)
        quest_id = quest_response.json()["id"]
        collect = self.client.post(f"/api/v1/pets/{pet_id}/travel_quests/{quest_id}/souvenirs/collect")
        self.assertEqual(collect.status_code, 200)

        before_economy = self.client.get(f"/api/v1/pets/{pet_id}/economy").json()
        before_inventory = self.client.get(f"/api/v1/pets/{pet_id}/inventory", params={"status": "all"}).json()
        before_tx_ids = [tx["tx_id"] for tx in before_economy["recent_transactions"]]
        before_item_ids = [item["id"] for item in before_inventory["items"]]

        for path in (
            f"/api/v1/pets/{pet_id}/economy",
            f"/api/v1/pets/{pet_id}/inventory?status=all",
            f"/api/v1/pets/{pet_id}/city_position",
            f"/api/v1/pets/{pet_id}/world_snapshot",
            f"/api/v1/pets/{pet_id}/life_tick",
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)

        after_economy = self.client.get(f"/api/v1/pets/{pet_id}/economy").json()
        after_inventory = self.client.get(f"/api/v1/pets/{pet_id}/inventory", params={"status": "all"}).json()
        self.assertEqual([tx["tx_id"] for tx in after_economy["recent_transactions"]], before_tx_ids)
        self.assertEqual([item["id"] for item in after_inventory["items"]], before_item_ids)
        self.assertEqual(after_economy["wallet"], before_economy["wallet"])

    def test_owner_fund_grant_requires_dev_admin_and_is_idempotent(self) -> None:
        pet_id = self.create_pet()
        disabled = self.client.post(
            f"/api/v1/pets/{pet_id}/owner_fund/grant",
            json={"grant_id": "grant-1", "star_dust": 1000, "reason": "test"},
        )
        self.assertEqual(disabled.status_code, 403)

        root = Path(self.tempdir.name) / "grant-app"
        settings = Settings(
            database_path=root / "petjourney.sqlite3",
            upload_dir=root / "uploads",
            public_base_url="http://testserver",
            economy_dev_grants_enabled=True,
            economy_admin_token="secret-token",
        )
        client = TestClient(create_app(settings))
        grant_pet_id = self.create_pet(client=client)

        wrong = client.post(
            f"/api/v1/pets/{grant_pet_id}/owner_fund/grant",
            headers={"X-PetJourney-Admin-Token": "wrong"},
            json={"grant_id": "grant-1", "star_dust": 1000, "project_budget": 700, "reason": "test"},
        )
        self.assertEqual(wrong.status_code, 403)

        ok = client.post(
            f"/api/v1/pets/{grant_pet_id}/owner_fund/grant",
            headers={"X-PetJourney-Admin-Token": "secret-token"},
            json={"grant_id": "grant-1", "star_dust": 1000, "project_budget": 700, "reason": "test"},
        )
        self.assertEqual(ok.status_code, 200)
        payload = ok.json()
        self.assertEqual(payload["wallet"]["star_dust"], 1000)
        self.assertEqual(payload["owner_fund"]["star_dust"], 1000)
        self.assertEqual(payload["owner_fund"]["project_budget"], 700)
        self.assertEqual(payload["recent_transactions"][0]["type"], "owner_fund_granted")

        repeated = client.post(
            f"/api/v1/pets/{grant_pet_id}/owner_fund/grant",
            headers={"X-PetJourney-Admin-Token": "secret-token"},
            json={"grant_id": "grant-1", "star_dust": 1000, "project_budget": 700, "reason": "test"},
        )
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.json()["wallet"]["star_dust"], 1000)
        self.assertEqual(len(repeated.json()["recent_transactions"]), 1)

    def test_economy_value_breakdown_is_stable_and_rarity_monotonic(self) -> None:
        engine = self.client.app.state.economy_engine
        pet = self.sample_pet()
        base_item = SouvenirItem(
            id="SV-TEST",
            pet_id=pet.pet_id,
            quest_id="TQ-TEST",
            template_id="tpl_test_shell",
            item_type=SouvenirItemType.found_object,
            title="测试贝壳",
            subtitle="一枚用于测试的贝壳",
            city="青岛",
            place_name="第一海水浴场",
            story="退潮时发现，像一颗小星星。",
            pet_voice="我想把它带回来。",
            image_prompt="test",
            rarity="common",
            obtained_at=datetime(2026, 7, 4, 8, 0, tzinfo=timezone.utc),
            source="test",
        )

        first = engine._value_for_item(
            pet=pet,
            item=base_item,
            source=AcquisitionSource.quest_reward,
            template_id="tpl_test_shell",
        )
        second = engine._value_for_item(
            pet=pet,
            item=base_item,
            source=AcquisitionSource.quest_reward,
            template_id="tpl_test_shell",
        )
        rare = engine._value_for_item(
            pet=pet,
            item=base_item.model_copy(update={"rarity": "rare"}),
            source=AcquisitionSource.quest_reward,
            template_id="tpl_test_shell",
        )

        self.assertEqual(first.value_breakdown, second.value_breakdown)
        self.assertGreater(rare.market_value, first.market_value)

