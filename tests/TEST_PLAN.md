# STS2 Overlay 测试计划

> 所有已修复的 bug 和已实现的 feature 对应的回归测试。  
> 运行：`cd ~/Projects/sts2 && python3 -m pytest tests/ -v`

---

## 一、已修复 Bug 回归测试

### Bug #1 — 商店"无物品"
- **原因**：API 用 `items` 数组，overlay 没适配
- **测试**：`test_bugs.py::test_shop_items_array`
- **验证**：shop state 包含 `items` 数组时，`_display_shop` 正确解析并分类显示

### Bug #2 — 路线分析覆盖战斗
- **原因**：过期分析没清理，盖住战斗 UI
- **测试**：`test_bugs.py::test_analysis_stale_on_state_change`
- **验证**：状态从 map 切到 monster 时，`_analysis_stale()` 返回 True

### Bug #3 — 角色名英文
- **原因**：缺少中文映射
- **测试**：`test_bugs.py::test_character_name_chinese`
- **验证**：存档中的 `CHARACTER.IRONCLAD` 等映射为中文

### Bug #4 — 卡组构建重复显示
- **原因**：多个区域同时渲染
- **测试**：`test_bugs.py::test_deck_display_separate_areas`
- **验证**：`box_deck_list`（结构）和 `box_deck`（AI分析）分离，互不覆盖

### Bug #5 — 选牌结果被覆盖
- **原因**：每次刷新都重写选牌结果
- **测试**：`test_bugs.py::test_card_reward_only_on_type_change`
- **验证**：同一 `card_reward` 状态重复 poll 不覆盖已有 AI 分析

### Bug #6 — "已移除：无"
- **原因**：没有对比初始牌组
- **测试**：`test_bugs.py::test_removed_cards_detection`
- **验证**：当存档牌组少于初始牌组时，能推断出被移除的牌

### Bug #7 — 商店 AI 建议写错位置
- **原因**：建议没显示在当前形势区域
- **测试**：`test_bugs.py::test_shop_advice_in_situation_box`
- **验证**：商店 AI 分析结果写入 `box_situation`，不是 `box_deck`

### Bug #8 — 截图黑屏（权限问题）
- **测试**：跳过（环境依赖，非代码 bug）

---

## 二、Feature 测试

### Feature #1 — 全中文化
- **测试**：`test_features.py::test_power_cn_translation`
- **测试**：`test_features.py::test_relic_cn_translation`
- **测试**：`test_features.py::test_potion_cn_translation`
- **测试**：`test_features.py::test_cn_power_function`
- **测试**：`test_features.py::test_cn_power_fallback`
- **验证**：POWER_CN / RELIC_CN / POTION_CN 字典完整，`_cn_power()` 翻译正确，未知名称回退原名

### Feature #2 — 卡组结构化显示
- **测试**：`test_features.py::test_deck_list_by_type`
- **测试**：`test_features.py::test_deck_box_empty_on_new_run`
- **测试**：`test_features.py::test_deck_box_only_on_manual_trigger`
- **验证**：牌组按攻击/技能/能力分类显示，新局 box_deck 为空，只有手动点击才填充

### Feature #3 — Session 持久化
- **测试**：`test_features.py::test_save_session`
- **测试**：`test_features.py::test_load_session_same_run`
- **测试**：`test_features.py::test_load_session_different_run`
- **测试**：`test_features.py::test_session_cleared_on_new_run`
- **测试**：`test_features.py::test_make_run_id`
- **验证**：session.json 正确保存/恢复，不同局不恢复，新局清空

### Feature #4 — 意图翻译
- **测试**：`test_features.py::test_intent_translation`
- **测试**：`test_features.py::test_intent_damage_display`
- **验证**：敌人意图正确翻译为中文，多段攻击显示总伤

### Feature #5 — 战斗状态显示
- **测试**：`test_features.py::test_combat_display_enemies`
- **测试**：`test_features.py::test_combat_display_allies`
- **验证**：敌人/友方召唤物（Osty等）正确显示

### Feature #6 — 智能上下文构建
- **测试**：`test_features.py::test_build_context_returns_string`
- **验证**：`_build_context()` 返回非空字符串（有知识库数据时）

---

## 三、数据完整性测试

### 翻译字典覆盖率
- **测试**：`test_data.py::test_power_cn_minimum_coverage`
- **测试**：`test_data.py::test_relic_cn_minimum_coverage`
- **测试**：`test_data.py::test_potion_cn_minimum_coverage`
- **验证**：翻译字典至少覆盖 N 个条目

### 知识库文件完整性
- **测试**：`test_data.py::test_knowledge_files_exist`
- **测试**：`test_data.py::test_knowledge_files_valid_json`
- **验证**：所有知识库 JSON 文件存在且可解析

### 卡牌数据库
- **测试**：`test_data.py::test_card_dict_not_empty`
- **测试**：`test_data.py::test_character_cards_all_have_names`
- **验证**：卡牌字典和角色卡牌数据完整

---

## 四、运行方式

```bash
# 全部测试
python3 -m pytest tests/ -v

# 只跑 bug 回归
python3 -m pytest tests/test_bugs.py -v

# 只跑 feature 测试
python3 -m pytest tests/test_features.py -v

# 只跑数据完整性
python3 -m pytest tests/test_data.py -v

# 带覆盖率
python3 -m pytest tests/ -v --tb=short
```
