import os
import json
import subprocess
import logging
import firebase_admin
from firebase_admin import credentials, storage
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename

# --- App Configuration ---
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
CORS(app, resources={r"/stream": {"origins": "*"}})

# --- Firebase Admin SDK Initialization ---
try:
    # Railway-এর Environment Variable থেকে সার্ভিস অ্যাকাউন্টের তথ্য নেওয়া
    service_account_str = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
    storage_bucket_url = os.getenv('STORAGE_BUCKET_URL')

    if not service_account_str or not storage_bucket_url:
        logging.warning("Firebase environment variables not set. Backend might not work correctly.")
    else:
        service_account_info = json.loads(service_account_str)
        cred = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(cred, {
            'storageBucket': storage_bucket_url
        })
        logging.info("Firebase Admin SDK initialized successfully.")

except Exception as e:
    logging.error(f"Error initializing Firebase Admin SDK: {e}")


# --- General Configuration ---
UPLOAD_FOLDER = 'temp_videos' # Temporary folder to store videos for streaming
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- Routes ---
@app.route('/')
def health_check():
    return jsonify({"status": "ok", "message": "Backend v2 is running and ready to stream from Firebase Storage!"})

@app.route('/stream', methods=['POST'])
def start_stream():
    try:
        # ফ্রন্টএন্ড থেকে আসা ডেটা নেওয়া
        storage_path = request.form.get('storage_path')
        stream_url = request.form.get('stream_url')
        stream_key = request.form.get('stream_key')

        if not all([storage_path, stream_url, stream_key]):
            return jsonify({"error": "Missing storage_path, stream_url, or stream_key."}), 400
        
        logging.info(f"Received request to stream: {storage_path}")

        # 1. Firebase Storage থেকে ভিডিও ডাউনলোড করা
        bucket = storage.bucket()
        blob = bucket.blob(storage_path)
        
        # একটি লোকাল পাথ তৈরি করা
        local_filename = os.path.join(app.config['UPLOAD_FOLDER'], storage_path.split('/')[-1])
        
        logging.info(f"Downloading to: {local_filename}...")
        blob.download_to_filename(local_filename)
        logging.info("Download complete.")

        # 2. FFmpeg দিয়ে স্ট্রিমিং শুরু করা
        full_rtmp_url = f"{stream_url.strip()}/{stream_key.strip()}"
        
        command = [
            'ffmpeg', '-re', '-stream_loop', '-1',
            '-i', local_filename,
            '-c:v', 'copy', '-c:a', 'copy', '-f', 'flv',
            full_rtmp_url
        ]
        
        logging.info(f"Starting FFmpeg...")
        # Popen ব্যবহার করা হয়েছে যাতে সার্ভারটি ব্লক না হয়ে যায়
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Note: In a real production system, you'd want a mechanism to clean up the downloaded files.
        # For now, they will persist in the temporary folder.

        return jsonify({"message": f"Stream for '{storage_path.split('/')[-1]}' has been started successfully!"}), 200

    except Exception as e:
        logging.error(f"An error occurred in /stream: {e}")
        return jsonify({"error": f"An internal server error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
