import os
import tempfile
import time
import requests
import assemblyai as aai
from google.cloud import storage
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
import gc

# AssemblyAI API settings
aai.settings.api_key = "2457c9bfd3c842df9ee26db8b65f8f35"

def process_word_batch(words, video_w, video_h, video_duration, batch_size=5):
    """Process words in batches to create caption clips"""
    clips = []
    for i in range(0, len(words), batch_size):
        batch = words[i:i + batch_size]
        batch_clips = []
        
        for word in batch:
            start = word.start / 1000
            end = word.end / 1000
            
            if start < video_duration:
                end = min(end, video_duration)
                duration = end - start
                
                # Use 'label' method instead of 'caption'
                text_clip = (TextClip(
                    word.text,
                    method='label',  # Changed to 'label'
                    font='Arial',    # Specify a common font
                    size=(video_w, None),  # Auto-height
                    color='white',
                    bg_color='black',
                    fontsize=50
                )
                .set_position(('center', 'bottom'))
                .set_start(start)
                .set_duration(duration)
                .margin(opacity=0))  # Transparent margin
                
                batch_clips.append(text_clip)
        
        clips.extend(batch_clips)
        gc.collect()
    
    return clips

def add_captions(request):
    """Main Cloud Function entry point"""
    temp_files = []
    
    try:
        temp_dir = tempfile.mkdtemp(dir='/tmp')
        
        request_json = request.get_json()
        if not request_json:
            return ('No JSON data provided', 400)

        video_url = request_json.get('video_url')
        output_file = request_json.get('output_file')
        
        if not video_url or not output_file:
            return ('Video URL and output file path are required', 400)

        # Download video
        video_path = os.path.join(temp_dir, 'input.mp4')
        temp_files.append(video_path)
        
        print(f"Downloading video from: {video_url}")
        response = requests.get(video_url)
        with open(video_path, 'wb') as f:
            f.write(response.content)

        print("Loading video...")
        video = VideoFileClip(video_path, audio=True)
        video_duration = video.duration
        print(f"Video duration: {video_duration} seconds")

        # Extract audio
        print("Extracting audio from video...")
        audio_path = os.path.join(temp_dir, 'extracted_audio.mp3')
        temp_files.append(audio_path)
        video.audio.write_audiofile(audio_path, fps=16000)

        # Transcribe audio
        print("Transcribing audio...")
        transcriber = aai.Transcriber()
        transcript = transcriber.transcribe(audio_path)
        
        while transcript.status != aai.TranscriptStatus.completed:
            if transcript.status == aai.TranscriptStatus.error:
                raise RuntimeError(f"Transcription failed: {transcript.error}")
            time.sleep(3)
            transcript = transcriber.get_transcript(transcript.id)

        print("Transcription completed successfully")
        
        # Process captions in batches
        print("Creating caption clips...")
        caption_clips = process_word_batch(
            transcript.words,
            video.w,
            video.h,
            video_duration
        )

        # Combine video with captions
        print(f"Adding {len(caption_clips)} caption clips to video...")
        final_video = CompositeVideoClip(
            [video] + caption_clips,
            size=(video.w, video.h)
        )

        # Write output
        output_path = os.path.join(temp_dir, 'output.mp4')
        temp_files.append(output_path)
        
        print("Writing final video...")
        final_video.write_videofile(
            output_path,
            fps=video.fps,
            codec='libx264',
            audio_codec='aac',
            threads=2,
            preset='ultrafast',
            logger=None
        )

        # Upload to GCS
        print(f"Uploading to: {output_file}")
        storage_client = storage.Client()
        bucket = storage_client.bucket('make-video')
        blob = bucket.blob(output_file)
        blob.upload_from_filename(output_path)

        return {
            'status': 'success',
            'output_url': f"https://storage.googleapis.com/make-video/{output_file}"
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {'error': str(e)}, 500

    finally:
        # Cleanup
        print("Cleaning up resources...")
        if 'video' in locals():
            video.close()
        if 'final_video' in locals():
            final_video.close()
        
        for file_path in temp_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"Error cleaning up {file_path}: {str(e)}")
        
        gc.collect()