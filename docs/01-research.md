# 阶段一：调研与基准分析

> 本文保留初期调研与设计记录。当前实现能力、实际验证范围和待办以 [README 审查记录](../README.md#验证与开发) 为准；第三方规范描述不代表 OpenAI 官方保证。

调研时间：2026-11。对象：`HanaAyane/remielle-codex-pet`（小蕾米）、Codex v2 宠物合同、PetPack / PetX / qwen-audio-agent / DSH 桌宠插件的实现差异，以及《舞萌DX》莎露朵的角色资料。

## 1. 小蕾米仓库的结构

仓库是**素材包**，不是运行器。默认分支 `main`，Release `v1.0.0`，约 56 MB。

```text
remielle-codex-pet/
├─ README.md                 # 安装、动作图鉴、WSL 兼容性、已知限制
├─ NOTICE.md                 # 第三方来源与版权边界
├─ ASSET-USAGE.md            # 非商业署名使用说明
├─ output/xiaolemi/          # ← 真正安装到 Codex 的目录
│  ├─ pet.json               # 仅 5 个字段
│  ├─ spritesheet.webp       # 1536×2288，约 3.1 MB
│  ├─ animation-triggers.json# 声明式事件映射（非 Codex 读取）
│  └─ ANIMATION-TRIGGERS.md
├─ gif/1.gif … 7.gif         # 原始动作 GIF（1 idle, 2 expect, 3 pen_idle,
│                            #   4 draw_continuous, 5 smug, 6 draw_intermittent, 7 think）
├─ 表情包单张预览/            # 9 张 192×208 透明 PNG + manifest.json
└─ assets/readme/            # 宣传图、GIF 预览、排版 SVG
```

关键事实：

- **原生安装只需要两个文件**：`pet.json` + `spritesheet.webp`，放到 `~/.codex/pets/<id>/`（Windows 为 `%USERPROFILE%\.codex\pets\<id>\`）。
- `animation-triggers.json`、`ANIMATION-TRIGGERS.md`、`NOTICE.md` **不是** Codex v2 的硬性安装字段；仓库本身不含鼠标监听、任务状态监听或通知监听程序，触发映射只是声明。
- 小蕾米的 `pet.json` 实测内容只有：

```json
{
  "id": "xiaolemi",
  "displayName": "小蕾米",
  "description": "一只粉发白翼、抱着画板和画笔的日系Q版小天使桌宠。.",
  "spriteVersionNumber": 2,
  "spritesheetPath": "spritesheet.webp"
}
```

## 2. `pet.json` 字段：官方、派生与第三方扩展

### 2.1 Codex 官方字段（v2）

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | 是 | 唯一标识；建议小写 ASCII，与目录名一致 |
| `displayName` | 建议 | 设置里显示的名字 |
| `description` | 可选 | 一句话介绍 |
| `spriteVersionNumber` | v2 必填 `2` | 省略按 v1（8×9）解析；2288 高的图集会被 v1 拒绝 |
| `spritesheetPath` | 建议 | 图集文件名；官方缺省 `spritesheet.webp`，必须是宠物根目录内的文件名 |

### 2.2 由版本派生、不需要写进 JSON 的字段

| 概念 | 值 | 来源 |
| --- | --- | --- |
| `cell` | `192 × 208` | v1/v2 固定 |
| `columns` | `8` | 固定 |
| `rows` | v2 = `11`，v1 = `9` | 由 `spriteVersionNumber` 推导 |
| 帧索引 | `row × 8 + col` | 固定 |
| 每行有效帧数 | `6, 8, 8, 4, 5, 8, 6, 6, 6` | Codex / PetPack 的默认表 |
| 默认时序 | 约 8 fps（各运行器略有差异） | 运行器决定 |

### 2.3 第三方扩展（不是 Codex 官方字段）

调研中出现的三类扩展，容易和官方字段混淆：

1. **DSH 桌宠插件**（`dsh-pet-desktop`）额外支持 `cell`、`columns`、`frames`、`tracks`（每轨 `{durations, loop, fallback}`）、`sequences`（如 `{"done": ["jumping","waving","idle"]}`）、`remarks`（`pet|petCooldown|feed|feedCooldown|noTreats` 回复池）。默认值仍是 192×208 / 8 列 / 9 行 / `[6,8,8,4,5,8,6,6,6]`，`spriteVersionNumber: 2` 才变 11 行。
2. **qwen-audio-agent** 的 `animations`：每个动作 `{frames: [全局索引], fps}`；注明「`animations` 是扩展，不是 Codex Pet 官方清单字段」，原生 Codex 可能忽略。
3. **PetX** 同样支持用 `animations` 覆盖行/帧数；`sleeping` 是 row 6 的兼容别名。

> 结论：给 Codex 的 `pet.json` 只写官方 5 字段最稳；`cell/frames/tracks/sequences/remarks` 放到独立的 `pet.extended.json` 或 `animation-triggers.json`，由自己的渲染器读取。本仓库就是这样做的。

### 2.4 一个容易踩的差异：v2 的「正面帧」

- 官方合同：正面/中性**不占方向格**，指针无方向时回退到 `idle`；`idle` 第 0 帧同时是静态回退图。
- PetPack 文档：v2 的 `idle` 第 6 列被当作「中性/正面注视帧」。
- 小蕾米与官方合同一致：方向只用 9–10 行。

本仓库按官方合同实现：`idle` 用 0–5 共 6 帧，方向 9–10 行各 8 格，正面回退 `idle`。若你的运行器按 PetPack 约定取 `idle` 第 6 列，可在扩展清单里把 `frames.idle` 设为 7 并补一张正面帧——不要改官方 `pet.json` 的 5 字段。

## 3. Codex v2 硬规格

| 项目 | 要求 |
| --- | --- |
| 图集 | 1536 × 2288 |
| 网格 | 8 列 × 11 行 |
| 单帧 | 192 × 208 |
| 格式 | 透明 WebP 或 PNG（RGBA） |
| 体积 | ≤ 16 MiB（部分实现更保守，小蕾米 3.1 MB） |
| 第 0–8 行 | 9 个标准动作；未使用的格必须**完全透明** |
| 第 9–10 行 | 16 个顺时针方向，每行 8 格 |
| 方向顺序 | 第 9 行 `000, 022.5, 045, 067.5, 090, 112.5, 135, 157.5`；第 10 行 `180, 202.5, 225, 247.5, 270, 292.5, 315, 337.5` |
| 方向含义 | `000` 正上、`090` 屏幕右、`180` 下、`270` 屏幕左 |
| 基线 | 同一角色尺度与脚底基线；跳跃只改身体位置，不逐帧缩放 |
| 特效 | 不要速度线、尘土、地面阴影、漂浮符号、文字、格线 |

v1 对照：1536 × 1872，8 × 9，同样 192 × 208；前 9 行的状态与 v2 完全相同，只是没有视线行。v2 的 8×9 中间产物不能当成品发布。

## 4. 九种状态的语义与帧数

| 行 | 状态 | 帧数 | 合同语义 | 小蕾米的实际素材 |
| --- | --- | ---: | --- | --- |
| 0 | `idle` | 6 | 安静呼吸、眨眼、轻微起伏；首帧是静态回退 | `gif/1.gif` |
| 1 | `running-right` | 8 | 向右移动的循环 | 移动反馈 |
| 2 | `running-left` | 8 | 向左移动的循环 | 移动反馈 |
| 3 | `waving` | 4 | 友好招手/引起注意 | 启动、悬停、点击 |
| 4 | `jumping` | 5 | 蓄力、上升、顶点、下降、落稳 | `gif/5.gif`（smug 完成庆祝） |
| 5 | `failed` | 8 | 受阻、失败、取消的低落反应 | 失败 |
| 6 | `waiting` | 6 | 等待批准、帮助或输入 | 等待确认 |
| 7 | `running` | 6 | **正在处理任务**，不是原地跑步 | `gif/4.gif`（画画） |
| 8 | `review` | 6 | 专注检查已完成的结果 | `gif/7.gif`（思考） |

小蕾米的两个「名不副实」是刻意设计，也说明**状态名是运行器语义，不强制视觉动作**：

- `jumping` 播放的是「完成庆祝/smug」，不是物理跳跃；
- `running` 播放的是「工作中/画画」，不是奔跑。

本仓库的莎露朵保留更直白的语义：`jumping` 真的跳一下，`running` 用「揉面团」表达烘焙/工作中。

## 5. 16 向视线

- 16 个方向按顺时针、每 22.5° 一格，`000` 是正上而不是正面。
- 方向格不参与标准动作循环；只在指针/视线输入存在时覆盖 `idle`。
- 实现注视时**不能整只角色旋转/拉伸/仿射变形**：应由眼睛/眼睑先动，头颈与上身小幅跟随，耳朵、头发、尾巴按固定点滞后。
- 中性死区（指针在角色中心附近）回退 `idle`。

## 6. Codex 侧的加载与限制

- 目录：`${CODEX_HOME:-$HOME/.codex}/pets/<pet-name>/`，只放 `pet.json` 与 `spritesheet.webp`。
- 安装后重启 Codex → 设置 → Pets → 刷新 → 选择。
- Windows + WSL 后端可能发现不了自定义桌宠：上游 [openai/codex#20730](https://github.com/openai/codex/issues/20730)，仓库 Issue #1 有复现。临时方案是切 Windows 原生后端、从托盘完整退出再启动；不要改 `pet.json`、不要转 v1、不要重做图集。
- 目前 **没有** 公开的「Codex 图集事件总线」；鼠标、任务状态、通知的监听要靠外部运行器或自己的壳。

## 7. 莎露朵的角色基准

来自《maimai》系列（SEGA），首次登场于 `maimai MiLK`：

| 项目 | 设定 |
| --- | --- |
| 本名 | ソルト（Salt），中文译名纱露朵/莎露朵，别号「盐巴」 |
| 身份 | 猫娘面包师，CAFE MiLK 成员；为寻找爷爷故事里的「蓝色面粉」环游世界 |
| 外形 | 淡紫发、紫绿渐变瞳、猫耳、尾巴、豆眉、盘发/双马尾、女仆装、铃铛、袖套 |
| 性格 | 无口、弱气、怕羞；口癖「のです」 |
| 身高/年龄 | 142 cm / 12 岁 |
| 生日 | 8 月 23 日 |
| 声优 | 五十岚裕美 |
| 喜好 | 意式生牛肉片、三文鱼三明治、肉桂卷；兴趣是午觉 |
| 版本服装 | MiLK/FiNALE 女仆装、FESTiVAL 广袖+头花、PRiSM 魔法少女+伞 |

桌宠设计取向：**Q 版、非性化、面包师/盐主题**。12 岁角色不做暴露或暗示性表现；优先女仆装 + 围裙 + 盐罐挂饰 + 面包元素。

## 8. 莎露朵的状态映射（最初的设计稿）

> 最终图集改用用户提供的表情包（见 §10），下表是设计阶段为程序化方案定义的动作语义；替换素材时仍可按这张表挑帧。

| 状态 | 帧数 | 视觉动作（逐帧意图） | 触发事件 |
| --- | ---: | --- | --- |
| `idle` | 6 | 0–1 呼吸抬起；2 半闭眼；3 闭眼；4 呼气回落 + 耳朵抖；5 尾巴回摆 | 默认、回退 |
| `running-right` | 8 | 右倾 2 px，手臂前后摆，双腿交替抬落，尾巴向后上方甩 | 向右拖动 |
| `running-left` | 8 | 同一循环水平镜像（无左右不对称标记，允许镜像） | 向左拖动 |
| `waving` | 4 | 左手抬到脸颊外侧，手腕外摆/内收两次；歪头 4°、脸红、开口 | 启动、悬停、单击 |
| `jumping` | 5 | 0 蹲下、1 起跳、2 顶点双手上举、3 下落、4 落稳 | 双击、任务完成 |
| `failed` | 8 | 低头、耳朵下垂、半闭眼、泪滴、尾巴垂落、轻微左右摇 | 任务失败/取消 |
| `waiting` | 6 | 双手在身前交叠、歪头 5°、期待眨眼、耳朵竖起 | 等待批准/输入 |
| `running` | 6 | 前倾、双手在身前交替揉面、专注眼、汗滴、尾巴轻甩 | Agent 执行中 |
| `review` | 6 | 手托下巴、头歪向一侧、瞳孔左右扫读、轻微点头 | 检查结果 |
| 视线 9–10 行 | 16 | 瞳孔偏移 ±4 px、头部 ±3 px/±3°，上看睁眼、下看压上眼睑 | 指针方向 |

动作设计原则：

1. 所有帧共用同一尺度与脚底基线（本仓库基线约 y=202）；
2. 呼吸/跳跃只改整体 y 位移，不逐帧缩放；
3. 尾巴、耳朵、手臂绕固定点旋转，连接点不跳位；
4. 不使用速度线、尘土、阴影、漂浮符号；
5. 一次性动作（挥手/跳跃/失败）播完回到 `idle`，循环动作（等待/工作/检查）保持。

## 9. 调研结论

1. 小蕾米证明「两张文件 + 8×11 图集」就能被 Codex v2 识别；真正的工作量在**素材分帧、透明处理、基线对齐**，不在 JSON。
2. `pet.json` 必须极简；`cell/columns/frames/tracks` 不是官方字段，不要写进给 Codex 的清单。
3. 状态名与视觉不必一一对应（`jumping` 可庆祝、`running` 可工作），但同一套映射要在图集、触发文件、渲染器三处一致。
4. 原生 Codex 自行决定动作播放；资源包里的事件映射 JSON 不会替独立壳接入任务事件，独立运行器若要响应任务状态，需要另行实现事件输入。
5. 莎露朵的辨识度应放在「淡紫发 + 紫绿瞳 + 猫耳 + CAFE MiLK 围裙 + 盐罐/面包」上，而不是靠复杂动作。

## 10. 实际采用的素材（2026-11 更新）

调研结论中的「没有现成授权图集」仍然成立，但用户随后提供了一套可用的同人表情包，因此最终图集改为该素材，而不是程序化占位图。

- 来源：[【emotelab】来一份魔法盐巴～纱露朵表情包分享](https://www.bilibili.com/video/BV1Te896yE9d/)
- 作者：[@0x4682B4](https://space.bilibili.com/1354443)
- 形式：43 个 300×300 透明 PNGTuber GIF + 1 张 500×500 全身 PNG
- 要求：禁止商用、禁止投喂 AI、二创请告知
- 采用方式：确定性抽帧 + 缩放 + 瞳孔位移，不使用 AI；原始 GIF 不随仓库分发

| 状态 | GIF | 帧号 |
| --- | --- | --- |
| idle | `呆 3.gif` | 0,0,16,49,82,82 |
| running-right / left | `跳舞(Caramelldansen).gif` | 0,9,…,63（左右位移相反） |
| waving | `打招呼 1.gif` | 0,16,49,82 |
| jumping | `点赞.gif` | 0,7,18,32,48 |
| failed | `摇头.gif` | 0,4,8,12,16,20,24,28 |
| waiting | `茶 （闭眼.gif` | 0,13,26,39,52,65 |
| running | `打游戏.gif` | 0,8,16,24,32,38 |
| review | `主意.gif` | 0,9,19,46,56,65 |
| 16 向视线 | `呆 3.gif` 第 0 帧 | 瞳孔位移生成 16 帧 |

因为素材是胸像，最终图集是**半身桌宠**（184×184 放在 192×208 单元格底部裁切），不是全身立绘。转换脚本见 [`build_from_pack.py`](../tools/build_from_pack.py)，授权细节见 [`02-asset-plan.md`](02-asset-plan.md) 第 0 节与 [`NOTICE.md`](../NOTICE.md)。

## 参考链接

- [HanaAyane/remielle-codex-pet](https://github.com/HanaAyane/remielle-codex-pet)
- [Codex V2 Pet Contract（ai-skills）](https://github.com/rohitas-git/ai-skills/blob/main/skills/1-hatch-pet/references/codex-pet-contract.md)
- [PetPack 宠物包格式](https://mingfenghong.github.io/petpack/PET_FORMATS)
- [PetX（Codex Pet UI）](https://github.com/IchenDEV/petx)
- [qwen-audio-agent 桌宠皮肤协议](https://qwenaudio.github.io/qwen-audio-agent/zh/desktop/pet-skin-spec)
- [DSH 桌宠插件 README](https://raw.githubusercontent.com/qiqibabyy/dsh-pet-desktop/2c6947f20fd61b047ae355d36bb3617ec14d5fcd/assets/pets/README.md)
- [maimai 官方角色页](https://maimai.sega.jp/character/)
- [maimai 10 周年纪念ちほー2（ソルト 10 周年立绘）](https://info-maimai.sega.jp/4113/)
- [百度百科：莎露朵](https://baike.baidu.com/item/%E8%8E%8E%E9%9C%B2%E6%9C%B5/65476825)
- [萌娘百科：纱露朵](https://zh.moegirl.org.cn/%E7%BA%B1%E9%9C%B2%E6%9C%B5)
- [pixiv 百科：ソルト(maimai)](https://dic.pixiv.net/a/%E3%82%BD%E3%83%AB%E3%83%88%28maimai%29)
