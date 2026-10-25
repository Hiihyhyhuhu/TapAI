# TAP AI: Interactive Shoppable Media Engine

> **"Tap anything, buy anywhere"**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Manifest Version](https://img.shields.io/badge/Chrome_Extension-Manifest_V3-blue.svg)](https://developer.chrome.com/docs/extensions/mv3/intro/)
[![Tech Stack](https://img.shields.io/badge/AI-Meta_SAM_3_%7C_FastAPI_%7C_React-green.svg)](#tech-stack)

**TAP AI** is an open-source, multi-layer interactive video and image engine (**Shoppable Media Engine**). It turns static images and moving objects within videos into real-time interactive, clickable overlays that link directly to e-commerce products without interrupting the viewing experience.

---

## 📌 1. Background & Problem Statement

### Market Context
Short-form video content (TikTok, Instagram Reels, YouTube Shorts) and social commerce are experiencing exponential growth. Visual media currently yields the highest conversion rates in digital commerce.

### Pain Points

* **For Viewers:** When viewers spot an item they like in a video or photo, discovering where to buy it requires cumbersome steps: taking screenshots, using reverse image search tools, or leaving comments asking *"where can I buy this?"*.
* **For Creators & Brands:**
  * Affiliate links embedded in descriptions or bio links yield extremely low Click-Through Rates (CTR) as they disrupt the user experience.
  * Manual tagging of objects frame-by-frame across video content is labor-intensive, expensive, and non-scalable.
* **Technical Limitations:** Existing shoppable video platforms require **re-rendering the source video file** (heavy GPU load and high latency) or rely on static, fixed hotspots that fail to track moving objects across frames in real-time.

---

## 💡 2. Solution & Value Proposition

### 2.1 The Core Solution: OmniLayer AI Architecture
TAP AI introduces **OmniLayer AI**, an interactive media system based on the core paradigm:
> **"Pre-process once, render interactive overlays client-side."**

1. **Pre-processing (One-Time Execution):** AI runs in the background to segment objects in images/videos and generates an extremely lightweight tracking metadata file (`metadata.json`, $\approx 50\text{ KB}$).
2. **Real-time Client-side Rendering:** Video streams natively while a dynamic interactive UI layer is rendered on top in real time at $60\text{ FPS}$.

```
[Media Input: Video/Image]
       │
       ├─► [Backend Pre-processing Engine]
       │     ├─ SAM 3 (Spatial & Temporal Tracking) ──► Object Masks
       │     ├─ OpenCV / FFmpeg ─────────────► Keyframe Downsampling
       │     └─ Muse Spark (LLM Context Matcher) ───► Product Links & Metadata
       │           │
       │          ▼
       │     [Export: metadata.json (~50KB)]
       │
       └─► [Client-side Interactive Player / Extension]
             ├─ Video / Image Render Engine
             ├─ Canvas / WebGL (Glimmer Engine) ─────► Glowing Contours (60 FPS)
             └─ React Side Panel Component ──────────► Interactive Shopping Cards
```

### 2.2 Key Features

* ⚡ **Instant Image Tagging:** Hover over or tap static images (Instagram/Facebook style) to display object bounding outlines and product cards in $< 1\text{ second}$.
* 🎯 **Spatio-Temporal Video Tracking:** Seamlessly tracks moving items (apparel, bags, accessories) across video frames using bounding boxes and glowing contour overlays.
* 🛍️ **Dynamic Side Panel UI:** Clicking on any object in a video or image slides out a right-side panel displaying product specifications, pricing, and direct affiliate purchase links (*Shopee/Lazada*)—all while video playback continues without interruption.

### 2.3 Business & Monetization Model

* **B2C Affiliate Commissions:** Earn a $5\% - 20\%$ commission on sales completed via product link redirects from the TAP AI side panel.

---

## 🛠️ 3. Technical Architecture & Tech Stack

| Domain | Technology / Tool | Role & Responsibility |
| :--- | :--- | :--- |
| **AI / Computer Vision** | Meta SAM 3 | Object detection, mask generation, and spatio-temporal tracking across video frames. |
| **AI / Multimodal** | Muse Spark (LLM) | Contextual analysis of identified objects to match and retrieve relevant Shopee/Lazada product listings. |
| **Video Processing** | FFmpeg & OpenCV | Keyframe extraction, video compression, and chunking for parallel processing. |
| **Backend Framework** | Python (FastAPI) | High-performance RESTful APIs managing video/image ingestion and AI task pipelines. |
| **Task Queue & Cache** | Celery + Redis | Asynchronous background processing for long-duration video segmentation tasks. |
| **Frontend / Extension** | React.js / Chrome Extension Manifest V3 | Client-side extension UI (Video Overlay + Chrome `sidePanel` API integration). |
| **Overlay Engine** | HTML5 Canvas / WebGL (Glimmer) | Real-time rendering ($60\text{ FPS}$) of glowing contours and bounding overlays over media streams. |

---

## 👥 4. Team & Project Structure

TAP AI is developed as an **Open-Source** project. 

* **Frontend:** Chrome Extension UI & Canvas Overlay Engine *(Hy)*
* **Backend (Search & RAG):** Web Search, RAG Pipeline, and Product Re-ranking *(Khanh)*
* **Backend (Segmentation):** SAM 3 Spatio-Temporal Tracking Engine *(Dat)*
* **Research & Paper:** Knowledge Distillation (Distilling knowledge from Meta SAM 3 to a lightweight student model) *(Phuong)*

---

## 🚀 5. Getting Started (Chrome Extension Frontend)

### Prerequisites
* Google Chrome (v114+ for Manifest V3 SidePanel API support)
* Node.js (v18+) & `npm` / `pnpm`

### Local Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-org/tap-ai.git
   cd tap-ai
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Build the extension:**
   ```bash
   npm run build
   ```

4. **Load into Google Chrome:**
   * Open Chrome and navigate to `chrome://extensions/`.
   * Enable **Developer mode** (toggle in the top-right corner).
   * Click **Load unpacked**.
   * Select the `dist/` directory generated from the build step.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.