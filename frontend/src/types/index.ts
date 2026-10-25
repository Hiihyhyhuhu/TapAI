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
}

export type ChromeMessageType =
  | 'ITEM_CLICKED'
  | 'SCENE_ITEMS_UPDATED'
  | 'TOGGLE_OVERLAY';

export interface ChromeMessage {
  type: ChromeMessageType;
  data?: any;
}