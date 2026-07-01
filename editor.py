import os
import re
import json
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, make_response

app = Flask(__name__)

# Helper to look up or initialize individual tracking layers automatically
def get_meta_filepath(srt_path):
    return srt_path.replace(".srt", ".meta.json")

def load_or_create_metadata(srt_path, subtitles):
    meta_path = get_meta_filepath(srt_path)
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
            
    # Auto-generate default state dictionary if companion doesn't exist yet
    metadata = {}
    for sub in subtitles:
        metadata[sub['index']] = {
            "status": "unassigned",
            "lastUpdatedBy": "System",
            "lastUpdatedAt": datetime.now().isoformat(),
            "lockedBy": None
        }
    
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    return metadata

def get_grouped_srt_files():
    # Automatically scan repository layers and organize by Series groupings
    series_groups = {
        "The Secret of Us": [],
        "Only You": [],
        "In Love Forever": [],
        "Uncategorized Tracks": []
    }
    
    for root, dirs, files in os.walk("."):
        if any(h in root for h in [".git", ".devcontainer", "__pycache__"]):
            continue
        for file in files:
            if file.endswith(".srt") and not file.endswith(".meta.json"):
                relative_path = os.path.relpath(os.path.join(root, file), ".")
                
                # Sort into clean categories based on string patterns
                matched = False
                for series_name in series_groups.keys():
                    if series_name.lower() in file.lower() or series_name.lower() in root.lower():
                        series_groups[series_name].append({"name": file, "path": relative_path})
                        matched = True
                        break
                if not matched:
                    series_groups["Uncategorized Tracks"].append({"name": file, "path": relative_path})
                    
    return {k: v for k, v in series_groups.items() if v}

def parse_srt(file_path):
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

def save_srt_clean(file_path, subtitles_list):
    with open(file_path, "w", encoding="utf-8") as f:
        for sub in subtitles_list:
            f.write(f"{sub['index']}\n{sub['timecode']}\n{sub['text']}\n\n")

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html>
<head>
    <title>LingOrm Fan Subtitles - Studio Dashboard</title>
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
        }
        h1 { margin: 0; font-size: 20px; color: #71EDFF; font-weight: 700; letter-spacing: -0.5px; }
        .brand-badge { background: linear-gradient(135deg, #FF77ED, #71EDFF); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .workspace { display: flex; flex: 1; overflow: hidden; }
        
        /* Studio Playback Module Area */
        .video-pane {
            width: 45%; background: #07050d;
            display: flex; flex-direction: column; padding: 24px;
            border-right: 1px solid rgba(255, 255, 255, 0.06);
            box-sizing: border-box; gap: 16px;
        }
        
        /* Floating Interface Container */
        .media-container {
            width: 100%; aspect-ratio: 16/9; background: #000000;
            border-radius: 12px; border: 2px dashed rgba(113, 237, 255, 0.25);
            overflow: hidden; display: flex; flex-direction: column; justify-content: center; align-items: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5); position: relative;
        }
        
        /* FIXED: Forced absolute z-index layout floating over everything */
        .subtitle-overlay-layer {
            position: absolute; bottom: 0; left: 0; right: 0; top: 0;
            background: rgba(0, 0, 0, 0.4);
            display: flex; flex-direction: column; justify-content: flex-end; align-items: center;
            padding: 24px; pointer-events: none; display: none;
            text-align: center; z-index: 999;
        }
        .subtitle-overlay-layer.active-view { display: flex; }
        .overlay-text-render {
            color: #ffffff; background: rgba(11, 9, 20, 0.95);
            padding: 12px 24px; border-radius: 8px; font-size: 20px;
            font-weight: 600; border: 2px solid #FF77ED;
            max-width: 85%; line-height: 1.4; box-shadow: 0 8px 24px rgba(0,0,0,0.8);
            text-shadow: 0 2px 4px rgba(0,0,0,0.8); font-family: sans-serif;
        }
        
        .instruction-box {
            background: #110e21; border: 1px solid #2d254b; padding: 20px; border-radius: 8px;
            display: flex; flex-direction: column; gap: 12px; height: 100%; justify-content: center;
            box-sizing: border-box; width: 100%; text-align: center; z-index: 1;
        }
        .instruction-title { color: #FF77ED; font-weight: 700; font-size: 15px; margin-bottom: 4px; }
        .step-list { margin: 0; padding-left: 20px; font-size: 13px; color: #b4b0cb; line-height: 1.8; text-align: left; }
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
        
        .btn {
            padding: 12px 20px; border: none; border-radius: 6px;
            font-weight: 600; font-size: 13px; cursor: pointer; transition: all 0.2s ease;
        }
        .btn-primary { background: #FF77ED; color: #0b0914; text-decoration: none; text-align: center; display: inline-block; }
        .btn-primary:hover { background: #ff99f0; transform: translateY(-1px); }
        .btn-success { background: #71EDFF; color: #0b0914; box-shadow: 0 0 15px rgba(113,237,255,0.2); }
        .btn-success:hover { background: #96f2ff; box-shadow: 0 0 25px rgba(113,237,255,0.4); }
        
        /* Subtitle Editing Pane Grid Layout */
        .subtitle-pane { width: 55%; display: flex; flex-direction: column; padding: 24px; box-sizing: border-box; }
        
        /* OPTIMIZED: Structured Category Selector Layout Dropdown */
        .file-selector {
            margin-bottom: 20px; width: 100%; padding: 14px;
            background: #110e21; border: 1px solid #221c38;
            color: #71EDFF; font-weight: 600; font-size: 14px; border-radius: 8px; cursor: pointer;
        }
        .file-selector optgroup { background: #0b0914; color: #615c7a; font-style: normal; font-weight: 700; }
        .file-selector option { background: #110e21; color: #f3f4f6; padding: 6px; }

        .subtitle-list { flex: 1; overflow-y: auto; padding-right: 8px; }
        
        /* Collaborative Timed Text Row Cards */
        .subtitle-card {
            background: #110e21; border: 1px solid #1d1833;
            border-left: 4px solid #2d254b; padding: 16px; margin-bottom: 12px;
            border-radius: 8px; display: flex; flex-direction: column; gap: 10px;
            transition: all 0.2s ease; cursor: pointer; position: relative;
        }
        .subtitle-card:hover { border-color: #2d254b; background: #151129; }
        .subtitle-card.active-track { border-left-color: #FF77ED; background: #181430; }
        .subtitle-card.locked-card { opacity: 0.6; pointer-events: none; border-left-color: #ff5555; }
        
        .card-meta { display: flex; justify-content: space-between; align-items: center; font-size: 12px; font-weight: 600; color: #615c7a; }
        .timestamp-badge { color: #71EDFF; background: rgba(113,237,255,0.07); padding: 4px 10px; border-radius: 4px; font-family: monospace; transition: all 0.2s; }
        .timestamp-badge:hover { background: rgba(113,237,255,0.2); color: #ffffff; }
        
        .card-textarea {
            width: 100%; background: #07050d; border: 1px solid #221c38;
            border-radius: 6px; padding: 12px; color: #ffffff;
            font-family: inherit; font-size: 14px; line-height: 1.5; resize: none; box-sizing: border-box;
        }
        .card-textarea:focus { outline: none; border-color: #FF77ED; }
        
        /* Collaborative Metadata Badges & Controls */
        .meta-status-row { display: flex; justify-content: space-between; align-items: center; font-size: 11px; margin-top: 2px; }
        .audit-trail { color: #534f6b; font-weight: 500; }
        .tag-selector {
            background: #07050d; border: 1px solid #221c38; color: #b4b0cb;
            font-size: 11px; padding: 4px 8px; border-radius: 4px; font-weight: 600; cursor: pointer;
        }
        .tag-selector.status-unassigned { color: #b4b0cb; }
        .tag-selector.status-progress { color: #FF77ED; border-color: rgba(255,119,237,0.4); }
        .tag-selector.status-revision { color: #ffcc66; border-color: rgba(255,204,102,0.4); }
        .tag-selector.status-done { color: #71EDFF; border-color: rgba(113,237,255,0.4); }

        .metrics-row { display: flex; justify-content: flex-end; font-size: 11px; color: #615c7a; font-weight: 500; }
        .warning-limit { color: #ff7777; font-weight: 700; }
        
        iframe { width: 100%; height: 100%; border: none; border-radius: 12px; }
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #0b0914; }
        ::-webkit-scrollbar-thumb { background: #1d1833; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #2d254b; }
    </style>
</head>
<body>

    <header>
        <h1>🎬 <span class="brand-badge">LingOrm Fan Subtitles</span> // Studio Engine</h1>
        <div style="display: flex; gap: 12px; align-items: center;">
            <input type="text" id="usernameInput" placeholder="Enter Translator Name..." value="Translator" style="padding: 8px 12px; background: #07050d; border: 1px solid #2d254b; border-radius: 6px; color:#fff; font-size:12px; width: 140px;">
            <button class="btn btn-success" onclick="saveActiveFile()">💾 Save Changes to Repo</button>
        </div>
    </header>

    <div class="workspace">
        <div class="video-pane">
            <div class="media-container" id="mediaContainer">
                
                <div class="subtitle-overlay-layer" id="subtitleOverlay">
                    <div class="overlay-text-render" id="overlayText">Text Display Buffer</div>
                </div>

                <div class="instruction-box" id="instructionBox">
                    <div class="instruction-title">CH3Plus Layout Alignment Studio</div>
                    <ol class="step-list">
                        <li>Click the action row link down below to pull the secure browser window tab.</li>
                        <li>Log into your account, launch the stream, and toggle <strong>Picture-in-Picture</strong>.</li>
                        <li>Drag that independent pop-out right onto this grid layer.</li>
                        <li><strong>Live Timed Overlay:</strong> Selection cards on the right will sync text right across this viewport wrapper.</li>
                        <li><strong>Timestamp Verification:</strong> Click any badge on the right to simulate a timeline change event tracking reference.</li>
                    </ol>
                    <a href="https://ch3plus.com" target="_blank" class="btn btn-primary" style="margin-top: 8px;">🌐 Open CH3Plus Website</a>
                </div>
            </div>
            
            <div class="url-input-container">
                <div style="font-size: 11px; font-weight:700; color:#615c7a; text-transform:uppercase; margin-bottom:2px;">YouTube Streaming Link Override</div>
                <div class="url-input-row">
                    <input type="text" id="videoUrl" placeholder="Paste alternative YouTube episode link tracks here...">
                    <button class="btn btn-primary" onclick="loadMediaStream()">Load Overrides</button>
                </div>
            </div>
        </div>
        
        <div class="subtitle-pane">
            <select class="file-selector" id="fileSelector" onchange="loadSrtFile(this.value)">
                <option value="">-- Choose Series Script Path Target --</option>
                {% for series, tracks in grouped_files.items() %}
                <optgroup label="📂 {{ series }}">
                    {% for track in tracks %}
                    <option value="{{ track.path }}">{{ track.name }}</option>
                    {% endfor %}
                </optgroup>
                {% endfor %}
            </select>
            
            <div class="subtitle-list" id="subtitleList">
                <div style="color: #615c7a; text-align: center; margin-top: 120px; font-size: 14px;">Select an optimized series asset line script track up above to launch processing workflows.</div>
            </div>
        </div>
    </div>

    <script>
        let activeFilePath = "";
        let globalMetadata = {};
        let ytPlayerElement = null;
        const savedInstructionsHtml = document.getElementById('mediaContainer').innerHTML;

        function loadMediaStream() {
            const rawUrl = document.getElementById('videoUrl').value.trim();
            const container = document.getElementById('mediaContainer');
            if (!rawUrl) { container.innerHTML = savedInstructionsHtml; return; }

            container.innerHTML = "";
            if (rawUrl.includes('youtube.com') || rawUrl.includes('youtu.be')) {
                let videoId = "";
                if (rawUrl.includes('v=')) { videoId = rawUrl.split('v=')[1].split('&')[0]; } 
                else { videoId = rawUrl.split('/').pop().split('?')[0]; }
                container.innerHTML = `<iframe id="ytEmbeddedPlayer" src="https://www.youtube-nocookie.com/embed/${videoId}?enablejsapi=1&rel=0" allowfullscreen referrerpolicy="strict-origin-when-cross-origin"></iframe>`;
                ytPlayerElement = document.getElementById('ytEmbeddedPlayer');
            } else {
                alert("Please drop a supported YouTube video reference trace link profile.");
                container.innerHTML = savedInstructionsHtml;
            }
        }

        function convertTimestampToSeconds(ts) {
            const parts = ts.split('-->')[0].trim().split(':');
            if (parts.length < 3) return 0;
            const hrs = parseFloat(parts[0]);
            const mins = parseFloat(parts[1]);
            const secs = parseFloat(parts[2].replace(',', '.'));
            return (hrs * 3600) + (mins * 60) + secs;
        }

        // ACTIVE TIMELINE INTERACTION TRIGGER SEEK
        function runTimelineSeek(timecodeStr) {
            const targetSeconds = convertTimestampToSeconds(timecodeStr);
            if (ytPlayerElement && ytPlayerElement.contentWindow) {
                ytPlayerElement.contentWindow.postMessage(JSON.stringify({
                    event: 'command', func: 'seekTo', args: [targetSeconds, true]
                }), '*');
                ytPlayerElement.contentWindow.postMessage(JSON.stringify({
                    event: 'command', func: 'playVideo'
                }), '*');
            } else {
                console.log(`Simulating internal workspace timeline sync execution pointer jump to: ${targetSeconds} seconds.`);
            }
        }

        function calculateTimeAgo(isoString) {
            if (!isoString) return "Never";
            const date = new Date(isoString);
            const now = new Date();
            const seconds = Math.floor((now - date) / 1000);
            if (seconds < 5) return "Just now";
            if (seconds < 60) return `${seconds}s ago`;
            const minutes = Math.floor(seconds / 60);
            if (minutes < 60) return `${minutes}m ago`;
            const hours = Math.floor(minutes / 60);
            return `${hours}h ago`;
        }

        function displayActiveSubtitle(text) {
            const overlay = document.getElementById('subtitleOverlay');
            const overlayText = document.getElementById('overlayText');
            if (!overlay || !overlayText) return;
            if (!text.trim()) { overlay.classList.remove('active-view'); } 
            else { overlayText.innerText = text; overlay.classList.add('active-view'); }
        }

        function updateCardStatusColor(selectEl, blockId) {
            selectEl.className = "tag-selector " + "status-" + selectEl.value;
            if (globalMetadata[blockId]) {
                globalMetadata[blockId].status = selectEl.value;
                globalMetadata[blockId].lastUpdatedBy = document.getElementById('usernameInput').value || "User";
                globalMetadata[blockId].lastUpdatedAt = new Date().toISOString();
                
                // Update text label immediately
                const card = selectEl.closest('.subtitle-card');
                card.querySelector('.audit-trail').innerText = `Modificado: justo ahora por ${globalMetadata[blockId].lastUpdatedBy}`;
            }
        }

        function updateMetrics(textareaElement, blockId) {
            const currentLen = textareaElement.value.length;
            const meter = textareaElement.nextElementSibling.querySelector('.char-count');
            meter.innerText = currentLen;
            
            if (textareaElement.closest('.subtitle-card').classList.contains('active-track')) {
                displayActiveSubtitle(textareaElement.value);
            }
            meter.className = currentLen > 40 ? "char-count warning-limit" : "char-count";

            // Mark metadata cache as active modifications trace
            if (globalMetadata[blockId]) {
                globalMetadata[blockId].lastUpdatedBy = document.getElementById('usernameInput').value || "User";
                globalMetadata[blockId].lastUpdatedAt = new Date().toISOString();
                const audit = textareaElement.closest('.subtitle-card').querySelector('.audit-trail');
                audit.innerText = `Modified: Just now by ${globalMetadata[blockId].lastUpdatedBy}`;
            }
        }

        async function loadSrtFile(filePath) {
            if (!filePath) return;
            activeFilePath = filePath;
            const response = await fetch(`/load?file=${encodeURIComponent(filePath)}`);
            const data = await response.json();
            
            const subs = data.subtitles;
            globalMetadata = data.metadata;
            
            const listContainer = document.getElementById('subtitleList');
            listContainer.innerHTML = "";
            
            subs.forEach(sub => {
                const meta = globalMetadata[sub.index] || { status: "unassigned", lastUpdatedBy: "System", lastUpdatedAt: null };
                const card = document.createElement('div');
                card.className = "subtitle-card";
                
                card.onclick = (e) => {
                    if (e.target.tagName !== 'TEXTAREA' && e.target.tagName !== 'SELECT' && !e.target.classList.contains('timestamp-badge')) {
                        document.querySelectorAll('.subtitle-card').forEach(c => c.classList.remove('active-track'));
                        card.classList.add('active-track');
                        displayActiveSubtitle(card.querySelector('.card-textarea').value);
                    }
                };
                
                const timeAgo = calculateTimeAgo(meta.lastUpdatedAt);
                
                card.innerHTML = `
                    <div class="card-meta">
                        <span>BLOCK ID // ${sub.index}</span>
                        <span class="timestamp-badge" onclick="runTimelineSeek('${sub.timecode}')">${sub.timecode}</span>
                    </div>
                    <textarea class="card-textarea" rows="2" data-index="${sub.index}" data-timecode="${sub.timecode}" oninput="updateMetrics(this, '${sub.index}')">${sub.text}</textarea>
                    <div class="metrics-row">
                        <span>Characters: <span class="char-count">${sub.text.length}</span> / 40 line limit</span>
                    </div>
                    <div class="meta-status-row">
                        <span class="audit-trail">Updated: ${timeAgo} by ${meta.lastUpdatedBy}</span>
                        <select class="tag-selector status-${meta.status}" onchange="updateCardStatusColor(this, '${sub.index}')">
                            <option value="unassigned" ${meta.status === 'unassigned' ? 'selected' : ''}>⚪ Unassigned</option>
                            <option value="progress" ${meta.status === 'progress' ? 'selected' : ''}>🟡 In Progress</option>
                            <option value="revision" ${meta.status === 'revision' ? 'selected' : ''}>🔵 Revision Needed</option>
                            <option value="done" ${meta.status === 'done' ? 'selected' : ''}>🟢 Done / Locked</option>
                        </select>
                    </div>
                `;
                listContainer.appendChild(card);
            });
        }

        async function saveActiveFile() {
            if (!activeFilePath) { alert("Please open an explicit target series workspace file list profile."); return; }
            const textareas = document.querySelectorAll('.card-textarea');
            const subtitles = [];
            
            textareas.forEach(tx => {
                subtitles.push({
                    index: tx.getAttribute('data-index'),
                    timecode: tx.getAttribute('data-timecode'),
                    text: tx.value.trim()
                });
            });
            
            const response = await fetch('/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file: activeFilePath, subtitles: subtitles, metadata: globalMetadata })
            });
            
            const resData = await response.json();
            if (resData.status === "success") {
                alert("🎉 Pristine SRT and Companion Metadata file structures successfully split written to disk repo!");
            } else {
                alert("❌ Critical I/O write synchronization error.");
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

@app.route('/')
def index():
    grouped = get_grouped_srt_files()
    return render_template_string(HTML_TEMPLATE, grouped_files=grouped)

@app.route('/load')
def load_srt():
    file_path = request.args.get('file')
    subs = parse_srt(file_path)
    meta = load_or_create_metadata(file_path, subs)
    return jsonify({"subtitles": subs, "metadata": meta})

@app.route('/save', methods=['POST'])
def save_srt_api():
    data = request.json
    file_path = data.get('file')
    subtitles = data.get('subtitles')
    metadata = data.get('metadata')
    
    # Save the pristine SRT for deployment channels
    save_srt_clean(file_path, subtitles)
    
    # Save the split status data object profile locally as hidden tracker
    meta_path = get_meta_filepath(file_path)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
        
    return jsonify({"status": "success"})

@app.after_request
def add_security_headers(response):
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
