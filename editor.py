import os
import re
import json
import time
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

METADATA_FILE = "subtitle_metadata.json"

def load_metadata():
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_metadata(data):
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_srt_tree():
    """Builds a structured dictionary hierarchy grouped by directory folders"""
    tree = {}
    for root, dirs, files in os.walk("."):
        if any(h in root for h in [".git", ".devcontainer", "__pycache__"]):
            continue
        srt_files = [f for f in files if f.endswith(".srt")]
        if srt_files:
            folder_name = os.path.relpath(root, ".")
            if folder_name == ".":
                folder_name = "Root Directory"
            tree[folder_name] = []
            for file in srt_files:
                relative_path = os.path.relpath(os.path.join(root, file), ".")
                tree[folder_name].append({
                    "name": file,
                    "path": relative_path
                })
    return tree

def parse_srt(file_path):
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    blocks = re.split(r'\n\s*\n', content.strip())
    subtitles = []
    
    metadata = load_metadata().get(file_path, {})
    
    for block in blocks:
        lines = block.split('\n')
        if len(lines) >= 3:
            line_idx = lines[0].strip()
            timecode = lines[1].strip()
            text = " ".join(lines[2:]).strip()
            
            block_meta = metadata.get(line_idx, {
                "status": "Needs Revision",
                "updated_at": 0,
                "author": "System"
            })
            
            subtitles.append({
                "index": line_idx,
                "timecode": timecode,
                "text": text,
                "status": block_meta.get("status", "Needs Revision"),
                "updated_at": block_meta.get("updated_at", 0),
                "author": block_meta.get("author", "System")
            })
    return subtitles

def save_single_block_to_file(file_path, index, new_text, author, status):
    if not os.path.exists(file_path):
        return False
        
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    blocks = re.split(r'\n\s*\n', content.strip())
    updated_blocks = []
    
    for block in blocks:
        lines = block.split('\n')
        if len(lines) >= 3 and lines[0].strip() == str(index):
            lines[2] = new_text
            # Remove any trailing extra lines if present
            updated_blocks.append("\n".join(lines[:3]))
        else:
            updated_blocks.append(block)
            
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(updated_blocks) + "\n\n")
        
    # Update global JSON metadata state pipeline
    all_meta = load_metadata()
    if file_path not in all_meta:
        all_meta[file_path] = {}
        
    all_meta[file_path][str(index)] = {
        "status": status,
        "updated_at": int(time.time()),
        "author": author
    }
    save_metadata(all_meta)
    return True

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
        
        /* Left Column Pane */
        .video-pane {
            width: 40%; background: #07050d;
            display: flex; flex-direction: column; padding: 24px;
            border-right: 1px solid rgba(255, 255, 255, 0.06);
            box-sizing: border-box; gap: 16px; overflow-y: auto;
        }
        .media-container {
            width: 100%; aspect-ratio: 16/9; background: #000000;
            border-radius: 12px; border: 2px dashed rgba(113, 237, 255, 0.3);
            display: flex; flex-direction: column; justify-content: center; align-items: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5); position: relative; box-sizing: border-box;
        }
        
        /* Structural Script Manager Asset Tree */
        .tree-container {
            background: #110e21; border: 1px solid #221c38; border-radius: 8px; padding: 16px;
        }
        .tree-title { font-size: 12px; font-weight: 700; color: #615c7a; text-transform: uppercase; margin-bottom: 12px; }
        .folder-group { margin-bottom: 10px; }
        .folder-header {
            background: #18142c; padding: 8px 12px; border-radius: 6px; font-size: 13px; 
            font-weight: 600; color: #71EDFF; cursor: pointer; display: flex; justify-content: space-between;
        }
        .folder-content { padding-left: 12px; margin-top: 6px; display: flex; flex-direction: column; gap: 4px; }
        .file-item {
            padding: 8px 12px; font-size: 12px; color: #b4b0cb; border-radius: 4px; cursor: pointer;
            transition: all 0.2s; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .file-item:hover { background: rgba(255, 119, 237, 0.1); color: #FF77ED; }
        .file-item.active-file { background: #FF77ED; color: #0b0914; font-weight: 600; }

        /* Subtitle Spreadsheet Layout Pane */
        .subtitle-pane { width: 60%; display: flex; flex-direction: column; padding: 24px; box-sizing: border-box; }
        
        /* Dedicated Subtitle Text Overlay Monitor Ribbon */
        .monitor-ribbon {
            background: #000000; border: 1px solid rgba(113, 237, 255, 0.2);
            border-radius: 8px; padding: 16px; margin-bottom: 16px; min-height: 50px;
            display: flex; justify-content: center; align-items: center; text-align: center;
            box-shadow: inset 0 0 15px rgba(113, 237, 255, 0.05);
        }
        .monitor-text { color: #ffffff; font-size: 18px; font-weight: 500; font-family: sans-serif; }

        /* Jump Utility Search Bar Wrapper */
        .search-wrapper { display: flex; gap: 10px; margin-bottom: 16px; }
        
        .subtitle-list { flex: 1; overflow-y: auto; padding-right: 8px; }
        
        /* Multi-User Collaboration Subtitle Cards */
        .subtitle-card {
            background: #110e21; border: 1px solid #1d1833;
            border-left: 6px solid #2d254b; padding: 16px; margin-bottom: 12px;
            border-radius: 8px; display: flex; flex-direction: column; gap: 10px; position: relative;
        }
        .subtitle-card.active-track { box-shadow: 0 0 15px rgba(255,119,237,0.1); border-color: #2d254b; }
        
        /* Professional Color Code Tags */
        .card-tag-Done { border-left-color: #00ffcc !important; }
        .card-tag-InProgress { border-left-color: #ffcc00 !important; }
        .card-tag-NeedsRevision { border-left-color: #ff4466 !important; }

        .card-meta { display: flex; justify-content: space-between; align-items: center; font-size: 12px; font-weight: 600; color: #615c7a; }
        .timestamp-badge { color: #71EDFF; background: rgba(113,237,255,0.07); padding: 4px 10px; border-radius: 4px; font-family: monospace; }
        
        .card-textarea {
            width: 100%; background: #07050d; border: 1px solid #221c38;
            border-radius: 6px; padding: 12px; color: #ffffff;
            font-family: inherit; font-size: 14px; line-height: 1.5; resize: none; box-sizing: border-box;
        }
        .card-textarea:focus { outline: none; border-color: #FF77ED; }
        
        .collab-row { display: flex; justify-content: space-between; align-items: center; margin-top: 4px; }
        .author-input { background: transparent; border: none; border-bottom: 1px dashed #2d254b; color: #b4b0cb; font-size: 11px; width: 80px; padding: 2px; }
        .author-input:focus { outline: none; border-color: #FF77ED; }
        
        .status-select { background: #07050d; border: 1px solid #2d254b; color: #f3f4f6; font-size: 11px; padding: 4px 8px; border-radius: 4px; font-weight: 600; }
        
        .time-counter { font-size: 11px; color: #615c7a; font-weight: 500; }
        .collision-alert { color: #ff4466; font-weight: 700; font-size: 11px; display: none; }
        
        .instruction-box { background: #110e21; border: 1px solid #2d254b; padding: 16px; border-radius: 8px; box-sizing: border-box; width: 100%; text-align: left; }
        .instruction-title { color: #FF77ED; font-weight: 700; font-size: 14px; margin-bottom: 6px; }
        .step-list { margin: 0; padding-left: 16px; font-size: 12px; color: #b4b0cb; line-height: 1.6; }
        .step-list strong { color: #71EDFF; }

        .btn { padding: 12px 20px; border: none; border-radius: 6px; font-weight: 600; font-size: 13px; cursor: pointer; transition: all 0.2s ease; }
        .btn-primary { background: #FF77ED; color: #0b0914; text-decoration: none; text-align: center; }
        .btn-primary:hover { background: #ff99f0; }
        .btn-success { background: #71EDFF; color: #0b0914; }
        
        input[type="text"].search-box { background: #110e21; border: 1px solid #221c38; padding: 12px 16px; border-radius: 6px; color: #ffffff; font-size: 13px; flex: 1; }
        input[type="text"].search-box:focus { outline: none; border-color: #71EDFF; }
    </style>
</head>
<body>

    <header>
        <h1>🎬 <span class="brand-badge">LingOrm Fan Subtitles</span> // Global Verification Center</h1>
        <div>
            <span style="font-size: 12px; color: #615c7a; margin-right: 10px;">Your Workspace Initials:</span>
            <input type="text" id="globalAuthor" class="author-input" style="width: 50px; font-size: 13px; color:#71EDFF; text-align:center;" value="QC" placeholder="Initials">
        </div>
    </header>

    <div class="workspace">
        <div class="video-pane">
            <div class="media-container">
                <div class="instruction-box">
                    <div class="instruction-title">CH3Plus PiP Alignment Target</div>
                    <ol class="step-list">
                        <li>Open your CH3Plus episode tab, log in, and click <strong>Picture-in-Picture</strong>.</li>
                        <li>Drag and align your floating video over this dashed box.</li>
                    </ol>
                    <a href="https://ch3plus.com" target="_blank" class="btn btn-primary" style="margin-top: 10px; display:block; font-size:12px; padding:8px;">🌐 Open CH3Plus Portal</a>
                </div>
            </div>
            
            <div class="tree-container">
                <div class="tree-title">📁 Repository Structure Asset Tree</div>
                <div id="repoTree">
                    <!-- Dynamic Folder Groups Inject Here -->
                    {% for folder, files in tree.items() %}
                    <div class="folder-group">
                        <div class="folder-header" onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'none' ? 'flex' : 'none'">
                            <span>📂 {{ folder }}</span>
                            <span>▼</span>
                        </div>
                        <div class="folder-content">
                            {% for file in files %}
                            <div class="file-item" onclick="selectFile('{{ file.path }}', this)">📄 {{ file.name }}</div>
                            {% endfor %}
                        </div>
                    </div>
                    {% endfor %}
                </div>
            </div>
        </div>
        
        <div class="subtitle-pane">
            <!-- Continuous Text Layer Monitor Overlay View -->
            <div class="monitor-ribbon">
                <div class="monitor-text" id="monitorText">Select a script file card to review layout layers.</div>
            </div>

            <!-- Manual Search Jump Tool UI -->
            <div class="search-wrapper">
                <input type="text" id="searchJumpInput" class="search-box" placeholder="Type block ID or paste timestamp (e.g., 00:02:15) to jump instantly...">
                <button class="btn btn-success" onclick="executeSearchJump()">Jump to Line</button>
            </div>
            
            <div class="subtitle-list" id="subtitleList">
                <div style="color: #615c7a; text-align: center; margin-top: 120px; font-size: 14px;">Please open a folder group and select an SRT target asset to begin.</div>
            </div>
        </div>
    </div>

    <script>
        let activeFilePath = "";
        let timeUpdateIntervals = [];

        function formatTimeAgo(timestamp) {
            if (!timestamp || timestamp === 0) return "Never updated";
            const diff = Math.floor(Date.now() / 1000) - timestamp;
            if (diff < 5) return "Just now";
            if (diff < 60) return `${diff}s ago`;
            const mins = Math.floor(diff / 60);
            if (mins < 60) return `${mins}m ago`;
            return "Hours ago";
        }

        function executeSearchJump() {
            const query = document.getElementById('searchJumpInput').value.trim();
            if (!query) return;

            const cards = document.querySelectorAll('.subtitle-card');
            let targetCard = null;

            cards.forEach(card => {
                const blockIdx = card.getAttribute('data-index');
                const timecode = card.getAttribute('data-timecode');
                
                if (blockIdx === query || timecode.includes(query)) {
                    targetCard = card;
                }
            });

            if (targetCard) {
                targetCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
                targetCard.click(); // Triggers the highlight active state loop automatically
                document.getElementById('searchJumpInput').value = "";
            } else {
                alert("No matching Block ID or Timestamp position coordinates found inside this file.");
            }
        }

        async function selectFile(filePath, element) {
            document.querySelectorAll('.file-item').forEach(item => item.classList.remove('active-file'));
            element.classList.add('active-file');
            activeFilePath = filePath;
            
            // Clear prior timing loop allocations
            timeUpdateIntervals.forEach(clearInterval);
            timeUpdateIntervals = [];

            const response = await fetch(`/load?file=${encodeURIComponent(filePath)}`);
            const subs = await response.json();
            
            const listContainer = document.getElementById('subtitleList');
            listContainer.innerHTML = "";
            
            subs.forEach(sub => {
                const cleanedStatus = sub.status.replace(/\s+/g, '');
                const card = document.createElement('div');
                card.className = `subtitle-card card-tag-${cleanedStatus}`;
                card.setAttribute('data-index', sub.index);
                card.setAttribute('data-timecode', sub.timecode);
                card.id = `sub-card-${sub.index}`;
                
                card.onclick = () => {
                    document.querySelectorAll('.subtitle-card').forEach(c => c.classList.remove('active-track'));
                    card.classList.add('active-track');
                    document.getElementById('monitorText').innerText = card.querySelector('.card-textarea').value;
                };
                
                card.innerHTML = `
                    <div class="card-meta">
                        <span>BLOCK ID #<strong style="color:#ffffff;">${sub.index}</strong></span>
                        <div class="collision-alert" id="alert-${sub.index}">⚠️ Colliding Editor Active!</div>
                        <span class="timestamp-badge">${sub.timecode}</span>
                    </div>
                    <textarea class="card-textarea" rows="2" oninput="handleCardTyping(${sub.index}, this)">${sub.text}</textarea>
                    <div class="collab-row">
                        <div>
                            <span class="time-counter" id="timecounter-${sub.index}" data-time="${sub.updated_at}">
                                ${formatTimeAgo(sub.updated_at)}
                            </span>
                            <span style="font-size:11px; color:#4e4966; margin-left:6px;">by ${sub.author}</span>
                        </div>
                        <select class="status-select" onchange="updateBlockStatus(${sub.index}, this.value)">
                            <option value="Needs Revision" ${sub.status === 'Needs Revision' ? 'selected' : ''}>❌ Needs Revision</option>
                            <option value="In Progress" ${sub.status === 'In Progress' ? 'selected' : ''}>⏳ In Progress</option>
                            <option value="Done" ${sub.status === 'Done' ? 'selected' : ''}>✅ Done</option>
                        </select>
                    </div>
                `;
                listContainer.appendChild(card);
                
                // Keep the "time ago" counters updated live without reloading the app
                const interval = setInterval(() => {
                    const counter = document.getElementById(`timecounter-${sub.index}`);
                    if (counter) {
                        const originalTime = parseInt(counter.getAttribute('data-time'));
                        counter.innerText = formatTimeAgo(originalTime);
                    }
                }, 5000);
                timeUpdateIntervals.push(interval);
            });
        }

        async function handleCardTyping(index, textareaElement) {
            document.getElementById('monitorText').innerText = textareaElement.value;
            const author = document.getElementById('globalAuthor').value.trim() || "QC";
            const card = document.getElementById(`sub-card-${index}`);
            const selectElement = card.querySelector('.status-select');
            
            const response = await fetch('/save-block', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    file: activeFilePath,
                    index: index,
                    text: textareaElement.value,
                    author: author,
                    status: selectElement.value
                })
            });
            
            const data = await response.json();
            
            // Check for collision overlaps from other translation team members
            const alertBox = document.getElementById(`alert-${index}`);
            if (data.collision_detected) {
                alertBox.style.display = "block";
            } else {
                alertBox.style.display = "none";
            }
            
            // Update time badge instantly on save
            const counter = document.getElementById(`timecounter-${index}`);
            counter.setAttribute('data-time', Math.floor(Date.now() / 1000));
            counter.innerText = "Just now";
        }

        async function updateBlockStatus(index, newStatus) {
            const card = document.getElementById(`sub-card-${index}`);
            const textarea = card.querySelector('.card-textarea');
            
            // Strip spaces to match CSS class selectors safely
            const cleanedClass = newStatus.replace(/\s+/g, '');
            card.className = `subtitle-card card-tag-${cleanedClass} active-track`;
            
            handleCardTyping(index, textarea);
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    tree = get_srt_tree()
    return render_template_string(HTML_TEMPLATE, tree=tree)

@app.route('/load')
def load_srt():
    file_path = request.args.get('file')
    subs = parse_srt(file_path)
    return jsonify(subs)

@app.route('/save-block', methods=['POST'])
def save_block_api():
    data = request.json
    file_path = data.get('file')
    index = data.get('index')
    text = data.get('text')
    author = data.get('author')
    status = data.get('status')
    
    # Read the current metadata state to check for potential collisions
    all_meta = load_metadata()
    existing_block = all_meta.get(file_path, {}).get(str(index), {})
    last_update_time = existing_block.get("updated_at", 0)
    last_author = existing_block.get("author", "")
    
    collision_detected = False
    # If someone else edited this line within the last 60 seconds, flag a collision warning
    if (int(time.time()) - last_update_time) < 60 and last_author != author and last_author != "":
        collision_detected = True
        
    save_single_block_to_file(file_path, index, text, author, status)
    
    return jsonify({
        "status": "success", 
        "collision_detected": collision_detected
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
