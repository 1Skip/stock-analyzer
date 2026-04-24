import sys
sys.path.insert(0, '/c/Users/skip8/stock_analyzer')

from stock_recommendation import StockRecommender

recommender = StockRecommender()

# 测试获取推荐
print("Testing short term recommendations...")
try:
    result = recommender.get_short_term_recommendations(5)
    print(f"Got {len(result)} recommendations")
    for r in result[:3]:
        print(f"  {r['symbol']} {r['name']}: {r['score']}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

# 测试板块推荐
print("\nTesting sector recommendations...")
try:
    result = recommender.get_sector_short_term_recommendations("苹果概念", 3)
    print(f"Got {len(result)} sector recommendations")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
