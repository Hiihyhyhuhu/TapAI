# TAP AI Frontend

The TAP AI frontend is a Manifest V3 Chrome Extension that displays a side
panel for products detected in videos or images.

## Technologies

- React 19
- TypeScript
- Vite
- Tailwind CSS 3
- Chrome Extension Manifest V3

## Requirements

- Node.js 20 or later
- npm
- Google Chrome with Side Panel API support

## Installation

From the `frontend` directory:

```bash
npm install
```

## Main commands

```bash
# Start the Vite development server
npm run dev

# Check TypeScript and create a production build
npm run build

# Run ESLint
npm run lint
```

The build output is generated in the `dist` directory.

## Run the extension in Chrome

1. Run `npm run build`.
2. Open `chrome://extensions`.
3. Enable **Developer mode**.
4. Select **Load unpacked**.
5. Select the `frontend/dist` directory.
6. Click the TAP AI icon in the toolbar to open the side panel.

After each source change, run `npm run build` again and click **Reload** on the
`chrome://extensions` page.

## Directory structure

```text
frontend/
├── public/
│   ├── background.js       # Extension service worker
│   └── manifest.json       # Manifest V3 configuration
├── src/
│   ├── components/
│   │   └── SidePanel.tsx   # Side panel UI and message handling
│   ├── types/
│   │   └── index.ts        # Product and Chrome message types
│   ├── index.css           # Tailwind CSS entry point
│   └── main.tsx            # React entry point
├── sidepanel.html          # Side panel HTML entry point
├── tailwind.config.js      # Tailwind configuration
├── postcss.config.js       # PostCSS configuration
└── vite.config.ts          # Vite configuration
```

## Chrome extension messaging

The side panel listens for messages through `chrome.runtime.onMessage`. The
supported message types are:

- `ITEM_CLICKED`: Select a product.
- `SCENE_ITEMS_UPDATED`: Update the list of products in the scene.
- `TOGGLE_OVERLAY`: Message type reserved for overlay state changes.

Product payloads must include these required fields:

```ts
{
  id: string;
  title: string;
  price: string;
  image: string;
  link: string;
}
```

The `originalPrice`, `platform`, and `bbox` fields are optional. Invalid
payloads are ignored to prevent the side panel from breaking.

## Notes

- Vite copies `public/manifest.json` to `dist` during the build.
- `public/background.js` opens the side panel when the extension action is
  clicked.
- Rebuild after changing the manifest, service worker, or React source code.
