with open(r"C:\Users\skip8\stock_analyzer\recommend_ranker.py", "r", encoding="utf-8") as f:
    content = f.read()

# Find the exact text to replace - use the line as-is from the file
old_text = '    if sector and sector != "全部":\n        score += 2\n    return max(0, min(10, score))'
new_text = '    if sector and sector != "全部":\n        score += 2\n    if not score and strategy == "短线" and sector == "全部":\n        score = 4\n        reasons.append("热门板块成分股")\n    return max(0, min(10, score))'

found = old_text in content
print("Found target text: " + str(found))

if found:
    content = content.replace(old_text, new_text, 1)
    with open(r"C:\Users\skip8\stock_analyzer\recommend_ranker.py", "w", encoding="utf-8") as f:
        f.write(content)
    
    with open(r"C:\Users\skip8\stock_analyzer\recommend_ranker.py", "r", encoding="utf-8") as f:
        verify = f.read()
    has = 'if not score and strategy == "短线"' in verify
    print("Verified in file: " + str(has))
else:
    # Show what's actually there
    idx = content.find('if sector and sector != "全部"')
    if idx > 0:
        snippet = content[idx:idx+150].replace("\n", "\\n")
        print("Actual text at location: " + repr(snippet))
