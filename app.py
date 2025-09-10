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

        # Enhanced quality options for maximum video+audio quality with high resolution and fps
        # Prioritize combined video+audio formats first, then fallback to separate streams
        default_format = "best[vcodec^=av01][acodec!=none][height>=2160][fps>30]/best[vcodec^=vp9][acodec!=none][height>=2160][fps>30]/best[vcodec^=av01][acodec!=none][height>=1440][fps>30]/best[vcodec^=vp9][acodec!=none][height>=1440][fps>30]/best[vcodec^=av01][acodec!=none][height>=1080][fps>30]/best[vcodec^=vp9][acodec!=none][height>=1080][fps>30]/best[acodec!=none][height>=1080][fps>30]/best[vcodec^=av01][acodec!=none][height>=2160]/best[vcodec^=vp9][acodec!=none][height>=2160]/best[vcodec^=av01][acodec!=none][height>=1440]/best[vcodec^=vp9][acodec!=none][height>=1440]/best[vcodec^=av01][acodec!=none][height>=1080]/best[vcodec^=vp9][acodec!=none][height>=1080]/best[acodec!=none][height>=1080]/bestvideo[height>=1080]+bestaudio/best"
        
        ydl_opts = {
            "outtmpl": os.path.join(DOWNLOAD_FOLDER, "%(title).200s-%(id)s.%(ext)s"),
            "format": format_id if format_id else default_format,
            "progress_hooks": [p_hook],
            "quiet": True,
            "no_warnings": True,
            "prefer_ffmpeg": True,
            "keepvideo": False,
        }

        if audio_only_mp3:
            ydl_opts["format"] = "bestaudio[acodec^=opus]/bestaudio[acodec^=aac]/bestaudio[abr>=256]/bestaudio"
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            }]
        else:
            # Optimize settings for best video+audio sync and quality
            ydl_opts["merge_output_format"] = "mkv"  # Best container for high quality codecs
            # Removed redundant remuxer as merge_output_format handles this
            # Ensure perfect sync with additional options
            ydl_opts["fragment_retries"] = 10
            ydl_opts["socket_timeout"] = 30

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

            # Filter and prioritize high-quality formats
            quality_formats = []
            for f in formats:
                fid = f.get("format_id")
                if not fid or fid in seen:
                    continue
                seen.add(fid)

                ext = f.get("ext", "")
                height = f.get("height") or 0
                width = f.get("width") or 0
                # Normalize codec values to handle None/null cases
                acodec = f.get("acodec") or "none"
                vcodec = f.get("vcodec") or "none"
                abr = f.get("abr") or 0  # Audio bitrate
                vbr = f.get("vbr") or 0  # Video bitrate
                fps = f.get("fps") or 0
                size = f.get("filesize") or f.get("filesize_approx")

                # Skip very low quality formats
                if height and height < 240:
                    continue
                if acodec != "none" and abr and abr < 96:
                    continue

                # Quality assessment
                quality = ""
                quality_score = 0
                
                if height:
                    quality = f"{height}p"
                    quality_score += height
                    
                    # Bonus for high resolutions with enhanced scoring
                    if height >= 2160:  # 4K
                        quality += " 4K UHD"
                        quality_score += 4000  # Higher bonus for 4K
                    elif height >= 1440:  # 2K
                        quality += " 2K QHD"
                        quality_score += 2500  # Higher bonus for 2K
                    elif height >= 1080:  # FHD
                        quality += " 1080p FHD"
                        quality_score += 1500  # Higher bonus for 1080p
                    elif height >= 720:   # HD
                        quality += " 720p HD"
                        quality_score += 400   # Modest bonus for 720p
                        
                    # Enhanced fps scoring with higher bonuses
                    if fps >= 120:
                        quality += f" {fps}fps HFR"
                        quality_score += fps * 3  # Triple bonus for very high fps
                    elif fps >= 60:
                        quality += f" {fps}fps HFR" 
                        quality_score += fps * 2  # Double bonus for 60fps+
                    elif fps > 30:
                        quality += f" {fps}fps"
                        quality_score += fps * 1.5  # 1.5x bonus for >30fps
                        
                elif f.get("format_note"): 
                    quality = f.get("format_note")

                # Enhance quality scoring for codec preferences
                if vcodec:
                    if "av01" in vcodec:  # AV1 codec bonus
                        quality_score += 300
                        quality += " (AV1)"
                    elif "vp9" in vcodec:  # VP9 codec bonus
                        quality_score += 200
                        quality += " (VP9)"
                    elif "h264" in vcodec or "avc" in vcodec:
                        quality_score += 100
                        quality += " (H.264)"

                if acodec and acodec != "none":
                    if "opus" in acodec:  # Opus codec bonus
                        quality_score += 50
                    elif "aac" in acodec:
                        quality_score += 30
                    
                    if abr:
                        quality_score += abr // 10  # Bonus for higher audio bitrate

                # Type classification with massive bonus for video+audio combined formats
                if acodec != "none" and vcodec != "none": 
                    type_label = "Video+Audio"
                    quality_score += 5000  # MASSIVE preference for combined video+audio formats
                    
                    # Extra bonuses for high-quality combined formats
                    if height >= 2160:  # 4K video+audio
                        quality_score += 3000
                    elif height >= 1440:  # 2K video+audio  
                        quality_score += 2000
                    elif height >= 1080:  # 1080p video+audio
                        quality_score += 1500
                        
                    # High FPS bonus for video+audio
                    if fps >= 120:
                        quality_score += 800
                    elif fps >= 60:
                        quality_score += 500
                    elif fps >= 50:
                        quality_score += 300
                        
                elif acodec != "none" and vcodec == "none": 
                    type_label = "Audio only"
                elif acodec == "none" and vcodec != "none": 
                    type_label = "Video only"
                else: 
                    type_label = "Unknown"

                # Enhanced format labeling
                size_str = f" — {sizeof_fmt(size)}" if size else ""
                bitrate_info = ""
                if vbr and vbr > 1000:
                    bitrate_info += f" {vbr//1000}Mbps"
                elif abr and type_label == "Audio only":
                    bitrate_info += f" {abr}kbps"
                
                label = f"{ext.upper()} {quality} ({type_label}){bitrate_info}{size_str}"

                quality_formats.append({
                    "format_id": fid,
                    "ext": ext,
                    "height": height,
                    "note": label,
                    "acodec": acodec,
                    "vcodec": vcodec,
                    "quality_score": quality_score,
                    "type_label": type_label
                })

            # Sort by quality score (highest first) and filter to best options
            quality_formats.sort(key=lambda x: x["quality_score"], reverse=True)
            
            # Prioritize video+audio formats heavily, limit other types
            video_audio_formats = [f for f in quality_formats if f["type_label"] == "Video+Audio"][:15]  # More video+audio options
            video_only_formats = [f for f in quality_formats if f["type_label"] == "Video only"][:3]     # Fewer video-only
            audio_only_formats = [f for f in quality_formats if f["type_label"] == "Audio only"][:3]     # Fewer audio-only
            
            # Put video+audio formats first in the list
            fmt_list = video_audio_formats + video_only_formats + audio_only_formats

            # Add high-quality MP3 options
            best_audio_formats = [f for f in quality_formats if f["acodec"] != "none" and f["vcodec"] == "none"][:3]
            for f in best_audio_formats:
                # Extract quality info more safely
                note_parts = f['note'].split('(')
                quality_part = note_parts[0].strip() if note_parts else f['note']
                size_part = f['note'].split('—')[-1].strip() if '—' in f['note'] else ""
                
                mp3_label = f"🔊 MP3 320kbps High Quality (Audio only)"
                if size_part:
                    mp3_label += f" — {size_part}"
                    
                fmt_list.append({
                    "format_id": f["format_id"],
                    "ext": "mp3",
                    "height": None,
                    "note": mp3_label,
                    "acodec": f["acodec"],
                    "vcodec": "none",
                    "audio_only_mp3": True,
                    "quality_score": f["quality_score"] + 100  # Slight bonus for MP3 conversion
                })

            # Final sort by quality score to ensure best options appear first
            fmt_list = sorted(fmt_list, key=lambda x: x.get("quality_score", 0), reverse=True)
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
    format_type = data.get("format_type", "unknown")  # Get format type from frontend
    
    if not url or not format_id:
        return jsonify({"error": "URL or format missing"}), 400

    # Adjust format selection based on type to avoid unnecessary merging
    if format_type == "Video only" and not audio_only_mp3:
        # For video-only formats, add best audio
        final_format_id = f"{format_id}+bestaudio[acodec^=opus]/bestaudio[acodec^=aac]/bestaudio"
    elif format_type == "Video+Audio" or audio_only_mp3:
        # For combined formats or MP3 conversion, use format as-is
        final_format_id = format_id
    else:
        # Default case
        final_format_id = format_id

    tid = make_task_entry()
    t = threading.Thread(target=download_worker, args=(tid, url, final_format_id, audio_only_mp3), daemon=True)
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
    app.run(debug=True, host="0.0.0.0", port=5000, threaded=True)