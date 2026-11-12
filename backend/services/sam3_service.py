import os
import io
import time
import json
import base64
import logging
from typing import List, Dict, Optional, Tuple, Union, Any

import cv2
import numpy as np
from PIL import Image as PILImage

# Cấu hình Logger cho module SAM 3 Computer Vision
logger = logging.getLogger("TapAI.SAM3Service")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


from collections import deque


class TrackedObject:
    """Mô hình dữ liệu của 1 vật thể/người được tracking xuyên suốt luồng video"""
    def __init__(
        self,
        track_id: str,
        category: str,
        semantic_group: str,
        bbox: np.ndarray,
        mask: Optional[np.ndarray],
        color_hist: np.ndarray,
        frame_idx: int
    ):
        self.track_id = track_id
        self.category = category
        self.semantic_group = semantic_group
        self.last_bbox = bbox.astype(np.float32)
        self.last_mask = mask
        self.color_hist = color_hist
        self.first_seen_frame = frame_idx
        self.last_seen_frame = frame_idx
        self.hits = 1
        self.crop_webp_path: str = ""
        self.crop_image_base64_webp: str = ""
        self.crop_image_data_url_webp: str = ""
        self.quality_score: float = 0.0
        self.rag_cache: Optional[Dict[str, Any]] = None

    def update(
        self,
        bbox: np.ndarray,
        mask: Optional[np.ndarray],
        color_hist: np.ndarray,
        frame_idx: int,
        alpha_ema: float = 0.3
    ):
        self.last_bbox = bbox.astype(np.float32)
        self.last_mask = mask
        if color_hist is not None and self.color_hist is not None:
            self.color_hist = (1.0 - alpha_ema) * self.color_hist + alpha_ema * color_hist
            norm = np.sum(self.color_hist)
            if norm > 0:
                self.color_hist /= norm
        self.last_seen_frame = frame_idx
        self.hits += 1


class VideoSessionState:
    """Quản lý trạng thái tracking và LRU Ring Buffer cho 1 video session"""
    def __init__(self, video_id: str, max_cached_frames: int = 20):
        self.video_id = video_id
        self.active_tracks: Dict[str, TrackedObject] = {}
        self.retired_tracks: Dict[str, TrackedObject] = {}
        self.category_counters: Dict[str, int] = {}
        self.current_frame_idx: int = 0
        self.frame_buffer = deque(maxlen=max_cached_frames)


class PersistentObjectTracker:
    """
    Hệ thống Video Multi-Object Tracking & Visual Re-Identification (Re-ID).
    Duy trì ID duy nhất (VD: obj_jacket_01, obj_sneakers_01) cho cùng 1 vật thể
    hoặc con người qua các frame liên tiếp trong cùng một video/livestream.
    
    Tích hợp LRU Ring Buffer giải phóng RAM tự động, chống rò rỉ bộ nhớ (OOM)
    khi người dùng lướt web hoặc xem video TikTok FPS cao trong thời gian dài.
    """
    def __init__(
        self,
        max_cached_frames: int = 20,
        max_inactive_frames: int = 6,
        iou_weight: float = 0.45,
        color_weight: float = 0.35,
        cat_weight: float = 0.20,
        match_threshold: float = 0.35
    ):
        self.max_cached_frames = max_cached_frames
        self.max_inactive_frames = max_inactive_frames
        self.iou_weight = iou_weight
        self.color_weight = color_weight
        self.cat_weight = cat_weight
        self.match_threshold = match_threshold
        self.sessions: Dict[str, VideoSessionState] = {}

    @staticmethod
    def extract_color_descriptor(img_bgr: np.ndarray, mask: Optional[np.ndarray], bbox: np.ndarray) -> np.ndarray:
        """
        Trích xuất Color Histogram chuẩn hóa (HSV) đại diện cho ngoại hình (Appearance Re-ID)
        với khả năng bất biến dưới sự thay đổi nhẹ của góc nhìn và ánh sáng.
        """
        h, w = img_bgr.shape[:2]
        x1, y1, x2, y2 = [int(round(float(v))) for v in bbox[:4]]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return np.zeros((16 * 8,), dtype=np.float32)

        crop_bgr = img_bgr[y1:y2, x1:x2]
        crop_hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)

        crop_mask = None
        if mask is not None:
            if mask.shape[:2] != (h, w):
                mask = cv2.resize(mask.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)
            m_crop = (mask[y1:y2, x1:x2] > 0).astype(np.uint8)
            if np.sum(m_crop) > 10:
                crop_mask = m_crop * 255

        # 16 bins cho Hue (0-180), 8 bins cho Saturation (0-256) -> 128 đặc trưng
        hist = cv2.calcHist([crop_hsv], [0, 1], crop_mask, [16, 8], [0, 180, 0, 256])
        cv2.normalize(hist, hist, alpha=1.0, norm_type=cv2.NORM_L1)
        return hist.flatten().astype(np.float32)

    @staticmethod
    def compare_color_histograms(histA: np.ndarray, histB: np.ndarray) -> float:
        """So khớp tương đồng phân bố màu sắc bằng Histogram Intersection [0.0, 1.0]"""
        if histA is None or histB is None or histA.size == 0 or histB.size == 0:
            return 0.0
        sim = float(cv2.compareHist(histA.astype(np.float32), histB.astype(np.float32), cv2.HISTCMP_INTERSECT))
        return max(0.0, min(1.0, sim))

    def update(
        self,
        video_id: Optional[str],
        frame_idx: Optional[int],
        img_bgr: np.ndarray,
        candidates: List[Dict[str, Any]],
        compute_iou_fn
    ) -> List[Dict[str, Any]]:
        vid = str(video_id) if video_id else "default_video_session"
        if vid not in self.sessions:
            self.sessions[vid] = VideoSessionState(vid, max_cached_frames=self.max_cached_frames)
        session = self.sessions[vid]

        if frame_idx is not None:
            current_idx = int(frame_idx)
            session.current_frame_idx = max(session.current_frame_idx, current_idx)
        else:
            session.current_frame_idx += 1
            current_idx = session.current_frame_idx

        # 1. Trích xuất đặc trưng màu sắc cho từng ứng viên trong frame
        cand_descriptors = []
        for cand in candidates:
            hist = self.extract_color_descriptor(img_bgr, cand.get("mask"), cand["bbox"])
            cand_descriptors.append(hist)

        # 2. Xây dựng ma trận Affinity giữa Candidates và Active Tracks
        active_track_ids = list(session.active_tracks.keys())
        matched_cand_indices = set()
        matched_track_ids = set()

        if active_track_ids and candidates:
            pair_affinities = []
            for c_idx, cand in enumerate(candidates):
                c_hist = cand_descriptors[c_idx]
                c_bbox = cand["bbox"]
                c_cat = cand["category"]
                c_grp = cand.get("semantic_group", "general")

                for t_id in active_track_ids:
                    track = session.active_tracks[t_id]
                    iou, iomina = compute_iou_fn(c_bbox, track.last_bbox)
                    color_sim = self.compare_color_histograms(c_hist, track.color_hist)
                    cat_match = 1.0 if c_cat == track.category else (0.5 if c_grp == track.semantic_group else 0.0)

                    effective_spatial = max(iou, iomina * 0.75)
                    affinity = (
                        self.iou_weight * effective_spatial +
                        self.color_weight * color_sim +
                        self.cat_weight * cat_match
                    )

                    if c_cat == track.category and (iou > 0.18 or iomina > 0.40):
                        affinity = max(affinity, 0.50 + 0.50 * effective_spatial)

                    pair_affinities.append((affinity, c_idx, t_id, iou, iomina, color_sim))

            pair_affinities.sort(key=lambda x: x[0], reverse=True)

            for aff, c_idx, t_id, iou, iomina, csim in pair_affinities:
                if c_idx in matched_cand_indices or t_id in matched_track_ids:
                    continue
                cand_cat = candidates[c_idx]["category"]
                trk_cat = session.active_tracks[t_id].category
                is_same_cat = (cand_cat == trk_cat)
                
                if aff >= self.match_threshold or (is_same_cat and (iou >= 0.18 or iomina >= 0.40)) or (iou >= 0.20 and csim >= 0.35):
                    matched_cand_indices.add(c_idx)
                    matched_track_ids.add(t_id)

                    track = session.active_tracks[t_id]
                    track.update(
                        bbox=candidates[c_idx]["bbox"],
                        mask=candidates[c_idx]["mask"],
                        color_hist=cand_descriptors[c_idx],
                        frame_idx=current_idx
                    )
                    candidates[c_idx]["object_id"] = track.track_id
                    candidates[c_idx]["persistent_track_id"] = track.track_id
                    candidates[c_idx]["tracking_hits"] = track.hits
                    candidates[c_idx]["cached_track"] = track

        # 3. Cấp phát Canonical ID mới cho Candidates chưa khớp (Vật thể mới xuất hiện)
        for c_idx, cand in enumerate(candidates):
            if c_idx in matched_cand_indices:
                continue
            cat = cand["category"]
            cnt = session.category_counters.get(cat, 0) + 1
            session.category_counters[cat] = cnt
            new_id = f"obj_{cat}_{cnt:02d}"

            new_track = TrackedObject(
                track_id=new_id,
                category=cat,
                semantic_group=cand.get("semantic_group", "general"),
                bbox=cand["bbox"],
                mask=cand["mask"],
                color_hist=cand_descriptors[c_idx],
                frame_idx=current_idx
            )
            session.active_tracks[new_id] = new_track
            cand["object_id"] = new_id
            cand["persistent_track_id"] = new_id
            cand["tracking_hits"] = 1
            cand["cached_track"] = new_track

        # 4. Quản lý vòng đời Tracks & Giải phóng RAM (LRU Eviction)
        stale_track_ids = []
        for t_id, track in session.active_tracks.items():
            if (current_idx - track.last_seen_frame) > self.max_inactive_frames:
                stale_track_ids.append(t_id)

        for t_id in stale_track_ids:
            track = session.active_tracks.pop(t_id)
            track.last_mask = None  # Giải phóng mảng numpy mask nặng hạt để chống tràn RAM
            session.retired_tracks[t_id] = track
            if len(session.retired_tracks) > 50:
                oldest_retired = min(session.retired_tracks.keys(), key=lambda k: session.retired_tracks[k].last_seen_frame)
                session.retired_tracks.pop(oldest_retired, None)

        session.frame_buffer.append(current_idx)
        return candidates


class SAM3Engine:
    """
    TAP AI - High-Performance Interactive Segmentation Engine
    (Meta SAM 3 Teacher + Student YOLO-Seg + Transparent WebP Processing)
    """

    # Danh sách các Concept Prompts mở rộng toàn diện cho E-Commerce & Đồ dùng cá nhân
    SAM3_CONCEPT_PROMPTS = [
        # Trang phục phần trên (Tops & Outerwear)
        "sweater", "turtleneck sweater", "cardigan", "hoodie", "sweatshirt",
        "jacket", "coat", "blazer", "trench coat", "vest",
        "shirt", "t-shirt", "top", "blouse", "crop top", "suit",
        # Trang phục phần dưới (Bottoms)
        "pants", "jeans", "trousers", "sweatpants", "shorts", "skirt", "leggings", "cargo pants",
        # Toàn thân (Full Body)
        "dress", "jumpsuit",
        # Túi xách & Balo (Bags)
        "handbag", "shoulder bag", "crossbody bag", "tote bag", "backpack", "clutch", "purse", "wallet", "bag",
        # Giày dép (Footwear)
        "shoes", "sneakers", "boots", "sandals", "heels", "loafers", "slippers",
        # Mũ nón & Kính mắt (Headwear & Eyewear)
        "hat", "cap", "beanie", "sunglasses", "glasses",
        # Phụ kiện & Trang sức (Accessories & Jewelry)
        "watch", "smartwatch", "belt", "scarf", "tie", "necklace", "earrings", "bracelet", "ring",
        # Thiết bị công nghệ (Tech & Electronics)
        "cell phone", "smartphone", "laptop", "tablet", "headphones", "earphones",
        # Đồ dùng cá nhân (Personal & Beauty)
        "perfume", "cosmetics", "water bottle", "cup", "mug"
    ]

    # Bảng ánh xạ danh mục chuẩn (Canonical Name Mapping)
    CANONICAL_MAP = {
        "turtleneck sweater": "sweater", "sweater": "sweater", "cardigan": "cardigan",
        "hoodie": "hoodie", "sweatshirt": "hoodie", "blazer": "blazer", "trench coat": "coat",
        "shirt": "shirt", "t-shirt": "t-shirt", "jacket": "jacket", "coat": "coat",
        "top": "top", "blouse": "blouse", "crop top": "crop top", "vest": "vest", "suit": "suit",
        "skirt": "skirt", "dress": "dress", "jumpsuit": "jumpsuit",
        "pants": "pants", "jeans": "jeans", "shorts": "shorts", "trousers": "pants",
        "sweatpants": "sweatpants", "leggings": "leggings", "cargo pants": "pants",
        "handbag": "handbag", "shoulder bag": "shoulder bag", "crossbody bag": "crossbody bag",
        "tote bag": "tote bag", "backpack": "backpack", "clutch": "clutch", "purse": "handbag", "bag": "bag",
        "shoes": "shoes", "sneakers": "sneakers", "boots": "boots", "sandals": "sandals",
        "heels": "heels", "loafers": "loafers", "slippers": "slippers",
        "cell phone": "smartphone", "smartphone": "smartphone",
        "hat": "hat", "cap": "hat", "beanie": "hat", "sunglasses": "sunglasses", "glasses": "sunglasses",
        "watch": "watch", "smartwatch": "watch", "belt": "belt", "scarf": "scarf", "tie": "tie",
        "necklace": "necklace", "earrings": "earrings", "bracelet": "bracelet", "ring": "ring",
        "laptop": "laptop", "tablet": "tablet", "headphones": "headphones", "earphones": "headphones",
        "perfume": "perfume", "cosmetics": "cosmetics", "water bottle": "water bottle", "cup": "cup", "mug": "cup"
    }

    # Gom nhóm ngữ nghĩa phân cấp (Semantic Hierarchy)
    SEMANTIC_GROUPS = {
        "sweater": "upper_body", "cardigan": "upper_body", "hoodie": "upper_body",
        "shirt": "upper_body", "t-shirt": "upper_body", "top": "upper_body", "blouse": "upper_body",
        "crop top": "upper_body", "vest": "upper_body",
        "jacket": "outerwear", "coat": "outerwear", "blazer": "outerwear", "suit": "outerwear",
        "skirt": "lower_body", "pants": "lower_body", "jeans": "lower_body", "shorts": "lower_body",
        "sweatpants": "lower_body", "leggings": "lower_body",
        "dress": "full_body", "jumpsuit": "full_body",
        "handbag": "bag", "backpack": "bag", "shoulder bag": "bag", "crossbody bag": "bag",
        "tote bag": "bag", "clutch": "bag", "bag": "bag",
        "shoes": "footwear", "sneakers": "footwear", "boots": "footwear", "sandals": "footwear",
        "heels": "footwear", "loafers": "footwear", "slippers": "footwear",
        "smartphone": "device", "laptop": "device", "tablet": "device", "headphones": "device",
        "hat": "headwear", "sunglasses": "eyewear", "watch": "wrist",
        "belt": "accessory", "scarf": "accessory", "tie": "accessory",
        "necklace": "jewelry", "earrings": "jewelry", "bracelet": "jewelry", "ring": "jewelry",
        "perfume": "beauty", "cosmetics": "beauty", "water bottle": "lifestyle", "cup": "lifestyle"
    }

    def __init__(
        self,
        hf_token: Optional[str] = None,
        sam3_repo: str = "facebook/sam3",
        sam3_fallback_repo: str = "jetjodh/sam3",
        student_checkpoint: Optional[str] = None,
        device: Optional[str] = None,
        use_fp16: bool = True,
        contour_epsilon_factor: float = 0.0035,
        rag_api_url: Optional[str] = None,
        output_dir: str = "outputs/sam_crops"
    ):
        """
        Khởi tạo Engine xử lý ảnh và phân đoạn tương tác.
        Hỗ trợ 3 tầng mô hình:
          1. Meta SAM 3 Teacher (khi có GPU CUDA và HuggingFace Token).
          2. Student YOLO-Seg (YOLOv8/v11-seg chạy cực nhanh trên CPU/GPU local).
          3. Computer Vision Fallback (Contours + GrabCut luôn hoạt động 100% không lo lỗi thiếu model).
        """
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.contour_epsilon_factor = contour_epsilon_factor
        self.rag_api_url = rag_api_url or os.getenv("RAG_API_URL")

        # Thiết lập thiết bị xử lý (ưu tiên CUDA nếu có)
        if device:
            self.device = device
        else:
            env_dev = os.getenv("DEVICE", "").lower()
            if env_dev in ["cuda", "cpu"]:
                self.device = env_dev
            else:
                try:
                    import torch
                    self.device = "cuda" if torch.cuda.is_available() else "cpu"
                except ImportError:
                    self.device = "cpu"

        self.use_fp16 = use_fp16 and (self.device == "cuda")
        logger.info(f"🚀 [SAM 3 Engine] Khởi tạo thiết bị: {self.device.upper()} (FP16: {self.use_fp16})")

        # Quản lý HuggingFace Token
        self.hf_token = hf_token or os.getenv("HF_TOKEN")
        if self.hf_token:
            try:
                from huggingface_hub import login
                login(token=self.hf_token, add_to_git_credential=False)
                logger.info("🔑 Đã kết nối HuggingFace Token thành công.")
            except Exception as e:
                logger.warning(f"Không thể đăng nhập HuggingFace: {e}")

        # Trạng thái các tầng mô hình
        self.sam3_loaded = False
        self.sam3_model = None
        self.sam3_processor = None
        self.text_inputs_cache: Dict[str, Any] = {}

        self.student_loaded = False
        self.student_model = None
        self.is_open_vocabulary = False
        self.active_vocabulary: List[str] = list(self.SAM3_CONCEPT_PROMPTS)

        # Bộ điều phối Multi-Object Tracking & Visual Re-ID kèm LRU Ring Buffer
        self.tracker = PersistentObjectTracker(
            max_cached_frames=20,
            max_inactive_frames=6,
            iou_weight=0.45,
            color_weight=0.35,
            cat_weight=0.20,
            match_threshold=0.35
        )

        # Bộ nhớ đệm RAM cho Frame hiện tại (Dùng cho Hover / Hit-test siêu tốc)
        self._cached_image_hash: Optional[str] = None
        self._cached_img_bgr: Optional[np.ndarray] = None
        self._cached_candidates: List[Dict[str, Any]] = []

        # Tầng 1: Thử nạp Meta SAM 3 nếu chạy GPU
        if self.device == "cuda":
            self._try_load_sam3(sam3_repo, sam3_fallback_repo)

        # Tầng 2: Nạp Student Model (YOLO-seg) cho CPU hoặc phụ trợ
        self._try_load_student(student_checkpoint)

        logger.info(
            f"✅ [SAM 3 Engine] Đã nạp xong: Teacher SAM 3={self.sam3_loaded}, "
            f"Student Model={self.student_loaded}, Thư mục crops='{self.output_dir}'"
        )

    def _try_load_sam3(self, sam3_repo: str, fallback_repo: str):
        """Thử nạp Meta SAM 3 Teacher Model qua HuggingFace transformers"""
        try:
            import torch
            from transformers import Sam3Processor, Sam3Model
            self.dtype = torch.float16 if self.use_fp16 else torch.float32

            for repo in [sam3_repo, fallback_repo]:
                try:
                    logger.info(f"Đang tải Teacher SAM 3 từ repo '{repo}'...")
                    self.sam3_processor = Sam3Processor.from_pretrained(repo, token=self.hf_token)
                    self.sam3_model = Sam3Model.from_pretrained(
                        repo,
                        torch_dtype=self.dtype,
                        token=self.hf_token
                    ).to(self.device).eval()
                    self.sam3_loaded = True
                    logger.info(f"✅ Đã nạp thành công Teacher SAM 3 từ: {repo}")

                    # Pre-cache text inputs cho các concept prompts
                    for p in self.SAM3_CONCEPT_PROMPTS:
                        txt_in = self.sam3_processor(text=[p], return_tensors="pt")
                        self.text_inputs_cache[p] = {k: v.to(self.device) for k, v in txt_in.items()}
                    return
                except Exception as ex_repo:
                    logger.warning(f"Không thể nạp từ repo '{repo}': {ex_repo}")

        except Exception as e:
            logger.info(f"Môi trường chưa sẵn sàng cho SAM 3 Teacher ({e}). Sẽ sử dụng Student YOLO-Seg.")

    def _try_load_student(self, student_checkpoint: Optional[str]):
        """Thử nạp Student Model (Ưu tiên Open-Vocabulary YOLO-World, hoặc YOLO-Seg)"""
        try:
            from ultralytics import YOLO

            # Danh sách các đường dẫn tìm kiếm checkpoint
            search_paths = []
            if student_checkpoint:
                search_paths.append(student_checkpoint)
            
            # Kiểm tra trong thư mục hiện tại, backend/ và thư mục gốc
            # Ưu tiên YOLO-World Open-Vocabulary để mở rộng từ vựng không giới hạn
            common_names = [
                "yolov8s-world.pt",
                "yolov8m-worldv2.pt",
                "yolov8s-worldv2.pt",
                "yolow-v8s.pt",
                "yolov8n-seg.pt",
                "yolo11n-seg.pt",
                "yoloe-26s-seg.pt"
            ]
            for name in common_names:
                search_paths.extend([
                    name,
                    os.path.join("backend", name),
                    os.path.join("..", name),
                    os.path.join(os.path.dirname(__file__), "..", name),
                    os.path.join(os.path.dirname(__file__), "..", "..", name),
                ])

            # Lọc các file thực sự tồn tại trước
            valid_existing = [p for p in search_paths if os.path.exists(p)]
            targets = valid_existing if valid_existing else ["yolov8s-world.pt", "yolov8n-seg.pt"]

            for target in targets:
                try:
                    logger.info(f"Đang nạp Student Model từ '{target}'...")
                    self.student_model = YOLO(target)
                    self.student_loaded = True

                    # Kiểm tra và kích hoạt Open-Vocabulary nếu là mô hình YOLO-World
                    if hasattr(self.student_model, "set_classes"):
                        self.is_open_vocabulary = True
                        try:
                            self.student_model.set_classes(self.SAM3_CONCEPT_PROMPTS)
                            self.active_vocabulary = list(self.SAM3_CONCEPT_PROMPTS)
                            logger.info(
                                f"🌐 [Open-Vocabulary YOLO-World] Đã nạp thành công và kích hoạt "
                                f"{len(self.SAM3_CONCEPT_PROMPTS)} khái niệm từ vựng: {target}"
                            )
                        except Exception as ex_vocab:
                            logger.warning(f"Không thể đặt từ vựng mở cho {target}: {ex_vocab}")
                    else:
                        logger.info(f"✅ Đã nạp thành công Student Model: {target}")
                    return
                except Exception as ex_yolo:
                    logger.warning(f"Thử nạp {target} thất bại: {ex_yolo}")

        except Exception as e:
            logger.warning(f"Không thể khởi tạo Ultralytics YOLO ({e}). Sẽ dùng Vision Fallback Engine.")

    def set_active_vocabulary(self, vocabulary: List[str]):
        """Cập nhật danh sách từ vựng mở (Open-Vocabulary) linh hoạt theo yêu cầu."""
        if not vocabulary:
            return
        clean_vocab = [str(v).strip().lower() for v in vocabulary if str(v).strip()]
        if not clean_vocab:
            return
        self.active_vocabulary = clean_vocab
        if self.student_loaded and self.student_model is not None and hasattr(self.student_model, "set_classes"):
            try:
                self.student_model.set_classes(clean_vocab)
                logger.info(f"🌐 [Open-Vocabulary] Đã cập nhật {len(clean_vocab)} từ vựng mới: {clean_vocab[:5]}...")
            except Exception as ex:
                logger.warning(f"Lỗi khi cập nhật từ vựng mở: {ex}")

    # =========================================================================
    # TIỆN ÍCH DỮ LIỆU & JSON SANITIZER
    # =========================================================================
    @classmethod
    def sanitize_for_json(cls, obj: Any) -> Any:
        """
        Khử triệt để kiểu dữ liệu NumPy / Torch / Bytes để serialization JSON an toàn 100%,
        tránh lỗi: Object of type int64 / float32 is not JSON serializable.
        """
        if isinstance(obj, dict):
            return {str(k): cls.sanitize_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple, set)):
            return [cls.sanitize_for_json(v) for v in obj]
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, np.ndarray):
            return cls.sanitize_for_json(obj.tolist())
        try:
            import torch
            if torch.is_tensor(obj):
                return cls.sanitize_for_json(obj.detach().cpu().tolist())
        except ImportError:
            pass
        return obj

    @staticmethod
    def compute_iou_and_iomina(boxA: np.ndarray, boxB: np.ndarray) -> Tuple[float, float]:
        """
        Tính toán IoU (Intersection over Union) và IoMinA (Intersection over Min Area)
        để khử và gộp các hộp lồng nhau (Containment NMS).
        """
        xA, yA = max(float(boxA[0]), float(boxB[0])), max(float(boxA[1]), float(boxB[1]))
        xB, yB = min(float(boxA[2]), float(boxB[2])), min(float(boxA[3]), float(boxB[3]))
        inter_area = max(0.0, xB - xA) * max(0.0, yB - yA)
        if inter_area <= 0:
            return 0.0, 0.0
        areaA = max(1.0, (float(boxA[2]) - float(boxA[0])) * (float(boxA[3]) - float(boxA[1])))
        areaB = max(1.0, (float(boxB[2]) - float(boxB[0])) * (float(boxB[3]) - float(boxB[1])))
        iou = float(inter_area / (areaA + areaB - inter_area))
        iomina = float(inter_area / min(areaA, areaB))
        return iou, iomina

    @staticmethod
    def point_in_bbox(px: int, py: int, bbox: np.ndarray, pad: int = 8) -> bool:
        """Kiểm tra điểm (px, py) có nằm trong bbox mở rộng hay không."""
        return bool(
            (float(bbox[0]) - pad <= px <= float(bbox[2]) + pad) and
            (float(bbox[1]) - pad <= py <= float(bbox[3]) + pad)
        )

    # =========================================================================
    # CORE CV: BÓC TÁCH ẢNH .WEBP VỚI NỀN TRONG SUỐT (ALPHA CHANNEL 4 KÊNH)
    # =========================================================================
    def extract_transparent_webp(
        self,
        frame_bgr: np.ndarray,
        binary_mask: np.ndarray,
        bbox: np.ndarray,
        output_webp_path: Optional[str] = None,
        padding_pct: float = 0.05,
        feather_radius: int = 2,
        dark_pixel_floor: int = 12,
        webp_quality: int = 95
    ) -> Tuple[str, float, str, str]:
        """
        Bóc tách vật thể từ frame ảnh với NỀN TRONG SUỐT (BGRA, Alpha=0 cho background)
        xuất ra file .webp chất lượng cao và chuỗi Base64 Data URL.
        
        Các cải tiến đặc thù cho dự án TapAI:
          1. Padding thông minh: giữ trọn vẹn chi tiết mép vải, viền áo, quai túi.
          2. Anti-aliased Soft Feathering: làm mượt mép cắt trên kênh Alpha bằng Gaussian Filter,
             loại bỏ viền răng cưa sắc nhọn khi render đè lên UI Extension.
          3. Pixel Floor Enhancement: nâng ngưỡng sàn màu tối (>=12) để đồ màu đen không bị mất chi tiết.
          4. Định dạng WebP nén vượt trội: nhẹ hơn PNG từ 60% - 80% mà giữ trọn vẹn độ trong suốt,
             giúp truyền tải API tới Frontend mượt mà không nghẽn mạng.

        Returns:
            Tuple[output_path, quality_score, base64_webp, data_url_webp]
        """
        h, w = int(frame_bgr.shape[0]), int(frame_bgr.shape[1])
        if binary_mask.shape[:2] != (h, w):
            binary_mask = cv2.resize(binary_mask.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)

        # 1. Tính toán bounding box có padding
        bx1, by1, bx2, by2 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
        bw, bh = max(1.0, bx2 - bx1), max(1.0, by2 - by1)
        pad_x = int(bw * padding_pct)
        pad_y = int(bh * padding_pct)

        x1 = max(0, int(bx1) - pad_x)
        y1 = max(0, int(by1) - pad_y)
        x2 = min(w, int(bx2) + pad_x)
        y2 = min(h, int(by2) + pad_y)

        if x2 <= x1 or y2 <= y1:
            return "", 0.0, "", ""

        # 2. Cắt vùng ảnh gốc và mask tương ứng
        crop_bgr = frame_bgr[y1:y2, x1:x2].copy()
        crop_mask_bin = (binary_mask[y1:y2, x1:x2] > 0).astype(np.uint8)

        # Tăng nhẹ sàn màu tối để trang phục đen giữ được chi tiết bề mặt
        crop_boosted = np.maximum(crop_bgr, dark_pixel_floor)

        # 3. Tạo kênh Alpha trong suốt mượt mà (Anti-aliased Soft Feathering)
        alpha = (crop_mask_bin * 255).astype(np.uint8)

        if feather_radius > 0 and crop_mask_bin.sum() > 50:
            # Tạo dải viền (Edge band) bằng hiệu giãn - co (Morphological gradient)
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            dilated = cv2.dilate(alpha, kernel, iterations=1)
            eroded = cv2.erode(alpha, kernel, iterations=1)
            edge_band = (dilated > 0) & (eroded < 255)

            # Làm mượt chuyển tiếp chỉ ở mép viền, giữ nguyên độ đục 100% bên trong vật thể
            blurred_alpha = cv2.GaussianBlur(alpha, (feather_radius * 2 + 1, feather_radius * 2 + 1), 0.8)
            alpha[edge_band] = blurred_alpha[edge_band]

        # 4. Ghép 4 kênh B, G, R, Alpha (BGRA)
        b_ch, g_ch, r_ch = cv2.split(crop_boosted)
        # Xóa sạch màu nền ngoài mask thành 0 để khi render WebP không bị bóng màu lem
        b_ch[alpha == 0] = 0
        g_ch[alpha == 0] = 0
        r_ch[alpha == 0] = 0
        crop_bgra = cv2.merge([b_ch, g_ch, r_ch, alpha])

        # 5. Lưu ra file .webp
        if not output_webp_path:
            filename = f"crop_{int(time.time() * 1000)}_{np.random.randint(100, 999)}.webp"
            output_webp_path = os.path.join(self.output_dir, filename)

        if not output_webp_path.lower().endswith(".webp"):
            output_webp_path = os.path.splitext(output_webp_path)[0] + ".webp"

        # Ghi file WebP qua OpenCV với chất lượng cao
        success = False
        try:
            success = cv2.imwrite(
                output_webp_path,
                crop_bgra,
                [int(cv2.IMWRITE_WEBP_QUALITY), webp_quality]
            )
        except Exception as e:
            logger.debug(f"OpenCV webp write fallback sang PIL: {e}")

        if not success or not os.path.exists(output_webp_path):
            # Fallback lưu bằng Pillow nếu build OpenCV không có sẵn webp encoder
            pil_rgba = PILImage.fromarray(cv2.cvtColor(crop_bgra, cv2.COLOR_BGRA2RGBA))
            pil_rgba.save(output_webp_path, format="WEBP", quality=webp_quality)

        # 6. Mã hóa Base64 WebP phục vụ truyền trực tiếp qua API
        base64_webp = ""
        try:
            encode_ok, buf_webp = cv2.imencode(".webp", crop_bgra, [int(cv2.IMWRITE_WEBP_QUALITY), webp_quality])
            if encode_ok:
                base64_webp = base64.b64encode(buf_webp).decode("utf-8")
        except Exception:
            pass

        if not base64_webp and os.path.exists(output_webp_path):
            with open(output_webp_path, "rb") as f:
                base64_webp = base64.b64encode(f.read()).decode("utf-8")

        data_url_webp = f"data:image/webp;base64,{base64_webp}" if base64_webp else ""

        # Đánh giá điểm chất lượng bóc tách (Quality Score)
        mask_pixels = float(np.sum(crop_mask_bin > 0))
        total_pixels = float(crop_mask_bin.size)
        occupancy = (mask_pixels / total_pixels) if total_pixels > 0 else 0.5
        quality_score = min(1.0, max(0.5, 0.6 + occupancy * 0.4)) * 100.0

        return output_webp_path, quality_score, base64_webp, data_url_webp

    # =========================================================================
    # RÚT GỌN ĐA GIÁC CONTOUR CHO WEBGL 60 FPS
    # =========================================================================
    @staticmethod
    def mask_to_normalized_contour(
        binary_mask: np.ndarray,
        width: int,
        height: int,
        epsilon_factor: float = 0.0035
    ) -> Tuple[List[List[float]], np.ndarray]:
        """
        Chuyển mask nhị phân thành tập đỉnh đa giác viền sáng (WebGL 60 FPS Contour)
        chuẩn hóa [0.0, 1.0]. Ứng dụng cv2.approxPolyDP giảm số đỉnh về ~15-30 điểm/vật thể.
        """
        clean_pts: List[List[float]] = []
        closed_mask = binary_mask.copy().astype(np.uint8)

        # Đóng các lỗ hổng nhỏ trong mask bằng phép Morphological Close
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        closed_mask = cv2.morphologyEx(closed_mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(closed_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return clean_pts, closed_mask

        # Chọn contour lớn nhất
        largest_cnt = max(contours, key=cv2.contourArea)
        peri = cv2.arcLength(largest_cnt, True)
        epsilon = max(1.5, peri * epsilon_factor)
        approx = cv2.approxPolyDP(largest_cnt, epsilon, True)

        pts = approx.reshape(-1, 2)
        # Giới hạn tối đa 35 đỉnh để đảm bảo tốc độ render WebGL 60FPS
        if len(pts) > 35:
            step = int(np.ceil(len(pts) / 30))
            pts = pts[::step]

        for p in pts:
            nx = float(round(max(0.0, min(float(width), float(p[0]))) / float(width), 4))
            ny = float(round(max(0.0, min(float(height), float(p[1]))) / float(height), 4))
            clean_pts.append([nx, ny])

        return clean_pts, closed_mask

    @staticmethod
    def normalize_bbox(bbox: np.ndarray, width: int, height: int) -> List[float]:
        """Chuẩn hóa bbox pixel sang [x1, y1, x2, y2] trong khoảng [0.0, 1.0]."""
        x1, y1, x2, y2 = [float(v) for v in bbox[:4]]
        return [
            float(round(max(0.0, x1) / float(width), 4)),
            float(round(max(0.0, y1) / float(height), 4)),
            float(round(min(float(width), x2) / float(width), 4)),
            float(round(min(float(height), y2) / float(height), 4)),
        ]

    # =========================================================================
    # BỘ NHỚ ĐỆM PRE-COMPUTED CHO FRAME MÀN HÌNH / VIDEO
    # =========================================================================
    def warmup_frame_cache(
        self,
        img_bgr: np.ndarray,
        cache_key: Optional[str] = None,
        custom_vocabulary: Optional[List[str]] = None,
        video_id: Optional[str] = None,
        frame_index: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Quét trước toàn bộ frame màn hình và nạp các candidate vào RAM (hỗ trợ Open-Vocabulary & Persistent Tracking).
        Khi người dùng di chuột hoặc click, hit-test phản hồi ngay trong < 5ms.
        """
        t0 = time.perf_counter()
        h, w = int(img_bgr.shape[0]), int(img_bgr.shape[1])
        key = cache_key or f"frame_{h}x{w}_{int(time.time())}"

        self._cached_image_hash = key
        self._cached_img_bgr = img_bgr.copy()

        # Quét phân tách tất cả vật thể (hỗ trợ Open-Vocabulary)
        masks, bboxes, categories, confs = self._segment_all_objects(
            img_bgr,
            custom_vocabulary=custom_vocabulary
        )
        raw_candidates = []

        for idx, (m, b, c, s) in enumerate(zip(masks, bboxes, categories, confs)):
            contour_norm, refined_m = self.mask_to_normalized_contour(m, w, h, self.contour_epsilon_factor)
            raw_candidates.append({
                "mask": refined_m,
                "bbox": b,
                "category": str(c),
                "semantic_group": str(self.SEMANTIC_GROUPS.get(str(c), "general")),
                "conf": float(s),
                "contour_norm": contour_norm,
                "bbox_norm": self.normalize_bbox(b, w, h)
            })

        # Cập nhật Multi-Object Tracker & Visual Re-ID để duy trì ID xuyên suốt
        self._cached_candidates = self.tracker.update(
            video_id=video_id,
            frame_idx=frame_index,
            img_bgr=img_bgr,
            candidates=raw_candidates,
            compute_iou_fn=self.compute_iou_and_iomina
        )

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        logger.info(f"⚡ [CACHE WARMUP] Phát hiện {len(self._cached_candidates)} vật thể trong {elapsed_ms}ms")
        return {
            "status": "cached",
            "cache_key": key,
            "resolution": {"width": w, "height": h},
            "detected_objects_count": len(self._cached_candidates),
            "warmup_time_ms": elapsed_ms
        }

    # =========================================================================
    # QUÉT TOÀN MÀN HÌNH REALTIME (SCREEN SCAN)
    # =========================================================================
    def scan_screen_objects(
        self,
        image_source: Union[str, np.ndarray, PILImage.Image],
        extract_all_webp: bool = True,
        custom_vocabulary: Optional[List[str]] = None,
        video_id: Optional[str] = None,
        frame_index: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Quét và phân tách toàn diện các vật thể trên màn hình người dùng (Open-Vocabulary Screen Scan).
        Trả về danh sách các items kèm BBox, Polygon Contour, và ảnh WebP trong suốt.
        """
        t0 = time.perf_counter()

        if custom_vocabulary:
            self.set_active_vocabulary(custom_vocabulary)

        # Chuẩn hóa ảnh đầu vào sang BGR NumPy
        if isinstance(image_source, str):
            img_bgr = cv2.imread(image_source)
            if img_bgr is None:
                raise ValueError(f"Không thể đọc ảnh từ đường dẫn: {image_source}")
            image_name = os.path.splitext(os.path.basename(image_source))[0]
        elif isinstance(image_source, PILImage.Image):
            rgb = np.array(image_source.convert("RGB"))
            img_bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            image_name = f"scan_{int(time.time())}"
        else:
            img_bgr = image_source
            image_name = f"scan_{int(time.time())}"

        h, w = int(img_bgr.shape[0]), int(img_bgr.shape[1])
        self.warmup_frame_cache(
            img_bgr,
            cache_key=image_name,
            custom_vocabulary=custom_vocabulary,
            video_id=video_id,
            frame_index=frame_index
        )

        detected_items = []
        for cand in self._cached_candidates:
            obj_id = cand["object_id"]
            persistent_id = cand.get("persistent_track_id", obj_id)
            hits = cand.get("tracking_hits", 1)
            cached_track = cand.get("cached_track")
            cat = cand["category"]
            b = cand["bbox"]
            m = cand["mask"]

            webp_path = ""
            base64_webp = ""
            data_url_webp = ""
            quality_score = 0.0

            if extract_all_webp:
                out_path = os.path.join(self.output_dir, f"{image_name}_{obj_id}.webp")
                webp_path, quality_score, base64_webp, data_url_webp = self.extract_transparent_webp(
                    frame_bgr=img_bgr,
                    binary_mask=m,
                    bbox=b,
                    output_webp_path=out_path
                )
                if cached_track is not None:
                    cached_track.crop_webp_path = webp_path
                    cached_track.crop_image_base64_webp = base64_webp
                    cached_track.crop_image_data_url_webp = data_url_webp
                    cached_track.quality_score = quality_score

            detected_items.append({
                "object_id": obj_id,
                "persistent_track_id": persistent_id,
                "tracking_hits": hits,
                "category_hint": cat,
                "semantic_group": cand["semantic_group"],
                "confidence": round(float(cand["conf"]), 3),
                "quality_score": round(float(quality_score), 1),
                "bbox_pixel": [int(round(float(v))) for v in b[:4]],
                "bbox_norm": cand["bbox_norm"],
                "contour_norm": cand["contour_norm"],
                "crop_webp_path": str(webp_path),
                "crop_image_base64_webp": str(base64_webp),
                "crop_image_data_url_webp": str(data_url_webp)
            })

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

        # Xuất metadata theo hợp đồng dữ liệu chuẩn với Frontend
        metadata_contract = self.export_tap_ai_metadata(
            image_name=image_name,
            resolution=[w, h],
            detected_items=detected_items
        )

        return self.sanitize_for_json({
            "status": "success",
            "event_type": "screen_scan_segmentation",
            "processing_time_ms": elapsed_ms,
            "resolution": {"width": w, "height": h},
            "total_detected": len(detected_items),
            "items": detected_items,
            "tap_ai_metadata": metadata_contract
        })

    def export_tap_ai_metadata(
        self,
        image_name: str,
        resolution: List[int],
        detected_items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Chuẩn hóa kết quả theo đúng 100% Data Contract của metadata_sample.json
        để phục vụ Frontend Side Panel và Video Timeline Canvas/WebGL.
        """
        from datetime import datetime
        w, h = resolution[0], resolution[1]

        category_vietnamese = {
            # Tops & Outerwear
            "sweater": ("Áo len dệt kim", "Thời trang > Áo len & Cardigan > Áo len"),
            "cardigan": ("Áo khoác cardigan", "Thời trang nữ > Áo len & Cardigan"),
            "hoodie": ("Áo hoodie nỉ", "Thời trang > Áo nỉ & Hoodie"),
            "jacket": ("Áo khoác thời trang", "Thời trang > Áo khoác > Áo khoác thời trang"),
            "coat": ("Áo măng tô / Áo khoác dài", "Thời trang > Áo khoác > Áo choàng & Măng tô"),
            "blazer": ("Áo blazer thanh lịch", "Thời trang > Áo khoác > Áo vest & Blazer"),
            "shirt": ("Áo sơ mi công sở", "Thời trang > Áo sơ mi"),
            "t-shirt": ("Áo thun năng động", "Thời trang > Áo thun"),
            "top": ("Áo kiểu thời trang", "Thời trang nữ > Áo kiểu"),
            "blouse": ("Áo kiểu blouse", "Thời trang nữ > Áo kiểu"),
            "crop top": ("Áo croptop cá tính", "Thời trang nữ > Áo croptop"),
            "vest": ("Áo gile / Vest", "Thời trang > Áo khoác"),
            "suit": ("Bộ suit sang trọng", "Thời trang > Bộ âu phục / Suit"),
            # Bottoms
            "pants": ("Quần dài ống suông", "Thời trang > Quần dài > Quần tây & Quần vải"),
            "jeans": ("Quần jeans cá tính", "Thời trang > Quần jeans > Quần bò nữ"),
            "shorts": ("Quần short năng động", "Thời trang > Quần short"),
            "skirt": ("Chân váy thời trang", "Thời trang nữ > Chân váy"),
            "sweatpants": ("Quần jogger / Nỉ", "Thời trang > Quần nỉ & Jogger"),
            "leggings": ("Quần legging ôm", "Thời trang nữ > Quần legging"),
            # Full Body
            "dress": ("Đầm váy dáng xòe", "Thời trang nữ > Đầm & Váy > Đầm dáng xòe"),
            "jumpsuit": ("Bộ jumpsuit liền thân", "Thời trang nữ > Jumpsuit"),
            # Bags
            "handbag": ("Túi xách nữ thời thượng", "Túi ví nữ > Túi xách tay & Đeo chéo"),
            "shoulder bag": ("Túi kẹp nách đeo vai", "Túi ví nữ > Túi đeo vai"),
            "crossbody bag": ("Túi đeo chéo cá tính", "Túi ví nữ > Túi đeo chéo"),
            "tote bag": ("Túi tote tiện dụng", "Túi ví nữ > Túi tote"),
            "backpack": ("Balo thời trang cao cấp", "Balo & Túi ví > Balo thời trang"),
            "clutch": ("Ví cầm tay / Clutch", "Túi ví nữ > Ví & Clutch"),
            "bag": ("Túi xách thời trang", "Túi ví nữ > Túi xách"),
            # Footwear
            "shoes": ("Giày thời trang", "Giày dép > Giày"),
            "sneakers": ("Giày thể thao sneaker", "Giày dép > Giày thể thao / Sneaker"),
            "boots": ("Giày boots cá tính", "Giày dép > Giày boots"),
            "sandals": ("Giày sandal nữ", "Giày dép > Sandal & Dép"),
            "heels": ("Giày cao gót quyến rũ", "Giày dép > Giày cao gót"),
            "loafers": ("Giày lười loafer", "Giày dép > Giày lười"),
            "slippers": ("Dép thời trang", "Giày dép > Dép"),
            # Headwear & Eyewear
            "hat": ("Mũ nón thời trang", "Phụ kiện thời trang > Nón & Mũ"),
            "sunglasses": ("Kính mát chống tia UV", "Phụ kiện thời trang > Kính mắt"),
            # Accessories & Jewelry
            "watch": ("Đồng hồ đeo tay", "Đồng hồ > Đồng hồ thời trang"),
            "belt": ("Thắt lưng da", "Phụ kiện thời trang > Thắt lưng"),
            "scarf": ("Khăn quàng cổ", "Phụ kiện thời trang > Khăn quàng & Khăn choàng"),
            "tie": ("Cà vạt / Nơ cổ", "Phụ kiện thời trang > Cà vạt"),
            "necklace": ("Dây chuyền thời trang", "Trang sức > Vòng cổ"),
            "earrings": ("Khuyên tai / Bông tai", "Trang sức > Bông tai"),
            "bracelet": ("Vòng tay thời trang", "Trang sức > Vòng tay"),
            "ring": ("Nhẫn thời trang", "Trang sức > Nhẫn"),
            # Tech & Everyday
            "smartphone": ("Điện thoại thông minh", "Điện thoại & Phụ kiện > Điện thoại"),
            "laptop": ("Máy tính xách tay", "Máy tính & Laptop > Laptop"),
            "tablet": ("Máy tính bảng", "Điện thoại & Phụ kiện > Máy tính bảng"),
            "headphones": ("Tai nghe chụp tai", "Thiết bị âm thanh > Tai nghe"),
            "water bottle": ("Bình nước cá nhân", "Đồ gia dụng > Bình nước"),
            "cup": ("Cốc / Ly uống nước", "Đồ gia dụng > Cốc & Ly"),
            "perfume": ("Nước hoa cao cấp", "Sắc đẹp > Nước hoa"),
            "cosmetics": ("Mỹ phẩm làm đẹp", "Sắc đẹp > Chăm sóc da")
        }

        objects_dict = {}
        detections_list = []

        for it in detected_items:
            obj_id = it["object_id"]
            cat = it["category_hint"]
            conf = it["confidence"]
            crop_url = it.get("crop_image_data_url_webp") or it.get("crop_webp_path", "")
            bx1, by1, bx2, by2 = it["bbox_norm"]

            # BBox chuẩn theo metadata_sample.json: [ymin, xmin, ymax, xmax]
            bbox_ymin_xmin = [by1, bx1, by2, bx2]
            poly = it.get("contour_norm") or []

            label_vi, cat_vi = category_vietnamese.get(cat, (f"{cat.title()} thời trang", f"Thời trang > {cat.title()}"))

            # Tạo danh sách matched_products mẫu cho contract
            matched_prods = [
                {
                    "item_id": f"sp_{obj_id}_01",
                    "title": f"{label_vi} Cao Cấp - Phong cách Trẻ Trung Hàn Quốc",
                    "price": "320.000₫",
                    "platform": "Shopee Mall",
                    "product_url": f"https://shopee.vn/search?keyword={cat}",
                    "thumbnail_url": crop_url,
                    "query_used": f"{cat} phong cách hàn quốc",
                    "match_score": conf,
                    "commission_rate": 0.12,
                    "ranking_score": round(conf * 0.7 + 0.12 * 0.3, 3),
                    "match_reason": f"Khớp nhận diện vật thể {label_vi} từ frame quét."
                }
            ]

            objects_dict[obj_id] = {
                "object_id": obj_id,
                "label": label_vi,
                "category": cat_vi,
                "crop_image_url": crop_url,
                "primary_color": "đa sắc",
                "matched_products": matched_prods
            }

            detections_list.append({
                "object_id": obj_id,
                "bbox": bbox_ymin_xmin,
                "polygon": poly,
                "confidence": conf
            })

        return {
            "version": "1.0.0",
            "generated_at": datetime.utcnow().isoformat(),
            "media_info": {
                "media_id": image_name,
                "media_type": "image",
                "resolution": [h, w]
            },
            "objects": objects_dict,
            "timeline": [
                {
                    "timestamp": 0.0,
                    "frame_idx": 0,
                    "detections": detections_list
                }
            ]
        }

    # =========================================================================
    # DI CHUỘT / HIT-TEST SIÊU NHẸ (<5MS TỪ RAM CACHE)
    # =========================================================================
    def hit_test_cached_objects(
        self,
        tap_x: float,
        tap_y: float,
        is_normalized: bool = True
    ) -> Dict[str, Any]:
        """
        Hit-test điểm di chuột (Hover) trên bộ nhớ đệm RAM.
        Trả về contour và thông tin vật thể tức thì (< 5ms) để vẽ viền sáng (WebGL Glowing).
        """
        if not self._cached_candidates or self._cached_img_bgr is None:
            return {
                "status": "cache_empty",
                "message": "Chưa có frame quét trong cache. Vui lòng quét màn hình trước.",
                "hit": False
            }

        h, w = int(self._cached_img_bgr.shape[0]), int(self._cached_img_bgr.shape[1])
        if is_normalized:
            tx = int(round(tap_x * w))
            ty = int(round(tap_y * h))
        else:
            tx = int(round(tap_x))
            ty = int(round(tap_y))

        tx = max(0, min(w - 1, tx))
        ty = max(0, min(h - 1, ty))

        # Tìm các vật thể chứa điểm (tx, ty), ưu tiên diện tích nhỏ hơn (phụ kiện, túi xách)
        hits = []
        for cand in self._cached_candidates:
            m = cand["mask"]
            if m.shape[:2] != (h, w):
                m = cv2.resize(m.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)

            y1_p, y2_p = max(0, ty - 3), min(h, ty + 4)
            x1_p, x2_p = max(0, tx - 3), min(w, tx + 4)
            if np.any(m[y1_p:y2_p, x1_p:x2_p] > 0):
                mask_area = float(np.sum(m > 0))
                hits.append((mask_area, cand))

        if not hits:
            return {
                "status": "miss",
                "hit": False,
                "tap_coordinates": {"pixel": [tx, ty], "normalized": [round(tx/w, 4), round(ty/h, 4)]}
            }

        hits.sort(key=lambda x: x[0])
        best_cand = hits[0][1]

        return self.sanitize_for_json({
            "status": "hit",
            "hit": True,
            "object_id": best_cand["object_id"],
            "category_hint": best_cand["category"],
            "semantic_group": best_cand["semantic_group"],
            "confidence": best_cand["conf"],
            "bbox_norm": best_cand["bbox_norm"],
            "contour_norm": best_cand["contour_norm"],
            "tap_coordinates": {"pixel": [tx, ty], "normalized": [round(tx/w, 4), round(ty/h, 4)]}
        })

    # =========================================================================
    # CHẠM ĐỂ MUA (TAP TO BUY) & ĐỒNG BỘ VỚI BACKEND RAG
    # =========================================================================
    async def tap_and_extract_item(
        self,
        image_source: Union[str, np.ndarray, PILImage.Image],
        tap_x: float,
        tap_y: float,
        is_normalized: bool = True,
        send_to_rag: bool = True,
        search_pipeline_instance: Optional[Any] = None,
        rag_api_url: Optional[str] = None,
        target_dir: Optional[str] = None,
        video_id: Optional[str] = None,
        frame_index: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Nhận tọa độ click chuột của người dùng:
          1. Bóc tách vật thể tương ứng thành ảnh .webp NỀN TRONG SUỐT (Alpha Channel).
          2. Rút gọn đường viền Contour phục vụ hiển thị Glowing.
          3. Tự động chuyển tiếp ảnh WebP sang Backend Search & RAG để tìm sản phẩm Shopee/Lazada.
        """
        t0 = time.perf_counter()
        target_dir = target_dir or self.output_dir
        os.makedirs(target_dir, exist_ok=True)

        # Chuyển đổi định dạng ảnh đầu vào sang BGR NumPy
        if isinstance(image_source, str):
            img_bgr = cv2.imread(image_source)
            if img_bgr is None:
                raise ValueError(f"Không thể mở ảnh từ: {image_source}")
            image_name = os.path.splitext(os.path.basename(image_source))[0]
        elif isinstance(image_source, PILImage.Image):
            rgb = np.array(image_source.convert("RGB"))
            img_bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            image_name = f"tap_{int(time.time())}"
        else:
            img_bgr = image_source
            image_name = f"tap_{int(time.time())}"

        h, w = int(img_bgr.shape[0]), int(img_bgr.shape[1])

        # Quy đổi tọa độ click chuột
        if is_normalized:
            tx = int(round(tap_x * w))
            ty = int(round(tap_y * h))
        else:
            tx = int(round(tap_x))
            ty = int(round(tap_y))

        tx = max(0, min(w - 1, tx))
        ty = max(0, min(h - 1, ty))

        # Kiểm tra xem ảnh này đã được warmup cache chưa
        if self._cached_image_hash is None or self._cached_img_bgr is None or self._cached_img_bgr.shape != img_bgr.shape:
            self.warmup_frame_cache(img_bgr, cache_key=image_name)

        # BƯỚC 1: Tìm kiếm trong RAM Cache
        matching = []
        for cand in self._cached_candidates:
            m = cand["mask"]
            if m.shape[:2] != (h, w):
                m = cv2.resize(m.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)
            y1_p, y2_p = max(0, ty - 3), min(h, ty + 4)
            x1_p, x2_p = max(0, tx - 3), min(w, tx + 4)
            if np.any(m[y1_p:y2_p, x1_p:x2_p] > 0):
                mask_area = float(np.sum(m > 0))
                matching.append((mask_area, float(cand["conf"]), m, cand["bbox"], str(cand["category"])))

        selected_mask = None
        selected_bbox = None
        selected_category = "fashion_item"
        selected_conf = 0.85
        extraction_mode = "cache_hit"

        if matching:
            # Ưu tiên vật thể diện tích nhỏ hơn nằm đè bên trên
            matching.sort(key=lambda x: (x[0], -x[1]))
            _, selected_conf, selected_mask, selected_bbox, selected_category = matching[0]
        else:
            # BƯỚC 2: Nếu chưa trúng mask nào trong Cache -> Decode qua Prompt SAM 3 hoặc GrabCut
            extraction_mode = "dynamic_point_decode"
            selected_mask, selected_bbox, selected_category, selected_conf = self._decode_point_prompt(
                img_bgr, tx, ty
            )

        # BƯỚC 3: Rút gọn Contour và bóc tách ảnh .WEBP nền trong suốt
        contour_norm, refined_mask = self.mask_to_normalized_contour(
            selected_mask, w, h, self.contour_epsilon_factor
        )

        ys, xs = np.where(refined_mask > 0)
        if len(xs) > 0 and len(ys) > 0:
            selected_bbox = np.array([int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())], dtype=np.float32)

        item_id = f"item_{image_name}_{tx}_{ty}"
        crop_webp_path = os.path.join(target_dir, f"{item_id}_{selected_category}.webp")

        webp_path, quality_score, b64_webp, data_url_webp = self.extract_transparent_webp(
            frame_bgr=img_bgr,
            binary_mask=refined_mask,
            bbox=selected_bbox,
            output_webp_path=crop_webp_path
        )

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

        result_payload = self.sanitize_for_json({
            "status": "success",
            "schema_version": "2.0-tap-ai-transparent-webp",
            "event_type": "user_tap_extraction",
            "extraction_mode": extraction_mode,
            "processing_time_ms": elapsed_ms,
            "tap_coordinates": {
                "pixel": {"x": int(tx), "y": int(ty)},
                "normalized": {"x": float(round(tx / w, 4)), "y": float(round(ty / h, 4))}
            },
            "source_resolution": {"width": int(w), "height": int(h)},
            "extracted_item": {
                "object_id": str(item_id),
                "category_hint": str(selected_category),
                "semantic_group": str(self.SEMANTIC_GROUPS.get(selected_category, "general")),
                "confidence": float(round(float(selected_conf), 3)),
                "quality_score": float(round(float(quality_score), 1)),
                "bbox_pixel": [int(round(float(v))) for v in selected_bbox[:4]],
                "bbox_norm": self.normalize_bbox(selected_bbox, w, h),
                "contour_norm": contour_norm,
                "crop_webp_path": str(webp_path),
                "crop_image_base64_webp": str(b64_webp),
                "crop_image_data_url_webp": str(data_url_webp)
            }
        })

        # BƯỚC 4: Chuyển tiếp tới Backend RAG để tìm kiếm sản phẩm TMĐT
        if send_to_rag:
            rag_result = await self._forward_to_rag(
                item_payload=result_payload,
                search_pipeline_instance=search_pipeline_instance,
                rag_api_url=rag_api_url or self.rag_api_url
            )
            result_payload["rag_search_result"] = self.sanitize_for_json(rag_result)

        return result_payload

    # =========================================================================
    # PHÂN TÁCH TOÀN BỘ VẬT THỂ
    # =========================================================================
    def _segment_all_objects(
        self,
        img_bgr: np.ndarray,
        conf_thresh: float = 0.08,
        mask_thresh: float = 0.40,
        custom_vocabulary: Optional[List[str]] = None
    ) -> Tuple[List[np.ndarray], List[np.ndarray], List[str], List[float]]:
        """
        Phân tách tất cả các vật thể trong ảnh qua 3 tầng với độ nhạy cao:
          Tầng 1: Teacher Meta SAM 3 (Promptable Concept Segmentation trên GPU)
          Tầng 2: Student Model (YOLO-World Open-Vocabulary + Sub-pixel GrabCut Matting, hoặc YOLO-Seg)
          Tầng 3: Traditional Computer Vision Fallback (Contours + GrabCut luôn hoạt động)
        """
        h, w = int(img_bgr.shape[0]), int(img_bgr.shape[1])
        candidates = []

        if custom_vocabulary:
            self.set_active_vocabulary(custom_vocabulary)

        # 1. Thử Teacher SAM 3 nếu đã nạp
        if self.sam3_loaded and self.sam3_model is not None and self.sam3_processor is not None:
            try:
                import torch
                pil_img = PILImage.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
                img_inputs = self.sam3_processor(images=pil_img, return_tensors="pt").to(self.device)
                with torch.amp.autocast("cuda", enabled=self.use_fp16):
                    vision_embeds = self.sam3_model.get_vision_features(
                        pixel_values=img_inputs.pixel_values.to(self.dtype)
                    )

                active_prompts = custom_vocabulary if custom_vocabulary else self.SAM3_CONCEPT_PROMPTS
                for prompt_txt in active_prompts:
                    txt_in = self.text_inputs_cache.get(prompt_txt)
                    if txt_in is None:
                        txt_in = self.sam3_processor(text=[prompt_txt], return_tensors="pt")
                        txt_in = {k: v.to(self.device) for k, v in txt_in.items()}
                        self.text_inputs_cache[prompt_txt] = txt_in

                    outputs = self.sam3_model(vision_embeds=vision_embeds, **txt_in)
                    res = self.sam3_processor.post_process_instance_segmentation(
                        outputs, threshold=conf_thresh, mask_threshold=mask_thresh, target_sizes=[(h, w)]
                    )[0]

                    canonical_cat = self.CANONICAL_MAP.get(prompt_txt, prompt_txt)
                    for m, b, s in zip(res.get("masks", []), res.get("boxes", []), res.get("scores", [])):
                        box_np = b.cpu().numpy().astype(np.float32)
                        bw, bh = float(box_np[2] - box_np[0]), float(box_np[3] - box_np[1])
                        area = bw * bh
                        if bw < 12 or bh < 12 or area < (w * h * 0.001) or area > (w * h * 0.98):
                            continue
                        candidates.append({
                            "mask": m.cpu().numpy().astype(np.uint8),
                            "bbox": box_np,
                            "category": canonical_cat,
                            "group": self.SEMANTIC_GROUPS.get(canonical_cat, "general"),
                            "conf": float(s)
                        })
            except Exception as e:
                logger.warning(f"SAM 3 Teacher inference gặp lỗi: {e}")

        # 2. Sử dụng Student Model (Open-Vocabulary YOLO-World hoặc YOLO-Seg)
        if not candidates and self.student_loaded and self.student_model is not None:
            try:
                # Tính toán kích thước inference tối ưu theo độ phân giải ảnh thực tế
                target_imgsz = min(1280, max(640, int(np.ceil(max(w, h) / 32) * 32)))
                results = self.student_model.predict(
                    source=img_bgr,
                    device=self.device,
                    conf=conf_thresh,
                    imgsz=target_imgsz,
                    verbose=False
                )[0]

                # TH1: Mô hình trả về Instance Segmentation Masks (YOLO-seg)
                if results.masks is not None and len(results.masks) > 0:
                    for m, b, c, s in zip(
                        results.masks.data.cpu().numpy(),
                        results.boxes.xyxy.cpu().numpy(),
                        results.boxes.cls.cpu().numpy().astype(int),
                        results.boxes.conf.cpu().numpy()
                    ):
                        raw_cat = str(results.names[int(c)]).lower()
                        cat = self.CANONICAL_MAP.get(raw_cat, raw_cat)
                        m_resized = cv2.resize(m.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)
                        candidates.append({
                            "mask": m_resized,
                            "bbox": b.astype(np.float32),
                            "category": cat,
                            "group": self.SEMANTIC_GROUPS.get(cat, "general"),
                            "conf": float(s)
                        })
                # TH2: Mô hình Open-Vocabulary Detector (YOLO-World) trả về BBoxes
                #      -> Sinh Mask chính xác cao qua Sub-pixel GrabCut Matting
                elif results.boxes is not None and len(results.boxes) > 0:
                    for b, c, s in zip(
                        results.boxes.xyxy.cpu().numpy(),
                        results.boxes.cls.cpu().numpy().astype(int),
                        results.boxes.conf.cpu().numpy()
                    ):
                        raw_cat = str(results.names[int(c)]).lower()
                        cat = self.CANONICAL_MAP.get(raw_cat, raw_cat)
                        x1, y1, x2, y2 = [int(round(float(v))) for v in b[:4]]
                        x1, y1 = max(0, x1), max(0, y1)
                        x2, y2 = min(w, x2), min(h, y2)
                        bw, bh = x2 - x1, y2 - y1
                        if bw < 10 or bh < 10:
                            continue

                        # Sinh mask nhị phân bằng GrabCut trong vùng BBox
                        gc_mask = np.zeros((h, w), np.uint8)
                        bgd_model = np.zeros((1, 65), np.float64)
                        fgd_model = np.zeros((1, 65), np.float64)
                        try:
                            cv2.grabCut(img_bgr, gc_mask, (x1, y1, bw, bh), bgd_model, fgd_model, 2, cv2.GC_INIT_WITH_RECT)
                            bin_mask = np.where((gc_mask == 2) | (gc_mask == 0), 0, 1).astype(np.uint8)
                            if np.sum(bin_mask) < 20:
                                bin_mask = np.zeros((h, w), np.uint8)
                                bin_mask[y1:y2, x1:x2] = 1
                        except Exception:
                            bin_mask = np.zeros((h, w), np.uint8)
                            bin_mask[y1:y2, x1:x2] = 1

                        candidates.append({
                            "mask": bin_mask,
                            "bbox": b.astype(np.float32),
                            "category": cat,
                            "group": self.SEMANTIC_GROUPS.get(cat, "general"),
                            "conf": float(s)
                        })
            except Exception as e:
                logger.warning(f"Student Model inference gặp lỗi: {e}")

        # 3. Fallback Computer Vision (Contours & GrabCut) nếu chưa có candidate
        if not candidates:
            candidates = self._vision_fallback_candidates(img_bgr)

        # 4. Multi-Category Smart NMS: khử trùng lặp thông minh mà KHÔNG làm mất đồ vật nhỏ
        candidates.sort(key=lambda x: x["conf"], reverse=True)
        kept = []
        for item in candidates:
            drop = False
            for k in kept:
                iou, iomina = self.compute_iou_and_iomina(item["bbox"], k["bbox"])
                if item["category"] == k["category"]:
                    # Cùng một category: nếu trùng lặp lớn (IoU > 0.45) hoặc một hộp nằm trọn trong hộp kia (IoMinA > 0.85)
                    if iou > 0.45 or iomina > 0.85:
                        drop = True
                        break
                else:
                    # KHÁC category: CHỈ loại bỏ nếu 2 bounding box gần như hoàn toàn trùng khớp (IoU > 0.75)
                    # (ví dụ vùng trùng lặp cạnh tranh giữa jacket và coat)
                    # TUYỆT ĐỐI KHÔNG loại bỏ đồ vật nằm bên trong đồ vật khác (như khăn, túi, điện thoại, kính, đồng hồ trên trang phục)!
                    if iou > 0.75:
                        drop = True
                        break
            if not drop:
                kept.append(item)

        masks = [k["mask"] for k in kept]
        bboxes = [k["bbox"] for k in kept]
        categories = [k["category"] for k in kept]
        confs = [k["conf"] for k in kept]
        return masks, bboxes, categories, confs

    def _vision_fallback_candidates(self, img_bgr: np.ndarray) -> List[Dict[str, Any]]:
        """Thuật toán Computer Vision truyền thống phát hiện các mảng vật thể chính"""
        h, w = int(img_bgr.shape[0]), int(img_bgr.shape[1])
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 30, 150)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates = []
        for idx, cnt in enumerate(contours):
            area = cv2.contourArea(cnt)
            if area < (w * h * 0.02) or area > (w * h * 0.90):
                continue
            x, y, bw, bh = cv2.boundingRect(cnt)
            mask = np.zeros((h, w), dtype=np.uint8)
            cv2.drawContours(mask, [cnt], -1, 1, thickness=-1)
            candidates.append({
                "mask": mask,
                "bbox": np.array([x, y, x + bw, y + bh], dtype=np.float32),
                "category": "fashion_item",
                "group": "general",
                "conf": 0.65
            })

        if not candidates:
            # Nếu toàn cảnh không tách được, lấy vùng trung tâm 60%
            cx1, cy1 = int(w * 0.2), int(h * 0.15)
            cx2, cy2 = int(w * 0.8), int(h * 0.85)
            cmask = np.zeros((h, w), dtype=np.uint8)
            cmask[cy1:cy2, cx1:cx2] = 1
            candidates.append({
                "mask": cmask,
                "bbox": np.array([cx1, cy1, cx2, cy2], dtype=np.float32),
                "category": "fashion_item",
                "group": "general",
                "conf": 0.60
            })
        return candidates

    def _decode_point_prompt(
        self,
        img_bgr: np.ndarray,
        tx: int,
        ty: int
    ) -> Tuple[np.ndarray, np.ndarray, str, float]:
        """Giải mã phân đoạn khi người dùng click vào một điểm bất kỳ bằng GrabCut"""
        h, w = int(img_bgr.shape[0]), int(img_bgr.shape[1])
        pad_x = max(25, int(w * 0.15))
        pad_y = max(25, int(h * 0.15))
        rx1, ry1 = max(0, tx - pad_x), max(0, ty - pad_y)
        rw, rh = min(w - rx1, pad_x * 2), min(h - ry1, pad_y * 2)

        gc_mask = np.zeros((h, w), np.uint8)
        bgd_model = np.zeros((1, 65), np.float64)
        fgd_model = np.zeros((1, 65), np.float64)
        cv2.grabCut(img_bgr, gc_mask, (rx1, ry1, rw, rh), bgd_model, fgd_model, 3, cv2.GC_INIT_WITH_RECT)
        selected_mask = np.where((gc_mask == 2) | (gc_mask == 0), 0, 1).astype(np.uint8)
        selected_bbox = np.array([rx1, ry1, rx1 + rw, ry1 + rh], dtype=np.float32)
        return selected_mask, selected_bbox, "fashion_item", 0.70

    # =========================================================================
    # ĐỒNG BỘ VỚI BACKEND RAG
    # =========================================================================
    async def _forward_to_rag(
        self,
        item_payload: Dict[str, Any],
        search_pipeline_instance: Optional[Any] = None,
        rag_api_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Chuyển tiếp ảnh WebP bóc tách sang RAG Pipeline:
          1. Nếu cùng process FastAPI: Gọi in-memory search_pipeline_instance.process_image() trực tiếp.
          2. Nếu có rag_api_url: Gửi HTTP POST tới RAG webhook.
          3. Nếu chưa cấu hình API keys hoặc server riêng: Trả về cấu trúc mock sản phẩm Shopee/Lazada
             chuẩn 100% data contract để Frontend Side Panel hiển thị ngay lập tức.
        """
        extracted = item_payload.get("extracted_item", {})
        cat = str(extracted.get("category_hint", "thời trang"))
        obj_id = str(extracted.get("object_id", "obj_tap"))
        crop_webp_path = str(extracted.get("crop_webp_path", ""))

        # 1. Gọi trực tiếp in-memory nếu chạy chung Backend server
        if search_pipeline_instance is not None and os.path.exists(crop_webp_path):
            try:
                logger.info(f"🔗 [RAG INTEGRATION] Chuyển tiếp in-memory vật thể '{obj_id}' tới TapAISearchPipeline...")
                result = await search_pipeline_instance.process_image(
                    image_input=crop_webp_path,
                    object_id=obj_id,
                    top_k=5
                )
                return {
                    "status": "rag_success",
                    "mode": "in_memory_pipeline",
                    "data": result
                }
            except Exception as e:
                logger.warning(f"Không thể thực thi search_pipeline in-memory ({e}). Sẽ chuyển sang phương thức dự phòng...")

        # 2. Gọi qua HTTP POST nếu có webhook RAG API URL
        if rag_api_url and not rag_api_url.startswith("http://mock"):
            try:
                import httpx
                req_data = {
                    "object_id": obj_id,
                    "image_base64": extracted.get("crop_image_base64_webp", ""),
                    "category_hint": cat,
                    "top_k": 5
                }
                async with httpx.AsyncClient(timeout=8.0) as client:
                    resp = await client.post(rag_api_url, json=req_data)
                    if resp.status_code == 200:
                        return {
                            "status": "rag_success",
                            "mode": "http_webhook",
                            "http_code": resp.status_code,
                            "data": resp.json()
                        }
            except Exception as ex:
                logger.warning(f"Gửi RAG webhook thất bại: {ex}")

        # 3. Fallback / Mock Response chuẩn UI Side Panel
        return {
            "status": "mock_rag_preview",
            "message": "Đã bóc tách thành công ảnh WebP nền trong suốt. Sẵn sàng kết nối tới RAG khi có API Key.",
            "products": [
                {
                    "item_id": f"sp_{obj_id}_1",
                    "title": f"[Gợi ý RAG] {cat.title()} Thời Trang Cao Cấp Xu Hướng Trẻ",
                    "price": "289.000₫",
                    "originalPrice": "420.000₫",
                    "thumbnail_url": extracted.get("crop_image_data_url_webp", ""),
                    "platform": "Shopee Mall",
                    "product_url": f"https://shopee.vn/search?keyword={cat.replace(' ', '%20')}",
                    "match_score": 0.94,
                    "commission_rate": 0.15
                },
                {
                    "item_id": f"sp_{obj_id}_2",
                    "title": f"[Gợi ý RAG] {cat.title()} Thiết Kế Tinh Tế Chính Hãng",
                    "price": "345.000₫",
                    "originalPrice": "490.000₫",
                    "thumbnail_url": extracted.get("crop_image_data_url_webp", ""),
                    "platform": "Lazada",
                    "product_url": f"https://www.lazada.vn/catalog/?q={cat.replace(' ', '%20')}",
                    "match_score": 0.89,
                    "commission_rate": 0.10
                }
            ]
        }