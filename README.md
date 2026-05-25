# 🎯 Household Budgeting

A gorgeous, local-first, private-by-design desktop budgeting application.

This application replaces an older R/Shiny monolith with a modern, high-performance architecture: **FastAPI (Python)** on the backend and **Vite + React (TypeScript)** on the frontend. The entire application runs locally on your machine, utilizing **SQLite** for ultra-fast, offline-capable database persistence. Your financial data stays 100% private—there is no cloud tracking, telemetry, or external database setups.

---

## ✨ Features & Architecture

The application is structured around a high-fidelity user interface and a robust local API server, featuring:

*   **📊 Interactive Dashboard:** A premium high-level financial overview showcasing your current month's total spending vs. monthly income via a beautiful visual arc, live budget health metrics, recent transactions list, and visual goal progress indicators.
*   **💸 Ledger & Expense Management:** A full-featured transactional interface supporting instant client-side search, multi-column sorting, and pagination. Includes category/subcategory comboboxes, payer attribution (e.g., Caleb, Rae, Joint), and dedicated toggles to link expenses directly to saving goals.
*   **📅 Dynamic Budgets Planner:** A robust calendar-aware budget organizer. Set monthly limits per category and subcategory with customizable effective/conclusion dates. Features **Weighted Moving Average (WMA)** recommendations using historical spend patterns with "Hasty" (0.6/0.3/0.1) and "Conservative" (0.4/0.4/0.2) suggestion models.
*   **🎯 Goal Milestones:** Rich visual tracking cards for active and completed savings goals. Links directly to expense items, calculates dynamic completion progress, and supports granular budget-line matching rules.
*   **📈 Advanced Analytics & Reporting:** Full spending reports including period filters, interactive trend line/bar charts powered by **Recharts**, category breakdown visualizations, and highlighted budget overage tables sorted by worst-performing categories first.
*   **⚙️ Local Data & Statement Importer:** Interactive bank CSV statement ingestion workspace supporting **BECU Credit Card, Chase Credit Card, Chase Bank, and Generic** formats. Includes live duplicate transaction detection, bulk categorization, customizable column mapping, and absolute data safety through offline database backup triggers.

---

## 🎨 Design System & Aesthetics

Designed with a premium, state-of-the-art aesthetic that makes managing personal finance an engaging, tactile experience:

| Token | CSS Variable | Color Code | Description |
| :--- | :--- | :--- | :--- |
| **Background** | `--color-bg` | `#0F0F0F` | Deep dark mode background |
| **Surface** | `--color-surface` | `#1A1A1A` | Sleek cards, sidebars, and overlays |
| **Surface Raised**| `--color-surface-raised` | `#222222` | Raised button elements and active item fills |
| **Border** | `--color-border` | `#2A2A2A` | Sharp, dark interface borders |
| **Accent** | `--color-accent` | `#FF6719` | High-vibrancy Substack Orange |
| **Accent Dim** | `--color-accent-dim` | `#CC5214` | Accent color hover state |
| **Text** | `--color-text` | `#F0EDE8` | Warm off-white for reading comfort |
| **Text Muted** | `--color-text-muted` | `#8A867F` | Subtle descriptors and secondary info |
| **Danger** | `--color-danger` | `#E05252` | Budget overages, deletes, and errors |
| **Success** | `--color-success` | `#4CAF79` | Positive cash flows, goals met, and saved states |

*   **Typography:** Elegant typography using the premium serif font **Spectral** from Google Fonts (weights 200–800, normal and italic).
*   **Interactivity:** Smooth micro-animations on cards (scale transforms + custom box shadows), slide-in overlays, fade-in route transitions, and responsive toast notifications.

---

## 📂 Project Structure

```
budgeting_tool/
├── backend/                  # FastAPI Python backend
│   ├── main.py               # Main API Router & CORS configurations
│   ├── database.py           # SQLite direct interface & initial schema
│   ├── migrate.py            # Historical CSV migration script
│   ├── requirements.txt      # Backend Python dependencies
│   └── routers/              # Modular API endpoints (expenses, budgets, reporting, etc.)
├── web/                      # React / TypeScript frontend
│   ├── src/
│   │   ├── api/              # Strongly-typed fetch interfaces & client helpers
│   │   ├── components/ui/    # Custom primitive component library (Buttons, Modals, Badges)
│   │   ├── hooks/            # Custom React Query state hooks
│   │   ├── layouts/          # Persisted App Layout & navigation sidebar
│   │   ├── pages/            # View pages (Dashboard, Expenses, Budgets, Goals, etc.)
│   │   ├── styles/           # Global resets and Spectral design system configurations
│   │   └── App.tsx           # Application routing configuration
│   ├── index.html            # Web entrypoint
│   └── package.json          # Node dependencies & scripts
├── scripts/                  # Premium macOS application build pipeline
│   ├── generate_vector_icon.py  # Supersampled Pillow PNG generator
│   └── build_mac_app.py      # Retina macOS Bundle (.app) compiler
├── data/                     # Data persistence layer
│   └── budget.db             # Local SQLite database (replaces older CSV files)
├── backups/                  # SQLite backup target directory
├── desktop_app.py            # Cross-platform pywebview standalone wrapper
└── README.md                 # Project documentation
```

---

## 💻 Installation & Requirements

Ensure you have the following prerequisites installed:
*   **Python:** Version 3.9+
*   **Node.js:** Version 18+

### 1. Install Backend Dependencies
Set up your virtual environment and install the required modules:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### 2. Install Frontend Dependencies
Download Node packages for the React web client:
```bash
cd web
npm install
cd ..
```

---

## 🚀 Quick Start (Development)

To run the application locally with hot-reloading active on both the server and client:

1.  **Start the Backend:**
    ```bash
    source .venv/bin/activate
    uvicorn backend.main:app --reload --port 8000
    ```
2.  **Start the Frontend:**
    In a new terminal window:
    ```bash
    cd web
    npm run dev
    ```
3.  **Access the Application:**
    Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 💾 Historical Data Migration

If you are transitioning from the older R/Shiny version of the application, seed the SQLite database with your historical CSV sheets:

1.  Ensure your old CSV documents (`expenses.csv`, `category_budget.csv`, `income_sources.csv`, `goals.csv`, and `goal_budget_links.csv`) are placed in the `data/` directory.
2.  Run the migration pipeline from the project root:
    ```bash
    python backend/migrate.py
    ```
3.  This script compiles, deduplicates, and populates the tables in `data/budget.db` seamlessly.

---

## 🖥️ Desktop Launch (Standalone Window)

The budgeting application runs as a native cross-platform desktop utility utilizing `pywebview` to bridge the backend with the custom styled interface:

### Production Execution
Compile the frontend client and run the local production server wrapped in a native window:
```bash
# 1. Compile static web assets
cd web
npm run build
cd ..

# 2. Open standalone native desktop window
python desktop_app.py
```

### Desktop Developer Mode
Run the standalone window mapping directly to your hot-reloading Vite dev server (ideal for testing UI changes in real time):
```bash
# Make sure "npm run dev" is active in another terminal
python desktop_app.py --dev
```

---

## 🍎 Premium macOS App Bundle Compilation

The project provides custom Python scripts in the `scripts/` directory to compile a native, Retina-sharp macOS desktop application bundle (`Household Budgeting.app`) and deploy it to your Desktop.

> [!NOTE]
> Creating the app bundle requires the **Pillow** library. If not installed, run:
> `pip install pillow`

### 1. Generate the Pixel-Perfect App Icon
The vector generator draws a beautiful Substack orange `$` symbol inside a sharp white circle. It utilizes **4x supersampling (4096 x 4096)** and macOS serif font rendering, applying premium Lanczos downsampling to output a gorgeous Retina-ready icon:
```bash
python scripts/generate_vector_icon.py
```

### 2. Compile and Deploy the Mac Bundle
Build the `.app` package and place it on your Desktop:
```bash
python scripts/build_mac_app.py
```

This compilation script automates the following premium macOS workflows:
*   Creates a standard Apple bundle structure (`Household Budgeting.app/Contents/MacOS` and `/Resources`).
*   Runs the macOS `sips` system tool to resize the generated PNG into 10 multi-resolution assets, packing them into an `AppIcon.iconset`.
*   Uses native Apple `iconutil` to compile the iconset into a single Retina-compatible binary **`AppIcon.icns`**.
*   Generates a structured `Info.plist` mapping bundle configurations, bundle IDs, and window parameters.
*   Writes a custom shell launcher utilizing an AppleScript `osascript` Terminal bypass. This forces the application to run directly under your macOS terminal session, inheriting user permissions (Files & Folders access) without complex Finder sandboxing warnings.
*   Forces macOS Launch Services to register the bundle, touches the files, triggers a rename refresh loop, and restarts Finder to ensure your macOS Dock and Desktop show the gorgeous white-and-orange icon instantly!

Double-click the **Household Budgeting** shortcut on your Desktop to experience your private budgeting application in native full-desktop glory.

