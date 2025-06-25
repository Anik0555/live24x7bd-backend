import os
import subprocess
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import sys

# --- App Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# --- Storage Configuration ---
VOLUME_PATH = '/data'
VIDEO_STORAGE_PATH = os.path.join(VOLUME_PATH, 'videos')
if not os.path.exists(VIDEO_STORAGE_PATH):
    os.makedirs(VIDEO_STORAGE_PATH)
    logging.info(f"Created video storage directory at: {VIDEO_STORAGE_PATH}")

# --- Routes ---
@app.route('/')
def health_check():
    return jsonify({"status": "ok", "message": "Backend v5 (Final Production) is running!"})

@app.route('/upload', methods=['POST'])
def upload_video():
    try:
        if 'video' not in request.files or 'uid' not in request.form:
            return jsonify({"error": "Missing video file or user ID."}), 400
        video_file = request.files['video']
        uid = request.form.get('uid')
        if video_file.filename == '':
            return jsonify({"error": "No selected file."}), 400
        filename = f"{uid}__{secure_filename(video_file.filename)}"
        save_path = os.path.join(VIDEO_STORAGE_PATH, filename)
        video_file.save(save_path)
        return jsonify({"message": "Video uploaded successfully!", "filename": filename}), 200
    except Exception as e:
        logging.error(f"Error in /upload: {e}", exc_info=True)
        return jsonify({"error": "Internal server error during upload."}), 500

@app.route('/videos/<uid>', methods=['GET'])
def get_videos(uid):
    try:
        user_videos = []
        for filename in os.listdir(VIDEO_STORAGE_PATH):
            if filename.startswith(f"{uid}__"):
                original_name = filename.split('__', 1)[1]
                user_videos.append({"id": filename, "name": original_name})
        return jsonify(user_videos), 200
    except Exception as e:
        logging.error(f"Error in /videos: {e}", exc_info=True)
        return jsonify({"error": "Could not list videos."}), 500

@app.route('/stream', methods=['POST'])
def start_stream():
    try:
        filename = request.form.get('filename')
        stream_url = request.form.get('stream_url')
        stream_key = request.form.get('stream_key')

        if not all([filename, stream_url, stream_key]):
            return jsonify({"error": "Missing required streaming parameters."}), 400
        
        video_path = os.path.join(VIDEO_STORAGE_PATH, filename)

        if not os.path.exists(video_path):
             return jsonify({"error": f"Video file not found on server: {filename}"}), 404

        logging.info(f"Starting stream for video: {video_path}")
        
        full_rtmp_url = f"{stream_url.strip()}/{stream_key.strip()}"
        
        command = [
            'ffmpeg', '-re', '-stream_loop', '-1', '-i', video_path,
            '-c:v', 'libx264', '-preset', 'veryfast', '-maxrate', '2500k', 
            '-bufsize', '5000k', '-pix_fmt', 'yuv420p', '-g', '60',
            '-c:a', 'aac', '-b:a', '128k', '-ar', '44100',
            '-f', 'flv', full_rtmp_url
        ]
        
        # FFmpeg প্রসেসটিকে সম্পূর্ণ ব্যাকগ্রাউন্ডে চালানো
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        logging.info(f"FFmpeg process for '{filename}' has been started in the background.")
        
        return jsonify({"message": f"Stream for '{filename}' has been initiated successfully!"}), 200

    except Exception as e:
        logging.error(f"Error in /stream: {e}", exc_info=True)
        return jsonify({"error": "Internal server error while starting stream."}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
