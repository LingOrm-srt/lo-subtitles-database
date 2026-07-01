import os
import re
from flask import Flask, render_template_string, request, jsonify, make_response

app = Flask(__name__)

def get_all_srt_files():
    srt_files = []
    for root, dirs, files in os.walk("."):
        if any(h in root for h in [".git", ".devcontainer", "__pycache__"]):
            continue
        for file in files:
            if file.endswith(".srt"):
                relative_path = os.path.relpath(os.path.join(root, file), ".")
                srt_files.append(relative_path)
    return srt_files

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
        
        /* Studio Playback Module */
        .video-pane {
            width: 45%; background: #07050d;
            display: flex; flex-direction: column; padding: 24px;
            border-right: 1px solid rgba(255, 255, 255, 0.06);
            box-sizing: border-box; gap: 16px;
        }
        
        /* Visual Docking Container Layout */
        .media-container {
            width: 100%; aspect-ratio: 16/9; background: #000000;
            border-radius: 12px; border: 2px dashed rgba(113, 237, 255, 0.3);
            overflow: hidden; display: flex; flex-direction: column; justify-content: center; align-items: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5); position: relative;
            transition: all 0.3s ease;
        }
        
        /* Interactive Subtitle Overlay Screen */
        .subtitle-overlay-layer {
            position: absolute; bottom: 0; left: 0; right: 0; top: 0;
            background: rgba(0, 0, 0, 0.6);
            display: flex; flex-direction: column; justify-content: flex-end; align-items: center;
            padding: 24px; pointer-events: none; opacity: 0; transition: opacity 0.2s ease;
            text-align: center; z-index: 10;
        }
        .subtitle-overlay-layer.active-view { opacity: 1; }
        .overlay-text-render {
            color: #ffffff; background: rgba(0, 0, 0, 0.85);
            padding: 8px 16px; border-radius: 6px; font-size: 18px;
            font-weight: 500; border: 1px solid rgba(255, 255, 255, 0.1);
            max-width: 85%; line-height: 1.4; box-shadow: 0 4px 12px rgba(0,0,0,0.5);
            text-shadow: 0 2px 4px rgba(0,0,0,1); font-family: sans-serif;
        }
        
        .instruction-box {
            background: #110e21; border: 1px solid #2d254b; padding: 20px; border-radius: 8px;
            display: flex; flex-direction: column; gap: 12px; height: 100%; justify-content: center;
            box-sizing: border-box; width: 100%; text-align: center;
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
        
        /* Subtitle Spreadsheet Grid */
        .subtitle-pane { width: 55%; display: flex; flex-direction: column; padding: 24px; box-sizing: border-box; }
        .file-selector {
            margin-bottom: 20px; width: 100%; padding: 14px;
            background: #110e21; border: 1px solid #221c38;
            color: #71EDFF; font-weight: 600; font-size: 14px; border-radius: 8px; cursor: pointer;
        }
        .subtitle-list { flex: 1; overflow-y: auto; padding-right: 8px; }
        
        /* Timed Text Row Cards */
        .subtitle-card {
            background: #110e21; border: 1px solid #1d1833;
            border-left: 4px solid #2d254b; padding: 16px; margin-bottom: 12px;
            border-radius: 8px; display: flex; flex-direction: column; gap: 10px;
            transition: all 0.2s ease; cursor: pointer;
        }
        .subtitle-card:hover { border-color: #2d254b; background: #151129; }
        .subtitle-card.active-track { border-left-color: #FF77ED; background: #181430; box-shadow: inset 0 0 10px rgba(255,119,237,0.05); }
        
        .card-meta { display: flex; justify-content: space-between; font-size: 12px; font-weight: 600; color: #615c7a; }
        .timestamp-badge { color: #71EDFF; background: rgba(113,237,255,0.07); padding: 2px 8px; border-radius: 4px; font-family: monospace; cursor: copy; }
        .timestamp-badge:hover { background: rgba(113,237,255,0.2); }
        
        .card-textarea {
            width: 100%; background: #07050d; border: 1px solid #221c38;
            border-radius: 6px; padding: 12px; color: #ffffff;
            font-family: inherit; font-size: 14px; line-height: 1.5; resize: none; box-sizing: border-box;
        }
        .card-textarea:focus { outline: none; border-color: #FF77ED; }
        
        .metrics-row { display: flex; justify-content: flex-end; font-size: 11px; color: #615c7a; font-weight: 500; }
        .warning-limit { color: #ff7777; font-weight: 700; }
        
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #0b0914; }
        ::-webkit-scrollbar-thumb { background: #1d1833; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #2d254b; }
    </style>
</head>
<body>

    <header>
        <h1>🎬 <span class="brand-badge">LingOrm Fan Subtitles</span> // QC Verification Center</h1>
        <button class="btn btn-success" onclick="saveActiveFile()">💾 Save Changes to Repo</button>
    </header>

    <div class="workspace">
        <div class="video-pane">
            <div class="media-container" id="mediaContainer">
                
                <!-- Live Preview Text Layer Display System -->
                <div class="subtitle-overlay-layer" id="subtitleOverlay">
                    <div class="overlay-text-render" id="overlayText">Subtitle Preview Container</div>
                </div>

                <!-- Guidance Board -->
                <div class="instruction-box" id="instructionBox">
                    <div class="instruction-title">CH3Plus Workspace Setup Guide</div>
                    <ol class="step-list">
                        <li>Click the button below to open <strong>CH3Plus</strong> in a new window.</li>
                        <li>Log into your account, launch the episode, and right-click to activate <strong>Picture-in-Picture</strong>.</li>
                        <li>Return here and move the floating video panel over this dashed docking square.</li>
                        <li><strong>Subtitle Verification Layer:</strong> Clicking any subtitle block on the right instantly reflects the text layer onto this screen area.</li>
                        <li><strong>Timestamp Copying:</strong> Clicking the cyan badge copies the timecode so you can match it on your floating video player manually.</li>
                    </ol>
                    <a href="https://ch3plus.com" target="_blank" class="btn btn-primary" style="margin-top: 8px;">🌐 Open CH3Plus Website</a>
                </div>
            </div>
            
            <div class="url-input-container">
                <div style="font-size: 11px; font-weight:700; color:#615c7a; text-transform:uppercase; margin-bottom:2px;">YouTube Link Overrides</div>
                <div class="url-input-row">
                    <input type="text" id="videoUrl" placeholder="Paste a YouTube link if working on an alternative YouTube track...">
                    <button class="btn btn-primary" onclick="loadMediaStream()">Load YouTube</button>
                </div>
            </div>
        </div>
        
        <div class="subtitle-pane">
            <select class="file-selector" id="fileSelector" onchange="loadSrtFile(this.value)">
                <option value="">-- Select Active Script Target Folder --</option>
                {% for file in srt_files %}
                <option value="{{ file }}">{{ file }}</option>
                {% endfor %}
            </select>
            
            <div class="subtitle-list" id="subtitleList">
                <div style="color: #615c7a; text-align: center; margin-top: 120px; font-size: 14px;">Select an SRT track script asset from the drop-down menu layer to sync configuration lines.</div>
            </div>
        </div>
    </div>

    <script>
        let activeFilePath = "";
        const savedInstructionsHtml = document.getElementById('mediaContainer').innerHTML;

        function loadMediaStream() {
            const rawUrl = document.getElementById('videoUrl').value.trim();
            const container = document.getElementById('mediaContainer');
            
            if (!rawUrl) {
                container.innerHTML = savedInstructionsHtml;
                return;
            }

            if (rawUrl.includes('youtube.com') || rawUrl.includes('youtu.be')) {
                let videoId = "";
                if (rawUrl.includes('v=')) {
                    videoId = rawUrl.split('v=')[1].split('&')[0];
                } else {
                    videoId = rawUrl.split('/').pop().split('?')[0];
                }
                container.innerHTML = `<iframe id="ytEmbeddedPlayer" src="https://www.youtube-nocookie.com/embed/${videoId}?enablejsapi=1&rel=0" allowfullscreen referrerpolicy="strict-origin-when-cross-origin"></iframe>`;
            } else {
                alert("Please provide a valid YouTube link, or leave it blank to follow the CH3Plus instructions.");
                container.innerHTML = savedInstructionsHtml;
            }
        }

        function copyTimestampToClipboard(text, element) {
            navigator.clipboard.writeText(text).then(() => {
                const originalText = element.innerText;
                element.innerText = "COPIED!";
                setTimeout(() => {
                    element.innerText = originalText;
                }, 1000);
            });
        }

        // Display current card text directly over the alignment grid frame layer
        function displayActiveSubtitle(text) {
            const overlay = document.getElementById('subtitleOverlay');
            const overlayText = document.getElementById('overlayText');
            
            if (!overlay || !overlayText) return;
            
            if (!text.trim()) {
                overlay.classList.remove('active-view');
            } else {
                overlayText.innerText = text;
                overlay.classList.add('active-view');
            }
        }

        function updateMetrics(textareaElement) {
            const currentLen = textareaElement.value.length;
            const meter = textareaElement.nextElementSibling.querySelector('.char-count');
            meter.innerText = currentLen;
            
            // Sync text live to overlay if the card is currently highlighted
            if (textareaElement.closest('.subtitle-card').classList.contains('active-track')) {
                displayActiveSubtitle(textareaElement.value);
            }
            
            if (currentLen > 40) {
                meter.className = "char-count warning-limit";
            } else {
                meter.className = "char-count";
            }
        }

        async function loadSrtFile(filePath) {
            if (!filePath) return;
            activeFilePath = filePath;
            const response = await fetch(`/load?file=${encodeURIComponent(filePath)}`);
            const subs = await response.json();
            
            const listContainer = document.getElementById('subtitleList');
            listContainer.innerHTML = "";
            
            subs.forEach(sub => {
                const card = document.createElement('div');
                card.className = "subtitle-card";
                
                // Clicking anywhere triggers activation layout highlights and overlays text
                card.onclick = (e) => {
                    document.querySelectorAll('.subtitle-card').forEach(c => c.classList.remove('active-track'));
                    card.classList.add('active-track');
                    
                    const currentTextValue = card.querySelector('.card-textarea').value;
                    displayActiveSubtitle(currentTextValue);
                };
                
                card.innerHTML = `
                    <div class="card-meta">
                        <span>BLOCK ID // ${sub.index}</span>
                        <span class="timestamp-badge" title="Click to copy start time" onclick="copyTimestampToClipboard('${sub.timecode.split('-->')[0].trim()}', this); e.stopPropagation();">${sub.timecode}</span>
                    </div>
                    <textarea class="card-textarea" rows="2" data-index="${sub.index}" data-timecode="${sub.timecode}" oninput="updateMetrics(this)">${sub.text}</textarea>
                    <div class="metrics-row">
                        <span>Characters: <span class="char-count">${sub.text.length}</span> / 40 line limit</span>
                    </div>
                `;
                listContainer.appendChild(card);
            });
        }

        async function saveActiveFile() {
            if (!activeFilePath) { alert("No active script serialization layout target selected."); return; }
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
                body: JSON.stringify({ file: activeFilePath, subtitles: subtitles })
            });
            
            const resData = await response.json();
            if (resData.status === "success") {
                alert("🎉 Local database tracking synced successfully onto disk infrastructure!");
            } else {
                alert("❌ Critical write synchronization failure.");
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
    files = get_all_srt_files()
    return render_template_string(HTML_TEMPLATE, srt_files=files)

@app.route('/load')
def load_srt():
    file_path = request.args.get('file')
    subs = parse_srt(file_path)
    return jsonify(subs)

@app.route('/save', methods=['POST'])
def save_srt_api():
    data = request.json
    file_path = data.get('file')
    subtitles = data.get('subtitles')
    save_srt(file_path, subtitles)
    return jsonify({"status": "success"})

@app.after_request
def add_security_headers(response):
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
