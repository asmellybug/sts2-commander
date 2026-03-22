"""STS2 模拟器 CLI入口
Usage:
    python -m simulator 200          # 批量archetype模拟 (200局/流派)
    python -m simulator --full 100   # 三幕全流程模拟 (100局/角色)
"""
import sys
from .data_loader import ARCHETYPES
from .full_run import batch_simulate, batch_simulate_full


def main():
    args = sys.argv[1:]
    full_mode = "--full" in args
    args = [a for a in args if a != "--full"]
    runs = int(args[0]) if args else 30

    if full_mode:
        print(f"═══ STS2 三幕全流程模拟 — {runs}局/角色 ═══\n")
        for char_cn in ["铁甲战士", "静默猎手", "缺陷体", "储君", "亡灵契约师"]:
            result = batch_simulate_full(char_cn, runs=runs)
            bar = "█" * int(result["winrate"] * 10) + "░" * (10 - int(result["winrate"] * 10))
            print(f"  {char_cn:6s} {bar} {result['winrate']*100:5.1f}%  "
                  f"avg_hp:{result['avg_hp_left']:.0f}  avg_deck:{result['avg_deck_size']:.0f}")
            if result["top_deaths"]:
                for loc, cnt in result["top_deaths"][:3]:
                    print(f"    ☠️ {loc}: {cnt}次")
    else:
        print(f"═══ STS2 离线模拟器 v2.0 — {runs}局/流派 ═══\n")

        all_results = []

        for char_cn in ["铁甲战士", "静默猎手", "缺陷体", "储君", "亡灵契约师"]:
            char_data = ARCHETYPES.get("characters", {}).get(char_cn, {})
            archs = char_data.get("archetypes", {})

            print(f"\n{'=' * 50}")
            print(f"  {char_cn}")
            print(f"{'=' * 50}")

            for aname in archs:
                result = batch_simulate(char_cn, aname, runs=runs)
                all_results.append(result)

                bar = "█" * int(result["winrate"] * 10) + "░" * (10 - int(result["winrate"] * 10))
                print(f"  {aname:15s} {bar} {result['winrate']*100:5.1f}%  "
                      f"avg_hp:{result['avg_hp_left']:.0f}  avg_turns:{result['avg_turns']:.0f}")

        print(f"\n{'=' * 50}")
        print(f"  总排名（A0 胜率）")
        print(f"{'=' * 50}")
        all_results.sort(key=lambda x: -x["winrate"])
        for r in all_results:
            bar = "█" * int(r["winrate"] * 10) + "░" * (10 - int(r["winrate"] * 10))
            print(f"  {r['character']:6s} {r['archetype']:15s} {bar} {r['winrate']*100:5.1f}%")


if __name__ == "__main__":
    main()
