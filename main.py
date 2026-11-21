import os
import json
import uuid
import subprocess
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from google import genai
from google.genai import types

app = FastAPI()

# Diretórios
TEMP_DIR = Path("temp")
DOWNLOADS_DIR = Path("downloads")
TEMP_DIR.mkdir(exist_ok=True)
DOWNLOADS_DIR.mkdir(exist_ok=True)

# Armazena o status dos jobs em memória
jobs = {}

# Inicializa cliente do Gemini (lê automaticamente a variável de ambiente GEMINI_API_KEY)
client = genai.Client()

class ProcessRequest(BaseModel):
    url: str
    num_clips: int = 3

def run_clipping_pipeline(job_id: str, url: str, num_clips: int):
    video_path = TEMP_DIR / f"{job_id}.mp4"
    audio_path = TEMP_DIR / f"{job_id}.mp3"

    try:
        # 1. Download do vídeo com yt-dlp (limitado a 720p para economizar RAM/disco)
        jobs[job_id]["status"] = "Baixando a live..."
        subprocess.run([
            "yt-dlp",
            "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best",
            "--merge-output-format", "mp4",
            "-o", str(video_path),
            url
        ], check=True)

        # 2. Extrai apenas o áudio leve para enviar para a IA
        jobs[job_id]["status"] = "Extraindo áudio para análise..."
        subprocess.run([
            "ffmpeg", "-y", "-i", str(video_path),
            "-vn", "-acodec", "libmp3lame", "-q:a", "6",
            str(audio_path)
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 3. Envia o áudio para o Gemini identificar os melhores momentos
        jobs[job_id]["status"] = "IA identificando os melhores momentos..."
        audio_file = client.files.upload(file=str(audio_path))

        prompt = f"""
        Analise o áudio desta live/vídeo e encontre os {num_clips} momentos mais interessantes, engraçados, polêmicos ou com maior potencial viral.
        Cada corte deve ter entre 20 e 60 segundos.
        Retorne APENAS um JSON válido no seguinte formato, sem texto adicional:
        [
            {{
                "title": "Título chamativo curto",
                "start": "00:01:15",
                "end": "00:01:55",
                "reason": "Motivo curto de por que esse trecho é bom"
            }}
        ]
        """

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[audio_file, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

        # Remove o arquivo de áudio da nuvem do Gemini após análise
        client.files.delete(name=audio_file.name)

        clips_data = json.loads(response.text)
        generated_clips = []

        # 4. Corta os vídeos no formato vertical 9:16 (TikTok/Reels/Shorts)
        jobs[job_id]["status"] = "Renderizando cortes verticais..."
        for idx, clip in enumerate(clips_data):
            clip_filename = f"{job_id}_clip_{idx+1}.mp4"
            clip_path = DOWNLOADS_DIR / clip_filename

            # Corta no timestamp e faz crop central para 9:16
            subprocess.run([
                "ffmpeg", "-y",
                "-ss", clip["start"],
                "-to", clip["end"],
                "-i", str(video_path),
                "-vf", "crop=ih*9/16:ih,scale=720:1280",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                str(clip_path)
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            generated_clips.append({
                "title": clip["title"],
                "reason": clip["reason"],
                "start": clip["start"],
                "end": clip["end"],
                "url": f"/downloads/{clip_filename}"
            })

        jobs[job_id]["status"] = "done"
        jobs[job_id]["clips"] = generated_clips

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)

    finally:
        # Limpa os arquivos brutos para não lotar o servidor
        if video_path.exists():
            video_path.unlink()
        if audio_path.exists():
            audio_path.unlink()

@app.post("/api/process")
def start_process(req: ProcessRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {"status": "Iniciando...", "clips": [], "error": None}
    background_tasks.add_task(run_clipping_pipeline, job_id, req.url, req.num_clips)
    return {"job_id": job_id}

@app.get("/api/status/{job_id}")
def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return jobs[job_id]

# Serve os vídeos cortados para download e preview
app.mount("/downloads", StaticFiles(directory="downloads"), name="downloads")

# Serve o frontend mobile-first
@app.get("/")
def serve_frontend():
    return FileResponse("static/index.html")
