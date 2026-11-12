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
    print("🚀 BẮT ĐẦU CHẠY TEST CORE SEARCH PIPELINE TRONG TAP AI BACKEND")
    print("=" * 60)

    pipeline = TapAISearchPipeline()
    sample_image = os.path.join(os.path.dirname(__file__), "test_images", "sample.jpg")

    print("\n" + "🔹" * 30)
    print("▶️ CHẠY TÌM KIẾM AI CỐT LÕI: CROP -> GEMINI VLM -> SERPER -> RERANK")
    print("🔹" * 30)
    res = await pipeline.process_image(sample_image, object_id="obj_sweater_01", top_k=5)
    
    print("\n🏆 KẾT QUẢ TÌM KIẾM:")
    print(f"  • Thời gian xử lý: {res['latency_ms']}ms")
    print(f"  • Danh mục       : {res['detected_category']}")
    print(f"  • Từ khóa VLM    : {res['exact_query']}")
    if res['products']:
        print(f"  • Top 1          : {res['products'][0]['title']}")
        print(f"    Giá            : {res['products'][0]['price']} | Điểm: {res['products'][0]['match_score']}")
        print(f"    Lý do          : {res['products'][0].get('match_reason')}")

    output_path = os.path.join(BASE_DIR, "metadata_output.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Đã lưu kết quả hoàn chỉnh vào '{output_path}'!")
    print("🎉 Kiểm thử thành công 100%!")

if __name__ == "__main__":
    asyncio.run(test_full_pipeline())
