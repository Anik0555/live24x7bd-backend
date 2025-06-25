import os
import json
import subprocess
import logging
import firebase_admin
from firebase_admin import credentials, storage, firestore
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from datetime import datetime

# --- App Configuration ---
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
# CORS-কে দুটি রুটের জন্যই কনফিগার করা
CORS(app, resources={r"/*": {"origins": "*"}})

# --- Firebase Admin SDK Initialization ---
try:
    service_account_str = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
    storage_bucket_url = os.getenv('STORAGE_BUCKET_URL')

    if not service_account_str or not storage_bucket_url:
        logging.warning("Firebase environment variables not set. Backend will not function correctly.")
    else:
        service_account_info = json.loads(service_account_str)
        cred = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(cred, {
            'storageBucket': storage_bucket_url
        })
        db = firestore.client()
        logging.info("Firebase Admin SDK initialized successfully.")
except Exception as e:
    logging.error(f"Error initializing Firebase Admin SDK: {e}")

# --- General Configuration ---
UPLOAD_FOLDER = 'temp_videos'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- Routes ---
@app.route('/')
def health_check():
    return jsonify({"status": "ok", "message": "Backend v3 (Proxy Upload) is running!"})

@app.route('/upload', methods=['POST'])
def upload_video():
    try:
        if 'video' not in request.files or 'uid' not in request.form:
            return jsonify({"error": "Missing video file or user ID."}), 400

        video_file = request.files['video']
        uid = request.form.get('uid')
        
        if video_file.filename == '':
            return jsonify({"error": "No selected file."}), 400

        # 1. ফাইলটি Firebase Storage-এ আপলোড করা
        filename = secure_filename(video_file.filename)
        storage_path = f"{uid}/{int(datetime.now().timestamp())}_{filename}"
        
        bucket = storage.bucket()
        blob = bucket.blob(storage_path)
        
        logging.info(f"Uploading {filename} to Firebase Storage at {storage_path}...")
        blob.upload_from_file(video_file)
        logging.info("Upload to Firebase Storage complete.")

        # 2. ফাইলের তথ্য Firestore ডাটাবেজে সেভ করা
        video_metadata = {
            'name': filename,
            'storagePath': storage_path,
            'size': blob.size,
            'createdAt': firestore.SERVER_TIMESTAMP
        }
        db.collection('users').document(uid).collection('videos').add(video_metadata)
        logging.info("Video metadata saved to Firestore.")

        return jsonify({"message": "Video uploaded and data saved successfully!", "video": video_metadata}), 200

    except Exception as e:
        logging.error(f"An error occurred in /upload: {e}")
        return jsonify({"error": f"An internal server error occurred: {str(e)}"}), 500

@app.route('/stream', methods=['POST'])
def start_stream():
    try:
        storage_path = request.form.get('storage_path')
        stream_url = request.form.get('stream_url')
        stream_key = request.form.get('stream_key')

        if not all([storage_path, stream_url, stream_key]):
            return jsonify({"error": "Missing required streaming parameters."}), 400
        
        logging.info(f"Received request to stream: {storage_path}")

        # Firebase Storage থেকে ভিডিও ডাউনলোড করা
        bucket = storage.bucket()
        blob = bucket.blob(storage_path)
        local_filename = os.path.join(app.config['UPLOAD_FOLDER'], storage_path.split('/')[-1])
        
        logging.info(f"Downloading to: {local_filename}...")
        blob.download_to_filename(local_filename)
        logging.info("Download complete.")

        # FFmpeg দিয়ে স্ট্রিমিং শুরু করা
        full_rtmp_url = f"{stream_url.strip()}/{stream_key.strip()}"
        command = [
            'ffmpeg', '-re', '-stream_loop', '-1',
            '-i', local_filename,
            '-c:v', 'copy', '-c:a', 'copy', '-f', 'flv',
            full_rtmp_url
        ]
        
        logging.info(f"Starting FFmpeg...")
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        return jsonify({"message": f"Stream for '{storage_path.split('/')[-1]}' has started!"}), 200

    except Exception as e:
        logging.error(f"An error occurred in /stream: {e}")
        return jsonify({"error": f"An internal server error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
