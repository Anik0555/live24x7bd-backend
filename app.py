import os
import json
import subprocess
import logging
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

# --- App Configuration ---
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}) # Allow all routes

# --- Storage Configuration ---
# Railway-এর Volume-টি /data-তে মাউন্ট করা হয়েছে
VOLUME_PATH = '/data'
VIDEO_STORAGE_PATH = os.path.join(VOLUME_PATH, 'videos')

# নিশ্চিত করা যে ভিডিও ফোল্ডারটি তৈরি করা আছে
if not os.path.exists(VIDEO_STORAGE_PATH):
    os.makedirs(VIDEO_STORAGE_PATH)
    logging.info(f"Created video storage directory at: {VIDEO_STORAGE_PATH}")

# --- Routes ---
@app.route('/')
def health_check():
    return jsonify({"status": "ok", "message": "Backend v4 (Railway Volume Storage) is running!"})

@app.route('/upload', methods=['POST'])
def upload_video():
    try:
        if 'video' not in request.files or 'uid' not in request.form:
            return jsonify({"error": "Missing video file or user ID."}), 400

        video_file = request.files['video']
        uid = request.form.get('uid')
        
        if video_file.filename == '':
            return jsonify({"error": "No selected file."}), 400

        # একটি ইউনিক এবং নিরাপদ ফাইলের নাম তৈরি করা
        filename = f"{uid}__{secure_filename(video_file.filename)}"
        save_path = os.path.join(VIDEO_STORAGE_PATH, filename)
        
        logging.info(f"Saving video for user {uid} to {save_path}...")
        video_file.save(save_path)
        logging.info("Video saved successfully to volume.")
        
        return jsonify({"message": "Video uploaded successfully!", "filename": filename}), 200

    except Exception as e:
        logging.error(f"An error occurred in /upload: {e}", exc_info=True)
        return jsonify({"error": f"An internal server error occurred: {str(e)}"}), 500

@app.route('/videos/<uid>', methods=['GET'])
def get_videos(uid):
    try:
        user_videos = []
        logging.info(f"Scanning for videos for user {uid} in {VIDEO_STORAGE_PATH}")
        for filename in os.listdir(VIDEO_STORAGE_PATH):
            if filename.startswith(f"{uid}__"):
                # ফাইলের নাম থেকে UID অংশটি বাদ দিয়ে আসল নাম দেখানো
                original_name = filename.split('__', 1)[1]
                user_videos.append({
                    "id": filename, # Unique ID is the full filename
                    "name": original_name
                })
        logging.info(f"Found {len(user_videos)} videos.")
        return jsonify(user_videos), 200
    except Exception as e:
        logging.error(f"An error occurred in /videos: {e}", exc_info=True)
        return jsonify({"error": f"Could not list videos: {str(e)}"}), 500

@app.route('/stream', methods=['POST'])
def start_stream():
    try:
        filename = request.form.get('filename') # এখন আমরা filename ব্যবহার করব
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
            'ffmpeg', '-re', '-stream_loop', '-1',
            '-i', video_path,
            '-c:v', 'copy', '-c:a', 'copy', '-f', 'flv',
            full_rtmp_url
        ]
        
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        return jsonify({"message": f"Stream for '{filename}' has started!"}), 200
    except Exception as e:
        logging.error(f"An error occurred in /stream: {e}", exc_info=True)
        return jsonify({"error": f"An internal server error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
