import os
from flask import (
    Flask, render_template, request, redirect,
    url_for, send_from_directory, flash
)
from werkzeug.utils import secure_filename
from moviepy import VideoFileClip
import whisper
import time
import traceback

app = Flask(__name__)
app.secret_key = "YOUR SECRET KEY HERE"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
GENERATED_SUBTITLES_FOLDER = os.path.join(BASE_DIR, 'generated_subtitles')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['GENERATED_SUBTITLES_FOLDER'] = GENERATED_SUBTITLES_FOLDER
app.config['ALLOWED_EXTENSIONS'] = {'mp4', 'mov', 'avi', 'mkv', 'webm', 'flv', 'mpeg', 'mpg'}
app.config['MAX_CONTENT_LENGTH'] = 750 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(GENERATED_SUBTITLES_FOLDER, exist_ok=True)

def allowed_file(filename):
    if not isinstance(filename, str):
        return False
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def format_srt_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"

@app.route('/', methods=['GET', 'POST'])
def upload_and_process_video():
    if request.method == 'POST':
        if 'video' not in request.files:
            flash('Tidak ada file yang dipilih, Kakak! (・`ω´・)', 'error')
            return redirect(request.url)
        
        file = request.files['video']

        if not file.filename:
            flash('Belum ada file yang dipilih, coba lagi yaa! (o･ω･o)', 'error')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            original_filename = secure_filename(str(file.filename))
            
            timestamp_prefix = str(int(time.time()))
            video_filename = timestamp_prefix + "_" + original_filename
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], video_filename)
            
            audio_path = None
            srt_path = None

            try:
                file.save(video_path)
                
                if not os.path.exists(video_path):
                    flash(f"Error: Gagal menyimpan file '{original_filename}' ke server.", "error")
                    return redirect(request.url)

                audio_filename_no_ext = os.path.splitext(video_filename)[0]
                audio_filename_wav = audio_filename_no_ext + ".wav"
                audio_path = os.path.join(app.config['UPLOAD_FOLDER'], audio_filename_wav)
                
                flash("Memulai ekstraksi audio...", "info")
                with VideoFileClip(video_path) as video_clip:
                    audio_clip = video_clip.audio
                    if audio_clip is None:
                        flash(f"Video '{original_filename}' sepertinya tidak punya trek audio, Kakak! (・_・;)", 'error')
                        if os.path.exists(video_path): os.remove(video_path)
                        return redirect(request.url)
                    audio_clip.write_audiofile(audio_path, codec='pcm_s16le', ffmpeg_params=["-ac", "1"])
                
                if not os.path.exists(audio_path):
                    flash(f"Error: Gagal mengekstrak audio dari '{original_filename}'. Pastikan ffmpeg terinstall.", "error")
                    if os.path.exists(video_path): os.remove(video_path)
                    return redirect(request.url)
                
                flash("Ekstraksi audio selesai. Memulai transkripsi (ini bisa lama)...", "info")
                whisper_model = whisper.load_model("large") # Anda bisa coba model lain: "base", "tiny", "small", "medium", "large"
                result = whisper_model.transcribe(audio_path, fp16=False) # Deteksi bahasa otomatis
                
                detected_language = result.get('language', 'tidak terdeteksi')
                flash(f"Transkripsi selesai. Bahasa terdeteksi: {detected_language.upper()}", "info")

                srt_filename = audio_filename_no_ext + ".srt"
                srt_path = os.path.join(app.config['GENERATED_SUBTITLES_FOLDER'], srt_filename)
                
                srt_content = ""
                for i, segment in enumerate(result['segments']):
                    start_time_srt = format_srt_time(segment['start'])
                    end_time_srt = format_srt_time(segment['end'])
                    text = segment['text'].strip()
                    srt_content += f"{i+1}\n{start_time_srt} --> {end_time_srt}\n{text}\n\n"
                
                with open(srt_path, 'w', encoding='utf-8') as srt_file:
                    srt_file.write(srt_content)

                flash(f"Yeay! Subtitle untuk '{original_filename}' sudah jadi! <a href='{url_for('download_subtitle', filename=srt_filename)}' style='color: green; font-weight: bold;'>Download di sini ya!</a> 🎉", 'success')
                return redirect(url_for('upload_and_process_video'))

            except Exception as e:
                print("--- TERJADI ERROR ---")
                traceback.print_exc() 
                print("--- END ERROR ---")
                flash(f"Waduh, ada error nih Kakak saat proses '{original_filename}': {str(e)} (╥﹏╥)", 'error')
                return redirect(request.url)
            finally:
                if os.path.exists(video_path): 
                    try: os.remove(video_path)
                    except Exception as e_del: print(f"Gagal hapus video temp: {e_del}")
                if audio_path and os.path.exists(audio_path): 
                    try: os.remove(audio_path)
                    except Exception as e_del: print(f"Gagal hapus audio temp: {e_del}")
        else:
            flash('Format file tidak diizinkan atau nama file bermasalah, Kakak! Pilih .mp4, .mov, .avi, .mkv, .webm, .flv, .mpeg, atau .mpg yaa. (｀ε´)', 'error')
            return redirect(request.url)

    return render_template('index.html')

@app.route('/download_subtitle/<filename>')
def download_subtitle(filename):
    try:
        safe_filename = secure_filename(filename)
        if ".." in safe_filename or safe_filename.startswith(("/", "\\")):
             flash("Nama file tidak valid.", 'error')
             return redirect(url_for('upload_and_process_video'))

        return send_from_directory(
            app.config['GENERATED_SUBTITLES_FOLDER'],
            safe_filename,
            as_attachment=True
        )
    except FileNotFoundError:
        flash("Maaf, file subtitle tidak ditemukan! (╯︵╰,)", 'error')
        return redirect(url_for('upload_and_process_video'))
    except Exception as e:
        print(f"Error saat download: {e}")
        traceback.print_exc()
        flash("Terjadi kesalahan saat mencoba download file.", 'error')
        return redirect(url_for('upload_and_process_video'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)