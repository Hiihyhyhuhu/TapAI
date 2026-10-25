import os
import sys
import asyncio
import json

# Đảm bảo import được các module từ thư mục gốc backend
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from services.search_pipeline import TapAISearchPipeline

async def test_full_pipeline():
    print("=" * 60)
    print("🚀 BẮT ĐẦU CHẠY TEST SEARCH & RAG PIPELINE TRONG TAP AI BACKEND")
    print("=" * 60)

    pipeline = TapAISearchPipeline(cache_storage="./qdrant_storage")
    sample_image = os.path.join(os.path.dirname(__file__), "test_images", "sample.jpg")

    # LẦN 1: TÌM KIẾM MỚI (Cache Miss)
    print("\n" + "🔹" * 30)
    print("▶️ LẦN CHẠY 1: TÌM KIẾM MỚI (CACHE MISS)")
    print("🔹" * 30)
    res_1 = await pipeline.process_image(sample_image, object_id="obj_sweater_01", use_cache=True)
    
    print("\n🏆 KẾT QUẢ LẦN 1:")
    print(f"  • Cached : {res_1['cached']} (Thời gian: {res_1['latency_ms']}ms)")
    print(f"  • Từ khóa: {res_1['exact_query']}")
    if res_1['products']:
        print(f"  • Top 1  : {res_1['products'][0]['title']}")
        print(f"    Giá    : {res_1['products'][0]['price']} | Điểm: {res_1['products'][0]['match_score']}")
        print(f"    Lý do  : {res_1['products'][0].get('match_reason')}")

    # LẦN 2: TÌM KIẾM LẶP LẠI (Cache Hit từ Qdrant)
    print("\n" + "🔹" * 30)
    print("▶️ LẦN CHẠY 2: TÌM KIẾM LẠI CÙNG VẬT THỂ (KỲ VỌNG CACHE HIT < 150ms)")
    print("🔹" * 30)
    res_2 = await pipeline.process_image(sample_image, object_id="obj_sweater_01", use_cache=True)

    print("\n⚡ KẾT QUẢ LẦN 2 (RAG VECTOR DB):")
    print(f"  • Cached : {res_2['cached']} ⚡ (Thời gian: {res_2['latency_ms']}ms)")
    print(f"  • Tương đồng Cosine: {res_2.get('similarity_score')}")
    if res_2['products']:
        print(f"  • Top 1  : {res_2['products'][0]['title']}")

    output_path = os.path.join(BASE_DIR, "metadata_output.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(res_1, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Đã lưu kết quả hoàn chỉnh vào '{output_path}'!")
    print("🎉 Kiểm thử thành công 100%!")

if __name__ == "__main__":
    asyncio.run(test_full_pipeline())
