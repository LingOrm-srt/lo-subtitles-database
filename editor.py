import os
import re
import json
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

# Helper to look up or create automated meta logs without corrupting pristine SRTs
def get_meta_path(srt_path):
    return srt_path.replace(".srt", ".meta.json")

def load_or_create_metadata(srt_path, subtitles_list):
    meta_path = get_meta_path(srt_path)
    
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except:
                pass # Fallback to auto-generation if corrupted
                
    # Auto-Generation Loop: Creates parallel tracking layer natively
    metadata = {}
    for sub in subtitles_list:
        metadata[sub["index"]] = {
            "status": "unassigned", # unassigned, progress, revision, done
            "last_updated_by": "System",
            "last_updated_at": "",
            "locked_by": ""
        }
    
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    return metadata

def get_grouped_srt_files():
    """Scans the repo and builds a clean tree nested by Series / Folder Name"""
    grouped_files = {}
    for root, dirs, files in os.walk("."):
        if any(h in root for h in [".git", ".devcontainer", "__pycache__"]):
            continue
        for file in files:
            if file.endswith(".srt"):
                full_path = os.path.join(root, file)
                relative_path = os.path.relpath(full_path, ".")
                
                # Split path to determine the Series Name
                parts = relative_path.split(os.sep)
                series_name = parts[0] if len(parts) > 1 else "Standalone Scripts"
                display_name = os.path.join(*parts[1:]) if len(parts) > 1 else parts[0]
                
                if series_name not in grouped_files:
                    grouped_files[series_name] = []
                grouped_files[series_name].append({
                    "path": relative_path,
                    "name": display_name
                })
    return grouped_files

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

def save_srt(file_path, subtitles_list):
    with open(file_path, "w", encoding="utf-8") as f:
        for sub in subtitles_list:
            f.write(f"{sub['index']}\n{sub['timecode']}\n{sub['text']}\n\n")

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html>
<head>
    <title>LingOrm Fan Subtitles - Production Dashboard</title>
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
        
        .user-session-bar {
            display: flex; align-items: center; gap: 10px; background: #07050d;
            padding: 6px 12px; border-radius: 6px; border: 1px solid #2d254b;
        }
        .user-session-bar label { font-size: 11px; font-weight: 700; color: #615c7a; text-transform: uppercase; }
        .user-session-bar input { background: transparent; border: none; color: #FF77ED; font-weight: 600; font-size: 13px; outline: none; width: 100px; }

        .workspace { display: flex; flex: 1; overflow: hidden; }
        
        /* Studio Playback Module */
        .video-pane {
            width: 45%; background: #07050d;
            display: flex; flex-direction: column; padding: 24px;
            border-right: 1px solid rgba(255, 255, 255, 0.06);
            box-sizing: border-box; gap: 16px;
        }
        
        /* Fixed Stack Context Layout */
        .media-container {
            width: 100%; aspect-ratio: 16/9; background: #000000;
            border-radius: 12px; border: 2px dashed rgba(113, 237, 255, 0.2);
            overflow: hidden; display: flex; flex-direction: column; justify-content: center; align-items: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5); position: relative;
        }
        
        /* ELEVATED LAYER: Z-Indexed absolute overlay to float perfectly above standard frames */
        .subtitle-overlay-layer {
            position: absolute; bottom: 0; left: 0; right: 0; top: 0;
            background: rgba(0, 0, 0, 0.4);
            display: flex; flex-direction: column; justify-content: flex-end; align-items: center;
            padding: 30px 20px; pointer-events: none; opacity: 0; transition: opacity 0.15s ease;
            text-align: center; z-index: 9999 !important;
        }
        .subtitle-overlay-layer.active-view { opacity: 1; }
        .overlay-text-render {
            color: #ffffff; background: rgba(0, 0, 0, 0.85);
            padding: 10px 20px; border-radius: 8px; font-size: 20px;
            font-weight: 600; border: 1px solid rgba(255, 255, 255, 0.15);
            max-width: 85%; line-height: 1.4; box-shadow: 0 6px 20px rgba(0,0,0,0.7);
            text-shadow: 0 2px 4px rgba(0,0,0,1); font-family: sans-serif;
        }
        
        .instruction-box {
            background: #110e21; border: 1px solid #2d254b; padding: 20px; border-radius: 8px;
            display: flex; flex-direction: column; gap: 10px; height: 100%; justify-content: center;
            box-sizing: border-box; width: 100%; text-align: center; z-index: 1;
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
        
        .btn {
            padding: 12px 20px; border: none; border-radius: 6px;
            font-weight: 600; font-size: 13px; cursor: pointer; transition: all 0.2s ease;
        }
        .btn-primary { background: #FF77ED; color: #0b0914; text-decoration: none; text-align: center; }
        .btn-primary:hover { background: #ff99f0; }
        .btn-success { background: #71EDFF; color: #0b0914; }
        
        /* Subtitle Editing Pane */
        .subtitle-pane { width: 55%; display: flex; flex-direction: column; padding: 24px; box-sizing: border-box; }
        
        /* Optimized Multi-Level Selector Interface */
        .selector-container { display: flex; flex-direction: column; gap: 6px; margin-bottom: 20px; }
        .selector-label { font-size: 11px; font-weight: 700; color: #615c7a; text-transform: uppercase; letter-spacing: 0.5px; }
        .file-selector {
            width: 100%; padding: 14px; background: #110e21; border: 1px solid #221c38;
            color: #71EDFF; font-weight: 600; font-size: 14px; border-radius: 8px; cursor: pointer; outline: none;
        }
        .file-selector optgroup { background: #110e21; color: #615c7a; font-weight: 700; font-style: normal; }
        .file-selector option { color: #f3f4f6; font-weight: 500; padding: 6px; }

        .subtitle-list { flex: 1; overflow-y: auto; padding-right: 8px; }
        
        /* Team Production Block Card Layouts */
        .subtitle-card {
            background: #110e21; border: 1px solid #1d1833;
            border-left: 4px solid #2d254b; padding: 16px; margin-bottom: 12px;
            border-radius: 8px; display: flex; flex-direction: column; gap: 10px;
            transition: all 0.2s ease; position: relative;
        }
        .subtitle-card:hover { background: #151129; }
        .subtitle-card.active-track { border-left-color: #FF77ED; background: #181430; }
        .subtitle-card.read-only-lock { opacity: 0.6; pointer-events: none; border-left-color: #ff4444; }
        
        .card-meta { display: flex; justify-content: space-between; align-items: center; font-size: 12px; font-weight: 600; color: #615c7a; }
        .meta-left-group { display: flex; align-items: center; gap: 10px; }
        
        /* Functional Status Badges */
        .status-badge-select {
            background: #07050d; border: 1px solid #2d254b; color: #b4b0cb;
            font-size: 11px; font-weight: 700; border-radius: 4px; padding: 3px 6px; cursor: pointer; outline: none;
        }
        .status-unassigned { border-color: #4b5563; color: #9ca3af; }
        .status-progress { border-color: #f59e0b; color: #f59e0b; }
        .status-revision { border-color: #ec4899; color: #ec4899; }
        .status-done { border-color: #10b981; color: #10b981; }

        .timestamp-badge { color: #71EDFF; background: rgba(113,237,255,0.07); padding: 4px 10px; border-radius: 4px; font-family: monospace; font-size: 13px; cursor: pointer; }
        .timestamp-badge:hover { background: rgba(113,237,255,0.2); color: #ffffff; }
        
        .card-textarea {
            width: 100%; background: #07050d; border: 1px solid #221c38;
            border-radius: 6px; padding: 12px; color: #ffffff;
            font-family: inherit; font-size: 14px; line-height: 1.5; resize: none; box-sizing: border-box;
        }
        .card-textarea:focus { outline: none; border-color: #FF77ED; }
        
        .card-footer-metrics { display: flex; justify-content: space-between; align-items: center; font-size: 11px; color: #615c7a; font-weight: 500; }
        .log-tracking-string { font-style: italic; color: #4e4966; }
        .warning-limit { color: #ff7777; font-weight: 700; }
        
        iframe { width: 100%; height: 100%; border: none; }
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #0b0914; }
        ::-webkit-scrollbar-thumb { background: #1d1833; border-radius: 4px; }
    </style>
</head>
<body>

    <header>
        <h1>🎬 <span class="brand-badge">LingOrm Fan Subtitles</span> // Core Verification Dashboard</h1>
        <div style="display: flex; gap: 15px; align-items: center;">
            <div class="user-session-bar">
                <label>Translator ID:</label>
                <input type="text" id="usernameInput" value="Translator_1">
            </div>
            <button class="btn btn-success" onclick="saveActiveFile()">💾 Save Subtitles & Metadata</button>
        </div>
    </header>

    <div class="workspace">
        <div class="video-pane">
            <div class="media-container" id="mediaContainer">
                <div class="subtitle-overlay-layer" id="subtitleOverlay">
                    <div class="overlay-text-render" id="overlayText"></div>
                </div>

                <div class="instruction-box" id="instructionBox">
                    <div class="instruction-title">CH3Plus Media Work-Dock</div>
                    <ol class="step-list">
                        <li>Open CH3Plus and run your verified episode track script tab.</li>
                        <li>Pop out the media timeline using browser <strong>Picture-in-Picture</strong>.</li>
                        <li>Drag the floating player right inside this dashed alignment square frame layout.</li>
                        <li><strong>Live Timelines:</strong> Click any cyan badge timeline parameter code to seek an embedded YouTube video instantly.</li>
                    </ol>
                    <a href="https://ch3plus.com" target="_blank" class="btn btn-primary" style="margin-top: 4px;">🌐 Launch CH3Plus Website</a>
                </div>
            </div>
            
            <div class="url-input-container">
                <div style="font-size: 11px; font-weight:700; color:#615c7a; text-transform:uppercase; margin-bottom:2px;">YouTube Master Synchronizer Link</div>
                <div class="url-input-row">
                    <input type="text" id="videoUrl" placeholder="Paste YouTube link to enable automated timestamp seeking engine controls...">
                    <button class="btn btn-primary" onclick="loadMediaStream()">Hook Video</button>
                </div>
            </div>
        </div>
        
        <div class="subtitle-pane">
            <div class="selector-container">
                <div class="selector-label">Active Track Script Matrix</div>
                <select class="file-selector" id="fileSelector" onchange="loadSrtFile(this.value)">
                    <option value="">-- Browse Series Folders --</option>
                    {% for series, files in grouped_files.items() %}
                    <optgroup label="📂 {{ series }}">
                        {% for file in files %}
                        <option value="{{ file.path }}">&nbsp;&nbsp;📄 {{ file.name }}</option>
                        {% endfor %}
                    </optgroup>
                    {% endfor %}
                </select>
            </div>
            
            <div class="subtitle-list" id="subtitleList">
                <div style="color: #615c7a; text-align: center; margin-top: 120px; font-size: 14px;">Select a categorized sequence target to deploy code blocks.</div>
            </div>
        </div>
    </div>

    <script>
        let activeFilePath = "";
        let ytPlayerWindow = null;
        const savedInstructionsHtml = document.getElementById('mediaContainer').innerHTML;

        function loadMediaStream() {
            const rawUrl = document.getElementById('videoUrl').value.trim();
            const container = document.getElementById('mediaContainer');
            if (!rawUrl) return;

            if (rawUrl.includes('youtube.com') || rawUrl.includes('youtu.be')) {
                let videoId = "";
                if (rawUrl.includes('v=')) { videoId = rawUrl.split('v=')[1].split('&')[0]; } 
                else { videoId = rawUrl.split('/').pop().split('?')[0]; }
                
                // Keep subtitleOverlay inside structure intact when updating video embed layout frame
                container.innerHTML = `
                    <div class="subtitle-overlay-layer" id="subtitleOverlay">
                        <div class="overlay-text-render" id="overlayText"></div>
                    </div>
                    <iframe id="ytEmbeddedPlayer" src="https://www.youtube-nocookie.com/embed/${videoId}?enablejsapi=1&rel=0" allowfullscreen referrerpolicy="strict-origin-when-cross-origin"></iframe>`;
            }
        }

        function convertTimestampToSeconds(ts) {
            const parts = ts.split('-->')[0].trim().split(':');
            if (parts.length < 3) return 0;
            return (parseFloat(parts[0]) * 3600) + (parseFloat(parts[1]) * 60) + parseFloat(parts[2].replace(',', '.'));
        }

        function triggerVideoSeek(timecodeStr) {
            const secs = convertTimestampToSeconds(timecodeStr);
            const ytFrame = document.getElementById('ytEmbeddedPlayer');
            if (ytFrame && ytFrame.contentWindow) {
                ytFrame.contentWindow.postMessage(JSON.stringify({ event: 'command', func: 'seekTo', args: [secs, true] }), '*');
                ytFrame.contentWindow.postMessage(JSON.stringify({ event: 'command', func: 'playVideo' }), '*');
            }
        }

        function renderLiveTextOverlay(text) {
            const overlay = document.getElementById('subtitleOverlay');
            const overlayText = document.getElementById('overlayText');
            if (!overlay || !overlayText) return;
            if (!text.trim()) { overlay.classList.remove('active-view'); } 
            else { overlayText.innerText = text; overlay.classList.add('active-view'); }
        }

        function updateCardMetadata(card, index, changes) {
            const currentTranslator = document.getElementById('usernameInput').value.trim();
            const logString = card.querySelector('.log-tracking-string');
            
            // Auto-inject signature logs instantly into DOM dataset object arrays
            card.setAttribute('data-user', currentTranslator);
            card.setAttribute('data-time', new Date().toISOString());
            if(logString) {
                logString.innerText = `Modified just now by ${currentTranslator}`;
            }
        }

        function updateTextMetrics(textarea) {
            const card = textarea.closest('.subtitle-card');
            const countSpan = card.querySelector('.char-count');
            countSpan.innerText = textarea.value.length;
            if (textarea.value.length > 40) countSpan.className = "char-count warning-limit";
            else countSpan.className = "char-count";
            
            if (card.classList.contains('active-track')) { renderLiveTextOverlay(textarea.value); }
            updateCardMetadata(card, textarea.getAttribute('data-index'), 'text');
        }

        function calculateTimeAgo(isoString) {
            if (!isoString) return "Never modified";
            const parsed = new Date(isoString);
            if (isNaN(parsed)) return "Never modified";
            const diffMs = new Date() - parsed;
            const diffMins = Math.floor(diffMs / 60000);
            if (diffMins < 1) return "Modified just now";
            if (diffMins < 60) return `Modified ${diffMins}m ago`;
            return `Modified ${Math.floor(diffMins/60)}h ago`;
        }

        async function loadSrtFile(filePath) {
            if (!filePath) return;
            activeFilePath = filePath;
            const response = await fetch(`/load?file=${encodeURIComponent(filePath)}`);
            const payload = await response.json();
            
            const listContainer = document.getElementById('subtitleList');
            listContainer.innerHTML = "";
            
            payload.subtitles.forEach(sub => {
                const meta = payload.metadata[sub.index] || { status: 'unassigned', last_updated_by: 'System', last_updated_at: '' };
                const card = document.createElement('div');
                card.className = "subtitle-card";
                card.setAttribute('data-index', sub.index);
                card.setAttribute('data-timecode', sub.timecode);
                card.setAttribute('data-user', meta.last_updated_by);
                card.setAttribute('data-time', meta.last_updated_at);
                
                card.onclick = (e) => {
                    if (e.target.tagName !== 'TEXTAREA' && e.target.tagName !== 'SELECT') {
                        document.querySelectorAll('.subtitle-card').forEach(c => c.classList.remove('active-track'));
                        card.classList.add('active-track');
                        renderLiveTextOverlay(card.querySelector('.card-textarea').value);
                    }
                };

                const timeAgoStr = calculateTimeAgo(meta.last_updated_at);
                const trackingSign = meta.last_updated_at ? `${timeAgoStr} by ${meta.last_updated_by}` : 'Never modified';

                card.innerHTML = `
                    <div class="card-meta">
                        <div class="meta-left-group">
                            <span>BLOCK ${sub.index}</span>
                            <select class="status-badge-select status-${meta.status}" onchange="this.className='status-badge-select status-'+this.value; updateCardMetadata(this.closest('.subtitle-card'), '${sub.index}', 'status')">
                                <option value="unassigned" ${meta.status=='unassigned'?'selected':''}>⚪ Unassigned</option>
                                <option value="progress" ${meta.status=='progress'?'selected':''}>🟡 In Progress</option>
                                <option value="revision" ${meta.status=='revision'?'selected':''}>💖 Revision</option>
                                <option value="done" ${meta.status=='done'?'selected':''}>🟢 Done</option>
                            </select>
                        </div>
                        <span class="timestamp-badge" onclick="triggerVideoSeek('${sub.timecode}')">${sub.timecode}</span>
                    </div>
                    <textarea class="card-textarea" rows="2" data-index="${sub.index}" oninput="updateTextMetrics(this)">${sub.text}</textarea>
                    <div class="card-footer-metrics">
                        <span class="log-tracking-string">${trackingSign}</span>
                        <span>Chars: <span class="char-count">${sub.text.length}</span>/40</span>
                    </div>
                `;
                listContainer.appendChild(card);
            });
        }

        async function saveActiveFile() {
            if (!activeFilePath) return;
            const cards = document.querySelectorAll('.subtitle-card');
            const subtitles = [];
            const metadata = {};
            
            cards.forEach(card => {
                const idx = card.getAttribute('data-index');
                const textarea = card.querySelector('.card-textarea');
                const select = card.querySelector('.status-badge-select');
                
                subtitles.push({ index: idx, timecode: card.getAttribute('data-timecode'), text: textarea.value.trim() });
                metadata[idx] = {
                    status: select.value,
                    last_updated_by: card.getAttribute('data-user') || 'System',
                    last_updated_at: card.getAttribute('data-time') || ''
                };
            });
            
            const response = await fetch('/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file: activeFilePath, subtitles: subtitles, metadata: metadata })
            });
            
            const resData = await response.json();
            if (resData.status === "success") { alert("🎉 Changes & Collaboration Meta logs compiled successfully!"); loadSrtFile(activeFilePath); }
        }

        window.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); saveActiveFile(); }
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    grouped_files = get_grouped_srt_files()
    return render_template_string(HTML_TEMPLATE, grouped_files=grouped_files)

@app.route('/load')
def load_srt_and_meta():
    file_path = request.args.get('file')
    subtitles = parse_srt(file_path)
    metadata = load_or_create_metadata(file_path, subtitles)
    return jsonify({"subtitles": subtitles, "metadata": metadata})

@app.route('/save', methods=['POST'])
def save_srt_api():
    data = request.json
    file_path = data.get('file')
    subtitles = data.get('subtitles')
    metadata = data.get('metadata')
    
    # Write cleanly to both target tracking infrastructures individually
    save_srt(file_path, subtitles)
    
    meta_path = get_meta_path(file_path)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
        
    return jsonify({"status": "success"})

@app.after_request
def add_security_headers(response):
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
