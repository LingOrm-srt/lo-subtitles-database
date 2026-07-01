import os
import re
import datetime
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

# Track user memory caches for real-time collaboration logging simulations
ACTIVE_USER_SESSION = "QC_Lead_Translator"

def get_srt_file_tree():
    """Parses local workspace folders and groups SRT files logically by directory."""
    tree = {}
    for root, dirs, files in os.walk("."):
        if any(h in root for h in [".git", ".devcontainer", "__pycache__", "node_modules"]):
            continue
        for file in files:
            if file.endswith(".srt"):
                rel_dir = os.path.relpath(root, ".")
                folder_key = "Root Directory" if rel_dir == "." else rel_dir
                file_path = os.path.relpath(os.path.join(root, file), ".")
                
                if folder_key not in tree:
                    tree[folder_key] = []
                tree[folder_key].append({
                    "filename": file,
                    "filepath": file_path
                })
    return tree

def parse_srt_with_metadata(file_path):
    """Parses SRT blocks and scans for embedded metadata headers safely."""
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
            
            # Extract main dialogue text line strings
            text_lines = []
            status = "NEEDS_REVISION"  # Default workflow state fallback
            last_author = "System_Init"
            last_update = "N/A"
            
            for l in lines[2:]:
                raw_line = l.strip()
                # Parse localized comment metadata injection tracks out of SRT cleanly
                if raw_line.startswith("## STATUS="):
                    status = raw_line.split("=")[1]
                elif raw_line.startswith("## MOD_BY="):
                    last_author = raw_line.split("=")[1]
                elif raw_line.startswith("## MOD_AT="):
                    last_update = raw_line.split("=")[1]
                else:
                    text_lines.append(raw_line)
                    
            subtitles.append({
                "index": line_idx,
                "timecode": timecode,
                "text": " ".join(text_lines),
                "status": status,
                "last_author": last_author,
                "last_update": last_update
            })
    return subtitles

def serialize_srt_metadata(file_path, subtitles_list):
    """Writes standard SRT blocks while appending clean workspace state comments."""
    with open(file_path, "w", encoding="utf-8") as f:
        for sub in subtitles_list:
            f.write(f"{sub['index']}\n")
            f.write(f"{sub['timecode']}\n")
            f.write(f"## STATUS={sub['status']}\n")
            f.write(f"## MOD_BY={sub['last_author']}\n")
            f.write(f"## MOD_AT={sub['last_update']}\n")
            f.write(f"{sub['text']}\n\n")

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
            background: #07050d; color: #f3f4f6;
            display: flex; flex-direction: column; height: 100vh;
            overflow: hidden;
        }
        header {
            background: #0e0a1a; padding: 16px 28px;
            display: flex; justify-content: space-between; align-items: center;
            border-bottom: 1px solid rgba(113, 237, 255, 0.12);
            z-index: 100;
        }
        h1 { margin: 0; font-size: 18px; color: #71EDFF; font-weight: 700; letter-spacing: -0.5px; }
        .brand-badge { background: linear-gradient(135deg, #FF77ED, #71EDFF); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        
        .workspace { display: flex; flex: 1; overflow: hidden; height: calc(100vh - 140px); }
        
        /* Media & Navigation Control Hub */
        .video-pane {
            width: 35%; background: #0b0914;
            display: flex; flex-direction: column; padding: 20px;
            border-right: 1px solid rgba(255, 255, 255, 0.05);
            box-sizing: border-box; gap: 16px; overflow-y: auto;
        }
        
        .clock-hub {
            background: #110e21; border: 1px solid #221c38; padding: 16px; border-radius: 8px;
            display: flex; flex-direction: column; gap: 10px;
        }
        .clock-title { font-size: 11px; font-weight: 700; color: #71EDFF; text-transform: uppercase; letter-spacing: 0.5px; }
        .clock-row { display: flex; gap: 8px; }
        
        /* Tree Browser Layout */
        .tree-container {
            background: #110e21; border: 1px solid #1d1833; border-radius: 8px; padding: 14px;
            display: flex; flex-direction: column; gap: 12px;
        }
        .folder-node { font-weight: 700; font-size: 13px; color: #FF77ED; display: flex; align-items: center; gap: 6px; }
        .file-list { list-style: none; padding-left: 16px; margin: 4px 0 0 0; display: flex; flex-direction: column; gap: 6px; }
        .file-link {
            font-size: 12px; color: #b4b0cb; text-decoration: none; cursor: pointer;
            padding: 6px 10px; border-radius: 4px; display: block; background: rgba(255,255,255,0.02);
            border: 1px solid transparent; transition: all 0.2s ease;
        }
        .file-link:hover { background: rgba(113, 237, 255, 0.05); border-color: rgba(113, 237, 255, 0.2); color: #ffffff; }
        .file-link.active-file { background: rgba(255, 119, 237, 0.1); border-color: rgba(255, 119, 237, 0.3); color: #FF77ED; font-weight: 600; }
        
        /* Subtitle Spreadsheet Grid Area */
        .subtitle-pane { width: 65%; display: flex; flex-direction: column; padding: 20px; box-sizing: border-box; background: #07050d; }
        .subtitle-list { flex: 1; overflow-y: auto; padding-right: 4px; }
        
        /* Cards & Workflow Badges Layout */
        .subtitle-card {
            background: #110e21; border: 1px solid #1d1833;
            border-left: 4px solid #2d254b; padding: 14px; margin-bottom: 10px;
            border-radius: 6px; display: flex; flex-direction: column; gap: 8px;
            transition: all 0.2s ease; cursor: pointer; position: relative;
        }
        .subtitle-card:hover { border-color: #2d254b; background: #141026; }
        .subtitle-card.active-track { border-left-color: #FF77ED; background: #17122b; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
        
        /* Workflow State Indicator Matrix borders */
        .card-state-REVISION { border-left-color: #ff5555 !important; }
        .card-state-PROGRESS { border-left-color: #71EDFF !important; }
        .card-state-VERIFIED { border-left-color: #55ff99 !important; }

        .card-meta { display: flex; justify-content: space-between; align-items: center; font-size: 11px; font-weight: 600; color: #615c7a; }
        .timestamp-badge { color: #71EDFF; background: rgba(113,237,255,0.06); padding: 2px 8px; border-radius: 4px; font-family: monospace; }
        
        .tag-select {
            background: #07050d; color: #b4b0cb; border: 1px solid #2d254b;
            font-size: 11px; font-weight: 600; padding: 4px 8px; border-radius: 4px; cursor: pointer;
        }
        
        .card-textarea {
            width: 100%; background: #07050d; border: 1px solid #221c38;
            border-radius: 4px; padding: 10px; color: #ffffff;
            font-family: inherit; font-size: 13px; line-height: 1.4; resize: none; box-sizing: border-box;
        }
        .card-textarea:focus { outline: none; border-color: #FF77ED; }
        
        .log-footer { display: flex; justify-content: space-between; font-size: 10px; color: #514b66; font-weight: 500; }
        
        /* Master Floating Studio Subtitle Bar Overlay */
        .master-floating-overlay {
            height: 70px; background: #110e21; border-top: 2px solid #FF77ED;
            display: flex; justify-content: center; align-items: center;
            padding: 0 40px; box-shadow: 0 -4px 25px rgba(0,0,0,0.6); z-index: 9999; position: relative;
        }
        .master-overlay-text {
            color: #ffffff; font-size: 20px; font-weight: 600; text-align: center;
            font-family: sans-serif; letter-spacing: 0.3px;
            max-width: 90%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
            text-shadow: 0 2px 4px rgba(0,0,0,0.8);
        }

        .btn {
            padding: 10px 16px; border: none; border-radius: 4px;
            font-weight: 600; font-size: 12px; cursor: pointer; transition: all 0.15s ease;
        }
        .btn-primary { background: #FF77ED; color: #0b0914; text-decoration: none; text-align: center; }
        .btn-primary:hover { background: #ff99f0; }
        .btn-success { background: #71EDFF; color: #0b0914; box-shadow: 0 0 12px rgba(113,237,255,0.15); }
        .btn-success:hover { background: #96f2ff; }
        
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: #07050d; }
        ::-webkit-scrollbar-thumb { background: #1d1833; border-radius: 3px; }
    </style>
</head>
<body>

    <header>
        <h1>🎬 <span class="brand-badge">LingOrm Fan Subtitles</span> // Studio Deck Dashboard</h1>
        <button class="btn btn-success" onclick="publishActiveSubtitlesToDisk()">💾 Publish Build to Production Hub</button>
    </header>

    <div class="workspace">
        <div class="video-pane">
            
            <!-- Master Sync Engine Clock UI Box Container -->
            <div class="clock-hub">
                <div class="clock-title">⏱️ Universal Master Sync Clock</div>
                <div class="clock-row">
                    <input type="text" id="masterClockInput" placeholder="Type or paste video time (e.g. 01:23 or 00:04:12)..." style="flex:1; padding:10px; background:#07050d; border:1px solid #2d254b; border-radius:4px; color:#fff; font-family:monospace; font-size:13px;">
                    <button class="btn btn-primary" onclick="triggerMasterClockSync()">Sync View</button>
                </div>
                <div style="font-size:11px; color:#615c7a; line-height:1.4;">Type the timestamp currently showing on your floating CH3Plus window. The spreadsheet tracking loop will automatically snap focus to match!</div>
            </div>

            <!-- Optimized Directory Asset Tree Browser -->
            <div class="tree-container">
                <div class="clock-title">📂 Workspace Script Target Trees</div>
                <div id="treeBrowserContainer">
                    {% for folder, files in file_tree.items() %}
                    <div style="margin-bottom: 12px;">
                        <div class="folder-node">📁 {{ folder }}</div>
                        <ul class="file-list">
                            {% for file in files %}
                            <li>
                                <a class="file-link" id="link-{{ file.filepath }}" onclick="loadTargetSrtTrack('{{ file.filepath }}')">📄 {{ file.filename }}</a>
                            </li>
                            {% endfor %}
                        </ul>
                    </div>
                    {% endfor %}
                </div>
            </div>

            <div class="clock-hub" style="background: rgba(255,119,237,0.02);">
                <div class="clock-title" style="color:#FF77ED;">🌐 External Player Bridge</div>
                <a href="https://ch3plus.com" target="_blank" class="btn btn-primary" style="font-size:11px; padding:8px 12px; display:block; width:100%; box-sizing:border-box;">Open CH3Plus Site</a>
            </div>
        </div>
        
        <div class="subtitle-pane">
            <div class="subtitle-list" id="subtitleList">
                <div style="color: #615c7a; text-align: center; margin-top: 140px; font-size: 13px;">Select a project file script layout inside the workspace directory tree configuration frame to sync lines.</div>
            </div>
        </div>
    </div>

    <!-- Master Widescreen QC Subtitle Text Bar Overlay Layout Layer -->
    <div class="master-floating-overlay">
        <div class="master-overlay-text" id="globalFloatingSubtitleText">--- STUDIO MONITORS CONNECTED ---</div>
    </div>

    <script>
        let activeFilePath = "";
        let localInMemorySubtitleCache = [];

        function convertTimestampToSeconds(ts) {
            let clean = ts.split('-->')[0].trim().replace(',', '.');
            let parts = clean.split(':');
            if(parts.length === 2) {
                return (parseFloat(parts[0]) * 60) + parseFloat(parts[1]);
            } else if (parts.length === 3) {
                return (parseFloat(parts[0]) * 3600) + (parseFloat(parts[1]) * 60) + parseFloat(parts[2]);
            }
            return 0;
        }

        // Universal Master Sync Clock tracking algorithm loop logic
        function triggerMasterClockSync() {
            const inputVal = document.getElementById('masterClockInput').value.trim();
            if(!inputVal || localInMemorySubtitleCache.length === 0) return;
            
            const targetSeconds = convertTimestampToSeconds(inputVal);
            let closestBlock = null;
            let minimumDiff = Infinity;
            
            localInMemorySubtitleCache.forEach(sub => {
                const subStart = convertTimestampToSeconds(sub.timecode);
                const diff = Math.abs(subStart - targetSeconds);
                if(diff < minimumDiff) {
                    minimumDiff = diff;
                    closestBlock = sub.index;
                }
            });
            
            if(closestBlock !== null) {
                const targetCardElement = document.getElementById(`card-block-${closestBlock}`);
                if(targetCardElement) {
                    targetCardElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    targetCardElement.click();
                }
            }
        }

        async function loadTargetSrtTrack(filePath) {
            activeFilePath = filePath;
            
            document.querySelectorAll('.file-link').forEach(l => l.classList.remove('active-file'));
            const selectedLink = document.getElementById(`link-${filePath}`);
            if(selectedLink) selectedLink.classList.add('active-file');
            
            const response = await fetch(`/load?file=${encodeURIComponent(filePath)}`);
            localInMemorySubtitleCache = await response.json();
            
            renderSubtitleEditorGrid();
        }

        function renderSubtitleEditorGrid() {
            const listContainer = document.getElementById('subtitleList');
            listContainer.innerHTML = "";
            
            localInMemorySubtitleCache.forEach((sub, idx) => {
                const card = document.createElement('div');
                card.className = `subtitle-card card-state-${sub.status}`;
                card.id = `card-block-${sub.index}`;
                
                card.onclick = () => {
                    document.querySelectorAll('.subtitle-card').forEach(c => c.classList.remove('active-track'));
                    card.classList.add('active-track');
                    document.getElementById('globalFloatingSubtitleText').innerText = card.querySelector('.card-textarea').value;
                };
                
                card.innerHTML = `
                    <div class="card-meta">
                        <span>BLOCK ID // ${sub.index}</span>
                        <div style="display:flex; gap:10px; align-items:center;">
                            <span class="timestamp-badge">${sub.timecode}</span>
                            <select class="tag-select" onchange="updateBlockWorkflowStatus(${idx}, this.value, this)">
                                <option value="NEEDS_REVISION" ${sub.status === 'NEEDS_REVISION' ? 'selected' : ''}>⚠️ Needs Revision</option>
                                <option value="PROGRESS" ${sub.status === 'PROGRESS' ? 'selected' : ''}>🔷 In Progress</option>
                                <option value="VERIFIED" ${sub.status === 'VERIFIED' ? 'selected' : ''}>✅ Verified Done</option>
                            </select>
                        </div>
                    </div>
                    <textarea class="card-textarea" rows="2" oninput="updateBlockTextCache(${idx}, this)">${sub.text}</textarea>
                    <div class="log-footer">
                        <span>Modified By: <strong>${sub.last_author}</strong></span>
                        <span>Timestamp Sync Logs: <strong>${sub.last_update}</strong></span>
                    </div>
                `;
                listContainer.appendChild(card);
            });
        }

        function updateBlockTextCache(index, textareaElement) {
            localInMemorySubtitleCache[index].text = textareaElement.value;
            localInMemorySubtitleCache[index].last_author = "QC_Lead_Translator";
            localInMemorySubtitleCache[index].last_update = new Date().toLocaleTimeString();
            
            // Live push onto bottom widescreen display strip 
            document.getElementById('globalFloatingSubtitleText').innerText = textareaElement.value;
            
            const footerSpan = textareaElement.nextElementSibling.querySelectorAll('strong');
            footerSpan[0].innerText = "QC_Lead_Translator";
            footerSpan[1].innerText = localInMemorySubtitleCache[index].last_update;
        }

        function updateBlockWorkflowStatus(index, newStatus, selectElement) {
            localInMemorySubtitleCache[index].status = newStatus;
            localInMemorySubtitleCache[index].last_author = "QC_Lead_Translator";
            localInMemorySubtitleCache[index].last_update = new Date().toLocaleTimeString();
            
            const card = selectElement.closest('.subtitle-card');
            card.className = `subtitle-card card-state-${newStatus} active-track`;
            
            const footerSpan = card.querySelector('.log-footer').querySelectorAll('strong');
            footerSpan[0].innerText = "QC_Lead_Translator";
            footerSpan[1].innerText = localInMemorySubtitleCache[index].last_update;
        }

        async function publishActiveSubtitlesToDisk() {
            if (!activeFilePath) { alert("Select a project target file structure first."); return; }
            
            const response = await fetch('/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file: activeFilePath, subtitles: localInMemorySubtitleCache })
            });
            
            const resData = await response.json();
            if (resData.status === "success") {
                alert("🎉 Local track data builds successfully committed and compiled onto production disk assets! Ready for repository synchronization layers.");
            } else {
                alert("❌ Critical save serialization error.");
            }
        }

        window.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                e.preventDefault();
                publishActiveSubtitlesToDisk();
            }
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    tree = get_srt_file_tree()
    return render_template_string(HTML_TEMPLATE, file_tree=tree)

@app.route('/load')
def load_srt():
    file_path = request.args.get('file')
    subs = parse_srt_with_metadata(file_path)
    return jsonify(subs)

@app.route('/save', methods=['POST'])
def save_srt_api():
    data = request.json
    file_path = data.get('file')
    subtitles = data.get('subtitles')
    
    # Write metadata logs cleanly into file lines block sets
    serialize_srt_metadata(file_path, subtitles)
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
