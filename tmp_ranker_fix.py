with open(r"C:\Users\skip8\stock_analyzer\recommend_ranker.py", "r", encoding="utf-8") as f:
    content = f.read()

# Fix 1a: update function signature
old_sig = 'def _component_from_strategy_score(score: float | None, reasons: list[str], penalties: list[str]) -> int:'
new_sig = 'def _component_from_strategy_score(score: float | None, reasons: list[str], penalties: list[str], strategy: str = "") -> int:'
content = content.replace(old_sig, new_sig, 1)
print("1a signature:", "OK" if old_sig not in content else "FAILED")

# Fix 1b: insert short-term branch after return 0
old = '        return 0\n    if score >= 85:'
new = '        return 0\n    if strategy == "短线":\n        if score >= 95:\n            reasons.append("策略原始分强")\n            return 14\n        if score >= 85:\n            reasons.append("策略原始分较强")\n            return 10\n        if score >= 75:\n            reasons.append("策略原始分较高")\n            return 6\n        if score >= 65:\n            reasons.append("策略原始分达标")\n            return 2\n        if score >= 55:\n            return 0\n        if score >= 45:\n            penalties.append("策略原始分偏弱")\n            return -4\n        penalties.append("策略原始分偏弱")\n        return -8\n    if score >= 85:'
content = content.replace(old, new, 1)
print("1b branch:", "OK" if old not in content else "FAILED")

# Fix 2: trend MA20 check for short-term
old_ma20 = '        if price >= ma20:\n            score += 4\n            reasons.append("价格站上MA20")\n        else:\n            score -= 6\n            penalties.append("价格跌破MA20")'
new_ma20 = '        if strategy == "短线":\n            if price >= ma20:\n                score += 2\n                reasons.append("价格站上MA20")\n            else:\n                score -= 2\n                penalties.append("短线跌破MA20，观察修复")\n        elif price >= ma20:\n            score += 4\n            reasons.append("价格站上MA20")\n        else:\n            score -= 6\n            penalties.append("价格跌破MA20")'
content = content.replace(old_ma20, new_ma20, 1)
print("2 trend:", "OK" if old_ma20 not in content else "FAILED")

with open(r"C:\Users\skip8\stock_analyzer\recommend_ranker.py", "w", encoding="utf-8") as f:
    f.write(content)
print("\nDone")
