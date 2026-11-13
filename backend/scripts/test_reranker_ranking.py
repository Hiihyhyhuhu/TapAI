import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from services.reranker import MultimodalReranker, CandidateRubricEvaluation, MatchLevel
from models.search_schemas import ProductCandidate

print("🧪 1. Kiểm tra tính điểm tất định bằng Python Rubric Scoring (Deterministic Rubric)...")

# Case A: Trùng khớp hoàn toàn (Mẫu thiết kế giống hệt: phom, cổ, sọc kẻ, màu, khóa zip)
eval_exact = CandidateRubricEvaluation(
    item_id="sp_exact",
    silhouette_match=MatchLevel.EXACT,
    collar_neckline_match=MatchLevel.EXACT,
    pattern_match=MatchLevel.EXACT,
    color_palette_match=MatchLevel.EXACT,
    key_details_match=True,
    reason="Giống hệt áo mục tiêu về cổ polo zip, kẻ sọc ngang đỏ đen trắng và phom rộng."
)
score_exact = MultimodalReranker.compute_rubric_score(eval_exact)
print(f"   • Case A (Khớp 100% tất cả tiêu chí) -> Điểm Rubric: {score_exact}")
assert score_exact == 1.0, f"Expected 1.0, got {score_exact}"

# Case B: Cùng mẫu cổ polo zip nhưng khác màu hoặc hoa văn (ví dụ: áo polo zip trơn màu đen)
eval_close = CandidateRubricEvaluation(
    item_id="sp_diff_pattern",
    silhouette_match=MatchLevel.EXACT,       # 0.30
    collar_neckline_match=MatchLevel.EXACT,  # 0.25
    pattern_match=MatchLevel.DIFFERENT,      # 0.00 (thiếu sọc ngang)
    color_palette_match=MatchLevel.DIFFERENT,# 0.00 (màu đen trơn)
    key_details_match=True,                  # 0.10 (có khóa zip)
    reason="Cùng kiểu dáng áo polo khóa zip nhưng vải trơn đơn sắc, thiếu sọc kẻ ngang."
)
score_close = MultimodalReranker.compute_rubric_score(eval_close)
print(f"   • Case B (Cùng polo zip, khác sọc kẻ)  -> Điểm Rubric: {score_close}")
assert score_close == 0.65, f"Expected 0.65, got {score_close}"

# Case C: Khác hẳn phom dáng (ví dụ: áo thun cổ tròn cộc tay)
eval_diff = CandidateRubricEvaluation(
    item_id="sp_wrong_silhouette",
    silhouette_match=MatchLevel.DIFFERENT,
    collar_neckline_match=MatchLevel.DIFFERENT,
    pattern_match=MatchLevel.DIFFERENT,
    color_palette_match=MatchLevel.CLOSE,
    key_details_match=False,
    reason="Sai khác phom dáng: áo phông cổ tròn cộc tay."
)
score_diff = MultimodalReranker.compute_rubric_score(eval_diff)
print(f"   • Case C (Sai khác phom dáng)          -> Điểm Rubric: {score_diff}")
assert score_diff == 0.15, f"Expected 0.15, got {score_diff}"

print(f"\n   -> Thứ tự xếp hạng tất định: {score_exact} (Exact) > {score_close} (Partial) > {score_diff} (Diff)")
assert score_exact > score_close > score_diff

print("\n🧪 2. Kiểm tra sắp xếp ứng viên theo Rubric Match Score...")
cands = [
    ProductCandidate(
        item_id="p1", title="Áo polo zip kẻ sọc ngang chuẩn mẫu", price="500k", product_url="http", thumbnail_url="http", query_used="ao",
        match_score=score_exact
    ),
    ProductCandidate(
        item_id="p2", title="Áo polo zip trơn đơn sắc", price="450k", product_url="http", thumbnail_url="http", query_used="ao",
        match_score=score_close
    ),
    ProductCandidate(
        item_id="p3", title="Áo thun cổ tròn cộc tay", price="200k", product_url="http", thumbnail_url="http", query_used="ao",
        match_score=score_diff
    ),
]

sorted_cands = sorted(cands, key=lambda x: (x.match_score or 0.0), reverse=True)
print(f"   #1 Top: {sorted_cands[0].item_id} (Score: {sorted_cands[0].match_score}) - {sorted_cands[0].title}")
print(f"   #2 Top: {sorted_cands[1].item_id} (Score: {sorted_cands[1].match_score}) - {sorted_cands[1].title}")
print(f"   #3 Top: {sorted_cands[2].item_id} (Score: {sorted_cands[2].match_score}) - {sorted_cands[2].title}")

assert sorted_cands[0].item_id == "p1"
assert sorted_cands[1].item_id == "p2"
assert sorted_cands[2].item_id == "p3"

print("\n🧪 3. Kiểm tra cơ chế Dual Identifier Anti-Index Shifting & Giới hạn bản sao...")
# Mô phỏng tình huống:
# candidates có 5 sản phẩm:
# - c0: được gửi VLM (Slot CAND_1, ID: sp_100)
# - c1: bị lọc DHash (trùng ảnh với c0)
# - c2: bị lọc DHash (trùng ảnh thứ 2 với c0)
# - c3: được gửi VLM (Slot CAND_2, ID: sp_300)
# - c4: ngoài danh sách (fallback)
# VLM trả về đánh giá cho CAND_1 và CAND_2 (nhưng CAND_2 bị VLM điền nhầm slot_id="CAND_2" thay vì item_id="sp_300")

unique_pool_sim = [
    (ProductCandidate(item_id="sp_100", title="Mẫu áo 1", price="100k", product_url="http", thumbnail_url="http", query_used="q"), None),
    (ProductCandidate(item_id="sp_300", title="Mẫu áo 3", price="300k", product_url="http", thumbnail_url="http", query_used="q"), None)
]

vlm_eval_sim = [
    CandidateRubricEvaluation(
        item_id="sp_100",
        slot_id="CAND_1",
        silhouette_match=MatchLevel.EXACT,
        collar_neckline_match=MatchLevel.EXACT,
        pattern_match=MatchLevel.EXACT,
        color_palette_match=MatchLevel.EXACT,
        key_details_match=True,
        reason="Khớp mẫu 1."
    ),
    CandidateRubricEvaluation(
        item_id="CAND_2",  # VLM trả về slot_id trong trường item_id
        slot_id="CAND_2",
        silhouette_match=MatchLevel.CLOSE,
        collar_neckline_match=MatchLevel.CLOSE,
        pattern_match=MatchLevel.DIFFERENT,
        color_palette_match=MatchLevel.DIFFERENT,
        key_details_match=False,
        reason="Khớp mẫu 3."
    )
]

# Xây dựng maps
item_id_map = {}
slot_map = {}
for ev_item in vlm_eval_sim:
    raw_id = (ev_item.item_id or "").strip()
    if raw_id:
        item_id_map[raw_id.lower()] = ev_item
        clean_slot = raw_id.upper().replace("CANDIDATE_", "CAND_").replace("CANDIDATE", "CAND_")
        if "CAND" in clean_slot:
            slot_map[clean_slot] = ev_item
        digits = "".join(filter(str.isdigit, raw_id))
        if digits:
            slot_map[f"CAND_{digits}"] = ev_item
            slot_map[digits] = ev_item

    raw_slot = (ev_item.slot_id or "").strip().upper()
    if raw_slot:
        clean_slot = raw_slot.replace("CANDIDATE_", "CAND_").replace("CANDIDATE", "CAND_")
        slot_map[clean_slot] = ev_item
        digits = "".join(filter(str.isdigit, clean_slot))
        if digits:
            slot_map[f"CAND_{digits}"] = ev_item
            slot_map[digits] = ev_item

evaluated_scores_sim = {}
for slot_idx, (cand, _) in enumerate(unique_pool_sim, 1):
    cand_id_norm = cand.item_id.strip().lower()
    slot_key = f"CAND_{slot_idx}"
    ev = item_id_map.get(cand_id_norm) or slot_map.get(slot_key) or slot_map.get(str(slot_idx))
    assert ev is not None, f"Phải tìm thấy evaluation cho {cand.item_id} qua Dual Identifier!"
    score = MultimodalReranker.compute_rubric_score(ev)
    evaluated_scores_sim[cand.item_id] = score

# sp_100 khớp hoàn toàn -> 1.0
assert evaluated_scores_sim["sp_100"] == 1.0
# sp_300 nhận đúng evaluation của CAND_2 (không bị gán nhầm sang sản phẩm khác) -> score_close = 0.30*0.65 + 0.25*0.65 = 0.3575
assert evaluated_scores_sim["sp_300"] == 0.3575
print("   • Dual Identifier mapping: sp_100 -> 1.0 | sp_300 (qua Slot CAND_2) -> 0.3575 [CHÍNH XÁC]")

# Kiểm tra giới hạn bản sao MAX_CLONES = 1
cands_all = [
    ProductCandidate(item_id="sp_100", title="Shop 1 (Gốc)", price="100k", product_url="http", thumbnail_url="http", query_used="q"),
    ProductCandidate(item_id="sp_clone_1", title="Shop 2 (Bản sao 1)", price="95k", product_url="http", thumbnail_url="http", query_used="q"),
    ProductCandidate(item_id="sp_clone_2", title="Shop 3 (Bản sao 2)", price="90k", product_url="http", thumbnail_url="http", query_used="q"),
    ProductCandidate(item_id="sp_300", title="Shop 4 (Khác mẫu)", price="300k", product_url="http", thumbnail_url="http", query_used="q"),
    ProductCandidate(item_id="sp_fallback", title="Shop 5 (Dự phòng)", price="50k", product_url="http", thumbnail_url="http", query_used="q"),
]
duplicate_of_sim = {"sp_clone_1": "sp_100", "sp_clone_2": "sp_100"}
clone_counts_sim = {}
synced_sim = set()

for c in cands_all:
    if c.item_id in evaluated_scores_sim:
        c.match_score = evaluated_scores_sim[c.item_id]
    elif c.item_id in duplicate_of_sim:
        rep_id = duplicate_of_sim[c.item_id]
        rep_score = evaluated_scores_sim.get(rep_id)
        current_clones = clone_counts_sim.get(rep_id, 0)
        if rep_score is not None and rep_score >= 0.50 and current_clones < 1:
            clone_counts_sim[rep_id] = current_clones + 1
            c.match_score = round(rep_score - 0.005, 4)
            synced_sim.add(c.item_id)

for idx, c in enumerate(cands_all):
    if c.item_id not in evaluated_scores_sim and c.item_id not in synced_sim:
        c.match_score = max(0.18, round(0.38 - (idx * 0.015), 4))

print(f"   • Shop 1 (Gốc):      {cands_all[0].match_score}")
print(f"   • Shop 2 (Bản sao 1): {cands_all[1].match_score} (Được đồng bộ điểm)")
print(f"   • Shop 3 (Bản sao 2): {cands_all[2].match_score} (Bị chặn hạn ngạch, rơi xuống baseline)")
print(f"   • Shop 4 (Mẫu khác): {cands_all[3].match_score}")
print(f"   • Shop 5 (Dự phòng): {cands_all[4].match_score}")

assert cands_all[0].match_score == 1.0
assert cands_all[1].match_score == 0.995
assert cands_all[2].match_score < 0.40  # Bản sao 2 bị chặn
assert cands_all[3].match_score == 0.3575

print("\n✅ KIỂM THỬ DETERMINISTIC RUBRIC SCORING & ANTI-INDEX SHIFTING THÀNH CÔNG 100%!")
