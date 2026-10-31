import os
from datetime import datetime
from typing import Dict, Any, Optional

class SeasonalityEngine:
    """
    Bộ nhận diện và điều phối trọng số xếp hạng thích nghi theo mùa (Context-Aware / Seasonality-Adaptive):
    - Tự động phát hiện ngày đôi Siêu Sale (9.9, 10.10, 11.11, 12.12), Black Friday, Tết.
    - Cho phép ghi đè thủ công bất kỳ lúc nào qua biến môi trường RANKING_CAMPAIGN_MODE.
    """
    PROFILES = {
        "DEFAULT": {
            "A": 0.75,
            "B": 0.10,
            "min_gate": 0.60,
            "name": "Mặc định (Ưu tiên trải nghiệm thị giác chuẩn xác)"
        },
        "MEGA_SALE": {
            "A": 0.65,
            "B": 0.30,
            "min_gate": 0.55,
            "name": "Mùa Siêu Sale (Tối đa hóa hoa hồng thưởng từ sàn & nhãn hàng)"
        },
        "TET_HOLIDAY": {
            "A": 0.70,
            "B": 0.25,
            "min_gate": 0.60,
            "name": "Mùa sắm Tết (Cân bằng giá trị giỏ hàng quà tặng cao)"
        }
    }

    @classmethod
    def detect_campaign(cls, target_date: Optional[datetime] = None) -> str:
        override_mode = os.getenv("RANKING_CAMPAIGN_MODE", "AUTO").upper().strip()
        if override_mode in cls.PROFILES:
            return override_mode

        dt = target_date or datetime.now()
        month, day = dt.month, dt.day

        is_double_day = (month in [9, 10, 11, 12]) and (day in [9, 10, 11, 12, 13, 14, 15])
        is_black_friday_week = (month == 11 and 20 <= day <= 30)

        if is_double_day or is_black_friday_week:
            return "MEGA_SALE"

        is_tet_season = (month == 1 and day >= 5) or (month == 2 and day <= 15)
        if is_tet_season:
            return "TET_HOLIDAY"

        return "DEFAULT"

    @classmethod
    def get_weights(cls, target_date: Optional[datetime] = None) -> Dict[str, Any]:
        campaign = cls.detect_campaign(target_date)
        profile = cls.PROFILES[campaign].copy()
        profile["campaign_key"] = campaign
        return profile
