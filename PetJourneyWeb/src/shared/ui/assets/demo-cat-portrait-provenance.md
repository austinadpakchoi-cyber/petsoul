# 演示头像 `demo-cat-portrait-v1.webp`

## 来源

从 `src/features/home/assets/living/sample-cat-photo-sit-v2.webp`（内部测试小灰猫的写实坐姿抠图，来源与授权见同目录 `photo-cat-provenance-v2.md`：用户在对话里提供参考照片，并明确授权作为内部测试猫使用）裁出以脸为中心的方形头像：
- 原图 640×854，裁切框 (190, 0, 540, 350)，铺暖米色底 `#EFE6D6`（圆形头像不透底），Lanczos 缩到 256×256，WebP 质量 86。
- 2026-09-24 由 claude-20260923-185525-6c2b 用本机 Python Pillow 11.0.0 处理，没有调用任何生图或外部服务。
- 2026-09-24 从 `src/features/pets/assets/` 原样挪到 `src/shared/ui/assets/`（字节不变，sha256 `ea69eb0be94a821f43c150bdfb96b9714beee6783af8614cfde7a9b11ed53c28`），因为全站共用的 `PetAvatar` 也要用它，`shared` 不反向引用 `features`。

## 用途与边界

用户 2026-09-24 原话：“宠物你不要以他名字第一个字作为头像……还是宠物自己的形象，如果是预设的那些没有你就用那种小灰猫的作为测试的演示对象”。

- **只在 fixture（演示）模式**、且宠物没有照片时作为头像显示（`src/shared/ui/PetAvatar.tsx` 的 `petPortraitUrl`；`PetAvatar` 与 `features/pets/PetPortrait` 都经它取图）。
- live 模式永远不用它：真实宠物只显示主人上传的照片或服务端生成的写实照；都没有时显示中性的爪印占位，不用名字首字，也不借这只猫冒充任何真实宠物。
- 它不是某个真实账号或宠物的照片；演示世界里的名字（如“团子”）只是演示数据。
