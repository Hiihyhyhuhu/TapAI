import sys
sys.stdout.reconfigure(encoding='utf-8')
import random
from typing import List, Dict, Any

# Giả lập tập dữ liệu kiểm thử (Offline Evaluation Dataset)
# Mỗi sample gồm 1 ảnh crop và danh sách các sản phẩm ứng viên tìm được từ sàn
MOCK_DATASET = [
    {
        "query_id": "crop_sweater_01",
        "description": "Áo len cổ bẻ kẻ sọc ngang đỏ đen trắng",
        "candidates": [
            {"id": "sp_1", "similarity": 0.95, "commission_rate": 0.05, "price": 680000},
            {"id": "sp_2", "similarity": 0.88, "commission_rate": 0.18, "price": 450000},
            {"id": "sp_3", "similarity": 0.65, "commission_rate": 0.20, "price": 320000},
            {"id": "sp_4", "similarity": 0.40, "commission_rate": 0.25, "price": 250000},
        ]
    },
    {
        "query_id": "crop_handbag_02",
        "description": "Túi kẹp nách nữ da bóng khóa kim loại",
        "candidates": [
            {"id": "bag_1", "similarity": 0.92, "commission_rate": 0.08, "price": 190000},
            {"id": "bag_2", "similarity": 0.90, "commission_rate": 0.15, "price": 250000},
            {"id": "bag_3", "similarity": 0.70, "commission_rate": 0.12, "price": 180000},
            {"id": "bag_4", "similarity": 0.35, "commission_rate": 0.22, "price": 150000},
        ]
    },
    {
        "query_id": "crop_jacket_03",
        "description": "Áo khoác bomber kaki unisex",
        "candidates": [
            {"id": "jk_1", "similarity": 0.94, "commission_rate": 0.04, "price": 550000},
            {"id": "jk_2", "similarity": 0.85, "commission_rate": 0.14, "price": 480000},
            {"id": "jk_3", "similarity": 0.78, "commission_rate": 0.16, "price": 420000},
            {"id": "jk_4", "similarity": 0.50, "commission_rate": 0.20, "price": 300000},
        ]
    }
]

def score_candidate(cand: Dict[str, Any], A: float, B: float, min_gate: float) -> float:
    sim = cand["similarity"]
    if sim < min_gate:
        return -1.0

    norm_comm = (cand["commission_rate"] - 0.01) / (0.25 - 0.01)
    norm_comm = max(0.0, min(1.0, norm_comm))

    return (A * sim) + (B * norm_comm)

def run_optuna_study():
    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        print("❌ Chưa cài đặt thư viện 'optuna'. Hãy chạy: pip install optuna")
        return

    print("🚀 Bắt đầu tối ưu đa mục tiêu (Multi-Objective Optimization) bằng Optuna...")
    print("   • Mục tiêu 1: Tối đa hóa Độ chính xác thị giác Top-1 (Visual Accuracy)")
    print("   • Mục tiêu 2: Tối đa hóa Tiền hoa hồng kỳ vọng Top-1 (Expected Commission VND)\n")

    def objective(trial):
        A = trial.suggest_float("A", 0.50, 0.95, step=0.05)
        B = trial.suggest_float("B", 0.05, 0.50, step=0.05)
        min_gate = trial.suggest_float("min_similarity_gate", 0.55, 0.75, step=0.05)

        total_top1_similarity = 0.0
        total_top1_commission_vnd = 0.0

        for sample in MOCK_DATASET:
            candidates = sample["candidates"]
            scored_cands = []
            for c in candidates:
                s = score_candidate(c, A, B, min_gate)
                if s >= 0:
                    scored_cands.append((s, c))

            if scored_cands:
                scored_cands.sort(key=lambda x: x[0], reverse=True)
                top1 = scored_cands[0][1]
                total_top1_similarity += top1["similarity"]
                total_top1_commission_vnd += (top1["price"] * top1["commission_rate"])

        avg_similarity = total_top1_similarity / len(MOCK_DATASET)
        avg_commission_vnd = total_top1_commission_vnd / len(MOCK_DATASET)

        return avg_similarity, avg_commission_vnd

    study = optuna.create_study(
        study_name="tap_ai_ranking_optimization",
        directions=["maximize", "maximize"],
        sampler=optuna.samplers.NSGAIISampler(seed=42)
    )

    study.optimize(objective, n_trials=100)

    print("🏆 KẾT QUẢ ĐƯỜNG CONG TỐI ƯU PARETO (PARETO FRONTIER):")
    print("=" * 75)
    print(f"{'Trial #':<8} | {'Trọng số A':<10} | {'Trọng số B':<10} | {'Gate Sim':<10} | {'Độ chính xác Top-1':<18} | {'Hoa hồng TB (VNĐ)':<15}")
    print("-" * 75)

    pareto_trials = study.best_trials
    for t in pareto_trials:
        p = t.params
        v = t.values
        print(f"#{t.number:<7} | A = {p['A']:<6.2f} | B = {p['B']:<6.2f} | Gate = {p['min_similarity_gate']:<4.2f} | {v[0]*100:<5.1f}%             | {int(v[1]):,} VNĐ")

    print("=" * 75)

if __name__ == "__main__":
    run_optuna_study()
