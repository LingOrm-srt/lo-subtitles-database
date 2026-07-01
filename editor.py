import os
import re
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

# Locate all subtitle tracks inside the repository structure dynamically
def get_all_srt_files():
    srt_files = []
    for root, dirs, files in os.walk("."):
        # Ignore hidden folders like .git or .devcontainer
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
    
    # Split blocks by double newlines
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

# Added an 'r' before the triple quotes to make it a Raw String and prevent escape warnings
HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html>
<head>
    <title>LO Arena - Verification Studio</title>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        body {
            margin: 0; padding: 0;
            font-family: 'Poppins', sans-serif;
            background: #090710; color: #ffffff;
            display: flex; flex-direction: column; height: 100vh;
            overflow: hidden;
        }
        header {
            background: #120f1d; padding: 14px 24px;
            display: flex; justify-content: space-between; align-items: center;
            border-bottom: 1px solid rgba(113, 237, 255, 0.1);
        }
        h1 { margin: 0; font-size: 18px; color: #71EDFF; letter-spacing: 0.5px; }
        .workspace { display: flex; flex: 1; overflow: hidden; }
        
        /* Video Viewport Pane */
        .video-pane {
            width: 45%; background: #000000;
            display: flex; flex-direction: column; padding: 20px;
            border-right: 1px solid rgba(255, 255, 255, 0.05);
            box-sizing: border-box;
        }
        .video-box {
            width: 100%; aspect-ratio: 16/9; background: #120f1d;
            border-radius: 8px; border: 1px solid #2e264f;
            display: flex; justify-content: center; align-items: center;
            color: #666; font-size: 14px; margin-bottom: 15px;
        }
        .url-input-row { display: flex; gap: 10px; }
        input[type="text"] {
            flex: 1; padding: 10px; background: #120f1d;
            border: 1px solid #2e264f; border-radius: 6px;
            color: #ffffff; font-family: inherit; font-size: 12px;
        }
        .btn {
            padding: 10px 16px; border: none; border-radius: 6px;
            font-weight: 600; font-size: 12px; cursor: pointer; transition: all 0.2s;
        }
        .btn-primary { background: #FF77ED; color: #000; }
        .btn-primary:hover { background: #ff9eff; }
        .btn-success { background: #71EDFF; color: #000; }
        .btn-success:hover { background: #a2f5ff; }
        
        /* Subtitle Editing Pane */
        .subtitle-pane { width: 55%; display: flex; flex-direction: column; padding: 20px; box-sizing: border-box; }
        .file-selector { margin-bottom: 20px; width: 100%; padding: 10px; background: #120f1d; border: 1px solid #2e264f; color: #71EDFF; font-weight: 600; border-radius: 6px; }
        .subtitle-list { flex: 1; overflow-y: auto; padding-right: 10px; }
        
        /* Subtitle Line Rows */
        .subtitle-card {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-left: 3px solid #FF77ED;
            padding: 12px; margin-bottom: 10px; border-radius: 6px;
            display: flex; flex-direction: column; gap: 8px;
        }
        .card-meta { display: flex; justify-content: space-between; font-size: 11px; color: #6a677a; font-weight: 600; }
        .card-textarea {
            width: 100%; background: #0d0b16; border: 1px solid #2e264f;
            border-radius: 4px; padding: 8px; color: #ffffff;
            font-family: inherit; font-size: 13px; resize: vertical; box-sizing: border-box;
        }
        .card-textarea:focus { outline: none; border-color: #71EDFF; }
        
        /* Save Footer Bar */
        .action-bar { display: flex; justify-content: flex-end; padding-top: 15px; border-top: 1px solid rgba(255, 255, 255, 0.05); }
    </style>
</head>
<body>

    <header>
        <h1>🎬 LINGORM STUDIO // Verification Workspace</h1>
        <button class="btn btn-success" onclick="saveActiveFile()">💾 Save Changes to Repository</button>
    </header>

    <div class="workspace">
        <div class="video-pane">
            <div class="video-box" id="videoContainer">No Active Video Preview Loaded</div>
            <div class="url-input-row">
                <input type="text" id="videoUrl" placeholder="Paste YouTube Video URL here...">
                <button class="btn btn-primary" onclick="loadVideo()">Load Video</button>
            </div>
        </div>
        
        <div class="subtitle-pane">
            <select class="file-selector" id="fileSelector" onchange="loadSrtFile(this.value)">
                <option value="">-- Choose a Subtitle File to Review --</option>
                {% for file in srt_files %}
                <option value="{{ file }}">{{ file }}</option>
                {% endfor %}
            </select>
            
            <div class="subtitle-list" id="subtitleList">
                <div style="color: #6a677a; text-align: center; margin-top: 100px;">Select a track script to populate the sequence timelines.</div>
            </div>
        </div>
    </div>

    <script>
        let activeFilePath = "";

        function loadVideo() {
            const urlInput = document.getElementById('videoUrl').value;
            const container = document.getElementById('videoContainer');
            if (urlInput.includes('youtube.com') || urlInput.includes('youtu.be')) {
                let videoId = "";
                if (urlInput.includes('v=')) {
                    videoId = urlInput.split('v=')[1].split('&')[0];
                } else {
                    videoId = urlInput.split('/').pop();
                }
                container.innerHTML = `<iframe width="100%" height="100%" src="https://www.youtube.com/embed/${videoId}" frameborder="0" allowfullscreen style="border-radius:6px;"></iframe>`;
            } else {
                alert("Please enter a valid YouTube video track link.");
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
                card.innerHTML = `
                    <div class="card-meta">
                        <span>SEQUENCE NO. ${sub.index}</span>
                        <span style="color: #71EDFF;">${sub.timecode}</span>
                    </div>
                    <textarea class="card-textarea" data-index="${sub.index}" data-timecode="${sub.timecode}">${sub.text}</textarea>
                `;
                listContainer.appendChild(card);
            });
        }

        async function saveActiveFile() {
            if (!activeFilePath) { alert("No track target is selected."); return; }
            const textareas = document.querySelectorAll('.card-textarea');
            const subtitles = [];
            
            textareas.forEach(tx => {
                subtitles.push({
                    index: tx.getAttribute('data-index'),
                    timecode: tx.getAttribute('data-timecode'),
                    text: tx.value
                });
            });
            
            const response = await fetch('/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file: activeFilePath, subtitles: subtitles })
            });
            
            const resData = await response.json();
            if (resData.status === "success") {
                alert("🎉 File written directly to disk repository! Sync via your Git tab to update Cloudflare.");
            } else {
                alert("❌ Error compiling file changes onto disk.");
            }
        }
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
