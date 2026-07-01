import os
import re
import json
import time
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, make_response

app = Flask(__name__)

# --- ARCHITECTURE LAYER: SPLIT-FILE COMPANION MANAGEMENT ---

def get_all_srt_files():
    """Scans repository and extracts subtitle data grouped by Series name."""
    catalog = {}
    for root, dirs, files in os.walk("."):
        if any(h in root for h in [".git", ".devcontainer", "__pycache__"]):
            continue
        for file in files:
            if file.endswith(".srt"):
                relative_path = os.path.relpath(os.path.join(root, file), ".")
                
                # Smart categorization logic: Group files by folder hierarchy or filename markers
                # Expected structure example: ./The Secret of Us/EP1_Spanish.srt
                parts = relative_path.split(os.sep)
                if len(parts) >= 2:
                    series_name = parts[0]
                    file_label = os.sep.join(parts[1:])
                else:
                    # Fallback if files are sitting in the root folder
                    series_name = "Independent Tracks"
                    file_label = relative_path
                
                if series_name not in catalog:
                    catalog[series_name] = []
                catalog[series_name].append({
                    "path": relative_path,
                    "label": file_label
                })
    return catalog

def parse_srt(file_path):
    """Reads a pure production SRT file."""
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    blocks = re.split(r'\n\s*\n', content.strip())
    subtitles = []
    
    for block in blocks:
        lines = block.split('\n')
        if len(lines) >= 3:
            line_idx = lines[0].strip()
            timecode = lines[1].strip()
            text = " ".join(lines[2:]).strip()
            subtitles.append({
                "index": line_idx,
                "timecode": timecode,
                "text": text
            })
    return subtitles

def get_or_create_metadata(srt_path, total_blocks):
    """Manages the parallel tracking layer without touching the pristine SRT."""
    meta_path = srt_path + ".meta.json"
    
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                pass # If corrupt, auto-generate fallback recovery layout node
                
    # Auto-generation sequence if file doesn't exist
    default_meta = {}
    for idx in range(1, total_blocks + 1):
        default_meta[str(idx)] = {
            "status": "unassigned", # options: unassigned, progress, revision, done
            "last_updated_by": "System Engine",
            "last_updated_at": int(time.time()),
            "locked_by": ""
        }
    
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(default_meta, f, indent=2)
    return default_meta

def save_split_layers(srt_path, subtitles_list, metadata_dict):
    """Writes to both files completely independently."""
    # 1. Output Pristine Production SRT Track
    with open(srt_path, "w", encoding="utf-8") as f:
        for sub in subtitles_list:
            f.write(f"{sub['index']}\n{sub['timecode']}\n{sub['text']}\n\n")
            
    # 2. Output Workflow Companion JSON
    meta_path = srt_path + ".meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata_dict, f, indent=2)


# --- HTML STUDIO SYSTEM TEMPLATE (UI GRID LAYER) ---

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html>
<head>
    <title>LingOrm Fan Subtitles - Production Studio</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body {
            margin: 0; padding: 0;
            font-family: 'Inter', sans-serif;
            background: #0b0914; color: #f3f4f6;
            display: flex; flex-direction: column; height: 100vh;
            overflow: hidden;
        }
        header {
            background: #110e21; padding: 16px 28px;
            display: flex; justify-content: space-between; align-items: center;
            border-bottom: 1px solid rgba(113, 237, 255, 0.15);
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
            z-index: 100;
        }
        h1 { margin: 0; font-size: 20px; color: #71EDFF; font-weight: 700; letter-spacing: -0.5px; }
        .brand-badge { background: linear-gradient(135deg, #FF77ED, #71EDFF); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        
        .user-identity-box {
            display: flex; align-items: center; gap: 10px;
            background: rgba(255,255,255,0.03); padding: 6px 14px; border-radius: 6px;
            border: 1px solid rgba(255,255,255,0.05); font-size: 12px;
        }
        .user-identity-box input {
            background: transparent; border: none; color: #FF77ED; font-weight: 700;
            width: 100px; outline: none; font-family: inherit;
        }

        .workspace { display: flex; flex: 1; overflow: hidden; }
        
        /* Studio Playback Viewport */
        .video-pane {
            width: 45%; background: #07050d;
            display: flex; flex-direction: column; padding: 24px;
            border-right: 1px solid rgba(255, 255, 255, 0.06);
            box-sizing: border-box; gap: 16px;
        }
        
        /* CRITICAL FIX: Higher Stacking Layer Context for Text Overlays */
        .media-container {
            width: 100%; aspect-ratio: 16/9; background: #000000;
            border-radius: 12px; border: 2px dashed rgba(113, 237, 255, 0.2);
            overflow: hidden; display: flex; flex-direction: column; justify-content: center; align-items: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5); position: relative;
        }
        iframe { width: 100%; height: 100%; border: none; z-index: 10; }
        
        /* Premium Floating Subtitle Preview - Forces rendering over top of embeds */
        .subtitle-overlay-layer {
            position: absolute; bottom: 15%; left: 0; right: 0;
            display: flex; justify-content: center; align-items: center;
            padding: 0 24px; pointer-events: none; opacity: 0; transition: opacity 0.15s ease;
            text-align: center; z-index: 99999 !important; /* Forces layout to floating crown topmost index */
        }
        .subtitle-overlay-layer.active-view { opacity: 1; }
        .overlay-text-render {
            color: #ffffff; background: rgba(0, 0, 0, 0.85);
            padding: 10px 20px; border-radius: 6px; font-size: 20px;
            font-weight: 600; border: 1px solid rgba(255, 255, 255, 0.15);
            max-width: 85%; line-height: 1.4; box-shadow: 0 4px 20px rgba(0,0,0,0.8);
            text-shadow: 0 2px 4px rgba(0,0,0,1); font-family: sans-serif;
        }
        
        .instruction-box {
            background: #110e21; border: 1px solid #2d254b; padding: 20px; border-radius: 8px;
            display: flex; flex-direction: column; gap: 10px; height: 100%; justify-content: center;
            box-sizing: border-box; width: 100%; text-align: center; z-index: 5;
        }
        .instruction-title { color: #FF77ED; font-weight: 700; font-size: 15px; }
        .step-list { margin: 0; padding-left: 20px; font-size: 13px; color: #b4b0cb; line-height: 1.7; text-align: left; }
        .step-list strong { color: #71EDFF; }

        .url-input-container {
            background: #110e21; border: 1px solid #221c38; padding: 12px; border-radius: 8px;
            display: flex; flex-direction: column; gap: 8px;
        }
        .url-input-row { display: flex; gap: 10px; }
        input[type="text"] {
            flex: 1; padding: 12px 16px; background: #07050d;
            border: 1px solid #2d254b; border-radius: 6px;
            color: #ffffff; font-family: inherit; font-size: 13px;
        }
        input[type="text"]:focus { outline: none; border-color: #71EDFF; }
        
        /* Subtitle Editing Grid Modules */
        .subtitle-pane { width: 55%; display: flex; flex-direction: column; padding: 24px; box-sizing: border-box; }
        
        /* OPTIMIZED DROP-DOWN PICKER SELECTION */
        .catalog-container { margin-bottom: 20px; display: flex; gap: 12px; }
        .styled-picker {
            flex: 1; padding: 14px; background: #110e21; border: 1px solid #221c38;
            color: #71EDFF; font-weight: 600; font-size: 14px; border-radius: 8px; cursor: pointer;
            outline: none;
        }
        
        .subtitle-list { flex: 1; overflow-y: auto; padding-right: 8px; }
        
        /* Timed Text Row Cards */
        .subtitle-card {
            background: #110e21; border: 1px solid #1d1833;
            border-left: 4px solid #2d254b; padding: 16px; margin-bottom: 12px;
            border-radius: 8px; display: flex; flex-direction: column; gap: 10px;
            transition: all 0.2s ease; position: relative;
        }
        .subtitle-card:hover { border-color: #2d254b; background: #151129; }
        .subtitle-card.active-track { border-left-color: #FF77ED; background: #181430; }
        
        /* Collaboration Workflow Sub-UI elements */
        .card-header-row { display: flex; justify-content: space-between; align-items: center; }
        .card-meta-left { display: flex; align-items: center; gap: 10px; font-size: 12px; font-weight: 600; color: #615c7a; }
        .card-meta-right { display: flex; align-items: center; gap: 8px; }
        
        .timestamp-badge { color: #71EDFF; background: rgba(113,237,255,0.07); padding: 4px 10px; border-radius: 4px; font-family: monospace; font-size: 12px; font-weight: 600; cursor: pointer; }
        .timestamp-badge:hover { background: rgba(113,237,255,0.2); color: #fff; }
        
        /* Collaborative Tag Configuration System */
        .status-badge { padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; text-transform: uppercase; cursor: pointer; }
        .status-unassigned { background: rgba(255,255,255,0.05); color: #8c88a5; border: 1px solid rgba(255,255,255,0.1); }
        .status-progress { background: rgba(255, 166, 0, 0.1); color: #ffa600; border: 1px solid rgba(255, 166, 0, 0.2); }
        .status-revision { background: rgba(255, 119, 237, 0.1); color: #FF77ED; border: 1px solid rgba(255, 119, 237, 0.2); }
        .status-done { background: rgba(113, 237, 255, 0.1); color: #71EDFF; border: 1px solid rgba(113, 237, 255, 0.3); }

        .log-footer-row { display: flex; justify-content: space-between; font-size: 11px; color: #514b6e; font-weight: 500; border-top: 1px solid rgba(255,255,255,0.02); padding-top: 6px; }
        .soft-lock-banner { background: #3a1515 !important; border-left-color: #ff5555 !important; opacity: 0.8; pointer-events: none; }
        .lock-indicator { color: #ff5555; font-size: 11px; font-weight: 700; }

        .card-textarea {
            width: 100%; background: #07050d; border: 1px solid #221c38;
            border-radius: 6px; padding: 12px; color: #ffffff;
            font-family: inherit; font-size: 14px; line-height: 1.5; resize: none; box-sizing: border-box;
        }
        .card-textarea:focus { outline: none; border-color: #FF77ED; }
        
        .btn { padding: 12px 20px; border: none; border-radius: 6px; font-weight: 600; font-size: 13px; cursor: pointer; transition: all 0.2s ease; }
        .btn-primary { background: #FF77ED; color: #0b0914; }
        .btn-success { background: #71EDFF; color: #0b0914; box-shadow: 0 0 15px rgba(113,237,255,0.2); }
        .btn-success:hover { background: #96f2ff; }
        
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #0b0914; }
        ::-webkit-scrollbar-thumb { background: #1d1833; border-radius: 4px; }
    </style>
</head>
<body>

    <header>
        <h1>🎬 <span class="brand-badge">LingOrm Fan Subtitles</span> // Core Verification Engine</h1>
        <div style="display: flex; gap: 15px; align-items: center;">
            <div class="user-identity-box">
                <span>👤 Translator Profile Name:</span>
                <input type="text" id="usernameInput" value="Translator_1">
            </div>
            <button class="btn btn-success" onclick="saveActiveFile()">💾 Commit Changes to Disk</button>
        </div>
    </header>

    <div class="workspace">
        <div class="video-pane">
            <div class="media-container" id="mediaContainer">
                <div class="subtitle-overlay-layer" id="subtitleOverlay">
                    <div class="overlay-text-render" id="overlayText">Subtitle Overlay Layer</div>
                </div>

                <div class="instruction-box" id="instructionBox">
                    <div class="instruction-title">Integrated Workspace Alignment Protocol</div>
                    <ol class="step-list">
                        <li>Load a clean production track file from the sorted catalog menu.</li>
                        <li>Launch your external media source tab and pull the active stream into <strong>Picture-In-Picture</strong> mode.</li>
                        <li>Drag the floating window over this dashed boundary box for perfect alignment tracking.</li>
                        <li><strong>Live Timed Seeking:</strong> Clicking any active cyan timestamp block will attempt synchronization callbacks to integrated YouTube iframe instances.</li>
                    </ol>
                </div>
            </div>
            
            <div class="url-input-container">
                <div style="font-size: 11px; font-weight:700; color:#615c7a; text-transform:uppercase; margin-bottom:2px;">Dynamic Media Player Multiplexer</div>
                <div class="url-input-row">
                    <input type="text" id="videoUrl" placeholder="Enter standard YouTube link to establish real-time active tracking...">
                    <button class="btn btn-primary" onclick="loadMediaStream()">Link Player</button>
                </div>
            </div>
        </div>
        
        <div class="subtitle-pane">
            <div class="catalog-container">
                <select class="styled-picker" id="fileSelector" onchange="loadSrtFile(this.value)">
                    <option value="">-- Choose Series / Episode Script Assets --</option>
                    {% for series, tracks in catalog.items() %}
                        <optgroup label="📂 SERIES // {{ series }}">
                            {% for track in tracks %}
                                <option value="{{ track.path }}">{{ track.label }}</option>
                            {% endfor %}
                        </optgroup>
                    {% endfor %}
                </select>
            </div>
            
            <div class="subtitle-list" id="subtitleList">
                <div style="color: #615c7a; text-align: center; margin-top: 120px; font-size: 14px;">Select an asset configuration nodes file structure above to begin validation routing.</div>
            </div>
        </div>
    </div>

    <script>
        let activeFilePath = "";
        let ytPlayer = null;
        let globalSubtitles = [];
        let globalMetadata = {};

        // JavaScript YouTube iFrame API Injection to manage programmatic skipping
        function loadMediaStream() {
            const rawUrl = document.getElementById('videoUrl').value.trim();
            const container = document.getElementById('mediaContainer');
            if (!rawUrl) return;

            if (rawUrl.includes('youtube.com') || rawUrl.includes('youtu.be')) {
                let videoId = "";
                if (rawUrl.includes('v=')) { videoId = rawUrl.split('v=')[1].split('&')[0]; } 
                else { videoId = rawUrl.split('/').pop().split('?')[0]; }
                
                container.innerHTML = `
                    <div class="subtitle-overlay-layer" id="subtitleOverlay">
                        <div class="overlay-text-render" id="overlayText"></div>
                    </div>
                    <iframe id="ytEmbeddedPlayer" src="https://www.youtube-nocookie.com/embed/${videoId}?enablejsapi=1&rel=0" allowfullscreen referrerpolicy="strict-origin-when-cross-origin"></iframe>`;
            } else {
                alert("Only native YouTube URL schemas are supported for direct timeline seeking integrations.");
            }
        }

        function seekToTimecode(timecodeStr) {
            const parts = timecodeStr.split('-->')[0].trim().split(':');
            if (parts.length < 3) return;
            const hrs = parseFloat(parts[0]);
            const mins = parseFloat(parts[1]);
            const secs = parseFloat(parts[2].replace(',', '.'));
            const totalSeconds = (hrs * 3600) + (mins * 60) + secs;

            const ytFrame = document.getElementById('ytEmbeddedPlayer');
            if (ytFrame && ytFrame.contentWindow) {
                ytFrame.contentWindow.postMessage(JSON.stringify({
                    event: 'command', func: 'seekTo', args: [totalSeconds, true]
                }), '*');
                ytFrame.contentWindow.postMessage(JSON.stringify({
                    event: 'command', func: 'playVideo'
                }), '*');
            }
        }

        function calculateTimeAgo(timestamp) {
            if (!timestamp || timestamp === "Never") return "Never";
            const diff = Math.floor(Date.now() / 1000) - timestamp;
            if (diff < 60) return "Just now";
            if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
            return `${Math.floor(diff / 3600)}h ago`;
        }

        function toggleStatus(blockIndex) {
            const currentStatus = globalMetadata[blockIndex].status;
            const cycle = ["unassigned", "progress", "revision", "done"];
            let nextIndex = (cycle.indexOf(currentStatus) + 1) % cycle.length;
            const nextStatus = cycle[nextIndex];
            
            globalMetadata[blockIndex].status = nextStatus;
            globalMetadata[blockIndex].last_updated_by = document.getElementById('usernameInput').value;
            globalMetadata[blockIndex].last_updated_at = Math.floor(Date.now() / 1000);
            
            // Re-render single row state to present updated configuration UI properties
            renderBlockRow(blockIndex);
        }

        function renderBlockRow(index) {
            const card = document.getElementById(`card-${index}`);
            const sub = globalSubtitles.find(s => s.index === index);
            const meta = globalMetadata[index];
            const currentUser = document.getElementById('usernameInput').value;

            let isLocked = meta.locked_by && meta.locked_by !== currentUser;
            let classStatus = `status-${meta.status}`;
            let displayTime = calculateTimeAgo(meta.last_updated_at);

            card.className = `subtitle-card ${isLocked ? 'soft-lock-banner' : ''}`;
            card.innerHTML = `
                <div class="card-header-row">
                    <div class="card-meta-left">
                        <span>BLOCK REF // ${sub.index}</span>
                        <span class="timestamp-badge" onclick="seekToTimecode('${sub.timecode}')">⏱️ ${sub.timecode}</span>
                    </div>
                    <div class="card-meta-right">
                        ${isLocked ? `<span class="lock-indicator">🔒 LOCKED BY ${meta.locked_by.toUpperCase()}</span>` : ''}
                        <span class="status-badge ${classStatus}" onclick="toggleStatus('${sub.index}')">${meta.status}</span>
                    </div>
                </div>
                <textarea class="card-textarea" rows="2" ${isLocked ? 'disabled' : ''} onfocus="setActiveCard('${sub.index}')" oninput="updateLiveText('${sub.index}', this)">${sub.text}</textarea>
                <div class="log-footer-row">
                    <span>Mod: ${meta.last_updated_by} (${displayTime})</span>
                    <span>Characters: <span class="cnt">${sub.text.length}</span> / 40 limit</span>
                </div>
            `;
        }

        function setActiveCard(index) {
            document.querySelectorAll('.subtitle-card').forEach(c => c.classList.remove('active-track'));
            const activeCard = document.getElementById(`card-${index}`);
            if (activeCard) activeCard.classList.add('active-track');
            
            const txt = activeCard.querySelector('.card-textarea').value;
            updateOverlayDisplay(txt);
        }

        function updateLiveText(index, txElement) {
            const sub = globalSubtitles.find(s => s.index === index);
            sub.text = txElement.value;
            
            globalMetadata[index].last_updated_by = document.getElementById('usernameInput').value;
            globalMetadata[index].last_updated_at = Math.floor(Date.now() / 1000);
            
            txElement.nextElementSibling.querySelector('.cnt').innerText = txElement.value.length;
            updateOverlayDisplay(txElement.value);
        }

        function updateOverlayDisplay(text) {
            const overlay = document.getElementById('subtitleOverlay');
            const target = document.getElementById('overlayText');
            if (!overlay || !target) return;
            if (!text.trim()) {
                overlay.classList.remove('active-view');
            } else {
                target.innerText = text;
                overlay.classList.add('active-view');
            }
        }

        async function loadSrtFile(filePath) {
            if (!filePath) return;
            activeFilePath = filePath;
            
            const response = await fetch(`/load?file=${encodeURIComponent(filePath)}`);
            const data = await response.json();
            
            globalSubtitles = data.subtitles;
            globalMetadata = data.metadata;
            
            const listContainer = document.getElementById('subtitleList');
            listContainer.innerHTML = "";
            
            globalSubtitles.forEach(sub => {
                const card = document.createElement('div');
                card.id = `card-${sub.index}`;
                listContainer.appendChild(card);
                renderBlockRow(sub.index);
            });
        }

        async function saveActiveFile() {
            if (!activeFilePath) return;
            
            const response = await fetch('/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    file: activeFilePath,
                    subtitles: globalSubtitles,
                    metadata: globalMetadata
                })
            });
            
            const resData = await response.json();
            if (resData.status === "success") {
                alert("🎉 Clean SRT tracks & Meta companion matrices flushed to drive array successfully!");
            }
        }

        window.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                e.preventDefault();
                saveActiveFile();
            }
        });
    </script>
</body>
</html>
"""

# --- ROUTER SERVICE ENDPOINTS ---

@app.route('/')
def index():
    catalog = get_all_srt_files()
    return render_template_string(HTML_TEMPLATE, catalog=catalog)

@app.route('/load')
def load_srt_package():
    file_path = request.args.get('file')
    subtitles = parse_srt(file_path)
    metadata = get_or_create_metadata(file_path, len(subtitles))
    return jsonify({
        "subtitles": subtitles,
        "metadata": metadata
    })

@app.route('/save', methods=['POST'])
def save_srt_package():
    data = request.json
    file_path = data.get('file')
    subtitles = data.get('subtitles')
    metadata = data.get('metadata')
    
    save_split_layers(file_path, subtitles, metadata)
    return jsonify({"status": "success"})

@app.after_request
def add_security_headers(response):
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
