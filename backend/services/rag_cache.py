import os
import uuid
import time
from typing import List, Optional, Dict, Any, Union
from PIL import Image
import torch
import timm
from timm.data import create_transform, resolve_model_data_config
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from models.search_schemas import ProductCandidate, EcomSearchQuery

class ImageEmbedder:
    """
    Mô hình tạo vector nhúng (embedding) siêu nhạy cho bài toán so khớp vật thể (Re-ID)
    Sử dụng DINOv2 (Meta) - 'vit_small_patch14_dinov2' (384 chiều, siêu nhẹ ~85MB)
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ImageEmbedder, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, model_name: str = "vit_small_patch14_dinov2"):
        if getattr(self, "_initialized", False):
            return
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = timm.create_model(model_name, pretrained=True, num_classes=0)
        self.model.to(self.device)
        self.model.eval()

        config = resolve_model_data_config(self.model)
        self.transform = create_transform(**config, is_training=False)
        self.dim = 384
        self._initialized = True

    def _normalize_image(self, image_input: Union[str, Image.Image]) -> Image.Image:
        """
        Xử lý chuẩn hóa ảnh crop từ SAM 3:
        - Tự động chuyển đổi nền trong suốt (Alpha/RGBA) thành nền trắng thuần (#FFFFFF)
        - Tránh tình trạng chuyển sang RGB bị viền đen xì làm hỏng vector đặc trưng
        """
        if isinstance(image_input, str):
            if not os.path.exists(image_input):
                raise FileNotFoundError(f"Không tìm thấy file ảnh: {image_input}")
            img = Image.open(image_input)
        else:
            img = image_input

        # Xử lý kênh Alpha (nền trong suốt từ SAM 3)
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            img = img.convert("RGBA")
            white_bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
            img = Image.alpha_composite(white_bg, img).convert("RGB")
        else:
            img = img.convert("RGB")

        return img

    def embed_image(self, image_input: Union[str, Image.Image]) -> List[float]:
        """Chuyển đổi ảnh SAM 3 thành vector 384 chiều của DINOv2 đã chuẩn hóa L2"""
        clean_img = self._normalize_image(image_input)
        tensor = self.transform(clean_img).unsqueeze(0).to(self.device)

        with torch.no_grad():
            feat = self.model(tensor)
            feat = feat / feat.norm(dim=-1, keepdim=True)
            return feat.squeeze(0).cpu().tolist()

class ProductRAGCache:
    """Module D: Bộ nhớ đệm Vector DB (Qdrant) hỗ trợ DINOv2"""
    def __init__(self, storage_path: str = "./qdrant_storage", collection_name: str = "tap_ai_products_dinov2"):
        self.collection_name = collection_name
        self.storage_path = storage_path
        self.embedder = ImageEmbedder()

        if storage_path == ":memory:":
            self.client = QdrantClient(":memory:")
        else:
            os.makedirs(storage_path, exist_ok=True)
            self.client = QdrantClient(path=storage_path)

        self._ensure_collection()

    def _ensure_collection(self):
        """Tạo collection nếu chưa tồn tại hoặc tự động nâng cấp kích thước vector"""
        collections = [col.name for col in self.client.get_collections().collections]
        if self.collection_name in collections:
            info = self.client.get_collection(self.collection_name)
            curr_size = info.config.params.vectors.size
            if curr_size != self.embedder.dim:
                self.client.delete_collection(self.collection_name)
                collections.remove(self.collection_name)

        if self.collection_name not in collections:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.embedder.dim, distance=Distance.COSINE),
            )

    def search_cache(
        self,
        v_crop: List[float],
        score_threshold: float = 0.88
    ) -> Optional[Dict[str, Any]]:
        """Tìm kiếm vector ảnh trong Cache Qdrant (DINOv2 Cosine Similarity >= threshold)"""
        try:
            hits = self.client.query_points(
                collection_name=self.collection_name,
                query=v_crop,
                score_threshold=score_threshold,
                limit=1,
            ).points

            if hits:
                best_hit = hits[0]
                payload = best_hit.payload or {}
                raw_prods = payload.get("products", [])
                products = [ProductCandidate.model_validate(p) for p in raw_prods]
                
                return {
                    "cache_hit": True,
                    "similarity_score": round(best_hit.score, 4),
                    "category_path": payload.get("category_path", ""),
                    "exact_query": payload.get("exact_query", ""),
                    "products": products
                }
        except Exception as e:
            print(f"⚠️ Lỗi truy vấn Qdrant Cache: {e}")

        return None

    def search_by_image(
        self,
        image_input: Union[str, Image.Image],
        score_threshold: float = 0.88
    ) -> Optional[Dict[str, Any]]:
        v_crop = self.embedder.embed_image(image_input)
        return self.search_cache(v_crop, score_threshold=score_threshold)

    def save_cache(
        self,
        v_crop: List[float],
        top_products: List[ProductCandidate],
        query_info: EcomSearchQuery,
    ) -> str:
        point_id = str(uuid.uuid4())
        payload = {
            "category_path": query_info.category_path,
            "exact_query": query_info.exact_query,
            "saved_at": time.time(),
            "products": [p.model_dump() for p in top_products]
        }

        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=point_id,
                    vector=v_crop,
                    payload=payload
                )
            ]
        )
        return point_id

    def save_by_image(
        self,
        image_input: Union[str, Image.Image],
        top_products: List[ProductCandidate],
        query_info: EcomSearchQuery,
    ) -> str:
        v_crop = self.embedder.embed_image(image_input)
        return self.save_cache(v_crop, top_products, query_info)

    def count(self) -> int:
        info = self.client.get_collection(self.collection_name)
        return info.points_count or 0
