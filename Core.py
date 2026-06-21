#!/usr/bin/env python3
"""
================================================================================
  TOOL INVENTORY & BARCODE SYSTEM  v2.0
  Single-file desktop app with permanent SQLite storage, shelf/row/bin tracking,
  barcode generation, photo storage, and full audit logging.

  USAGE:
    python tool_inventory.py

  Then open http://localhost:8765 in your browser (auto-opens).

  Press Ctrl+C to stop the server.
================================================================================
"""

import os, sys, sqlite3, json, csv, io, base64, webbrowser, threading, uuid, time, random
from datetime import datetime
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import mimetypes

# ─── CONFIG ────────────────────────────────────────────────────────────────────
APP_DIR   = Path(__file__).parent.resolve()
DB_PATH   = APP_DIR / "inventory.db"
PHOTO_DIR = APP_DIR / "photos"
EXPORT_DIR= APP_DIR / "exports"
PORT      = 8765

PHOTO_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

# ─── DATABASE ─────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS tools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            barcode TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL DEFAULT 0,
            condition TEXT DEFAULT 'Good',
            shelf TEXT, row_num TEXT, bin TEXT,
            photo_filename TEXT,
            status TEXT DEFAULT 'available',
            buyer_name TEXT, sale_price REAL, sale_date TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_id INTEGER, action TEXT NOT NULL, details TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tool_id) REFERENCES tools(id)
        )
    """)
    conn.commit(); conn.close()
    print("[DB] Ready.")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def log_action(tid, act, det=""):
    c = get_db(); c.execute("INSERT INTO audit_log (tool_id,action,details) VALUES (?,?,?)",(tid,act,det))
    c.commit(); c.close()

def gen_barcode():
    return "TL" + hex(int(time.time()*1000))[2:].upper()[:8] + "".join(random.choices("0123456789ABCDEF",k=4))

def save_photo(b64):
    if not b64: return None
    try:
        if "," in b64: b64 = b64.split(",")[1]
        fn = f"{uuid.uuid4().hex}.jpg"
        (PHOTO_DIR/fn).write_bytes(base64.b64decode(b64))
        return fn
    except Exception as e:
        print(f"[PHOTO ERR] {e}"); return None

def del_photo(fn):
    if fn and (PHOTO_DIR/fn).exists(): (PHOTO_DIR/fn).unlink()

# ─── EMBEDDED HTML FRONTEND ───────────────────────────────────────────────────
HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tool Inventory & Barcode System</title>
<script src="https://cdn.jsdelivr.net/npm/jsbarcode@3.11.5/dist/JsBarcode.all.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/quagga@0.12.1/dist/quagga.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--p:#667eea;--pd:#5a67d8;--s:#764ba2;--ok:#28a745;--no:#dc3545;--w:#ffc107;--d:#2d3748;--g:#718096;--l:#f7fafc;--b:#e2e8f0}
body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--l);color:var(--d);line-height:1.6}
.container{max-width:1400px;margin:0 auto;padding:20px}
header{background:linear-gradient(135deg,var(--p) 0%,var(--s) 100%);color:#fff;padding:30px;border-radius:16px;margin-bottom:25px;box-shadow:0 10px 40px rgba(102,126,234,0.3);position:relative;overflow:hidden}
header::before{content:'';position:absolute;top:-50%;right:-10%;width:300px;height:300px;background:rgba(255,255,255,0.1);border-radius:50%}
h1{font-size:2.2em;margin-bottom:5px}.subtitle{opacity:.9;font-size:1.1em}
.tabs{display:flex;gap:8px;margin-bottom:25px;flex-wrap:wrap;background:#fff;padding:8px;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.05)}
.tab{padding:12px 24px;background:transparent;border:none;border-radius:8px;cursor:pointer;font-weight:600;transition:all .3s;font-size:.95em;color:var(--g)}
.tab:hover{color:var(--p);background:rgba(102,126,234,0.05)}
.tab.active{background:linear-gradient(135deg,var(--p),var(--s));color:#fff;box-shadow:0 4px 12px rgba(102,126,234,0.3)}
.panel{display:none;animation:fadeIn .3s}.panel.active{display:block}
@keyframes fadeIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
.card{background:#fff;border-radius:16px;padding:28px;margin-bottom:20px;box-shadow:0 2px 12px rgba(0,0,0,0.04);border:1px solid var(--b)}
.card-title{font-size:1.3em;font-weight:700;margin-bottom:20px;color:var(--d);display:flex;align-items:center;gap:10px}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}
@media(max-width:768px){.form-grid{grid-template-columns:1fr}}
.form-group label{display:block;margin-bottom:8px;font-weight:600;color:var(--d);font-size:.9em}
.form-group input,.form-group textarea,.form-group select{width:100%;padding:12px 16px;border:2px solid var(--b);border-radius:10px;font-size:1em;transition:all .3s;background:#fff}
.form-group input:focus,.form-group textarea:focus,.form-group select:focus{outline:none;border-color:var(--p);box-shadow:0 0 0 3px rgba(102,126,234,0.1)}
.form-group textarea{resize:vertical;min-height:100px}
.location-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:15px}
@media(max-width:768px){.location-grid{grid-template-columns:1fr}}
.photo-upload{border:3px dashed var(--b);border-radius:12px;padding:40px;text-align:center;cursor:pointer;transition:all .3s;background:var(--l)}
.photo-upload:hover{border-color:var(--p);background:rgba(102,126,234,0.03)}
.photo-upload.has-image{border-style:solid;border-color:var(--p);padding:12px;background:#fff}
.photo-preview{max-width:100%;max-height:220px;border-radius:10px;display:none}
.photo-upload.has-image .photo-preview{display:block}.photo-upload.has-image .upload-text{display:none}
.btn{padding:12px 24px;border:none;border-radius:10px;font-size:.95em;font-weight:600;cursor:pointer;transition:all .3s;display:inline-flex;align-items:center;gap:8px}
.btn-primary{background:linear-gradient(135deg,var(--p),var(--s));color:#fff}
.btn-primary:hover{transform:translateY(-2px);box-shadow:0 6px 20px rgba(102,126,234,0.35)}
.btn-secondary{background:var(--l);color:var(--d);border:2px solid var(--b)}
.btn-secondary:hover{background:var(--b)}
.btn-success{background:var(--ok);color:#fff}.btn-danger{background:var(--no);color:#fff}.btn-warning{background:var(--w);color:var(--d)}
.btn-sm{padding:8px 16px;font-size:.85em}.btn:disabled{opacity:.5;cursor:not-allowed}
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:15px;margin-bottom:25px}
.stat-card{background:#fff;padding:24px;border-radius:14px;text-align:center;box-shadow:0 2px 10px rgba(0,0,0,0.04);border:1px solid var(--b);transition:transform .3s}
.stat-card:hover{transform:translateY(-3px)}.stat-number{font-size:2em;font-weight:800;color:var(--p)}.stat-label{color:var(--g);font-size:.85em;margin-top:4px}
.stat-card.sold .stat-number{color:var(--ok)}.stat-card.revenue .stat-number{color:var(--s)}
.search-bar{display:flex;gap:12px;margin-bottom:24px;flex-wrap:wrap}
.search-bar input,.search-bar select{padding:12px 16px;border:2px solid var(--b);border-radius:10px;font-size:.95em;background:#fff}
.search-bar input{flex:1;min-width:200px}.search-bar input:focus,.search-bar select:focus{outline:none;border-color:var(--p)}
.inventory-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:20px}
.tool-card{background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.04);border:1px solid var(--b);transition:all .3s;position:relative}
.tool-card:hover{transform:translateY(-4px);box-shadow:0 12px 30px rgba(0,0,0,0.08)}
.tool-card.sold{opacity:.7}.tool-card.sold::after{content:'SOLD';position:absolute;top:15px;right:-30px;background:var(--ok);color:#fff;padding:4px 40px;font-size:.75em;font-weight:700;transform:rotate(45deg);letter-spacing:2px}
.tool-image{width:100%;height:220px;object-fit:cover;background:var(--l);display:flex;align-items:center;justify-content:center;color:var(--g);position:relative}
.tool-image img{width:100%;height:100%;object-fit:cover}
.tool-location-badge{position:absolute;bottom:10px;left:10px;background:rgba(0,0,0,0.7);color:#fff;padding:4px 12px;border-radius:20px;font-size:.8em;font-weight:600}
.tool-info{padding:20px}.tool-title{font-size:1.15em;font-weight:700;margin-bottom:6px;color:var(--d)}
.tool-desc{color:var(--g);font-size:.9em;margin-bottom:12px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.tool-meta{display:flex;gap:12px;margin-bottom:12px;flex-wrap:wrap}
.tool-meta span{font-size:.8em;padding:4px 10px;border-radius:6px;background:var(--l);color:var(--g);font-weight:500}
.tool-price{font-size:1.4em;font-weight:800;color:var(--p);margin-bottom:15px}
.tool-actions{display:flex;gap:8px;flex-wrap:wrap}
.barcode-container{background:#fff;padding:24px;border-radius:12px;text-align:center;margin-top:10px;border:1px solid var(--b)}
.barcode-container svg{max-width:100%}
.scanner-container{position:relative;width:100%;max-width:600px;margin:0 auto;background:#000;border-radius:16px;overflow:hidden}
#scanner-video{width:100%;display:block}
.scanner-overlay{position:absolute;top:0;left:0;right:0;bottom:0;border:2px solid rgba(102,126,234,0.5);pointer-events:none}
.scanner-laser{position:absolute;top:50%;left:10%;right:10%;height:2px;background:#f44;box-shadow:0 0 10px #f44;animation:scan 2s infinite}
@keyframes scan{0%,100%{opacity:0}50%{opacity:1}}
.scan-result{margin-top:20px;padding:24px;background:#e8f5e9;border-radius:12px;border-left:4px solid var(--ok);display:none}
.scan-result.found{display:block}.scan-result.not-found{background:#ffebee;border-left-color:var(--no);display:block}
.modal-overlay{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.6);z-index:1000;align-items:center;justify-content:center;padding:20px;backdrop-filter:blur(4px)}
.modal-overlay.active{display:flex}
.modal{background:#fff;border-radius:20px;max-width:700px;width:100%;max-height:90vh;overflow-y:auto;padding:32px;position:relative;box-shadow:0 25px 50px rgba(0,0,0,0.2)}
.modal-close{position:absolute;top:20px;right:20px;background:var(--l);border:none;width:36px;height:36px;border-radius:50%;font-size:1.3em;cursor:pointer;color:var(--g);display:flex;align-items:center;justify-content:center}
.modal-close:hover{background:var(--b);color:var(--d)}
.print-label{display:none}
@media print{body *{display:none!important}.print-label,.print-label *{display:block!important}.print-label{position:absolute;top:0;left:0;width:2in;padding:.1in;text-align:center}.print-label .label-title{font-size:10pt;font-weight:bold;margin-bottom:5px}.print-label .label-price{font-size:12pt;color:#000;margin-bottom:5px}.print-label .label-loc{font-size:8pt;color:#666;margin-bottom:5px}.print-label svg{max-width:1.8in;height:auto}}
.empty-state{text-align:center;padding:60px 20px;color:var(--g);grid-column:1/-1}
.empty-state svg{width:80px;height:80px;margin-bottom:20px;opacity:.3}
.toast{position:fixed;bottom:30px;right:30px;background:var(--d);color:#fff;padding:16px 28px;border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,0.3);display:none;z-index:2000;animation:slideIn .3s;font-weight:500}
@keyframes slideIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}
.barcode-input-group{display:flex;gap:10px;align-items:flex-end}.barcode-input-group input{flex:1}
.manual-scan-input{font-size:1.2em;letter-spacing:2px;text-align:center;font-family:monospace}
.hidden-file-input{display:none}
.filter-row{display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap;align-items:center}
.filter-row select{padding:10px 14px;border:2px solid var(--b);border-radius:10px;background:#fff;font-size:.9em;min-width:140px}
.label-item{display:flex;align-items:center;gap:15px;padding:16px;border:2px solid var(--b);border-radius:12px;cursor:pointer;transition:all .2s;background:#fff}
.label-item:hover{border-color:var(--p)}.label-item.selected{border-color:var(--p);background:rgba(102,126,234,0.05)}
.label-item input[type="checkbox"]{width:22px;height:22px;accent-color:var(--p)}
.audit-log{max-height:400px;overflow-y:auto}
.audit-entry{padding:12px 16px;border-bottom:1px solid var(--b);display:flex;justify-content:space-between;align-items:center}
.audit-entry:last-child{border-bottom:none}
.audit-time{font-size:.8em;color:var(--g)}.audit-action{font-size:.75em;padding:3px 10px;border-radius:20px;font-weight:600;text-transform:uppercase}
.audit-action.CREATE{background:#e8f5e9;color:var(--ok)}.audit-action.UPDATE{background:#fff3e0;color:#f57c00}
.audit-action.DELETE{background:#ffebee;color:var(--no)}.audit-action.SOLD{background:#e3f2fd;color:var(--p)}
.sell-form{background:var(--l);padding:20px;border-radius:12px;margin-top:16px}
.status-badge{display:inline-block;padding:4px 12px;border-radius:20px;font-size:.75em;font-weight:700;text-transform:uppercase;letter-spacing:.5px}
.status-badge.available{background:#e8f5e9;color:var(--ok)}.status-badge.sold{background:#ffebee;color:var(--no)}
</style>
</head>
<body>
<div class="container">
<header><h1>🔧 Tool Inventory System</h1><p class="subtitle">Permanent Storage · Shelf/Row/Bin Tracking · Barcode Generation</p></header>
<div class="tabs">
<button type="button" class="tab active" data-tab="add" onclick="switchTab('add')">➕ Add Tool</button>
<button type="button" class="tab" data-tab="inventory" onclick="switchTab('inventory')">📦 Inventory</button>
<button type="button" class="tab" data-tab="scan" onclick="switchTab('scan')">📷 Scan</button>
<button type="button" class="tab" data-tab="labels" onclick="switchTab('labels')">🏷️ Labels</button>
<button type="button" class="tab" data-tab="audit" onclick="switchTab('audit')">📋 Audit Log</button>
</div>

<div id="panel-add" class="panel active">
<div class="card">
<div class="card-title">➕ Add New Tool</div>
<form id="addToolForm" onsubmit="addTool(event)">
<div class="form-grid">
<div class="form-group"><label>Tool Title *</label><input type="text" id="toolTitle" required placeholder="e.g., Vintage Craftsman Wrench Set"></div>
<div class="form-group"><label>Price ($) *</label><input type="number" id="toolPrice" step="0.01" min="0" required placeholder="29.99"></div>
</div>
<div class="form-group" style="margin-bottom:20px"><label>Description</label><textarea id="toolDesc" placeholder="Condition, size, brand, any details..."></textarea></div>
<div class="form-group" style="margin-bottom:20px"><label>Location (Shelf / Row / Bin)</label><div class="location-grid">
<input type="text" id="toolShelf" placeholder="Shelf (A, B, C...)">
<input type="text" id="toolRow" placeholder="Row (1, 2, 3...)">
<input type="text" id="toolBin" placeholder="Bin (01, 02...)">
</div></div>
<div class="form-grid">
<div class="form-group"><label>Condition</label><select id="toolCondition"><option>New</option><option>Like New</option><option selected>Good</option><option>Fair</option><option>Parts</option></select></div>
<div class="form-group"><label>Notes</label><input type="text" id="toolNotes" placeholder="Internal notes..."></div>
</div>
<div class="form-group" style="margin-bottom:20px"><label>Photo (Optional)</label>
<div class="photo-upload" id="photoUpload" onclick="document.getElementById('photoInput').click()">
<input type="file" id="photoInput" class="hidden-file-input" accept="image/*" capture="environment" onchange="handlePhotoSelect(event)">
<div class="upload-text"><svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin-bottom:12px;opacity:.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg><p style="font-weight:600">Click to upload or take photo</p><small style="color:var(--g)">JPG, PNG (auto-compressed)</small></div>
<img id="photoPreview" class="photo-preview" alt="Preview">
</div>
<button type="button" class="btn btn-secondary btn-sm" onclick="clearPhoto()" id="clearPhotoBtn" style="display:none;margin-top:10px">Remove Photo</button>
</div>
<div class="form-group" style="margin-bottom:20px"><label>Barcode ID (Auto-generated)</label>
<div class="barcode-input-group"><input type="text" id="barcodeId" readonly style="background:var(--l)"><button type="button" class="btn btn-secondary" onclick="regenerateBarcode()">🔄 Regenerate</button></div>
<small style="color:var(--g)">Unique code printed on barcode label</small></div>
<div class="barcode-container" id="previewBarcodeContainer" style="display:none"><svg id="previewBarcode"></svg></div>
<div style="display:flex;gap:10px;margin-top:20px"><button type="submit" class="btn btn-primary">💾 Save Tool & Generate Barcode</button><button type="button" class="btn btn-secondary" onclick="resetForm()">Clear</button></div>
</form>
</div>
</div>

<div id="panel-inventory" class="panel">
<div class="stats-grid" id="statsGrid">
<div class="stat-card"><div class="stat-number" id="totalTools">0</div><div class="stat-label">Total Tools</div></div>
<div class="stat-card"><div class="stat-number" id="availableTools">0</div><div class="stat-label">Available</div></div>
<div class="stat-card sold"><div class="stat-number" id="soldTools">0</div><div class="stat-label">Sold</div></div>
<div class="stat-card"><div class="stat-number" id="totalValue">$0</div><div class="stat-label">Inventory Value</div></div>
<div class="stat-card revenue"><div class="stat-number" id="totalRevenue">$0</div><div class="stat-label">Revenue</div></div>
<div class="stat-card"><div class="stat-number" id="withPhotos">0</div><div class="stat-label">With Photos</div></div>
</div>
<div class="card">
<div class="search-bar">
<input type="text" id="searchInput" placeholder="🔍 Search by title, description, barcode, or location..." oninput="searchTools()">
<select id="statusFilter" onchange="searchTools()"><option value="">All Status</option><option value="available">Available</option><option value="sold">Sold</option></select>
<select id="sortFilter" onchange="searchTools()"><option value="created_at_desc">Newest First</option><option value="created_at_asc">Oldest First</option><option value="price_desc">Price: High→Low</option><option value="price_asc">Price: Low→High</option><option value="title_asc">Title: A→Z</option><option value="title_desc">Title: Z→A</option></select>
</div>
<div class="filter-row" id="locationFilters">
<select id="shelfFilter" onchange="searchTools()"><option value="">All Shelves</option></select>
<select id="rowFilter" onchange="searchTools()"><option value="">All Rows</option></select>
<select id="binFilter" onchange="searchTools()"><option value="">All Bins</option></select>
<button class="btn btn-secondary btn-sm" onclick="clearFilters()">Clear Filters</button>
</div>
<div id="inventoryList" class="inventory-grid">
<div class="empty-state"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="80" height="80"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg><h3>No tools yet</h3><p>Add your first tool to get started!</p></div>
</div>
</div>
</div>

<div id="panel-scan" class="panel">
<div class="card">
<div class="card-title">📷 Scan Barcode</div>
<p style="margin-bottom:20px;color:var(--g)">Use camera to scan, or type barcode manually below.</p>
<div class="form-group" style="margin-bottom:20px"><label>Manual Entry</label><div style="display:flex;gap:10px"><input type="text" id="manualBarcode" class="manual-scan-input" placeholder="Type barcode..."><button class="btn btn-primary" onclick="manualScan()">🔍 Lookup</button></div></div>
<div class="scanner-container" id="scannerContainer"><video id="scanner-video"></video><div class="scanner-overlay"><div class="scanner-laser"></div></div></div>
<div style="text-align:center;margin-top:15px"><button class="btn btn-primary" id="cameraBtn" onclick="toggleScanner()">📷 Start Camera</button><p style="margin-top:10px;color:var(--g);font-size:.9em">Camera works best in good lighting. Hold barcode steady.</p></div>
<div id="scanResult" class="scan-result"><h3 id="scanResultTitle"></h3><p id="scanResultDesc"></p><div class="tool-price" id="scanResultPrice"></div><div id="scanResultLocation"></div><div id="scanResultImage"></div></div>
</div>
</div>

<div id="panel-labels" class="panel">
<div class="card">
<div class="card-title">🏷️ Print Barcode Labels</div>
<p style="margin-bottom:20px;color:var(--g)">Select tools to print labels with location info.</p>
<div id="labelList" style="margin-bottom:20px"><p style="color:var(--g);text-align:center;padding:40px">No tools available.</p></div>
<div style="display:flex;gap:10px;justify-content:center"><button class="btn btn-primary" onclick="printSelectedLabels()">🖨️ Print Selected</button><button class="btn btn-secondary" onclick="selectAllLabels()">Select All</button><button class="btn btn-secondary" onclick="deselectAllLabels()">Deselect All</button></div>
</div>
</div>

<div id="panel-audit" class="panel">
<div class="card">
<div class="card-title">📋 Audit Log</div>
<p style="margin-bottom:20px;color:var(--g)">Track all changes to your inventory.</p>
<div class="audit-log" id="auditLog"><p style="color:var(--g);text-align:center;padding:40px">Loading...</p></div>
</div>
<div class="card">
<div class="card-title">💾 Backup & Restore</div>
<div style="display:flex;gap:12px;flex-wrap:wrap"><button class="btn btn-primary" onclick="exportCSV()">📥 Export CSV</button><label class="btn btn-secondary" style="cursor:pointer">📤 Import CSV<input type="file" class="hidden-file-input" accept=".csv" onchange="importCSV(event)"></label></div>
</div>
</div>
</div>

<div class="modal-overlay" id="toolModal"><div class="modal"><button class="modal-close" onclick="closeModal()">&times;</button><div id="modalContent"></div></div></div>
<div class="print-label" id="printLabelContainer"></div>
<div class="toast" id="toast"></div>

<script>
let currentPhoto=null,photoAction='none',scannerActive=false,editingToolId=null;
document.addEventListener('DOMContentLoaded',()=>{
    generateBarcodeId();
    loadTools();
    loadStats();
    loadLocations();
    loadAuditLog();
    document.getElementById('manualBarcode').addEventListener('keypress',e=>{if(e.key==='Enter')manualScan()});
    document.getElementById('toolModal').addEventListener('click',e=>{if(e.target===e.currentTarget)closeModal()});
    document.querySelectorAll('.tab').forEach(tab=>tab.addEventListener('click',()=>switchTab(tab.getAttribute('data-tab')||tab.textContent.toLowerCase())));
});
async function apiGet(endpoint,params={}){const q=new URLSearchParams(params).toString();const url=q?`${endpoint}?${q}`:endpoint;const r=await fetch(url);return r.json()}
async function apiPost(endpoint,data){const r=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});return r.json()}
async function apiDelete(endpoint){const r=await fetch(endpoint,{method:'DELETE'});return r.json()}
function switchTab(tabName){
    const tabs = document.querySelectorAll('.tab');
    const panels = document.querySelectorAll('.panel');
    tabs.forEach(t=>t.classList.remove('active'));
    panels.forEach(p=>p.classList.remove('active'));
    const mapping = {add:0,inventory:1,scan:2,labels:3,audit:4};
    const tabIndex = mapping[tabName];
    if(tabIndex!==undefined && tabs[tabIndex]) tabs[tabIndex].classList.add('active');
    const panel = document.getElementById('panel-'+tabName);
    if(panel) panel.classList.add('active');
    if(tabName==='inventory'){loadTools();loadStats()}
    if(tabName==='labels')updateLabelList();
    if(tabName==='audit')loadAuditLog();
}
function generateBarcodeId(){const p="TL",ts=Date.now().toString(36).toUpperCase().slice(-8),rand=Math.random().toString(36).substring(2,6).toUpperCase();const id=p+ts+rand;document.getElementById('barcodeId').value=id;generateBarcodePreview(id);return id}
function regenerateBarcode(){generateBarcodeId();showToast('New barcode ID generated')}
function generateBarcodePreview(code){const c=document.getElementById('previewBarcodeContainer'),s=document.getElementById('previewBarcode');if(code&&typeof JsBarcode!=='undefined'){c.style.display='block';JsBarcode(s,code,{format:"CODE128",lineColor:"#000",width:2,height:60,displayValue:true,fontSize:14,margin:10})}}
function handlePhotoSelect(e){const f=e.target.files[0];if(!f)return;const r=new FileReader();r.onload=e=>{const img=new Image();img.onload=()=>{const cv=document.createElement('canvas'),ctx=cv.getContext('2d');let w=img.width,h=img.height;const mx=800;if(w>mx){h=(h*mx)/w;w=mx}cv.width=w;cv.height=h;ctx.drawImage(img,0,0,w,h);currentPhoto=cv.toDataURL('image/jpeg',0.7);photoAction='new';document.getElementById('photoPreview').src=currentPhoto;document.getElementById('photoUpload').classList.add('has-image');document.getElementById('clearPhotoBtn').style.display='inline-block'};img.src=e.target.result};r.readAsDataURL(f)}
function clearPhoto(){currentPhoto=null;photoAction=editingToolId?'remove':'none';document.getElementById('photoInput').value='';document.getElementById('photoPreview').src='';document.getElementById('photoUpload').classList.remove('has-image');document.getElementById('clearPhotoBtn').style.display='none'}
async function addTool(e){e.preventDefault();const data={barcode:document.getElementById('barcodeId').value,title:document.getElementById('toolTitle').value,price:parseFloat(document.getElementById('toolPrice').value||0),description:document.getElementById('toolDesc').value,condition:document.getElementById('toolCondition').value,shelf:document.getElementById('toolShelf').value,row_num:document.getElementById('toolRow').value,bin:document.getElementById('toolBin').value,notes:document.getElementById('toolNotes').value,photo_base64:photoAction==='keep'?'KEEP_EXISTING':photoAction==='remove'?'REMOVE':currentPhoto};let res;if(editingToolId){res=await apiPost('/api/tools/'+editingToolId,data);showToast('Tool updated!');editingToolId=null;document.querySelector('#panel-add .card-title').textContent='➕ Add New Tool';document.querySelector('button[type="submit"]').textContent='💾 Save Tool & Generate Barcode'}else{res=await apiPost('/api/tools',data);showToast('✅ "'+data.title+'" added!')}resetForm();generateBarcodeId();loadLocations();setTimeout(()=>switchTab('inventory'),500)}
function resetForm(){document.getElementById('addToolForm').reset();clearPhoto();editingToolId=null;photoAction='none';document.querySelector('#panel-add .card-title').textContent='➕ Add New Tool';document.querySelector('button[type="submit"]').textContent='💾 Save Tool & Generate Barcode'}
async function loadTools(){const params={search:document.getElementById('searchInput').value,status:document.getElementById('statusFilter').value,sort:document.getElementById('sortFilter').value,shelf:document.getElementById('shelfFilter').value,row:document.getElementById('rowFilter').value,bin:document.getElementById('binFilter').value};const d=await apiGet('/api/tools',params);renderTools(d.tools)}
function renderTools(tools){const c=document.getElementById('inventoryList');if(tools.length===0){c.innerHTML='<div class="empty-state"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="80" height="80"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg><h3>No tools found</h3><p>Try adjusting search or filters.</p></div>';return}c.innerHTML=tools.map(t=>`<div class="tool-card ${t.status}"><div class="tool-image">${t.photo_url?`<img src="${t.photo_url}" alt="${t.title}">`:`<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`}${t.shelf||t.row_num||t.bin?`<div class="tool-location-badge">${[t.shelf,t.row_num,t.bin].filter(Boolean).join('-')}</div>`:''}</div><div class="tool-info"><div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:6px"><div class="tool-title">${t.title}</div><span class="status-badge ${t.status}">${t.status}</span></div><div class="tool-desc">${t.description||'No description'}</div><div class="tool-meta"><span>${t.condition}</span>${t.shelf?`<span>Shelf ${t.shelf}</span>`:''}${t.row_num?`<span>Row ${t.row_num}</span>`:''}${t.bin?`<span>Bin ${t.bin}</span>`:''}</div><div class="tool-price">$${parseFloat(t.price).toFixed(2)}</div><div class="tool-actions"><button class="btn btn-sm btn-secondary" onclick="viewTool(${t.id})">👁️ View</button><button class="btn btn-sm btn-secondary" onclick="editTool(${t.id})">✏️ Edit</button>${t.status==='available'?`<button class="btn btn-sm btn-success" onclick="sellTool(${t.id})">💰 Sell</button>`:''}<button class="btn btn-sm btn-danger" onclick="deleteTool(${t.id})">🗑️</button></div></div></div>`).join('')}
function searchTools(){loadTools()}
function clearFilters(){document.getElementById('searchInput').value='';document.getElementById('statusFilter').value='';document.getElementById('shelfFilter').value='';document.getElementById('rowFilter').value='';document.getElementById('binFilter').value='';loadTools()}
async function loadStats(){const d=await apiGet('/api/stats');document.getElementById('totalTools').textContent=d.total;document.getElementById('availableTools').textContent=d.available;document.getElementById('soldTools').textContent=d.sold;document.getElementById('totalValue').textContent='$'+d.available_value.toFixed(2);document.getElementById('totalRevenue').textContent='$'+d.revenue.toFixed(2);document.getElementById('withPhotos').textContent=d.with_photos}
async function loadLocations(){const d=await apiGet('/api/locations');const u=(id,items,label)=>{const s=document.getElementById(id);const cv=s.value;s.innerHTML=`<option value="">All ${label}</option>`+items.map(i=>`<option value="${i}">${i}</option>`).join('');s.value=cv};u('shelfFilter',d.shelves,'Shelves');u('rowFilter',d.rows,'Rows');u('binFilter',d.bins,'Bins')}
async function viewTool(id){const d=await apiGet('/api/tools');const t=d.tools.find(x=>x.id===id);if(!t)return;const loc=[t.shelf,t.row_num,t.bin].filter(Boolean).join(' / ')||'Not assigned';document.getElementById('modalContent').innerHTML=`<h2>${t.title}</h2><div style="margin:20px 0">${t.photo_url?`<img src="${t.photo_url}" style="max-width:100%;border-radius:12px;margin-bottom:15px">`:''}<div class="tool-price" style="font-size:1.6em">$${parseFloat(t.price).toFixed(2)}</div><p style="color:var(--g);margin:10px 0">${t.description||'No description'}</p><div class="tool-meta" style="margin:15px 0"><span>Condition: ${t.condition}</span><span>Location: ${loc}</span><span>Status: ${t.status}</span></div>${t.notes?`<p style="background:var(--l);padding:12px;border-radius:8px;margin:10px 0;font-size:.9em"><strong>Notes:</strong> ${t.notes}</p>`:''}<p style="color:var(--g);font-size:.85em">Barcode: ${t.barcode}</p><p style="color:var(--g);font-size:.85em">Added: ${new Date(t.created_at).toLocaleDateString()}</p>${t.status==='sold'?`<div style="background:#e8f5e9;padding:12px;border-radius:8px;margin-top:10px"><strong>Sold to:</strong> ${t.buyer_name||'N/A'}<br><strong>Sale Price:</strong> $${parseFloat(t.sale_price||0).toFixed(2)}<br><strong>Sale Date:</strong> ${t.sale_date?new Date(t.sale_date).toLocaleDateString():'N/A'}</div>`:''}</div><div class="barcode-container"><svg id="modalBarcode"></svg></div><div style="margin-top:20px;display:flex;gap:10px"><button class="btn btn-primary" onclick="printSingleLabel(${t.id});closeModal()">🖨️ Print Label</button><button class="btn btn-secondary" onclick="closeModal()">Close</button></div>`;document.getElementById('toolModal').classList.add('active');setTimeout(()=>{if(typeof JsBarcode!=='undefined')JsBarcode('#modalBarcode',t.barcode,{format:"CODE128",width:2,height:80,displayValue:true,fontSize:16})},100)}
async function editTool(id){const d=await apiGet('/api/tools');const t=d.tools.find(x=>x.id===id);if(!t)return;editingToolId=id;document.getElementById('toolTitle').value=t.title;document.getElementById('toolPrice').value=t.price;document.getElementById('toolDesc').value=t.description||'';document.getElementById('toolCondition').value=t.condition;document.getElementById('toolShelf').value=t.shelf||'';document.getElementById('toolRow').value=t.row_num||'';document.getElementById('toolBin').value=t.bin||'';document.getElementById('toolNotes').value=t.notes||'';document.getElementById('barcodeId').value=t.barcode;if(t.photo_url){document.getElementById('photoPreview').src=t.photo_url;document.getElementById('photoUpload').classList.add('has-image');document.getElementById('clearPhotoBtn').style.display='inline-block';currentPhoto=null;photoAction='keep'}else{currentPhoto=null;photoAction='none'}generateBarcodePreview(t.barcode);document.querySelector('#panel-add .card-title').textContent='✏️ Edit Tool';document.querySelector('button[type="submit"]').textContent='💾 Update Tool';switchTab('add')}
async function sellTool(id){const d=await apiGet('/api/tools');const t=d.tools.find(x=>x.id===id);if(!t)return;const buyer=prompt('Buyer name:');if(buyer===null)return;const sp=prompt('Sale price:',t.price);if(sp===null)return;await apiPost('/api/sell',{tool_id:id,buyer_name:buyer,sale_price:parseFloat(sp)});showToast('💰 Sold "'+t.title+'" to '+buyer+'!');loadTools();loadStats();loadAuditLog()}
async function deleteTool(id){if(!confirm('Delete this tool? Cannot be undone.'))return;await apiDelete('/api/tools/'+id);showToast('Tool deleted');loadTools();loadStats();loadLocations();loadAuditLog()}
function closeModal(){document.getElementById('toolModal').classList.remove('active')}
function toggleScanner(){const b=document.getElementById('cameraBtn');if(!scannerActive){if(typeof Quagga==='undefined'){showToast('Scanner library not loaded');return}Quagga.init({inputStream:{name:"Live",type:"LiveStream",target:document.getElementById('scanner-video'),constraints:{facingMode:"environment",width:{min:640},height:{min:480}}},decoder:{readers:["code_128_reader","ean_reader","ean_8_reader","code_39_reader"]},locator:{patchSize:"medium",halfSample:true}},err=>{if(err){showToast('Camera error: '+err.message);return}Quagga.start();scannerActive=true;b.textContent='⏹️ Stop Camera';showToast('Camera started')});Quagga.onDetected(r=>{handleScanResult(r.codeResult.code);toggleScanner()})}else{Quagga.stop();scannerActive=false;b.textContent='📷 Start Camera'}}
async function manualScan(){const c=document.getElementById('manualBarcode').value.trim();if(c){await handleScanResult(c);document.getElementById('manualBarcode').value=''}else showToast('Enter a barcode number')}
async function handleScanResult(code){code = String(code||'').trim();const d=await apiGet('/api/tools');const t=d.tools.find(x=>String(x.barcode||'').trim()===code);const r=document.getElementById('scanResult');if(t){const loc=[t.shelf,t.row_num,t.bin].filter(Boolean).join(' / ')||'Not assigned';r.className='scan-result found';r.innerHTML=`<h3>${t.title}</h3><p>${t.description||'No description'}</p><div class="tool-price">$${parseFloat(t.price).toFixed(2)}</div><div style="margin:10px 0;color:var(--g)"><strong>Location:</strong> ${loc}<br><strong>Condition:</strong> ${t.condition}<br><strong>Status:</strong> ${t.status}</div>${t.photo_url?`<img src="${t.photo_url}" style="max-width:250px;border-radius:12px;margin-top:10px">`:''}`;showToast('Found: '+t.title)}else{r.className='scan-result not-found';r.innerHTML='<h3>Tool Not Found</h3><p>No tool with barcode: <strong>'+code+'</strong></p><p>This barcode is not in your inventory.</p>';showToast('Tool not found')}}
async function updateLabelList(){const d=await apiGet('/api/tools',{status:'available'});const c=document.getElementById('labelList');if(d.tools.length===0){c.innerHTML='<p style="color:var(--g);text-align:center;padding:40px">No available tools.</p>';return}c.innerHTML=d.tools.map(t=>`<div class="label-item" onclick="toggleLabelSelection(this,${t.id})" data-id="${t.id}"><input type="checkbox" onchange="event.stopPropagation()"><div style="flex:1"><div style="font-weight:700">${t.title}</div><div style="color:var(--p);font-weight:700">$${parseFloat(t.price).toFixed(2)}</div><div style="font-size:.8em;color:var(--g)">${t.barcode} ${t.shelf?'| Shelf '+t.shelf:''} ${t.row_num?'Row '+t.row_num:''} ${t.bin?'Bin '+t.bin:''}</div></div></div>`).join('')}
function toggleLabelSelection(el,id){const cb=el.querySelector('input');cb.checked=!cb.checked;el.classList.toggle('selected',cb.checked)}
function selectAllLabels(){document.querySelectorAll('.label-item').forEach(el=>{el.querySelector('input').checked=true;el.classList.add('selected')})}
function deselectAllLabels(){document.querySelectorAll('.label-item').forEach(el=>{el.querySelector('input').checked=false;el.classList.remove('selected')})}
async function printSelectedLabels(){const sel=Array.from(document.querySelectorAll('.label-item.selected')).map(el=>parseInt(el.dataset.id));if(sel.length===0){showToast('Select at least one tool');return}const d=await apiGet('/api/tools');const tp=d.tools.filter(t=>sel.includes(t.id));printLabels(tp)}
async function printSingleLabel(id){const d=await apiGet('/api/tools');const t=d.tools.find(x=>x.id===id);if(t)printLabels([t])}
function printLabels(tools){const c=document.getElementById('printLabelContainer');c.innerHTML=tools.map(t=>{const loc=[t.shelf,t.row_num,t.bin].filter(Boolean).join('-');return`<div style="page-break-after:always;width:2in;padding:.1in;text-align:center;font-family:Arial,sans-serif"><div style="font-size:10pt;font-weight:bold;margin-bottom:4px;word-wrap:break-word">${t.title}</div><div style="font-size:13pt;font-weight:bold;color:#000;margin-bottom:4px">$${parseFloat(t.price).toFixed(2)}</div>${loc?`<div style="font-size:8pt;color:#666;margin-bottom:4px">${loc}</div>`:''}<svg id="print-barcode-${t.id}" style="max-width:1.8in;height:.5in"></svg></div>`}).join('');tools.forEach(t=>{if(typeof JsBarcode!=='undefined')JsBarcode('#print-barcode-'+t.id,t.barcode,{format:"CODE128",width:1.5,height:40,displayValue:true,fontSize:8,margin:0})});setTimeout(()=>window.print(),500)}
async function loadAuditLog(){const d=await apiGet('/api/audit',{limit:50});const c=document.getElementById('auditLog');if(d.logs.length===0){c.innerHTML='<p style="color:var(--g);text-align:center;padding:40px">No activity yet.</p>';return}c.innerHTML=d.logs.map(l=>`<div class="audit-entry"><div><div style="font-weight:600">${l.tool_title||'Deleted Tool'}</div><div style="font-size:.85em;color:var(--g)">${l.details}</div></div><div style="text-align:right"><span class="audit-action ${l.action}">${l.action}</span><div class="audit-time">${new Date(l.timestamp).toLocaleString()}</div></div></div>`).join('')}
async function exportCSV(){const r=await fetch('/api/export');if(!r.ok){const err=await r.text();showToast('Export failed');console.error('Export error',err);return}const blob=await r.blob();const filename=(r.headers.get('Content-Disposition')||'').match(/filename="?([^";]+)"?/)?.[1]||'inventory.csv';const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=filename;a.click();URL.revokeObjectURL(url);showToast('Exported CSV file!')}
async function importCSV(e){const f=e.target.files[0];if(!f)return;const text=await f.text();const lines=text.split('\n').filter(l=>l.trim());const headers=lines[0].split(',').map(h=>h.trim().replace(/"/g,''));const items=[];for(let i=1;i<lines.length;i++){const values=lines[i].split(',').map(v=>v.trim().replace(/"/g,''));const item={};headers.forEach((h,idx)=>{item[h.toLowerCase()]=values[idx]||''});if(item.title)items.push(item)}if(items.length===0){showToast('No valid items found');return}if(!confirm('Import '+items.length+' tools?'))return;const r=await apiPost('/api/import',{items:items});showToast('Imported '+r.imported+' tools!');loadTools();loadStats();loadLocations();loadAuditLog()}
function showToast(m){const t=document.getElementById('toast');t.textContent=m;t.style.display='block';setTimeout(()=>t.style.display='none',3000)}
</script>
</body>
</html>"""

# ─── HTTP HANDLER ─────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        p = urlparse(self.path)
        path = p.path
        if path == "/":
            self.send_html(HTML_PAGE)
        elif path.startswith("/api/photo/"):
            self.send_photo(path.split("/")[-1])
        elif path == "/api/tools":
            self.list_tools(parse_qs(p.query))
        elif path == "/api/stats":
            self.get_stats()
        elif path == "/api/locations":
            self.get_locations()
        elif path == "/api/audit":
            self.get_audit(parse_qs(p.query))
        elif path == "/api/export":
            self.export_csv()
        else:
            self.send_error(404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n).decode()
        try: data = json.loads(body)
        except: data = {}
        path = urlparse(self.path).path
        if path == "/api/tools":
            self.create_tool(data)
        elif path.startswith("/api/tools/"):
            tid = path.split("/")[-1]
            if tid.isdigit(): self.update_tool(int(tid), data)
        elif path == "/api/sell":
            self.sell_tool(data)
        elif path == "/api/import":
            self.import_csv(data)
        else:
            self.send_error(404)

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path.startswith("/api/tools/"):
            tid = path.split("/")[-1]
            if tid.isdigit(): self.delete_tool(int(tid))
        else:
            self.send_error(404)

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def send_html(self, html):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def send_photo(self, fn):
        fp = PHOTO_DIR / fn
        if fp.exists():
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.end_headers()
            self.wfile.write(fp.read_bytes())
        else:
            self.send_error(404)

    # ─── API METHODS ──────────────────────────────────────────────────────────
    def list_tools(self, params):
        conn = get_db(); c = conn.cursor()
        q = "SELECT * FROM tools WHERE 1=1"; a = []
        if "search" in params:
            s = f"%{params['search'][0]}%"
            q += " AND (title LIKE ? OR description LIKE ? OR barcode LIKE ? OR shelf LIKE ? OR row_num LIKE ? OR bin LIKE ?)"
            a.extend([s]*6)
        for f in ["status","shelf","row","bin"]:
            if f in params and params[f][0]:
                q += f" AND {'row_num' if f=='row' else f} = ?"; a.append(params[f][0])
        sort = params.get("sort", ["created_at_desc"])[0]
        sm = {"created_at_desc":"created_at DESC","created_at_asc":"created_at ASC","price_desc":"price DESC","price_asc":"price ASC","title_asc":"title ASC","title_desc":"title DESC"}
        q += f" ORDER BY {sm.get(sort,'created_at DESC')}"
        c.execute(q, a); rows = c.fetchall(); conn.close()
        tools = []
        for r in rows:
            t = dict(r); t["photo_url"] = f"/api/photo/{t['photo_filename']}" if t["photo_filename"] else None
            tools.append(t)
        self.send_json({"tools": tools, "count": len(tools)})

    def create_tool(self, data):
        bc = data.get("barcode") or gen_barcode()
        pf = save_photo(data.get("photo_base64"))
        conn = get_db(); c = conn.cursor()
        c.execute("""INSERT INTO tools (barcode,title,description,price,condition,shelf,row_num,bin,photo_filename,notes)
                     VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (bc, data.get("title",""), data.get("description",""), float(data.get("price",0)),
             data.get("condition","Good"), data.get("shelf",""), data.get("row_num",""),
             data.get("bin",""), pf, data.get("notes","")))
        tid = c.lastrowid; conn.commit(); conn.close()
        log_action(tid, "CREATE", f"Created: {data.get('title')}")
        self.send_json({"success": True, "id": tid, "barcode": bc})

    def update_tool(self, tid, data):
        conn = get_db(); c = conn.cursor()
        c.execute("SELECT photo_filename FROM tools WHERE id=?", (tid,))
        row = c.fetchone(); old = row["photo_filename"] if row else None; pf = old
        if "photo_base64" in data and data["photo_base64"]:
            if data["photo_base64"] != "KEEP_EXISTING":
                pf = save_photo(data["photo_base64"])
                if pf and old: del_photo(old)
        c.execute("""UPDATE tools SET title=?,description=?,price=?,condition=?,shelf=?,row_num=?,bin=?,photo_filename=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (data.get("title",""), data.get("description",""), float(data.get("price",0)),
             data.get("condition","Good"), data.get("shelf",""), data.get("row_num",""),
             data.get("bin",""), pf, data.get("notes",""), tid))
        conn.commit(); conn.close()
        log_action(tid, "UPDATE", f"Updated: {data.get('title')}")
        self.send_json({"success": True})

    def delete_tool(self, tid):
        conn = get_db(); c = conn.cursor()
        c.execute("SELECT photo_filename,title FROM tools WHERE id=?", (tid,))
        row = c.fetchone()
        if row: del_photo(row["photo_filename"]); log_action(tid, "DELETE", f"Deleted: {row['title']}")
        c.execute("DELETE FROM tools WHERE id=?", (tid,)); conn.commit(); conn.close()
        self.send_json({"success": True})

    def sell_tool(self, data):
        tid = data.get("tool_id")
        conn = get_db(); c = conn.cursor()
        c.execute("""UPDATE tools SET status='sold',buyer_name=?,sale_price=?,sale_date=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (data.get("buyer_name",""), float(data.get("sale_price",0)), tid))
        conn.commit(); conn.close()
        log_action(tid, "SOLD", f"Sold to {data.get('buyer_name')} for ${data.get('sale_price')}")
        self.send_json({"success": True})

    def get_stats(self):
        conn = get_db(); c = conn.cursor()
        c.execute("SELECT COUNT(*) as t FROM tools"); total = c.fetchone()["t"]
        c.execute("SELECT COUNT(*) as s FROM tools WHERE status='sold'"); sold = c.fetchone()["s"]
        c.execute("SELECT COALESCE(SUM(price),0) as v FROM tools WHERE status='available'"); av = c.fetchone()["v"]
        c.execute("SELECT COALESCE(SUM(sale_price),0) as r FROM tools WHERE status='sold'"); rev = c.fetchone()["r"]
        c.execute("SELECT COUNT(*) as p FROM tools WHERE photo_filename IS NOT NULL"); wp = c.fetchone()["p"]
        conn.close()
        self.send_json({"total":total,"sold":sold,"available":total-sold,"available_value":round(av,2),"revenue":round(rev,2),"with_photos":wp})

    def get_locations(self):
        conn = get_db(); c = conn.cursor(); out = {}
        for col, key in [("shelf","shelves"),("row_num","rows"),("bin","bins")]:
            c.execute(f"SELECT DISTINCT {col} FROM tools WHERE {col} IS NOT NULL AND {col}!='' ORDER BY {col}")
            out[key] = [r[col] for r in c.fetchall()]
        conn.close(); self.send_json(out)

    def get_audit(self, params):
        conn = get_db(); c = conn.cursor(); lim = int(params.get("limit",["50"])[0])
        c.execute("""SELECT a.*, t.title as tool_title FROM audit_log a LEFT JOIN tools t ON a.tool_id=t.id ORDER BY a.timestamp DESC LIMIT ?""", (lim,))
        logs = [dict(r) for r in c.fetchall()]; conn.close()
        self.send_json({"logs": logs})

    def export_csv(self):
        conn = get_db(); c = conn.cursor()
        c.execute("SELECT * FROM tools ORDER BY created_at DESC"); rows = c.fetchall(); conn.close()
        if not rows:
            self.send_error(404, "No tools to export")
            return
        out = io.StringIO(); w = csv.writer(out)
        w.writerow(["ID","Barcode","Title","Description","Price","Condition","Shelf","Row","Bin","Status","Buyer","Sale Price","Sale Date","Notes","Created At"])
        for r in rows:
            w.writerow([r["id"],r["barcode"],r["title"],r["description"],r["price"],r["condition"],r["shelf"],r["row_num"],r["bin"],r["status"],r["buyer_name"],r["sale_price"],r["sale_date"],r["notes"],r["created_at"]])
        fn = f"inventory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        csv_data = out.getvalue().encode('utf-8')
        (EXPORT_DIR/fn).write_bytes(csv_data)
        self.send_response(200)
        self.send_header('Content-Type', 'text/csv; charset=utf-8')
        self.send_header('Content-Disposition', f'attachment; filename="{fn}"')
        self.send_header('Content-Length', str(len(csv_data)))
        self.end_headers()
        self.wfile.write(csv_data)

    def import_csv(self, data):
        items = data.get("items",[])
        if not items: self.send_json({"error":"No items"},400); return
        conn = get_db(); c = conn.cursor(); n = 0
        for item in items:
            try:
                bc = item.get("barcode") or gen_barcode()
                c.execute("""INSERT INTO tools (barcode,title,description,price,condition,shelf,row_num,bin,notes,status)
                             VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (bc, item.get("title",""), item.get("description",""), float(item.get("price",0)),
                     item.get("condition","Good"), item.get("shelf",""), item.get("row_num",""),
                     item.get("bin",""), item.get("notes",""), item.get("status","available")))
                n += 1
            except Exception as e: print(f"[IMPORT ERR] {e}")
        conn.commit(); conn.close()
        self.send_json({"success":True,"imported":n})

# ─── START SERVER ─────────────────────────────────────────────────────────────
def main():
    init_db()
    srv = HTTPServer(("localhost", PORT), Handler)
    print(f"\n{'='*60}")
    print(f"  🔧 TOOL INVENTORY SYSTEM")
    print(f"  Running at: http://localhost:{PORT}")
    print(f"  Data folder: {APP_DIR}")
    print(f"{'='*60}\n")
    threading.Thread(target=lambda:(time.sleep(1),webbrowser.open(f"http://localhost:{PORT}")),daemon=True).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: print("\n👋 Stopped."); srv.shutdown()

if __name__ == "__main__":
    main()

