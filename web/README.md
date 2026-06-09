# web/ — IoTAPS Frontend (React + Vite)

The IoTAPS React SPA. Built with Vite, Tailwind CSS, and shadcn/ui conventions,
using ECharts, React Grid Layout, React Flow, Redux Toolkit, Phosphor Icons,
Framer Motion, and Sonner.

## Getting started

```bash
cd web
npm install
cp .env.example .env   # adjust proxy targets if needed
npm run dev            # http://localhost:5173
```

The dev server proxies `/api` and `/ws` to the FastAPI backend
(`http://localhost:8000` by default; see `vite.config.js`).

## Production build

```bash
npm run build          # outputs to web/dist/
```

Nginx serves the production build from `web/dist/` (mounted read-only into the
nginx container; see `docker-compose.yml` and
`infra/nginx/conf.d/iotaps.conf`).

## Project structure

```
web/
├─ index.html
├─ vite.config.js          # @ alias -> src/, dev proxy for /api and /ws
├─ tailwind.config.js      # shadcn/ui CSS-variable colors
├─ postcss.config.js
├─ components.json         # shadcn/ui generator config
├─ public/favicon.svg
└─ src/
   ├─ main.jsx             # entry: Provider + theme init before paint
   ├─ App.jsx              # RouterProvider + Sonner Toaster
   ├─ router.jsx           # routing skeleton (placeholders per feature task)
   ├─ styles/index.css     # role themes + light/dark CSS variables (Req 4.x)
   ├─ lib/
   │  ├─ apiClient.js      # axios client + JWT/refresh interceptor
   │  ├─ theme.js          # role -> theme + light/dark apply/persist (Req 4.4)
   │  └─ utils.js          # cn() classname helper
   ├─ store/
   │  ├─ index.js          # Redux store
   │  ├─ authSlice.js      # principal + theme/mode state
   │  ├─ uiSlice.js        # ephemeral UI state
   │  └─ hooks.js          # useAppDispatch / useAppSelector
   ├─ components/
   │  ├─ AppLayout.jsx     # authenticated shell layout
   │  └─ ThemeModeToggle.jsx
   └─ pages/Placeholder.jsx
```

## Theming (Requirement 4)

Two orthogonal axes are applied to `<html>`:

- **Role theme** via `data-theme`: `admin` (purple, Super_Admin),
  `project-center` (green-dark, Project_Center), `device-user`
  (blue-light, Device_User).
- **Visual mode** via the `dark` class: light (default) or dark, persisted per
  user. Toggling applies first and only persists on success — if the mode
  cannot be applied, the toggle fails without persisting (Req 4.4).

See `src/lib/theme.js` and `src/styles/index.css`.

> Auth screens (task 2.8) and dashboards (tasks 8.x) are intentionally not part
> of this shell; routes are stubbed with placeholders.
