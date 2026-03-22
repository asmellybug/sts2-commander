#!/bin/bash
# STS2 端到端API监测
# 用法: ./scripts/e2e_monitor.sh
# 自动记录所有场景变化到 runtime/e2e_log.txt

API="http://localhost:15526/api/v1/singleplayer"
LOG="$(dirname "$0")/../runtime/e2e_log.txt"
SNAP_DIR="$(dirname "$0")/../runtime/e2e_snaps"
mkdir -p "$SNAP_DIR"

LAST=""
SEEN=""
echo "$(date '+%H:%M:%S') 🎮 E2E监测启动" | tee "$LOG"

while true; do
    DATA=$(curl -s -m 3 "$API" 2>/dev/null)
    [ -z "$DATA" ] && sleep 2 && continue
    
    TYPE=$(echo "$DATA" | python3 -c "import json,sys; print(json.load(sys.stdin).get('state_type','?'))" 2>/dev/null)
    
    if [ "$TYPE" != "$LAST" ] && [ -n "$TYPE" ]; then
        TS=$(date '+%H:%M:%S')
        echo "" | tee -a "$LOG"
        echo "$TS ===== $LAST → $TYPE =====" | tee -a "$LOG"
        
        # 保存快照
        echo "$DATA" > "$SNAP_DIR/${TYPE}.json"
        
        # 解析关键信息
        echo "$DATA" | python3 -c "
import json,sys
s=json.load(sys.stdin)
t=s.get('state_type','?')
if t in ('monster','elite','boss'):
    b=s.get('battle',{});p=b.get('player',{})
    print(f'  {p.get(\"character\",\"?\")} HP:{p.get(\"hp\",\"?\")}/{p.get(\"max_hp\",\"?\")} E:{p.get(\"energy\",\"?\")} R{b.get(\"round\",\"?\")}')
    for e in b.get('enemies',[]):
        print(f'  敌: {e[\"name\"]} {e[\"hp\"]}/{e[\"max_hp\"]} {e.get(\"intents\",[])}')
    for a in b.get('allies',[]):
        if a.get('name'): print(f'  友: {a[\"name\"]} {a[\"hp\"]}/{a[\"max_hp\"]}')
elif t=='map':
    m=s.get('map',{});r=s.get('run',{})
    p=m.get('player',{})
    print(f'  幕{r.get(\"act\",\"?\")} 层{r.get(\"floor\",\"?\")} HP:{p.get(\"hp\",\"?\")}/{p.get(\"max_hp\",\"?\")} 金:{p.get(\"gold\",\"?\")}')
elif t=='card_reward':
    cards=[c['name'] for c in s.get('card_reward',{}).get('cards',[])]
    print(f'  选牌: {cards}')
elif t=='combat_rewards':
    items=[i.get('description','') for i in s.get('rewards',{}).get('items',[])]
    print(f'  战利品: {items}')
elif t=='event':
    ev=s.get('event',{})
    print(f'  事件: {ev.get(\"event_name\",\"?\")} ancient={ev.get(\"is_ancient\",False)}')
    for o in ev.get('options',[]):
        print(f'    [{o[\"index\"]}] {o[\"title\"]}: {o.get(\"description\",\"\")[:50]}')
elif t=='rest_site':
    rs=s.get('rest_site',{})
    opts=[o['name'] for o in rs.get('options',[]) if o.get('is_enabled')]
    print(f'  休息选项: {opts}')
elif t=='shop':
    print(f'  商店数据已保存到 {t}.json')
elif t=='treasure':
    tr=s.get('treasure',{})
    relics=[r['name'] for r in tr.get('relics',[])]
    print(f'  宝箱: {relics if relics else \"开启中...\"}')
else:
    print(f'  {json.dumps(s, ensure_ascii=False)[:200]}')
" 2>/dev/null | tee -a "$LOG"
        
        LAST="$TYPE"
    fi
    sleep 2
done
