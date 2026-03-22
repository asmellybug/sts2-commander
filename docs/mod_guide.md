# /sts2 — 杀戮尖塔2 快捷助手

## Triggers
- `/sts2` — 读取存档给建议
- `/sts2 advice` — 读取存档给建议
- `/sts2 save` — 显示存档状态
- `/sts2 backup` — 备份存档
- `/sts2 restore` — 恢复备份
- `/sts2 mod` — 修复/检查mod安装状态

## Behavior

### `/sts2` or `/sts2 advice`
1. 读取存档文件（modded优先，然后normal）
2. 解析角色/HP/牌组/遗物/Act
3. 根据当前状态给出建议（选牌/出牌/路线）
4. 回复到当前channel

### `/sts2 save`
显示当前存档状态（不分析）

### `/sts2 backup`
备份到 `~/Projects/sts2/backup/`

### `/sts2 restore`
从最近备份恢复

### `/sts2 mod`
检查并修复mod安装状态

## Mac Mod安装指南

### 游戏路径
```
游戏根目录: ~/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/
App包: SlayTheSpire2.app/Contents/
```

### Mod文件位置 (macOS)
```
SlayTheSpire2.app/Contents/MacOS/mods/
  ├── STS2_MCP.dll    ← mod主文件
  └── STS2_MCP.json   ← mod描述文件 (v0.99+必需)
```

**注意**: 右键SlayTheSpire2.app → 显示包内容 → Contents/MacOS/mods/

### STS2MCP Mod
- GitHub: https://github.com/Gennadiyev/STS2MCP
- 当前版本: 0.2.1-rev1
- 功能: 暴露游戏状态为HTTP API (localhost:15526)
- Release下载: `gh release download 0.2.1-rev1` (在sts2mcp仓库目录)

### 版本兼容性
- STS2 v0.99+ 不再需要.pck文件，改用.json描述文件
- **每次Steam更新游戏后，可能需要重新编译mod**
- 预编译dll通常兼容，除非游戏API变化

### 编译STS2MCP (游戏更新后需要)
```bash
cd ~/Projects/sts2mcp
# macOS需要修改csproj的HintPath (已done，sed替换windows路径为直接引用)
GAME_DATA="$HOME/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app/Contents/Resources/data_sts2_macos_arm64"
dotnet build -c Release -p:STS2GameDir="$GAME_DATA"
# 编译产物: bin/Release/net9.0/STS2_MCP.dll
cp bin/Release/net9.0/STS2_MCP.dll "$HOME/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app/Contents/MacOS/mods/"
```

### Harmony文件
- 位置: `SlayTheSpire2.app/Contents/Resources/data_sts2_macos_arm64/0Harmony.dll`
- **不要替换Harmony** — v0.99+使用游戏自带的原版Harmony
- 旧版mod(v0.98-)需要替换Harmony为HarmonyX，v0.99+不需要

### 存档分离
STS2的mod和非mod存档是分开的：
- Normal: `~/Library/Application Support/SlayTheSpire2/steam/76561198314080932/profile1/saves/`
- Modded: `~/Library/Application Support/SlayTheSpire2/steam/76561198314080932/modded/profile1/saves/`

要在mod模式下继续非mod存档：
```bash
cp -r ~/Library/Application\ Support/SlayTheSpire2/steam/76561198314080932/profile1/saves/* \
      ~/Library/Application\ Support/SlayTheSpire2/steam/76561198314080932/modded/profile1/saves/
```

### 启动脚本
- 一键启动: `~/Projects/sts2/overlay/launch.sh` 或桌面 `STS2_Advisor.command`
- 自动检查: Python依赖、知识库、mod安装、Harmony版本、API连接
- 自动等待游戏启动后连接

### 常见问题
1. **游戏没有mod选项**: 检查MacOS/mods/下是否有STS2_MCP.dll + STS2_MCP.json
2. **Steam更新后mod失效**: 下载最新release或重新编译
3. **mod存档为空**: 需要手动从normal存档复制到modded存档
4. **API不响应**: 游戏需要启动并开启mod模式，API在localhost:15526

## Save File Paths
- Normal: `~/Library/Application Support/SlayTheSpire2/steam/76561198314080932/profile1/saves/current_run.save`
- Modded: `~/Library/Application Support/SlayTheSpire2/steam/76561198314080932/modded/profile1/saves/current_run.save`
- Steam Cloud: `~/Library/Application Support/Steam/userdata/353815204/2868840/remote/profile1/saves/current_run.save`

## Save Format
STS2 save is JSON:
- `players[0]` — player data
- `players[0].current_hp` / `max_hp` — HP
- `players[0].gold` — gold
- `players[0].deck[]` — cards (each has `id`, `upgrades`)
- `players[0].relics[]` — relics (each has `id`)
- `current_act_index` — 0-based act index
- `acts[]` — act list with `type` field
- `ascension` — ascension level
- `visited_map_coords` — visited nodes

Card IDs are prefixed `CARD.` (e.g., `CARD.STRIKE_REGENT`).
Relic IDs are prefixed `RELIC.` (e.g., `RELIC.DIVINE_RIGHT`).

## Knowledge Base
All at `~/Projects/sts2/knowledge/`:
- `archetype_matrix.json` — 5chars × 35 archetypes
- `card_tier_list.json` — S/A/B/C/D ratings per stage
- `monster_ai.json` — 110 monsters
- `boss_counter_guide.json` — boss strategies
- `card_synergy_index.json` — card synergies
- `event_guide.json` — 66 events
- `potion_guide.json` — 63 potions
- `relic_pivot_rules.json` — relic strategies
- `combat_rules.json` — combat mechanics
- `lessons.json` — 71 learned lessons

## Analysis Guidelines
When giving advice:
- Use Chinese
- Be concise and direct
- Reference specific card names
- Consider HP%, act progress, deck composition
- Prioritize scaling (powers/key combos) over raw stats
- Note if deck is too large (>25) or too small (<15)
- Check strike/defend ratio — too many basics = bad
- Check knowledge base: archetype rankings, card tiers, lessons
- When editing saves, always patch ALL paths (normal + backup + steam cloud + modded)
