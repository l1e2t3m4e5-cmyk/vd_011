import os
import uuid
import threading
import traceback
from flask import Flask, render_template, request, jsonify, send_file
from yt_dlp import YoutubeDL

app = Flask(__name__)
DOWNLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), "downloads")
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

tasks = {}

def make_task_entry():
    tid = str(uuid.uuid4())
    tasks[tid] = {
        "status": "queued",
        "progress": 0.0,
        "filename": None,
        "filepath": None,
        "speed": None,
        "eta": None,
        "message": None,
    }
    return tid

def sizeof_fmt(num, suffix="B"):
    try:
        num = int(num)
    except:
        return ""
    for unit in ["", "K", "M", "G", "T"]:
        if abs(num) < 1024.0:
            return f"{num:.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}P{suffix}"

def download_worker(tid, url, format_id, audio_only_mp3=False):
    try:
        tasks[tid]["status"] = "downloading"

        def p_hook(d):
            try:
                if d.get("status") == "downloading":
                    total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    downloaded = d.get("downloaded_bytes", 0)
                    percent = 0.0
                    if total_bytes:
                        percent = downloaded * 100.0 / float(total_bytes)
                    tasks[tid]["progress"] = round(percent, 2)
                    tasks[tid]["speed"] = d.get("speed")
                    tasks[tid]["eta"] = d.get("eta")
                elif d.get("status") == "finished":
                    tasks[tid]["progress"] = 100.0
            except:
                pass

        ydl_opts = {
            "outtmpl": os.path.join(DOWNLOAD_FOLDER, "%(title).200s-%(id)s.%(ext)s"),
            "format": f"{format_id}+bestaudio/best" if format_id else "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "progress_hooks": [p_hook],
            "quiet": True,
            "no_warnings": True,
        }

        if audio_only_mp3:
            ydl_opts["format"] = "bestaudio/best"
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
            ydl_opts["merge_output_format"] = None

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

            file_found = None
            for f in os.listdir(DOWNLOAD_FOLDER):
                if info.get("id") and info.get("id") in f:
                    file_found = os.path.join(DOWNLOAD_FOLDER, f)
                    break

            if file_found:
                tasks[tid]["filepath"] = file_found
                tasks[tid]["filename"] = os.path.basename(file_found)
                tasks[tid]["status"] = "finished"
                tasks[tid]["progress"] = 100.0
                tasks[tid]["message"] = "Download complete"
            else:
                tasks[tid]["status"] = "error"
                tasks[tid]["message"] = "Downloaded but file not found."
    except Exception as e:
        tasks[tid]["status"] = "error"
        tasks[tid]["message"] = f"Error: {str(e)}"
        tasks[tid]["progress"] = 0.0
        traceback.print_exc()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/get_formats", methods=["POST"])
def get_formats():
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    tid = make_task_entry()
    tasks[tid]["status"] = "fetching_formats"
    try:
        ydl_opts = {"quiet": True, "no_warnings": True}
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get("formats", [])
            fmt_list = []
            seen = set()

            for f in formats:
                fid = f.get("format_id")
                if not fid or fid in seen:
                    continue
                seen.add(fid)

                ext = f.get("ext", "")
                height = f.get("height")
                acodec = f.get("acodec")
                vcodec = f.get("vcodec")
                size = f.get("filesize") or f.get("filesize_approx")

                quality = ""
                if height: quality = f"{height}p"
                elif f.get("format_note"): quality = f.get("format_note")

                if acodec != "none" and vcodec != "none": type_label = "Video+Audio"
                elif acodec != "none" and vcodec == "none": type_label = "Audio only"
                elif acodec == "none" and vcodec != "none": type_label = "Video only"
                else: type_label = "Unknown"

                size_str = f" — {sizeof_fmt(size)}" if size else ""
                label = f"{ext.upper()} {quality} ({type_label}){size_str}"

                fmt_list.append({
                    "format_id": fid,
                    "ext": ext,
                    "height": height,
                    "note": label,
                    "acodec": acodec,
                    "vcodec": vcodec
                })

            # Add MP3 option for audio-only
            audio_only_formats = [f for f in fmt_list if f["acodec"] != "none" and f["vcodec"] == "none"]
            for f in audio_only_formats:
                mp3_label = f"MP3 {f['note'].split()[1]} (Audio only) — {f['note'].split('—')[-1].strip()}"
                fmt_list.append({
                    "format_id": f["format_id"],
                    "ext": "mp3",
                    "height": None,
                    "note": mp3_label,
                    "acodec": f["acodec"],
                    "vcodec": "none",
                    "audio_only_mp3": True
                })

            fmt_list = sorted(fmt_list, key=lambda x: (x["height"] or 0), reverse=True)
            tasks[tid]["status"] = "ready"
            tasks[tid]["message"] = "Formats fetched"
            return jsonify({"task_id": tid, "title": info.get("title"), "formats": fmt_list})
    except Exception as e:
        tasks[tid]["status"] = "error"
        tasks[tid]["message"] = f"Error fetching formats: {str(e)}"
        return jsonify({"error": str(e)}), 500

@app.route("/download", methods=["POST"])
def start_download():
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    format_id = data.get("format_id")
    audio_only_mp3 = data.get("audio_only_mp3", False)
    if not url or not format_id:
        return jsonify({"error": "URL or format missing"}), 400

    tid = make_task_entry()
    t = threading.Thread(target=download_worker, args=(tid, url, format_id, audio_only_mp3), daemon=True)
    t.start()
    return jsonify({"task_id": tid})

@app.route("/progress/<task_id>")
def progress(task_id):
    entry = tasks.get(task_id)
    if not entry:
        return jsonify({"error": "Unknown task"}), 404
    return jsonify(entry)

@app.route("/file/<task_id>")
def get_file(task_id):
    entry = tasks.get(task_id)
    if not entry:
        return jsonify({"error": "Unknown task"}), 404
    if entry.get("status") != "finished" or not entry.get("filepath"):
        return jsonify({"error": "File not ready"}), 400

    file_path = entry["filepath"]
    if not os.path.exists(file_path):
        return jsonify({"error": "File missing on server"}), 500
    return send_file(file_path, as_attachment=True, download_name=entry.get("filename"))

if __name__ == "__main__":
    app.run(debug=True, threaded=True)
