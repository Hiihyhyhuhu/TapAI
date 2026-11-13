export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ProductItem {
  id: string;
  title: string;
  price: string;
  originalPrice?: string;
  image: string;
  link: string;
  platform?: 'Shopee' | 'Lazada' | 'Tiki' | 'TikTok Shop' | string;
  bbox?: [number, number, number, number];
  matchScore?: number;
  matchReason?: string;
}

export type ChromeMessageType =
  | 'ITEM_CLICKED'
  | 'SCENE_ITEMS_UPDATED'
  | 'TOGGLE_OVERLAY'
  | 'SEARCH_LOADING'
  | 'SEARCH_ERROR';

export interface ChromeMessage {
  type: ChromeMessageType;
  data?: ProductItem | ProductItem[] | string;
}

export interface TapAiStorageState {
  status: 'idle' | 'loading' | 'success' | 'error';
  loadingText?: string;
  errorMessage?: string | null;
  selectedItem?: ProductItem | null;
  detectedItems?: ProductItem[];
  updatedAt?: number;
}
