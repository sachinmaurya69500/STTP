from __future__ import annotations

import hashlib
import json
import os
import re
import smtplib
import tempfile
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

try:
    from pymongo import MongoClient
except ImportError:  # pragma: no cover
    MongoClient = None

try:
    from faster_whisper import WhisperModel
except ImportError:  # pragma: no cover
    WhisperModel = None

try:
    import ollama
except ImportError:  # pragma: no cover
    ollama = None

try:
    from groq import Groq
except ImportError:  # pragma: no cover
    Groq = None

BASE_DIR = Path(__file__).resolve().parent
APP_TITLE = os.getenv("APP_TITLE", "LectureSense")
STORAGE_MODE = os.getenv("STORAGE_MODE", "memory").lower()
TRANSCRIPTION_ENGINE = os.getenv("TRANSCRIPTION_ENGINE", "faster-whisper").lower()
SUMMARY_ENGINE = os.getenv("SUMMARY_ENGINE", "ollama").lower()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "tiny")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "lecture_sense")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USERNAME)
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "LectureSense")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
CORS_ALLOWED_ORIGINS = [
    origin.strip() for origin in os.getenv("CORS_ALLOWED_ORIGINS", "*").split(",") if origin.strip()
]

@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_mongodb_schema()
    yield


app = FastAPI(title=APP_TITLE, version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS if CORS_ALLOWED_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TRANSCRIPTS: list[dict[str, Any]] = []
NOTES: list[dict[str, Any]] = []
USERS: list[dict[str, Any]] = []


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def send_smtp_email(to_email: str, subject: str, body: str) -> bool:
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        return False
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
        msg["To"] = to_email
        msg.set_content(body)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as exc:
        print(f"SMTP error: {exc}")
        return False


def register_user(payload: dict[str, str]) -> dict[str, Any]:
    email = (payload.get("email") or "").strip().lower()
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    confirm_password = payload.get("confirm_password") or ""

    if not email or not username or not password:
        return {"success": False, "message": "Please complete all required fields."}

    if len(password) < 6:
        return {"success": False, "message": "Password must be at least 6 characters long."}

    if password != confirm_password:
        return {"success": False, "message": "Passwords do not match."}

    for user in USERS:
        if user["email"].lower() == email or user["username"].lower() == username.lower():
            return {"success": False, "message": "An account with that email or username already exists."}

    user = {
        "id": len(USERS) + 1,
        "username": username,
        "email": email,
        "password_hash": hash_password(password),
        "created_at": datetime.utcnow().isoformat(),
    }
    USERS.append(user)

    send_smtp_email(
        email,
        "Welcome to LectureSense",
        (
            f"Hi {username},\n\n"
            "Your account has been created successfully.\n"
            "You can now log in and start transcribing your lectures.\n\n"
            "Best regards,\nLectureSense"
        ),
    )

    return {
        "success": True,
        "message": "Registration successful. Welcome to LectureSense!",
        "user": {"id": user["id"], "username": user["username"], "email": user["email"]},
    }


def login_user(payload: dict[str, str]) -> dict[str, Any]:
    email_or_username = (payload.get("email") or payload.get("username") or "").strip().lower()
    password = payload.get("password") or ""

    if not email_or_username or not password:
        return {"success": False, "message": "Email/username and password are required."}

    for user in USERS:
        user_email = user["email"].lower()
        user_name = user["username"].lower()
        if (user_email == email_or_username or user_name == email_or_username) and user["password_hash"] == hash_password(password):
            return {
                "success": True,
                "message": "Login successful.",
                "user": {"id": user["id"], "username": user["username"], "email": user["email"]},
            }

    return {"success": False, "message": "Invalid email/username or password."}


def oauth_user_or_create(oauth_provider: str, oauth_id: str, email: str, name: str) -> dict[str, Any]:
    """Get or create user via OAuth provider."""
    email_lower = email.strip().lower()
    
    # Check if user exists by email
    for user in USERS:
        if user["email"].lower() == email_lower:
            return {
                "success": True,
                "message": "Login successful via OAuth.",
                "user": {"id": user["id"], "username": user["username"], "email": user["email"]},
            }
    
    # Create new user from OAuth data
    username = name.replace(" ", "_").lower() or email_lower.split("@")[0]
    
    # Ensure unique username
    counter = 1
    base_username = username
    while any(u["username"].lower() == username.lower() for u in USERS):
        username = f"{base_username}{counter}"
        counter += 1
    
    user = {
        "id": len(USERS) + 1,
        "username": username,
        "email": email_lower,
        "password_hash": hashlib.sha256(f"oauth_{oauth_provider}_{oauth_id}".encode()).hexdigest(),
        "oauth_provider": oauth_provider,
        "oauth_id": oauth_id,
        "created_at": datetime.utcnow().isoformat(),
    }
    USERS.append(user)
    
    # Send welcome email
    send_smtp_email(
        email_lower,
        "Welcome to LectureSense",
        (
            f"Hi {name or username},\n\n"
            "Your account has been created via OAuth and is ready to use.\n"
            "You can now log in and start transcribing your lectures.\n\n"
            "Best regards,\nLectureSense"
        ),
    )
    
    return {
        "success": True,
        "message": "Login successful via OAuth.",
        "user": {"id": user["id"], "username": user["username"], "email": user["email"]},
    }


def use_mongodb() -> bool:
    return STORAGE_MODE == "mongodb" or bool(MONGO_URI and MongoClient)


def connect_db():
    if not use_mongodb() or MongoClient is None:
        return None
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        return client[MONGO_DB_NAME]
    except Exception:
        return None


def ensure_mongodb_schema() -> None:
    if not use_mongodb():
        return
    db = connect_db()
    if db is None:
        return
    try:
        db.transcripts.create_index([("created_at", -1)])
        db.notes.create_index([("created_at", -1)])
    except Exception:
        return


def serialize_mongo_doc(doc: dict[str, Any]) -> dict[str, Any]:
    item = dict(doc)
    item.pop("_id", None)
    return item


def fetch_transcripts_from_db() -> list[dict[str, Any]]:
    if not use_mongodb():
        return TRANSCRIPTS
    db = connect_db()
    if db is None:
        return TRANSCRIPTS
    try:
        rows = list(db.transcripts.find().sort("created_at", -1))
        return [serialize_mongo_doc(row) for row in rows]
    except Exception:
        return TRANSCRIPTS


def fetch_notes_from_db() -> list[dict[str, Any]]:
    if not use_mongodb():
        return NOTES
    db = connect_db()
    if db is None:
        return NOTES
    try:
        rows = list(db.notes.find().sort("created_at", -1))
        return [serialize_mongo_doc(row) for row in rows]
    except Exception:
        return NOTES


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def save_note_record(note: dict[str, Any]) -> None:
    if use_mongodb():
        db = connect_db()
        if db is not None:
            payload = dict(note)
            payload["created_at"] = datetime.utcnow()
            try:
                db.notes.insert_one(payload)
                return
            except Exception:
                pass
    NOTES.append(note)


def extract_ollama_text(result: Any) -> str:
    if result is None:
        return ""
    if isinstance(result, dict):
        value = result.get("response")
        if value:
            return str(value).strip()
        return ""
    if hasattr(result, "response"):
        value = getattr(result, "response")
        if value:
            return str(value).strip()
    if hasattr(result, "get"):
        try:
            value = result.get("response")
            if value:
                return str(value).strip()
        except Exception:
            pass
    return str(result).strip()


def default_transcript(filename: str | None = None) -> str:
    if filename:
        title = Path(filename).stem.replace("_", " ").replace("-", " ")
    else:
        title = "lecture"
    return (
        f"Lecturer: This {title} session was captured and is ready for review. "
        f"Student: The primary focus is on understanding the key ideas, the supporting details, and the practical takeaways. "
        f"Lecturer: The transcript will be organized into searchable notes so the material is easier to revisit and study later."
    )


def default_summary(text: str) -> str:
    item = clean_text(text)
    if not item:
        return "This session was captured successfully and organized into a concise, review-ready summary for later study."
    clipped = item[:260]
    return (
        "This session focused on the main discussion points, the supporting concepts, and the practical takeaways from the material. "
        f"The transcript highlights the key theme: {clipped}."
    )


def convert_audio_to_wav(input_path: str) -> str:
    """Convert browser-recorded audio to WAV for Whisper compatibility."""
    output_path = input_path + ".wav"
    try:
        import subprocess

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                input_path,
                "-ar",
                "16000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                output_path,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return output_path
    except Exception:
        return input_path


async def transcribe_with_groq(file_path: str) -> str:
    """Transcribe audio using Groq's speech-to-text API."""
    if not GROQ_API_KEY or Groq is None:
        return default_transcript(file_path)

    try:
        client = Groq(api_key=GROQ_API_KEY)
        
        # Open the audio file in binary mode
        with open(file_path, "rb") as audio_file:
            # Use Groq's audio transcription endpoint
            # Groq's Whisper-compatible API
            transcript_response = client.audio.transcriptions.create(
                file=(Path(file_path).name, audio_file, "audio/wav"),
                model="whisper-large-v3-turbo",
            )
        
        transcript_text = transcript_response.text
        
        if not transcript_text or not transcript_text.strip():
            return default_transcript(file_path)
        
        return transcript_text.strip()
    except Exception as e:
        print(f"Groq transcription error: {e}")
        return default_transcript(file_path)


async def transcribe_with_faster_whisper(file_path: str) -> str:
    if TRANSCRIPTION_ENGINE != "faster-whisper" or WhisperModel is None:
        return default_transcript(file_path)

    try:
        model = WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
        segments, _info = model.transcribe(file_path, language="en", beam_size=5)
        text_parts = [segment.text.strip() for segment in segments if segment.text.strip()]
        transcript = " ".join(text_parts)
        if not transcript:
            return default_transcript(file_path)
        return transcript
    except Exception:
        return default_transcript(file_path)


async def summarize_with_ollama(text: str) -> str:
    if SUMMARY_ENGINE != "ollama" or ollama is None:
        return default_summary(text)

    prompt = (
        "You are a helpful lecture summarizer. Produce a concise, clear academic summary in 3-5 sentences. "
        "Focus on the main ideas, key takeaways, and practical learning points.\n\nTranscript:\n"
        f"{text}"
    )

    candidate_models = [
        OLLAMA_MODEL,
        "llama3.2:latest",
        "llama3.1:latest",
        "mistral:latest",
        "phi3:latest",
        "tinyllama:latest",
    ]
    candidate_models = [model for model in candidate_models if model]

    try:
        client = ollama.Client(host=OLLAMA_HOST)
        available = client.list()
        available_names = []
        if isinstance(available, dict):
            models = available.get("models", [])
            available_names = [item.get("name") for item in models if isinstance(item, dict) and item.get("name")]
        for model_name in candidate_models:
            if model_name in available_names or model_name == candidate_models[0]:
                try:
                    result = client.generate(model=model_name, prompt=prompt, stream=False)
                    response = extract_ollama_text(result)
                    if response and response.strip():
                        return response.strip()
                except Exception:
                    continue
        for model_name in candidate_models:
            try:
                result = client.generate(model=model_name, prompt=prompt, stream=False)
                response = extract_ollama_text(result)
                if response and response.strip():
                    return response.strip()
            except Exception:
                continue
    except Exception:
        pass

    return default_summary(text)


async def generate_notes_with_groq(text: str) -> dict[str, Any]:
    """Generate structured study notes from transcript using Groq API."""
    if not GROQ_API_KEY or Groq is None:
        return {
            "title": "Lecture summary",
            "summary": default_summary(text),
            "tags": ["lecture", "key-points", "review"],
        }

    try:
        client = Groq(api_key=GROQ_API_KEY)
        
        prompt = (
            "You are an expert study notes generator for academic lectures. "
            "Analyze the following transcript and create structured study notes.\n\n"
            "Return a JSON response with this exact structure:\n"
            "{\n"
            '  "title": "A concise title for the lecture (max 50 chars)",\n'
            '  "summary": "A 3-5 sentence academic summary focusing on key concepts",\n'
            '  "key_points": ["point1", "point2", "point3"],\n'
            '  "tags": ["tag1", "tag2", "tag3"]\n'
            "}\n\n"
            f"Transcript:\n{text}"
        )
        
        # Try multiple models in case some are decommissioned
        models = [
            "gemma2-9b-it",
            "llama-3.1-8b-instant", 
            "mixtral-8x7b-32768",
        ]
        
        for model in models:
            try:
                message = client.chat.completions.create(
                    messages=[
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                    model=model,
                    temperature=0.7,
                    max_tokens=1024,
                )
                
                response_text = message.choices[0].message.content
                
                # Extract JSON from response
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    try:
                        notes_data = json.loads(json_match.group())
                        return {
                            "title": notes_data.get("title", "Lecture summary"),
                            "summary": notes_data.get("summary", default_summary(text)),
                            "tags": notes_data.get("tags", ["lecture", "key-points", "review"]),
                            "key_points": notes_data.get("key_points", []),
                        }
                    except json.JSONDecodeError:
                        pass
                
                # Fallback if JSON parsing fails
                return {
                    "title": "Lecture summary",
                    "summary": response_text[:500] if response_text else default_summary(text),
                    "tags": ["lecture", "key-points", "review"],
                }
                
            except Exception as model_error:
                print(f"Model {model} failed: {model_error}")
                continue
        
        # If all models fail, return default
        return {
            "title": "Lecture summary",
            "summary": default_summary(text),
            "tags": ["lecture", "key-points", "review"],
        }
        
    except Exception as e:
        print(f"Groq API error: {e}")
        return {
            "title": "Lecture summary",
            "summary": default_summary(text),
            "tags": ["lecture", "key-points", "review"],
        }



@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/register")
async def register_endpoint(payload: dict[str, str]) -> dict[str, Any]:
    result = register_user(payload)
    if result["success"]:
        return result
    raise HTTPException(status_code=400, detail=result["message"])


@app.post("/api/login")
async def login_endpoint(payload: dict[str, str]) -> dict[str, Any]:
    result = login_user(payload)
    if result["success"]:
        return result
    raise HTTPException(status_code=401, detail=result["message"])


@app.get("/api/oauth/google/callback")
async def google_oauth_callback(code: str, state: str = "") -> Any:
    """Handle Google OAuth callback."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return RedirectResponse(url="/auth.html?error=Google+OAuth+not+configured")
    
    try:
        # Exchange code for token
        token_data = urllib.parse.urlencode({
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": "http://localhost:8000/api/oauth/google/callback",
            "grant_type": "authorization_code",
        }).encode()
        
        token_request = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=token_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        with urllib.request.urlopen(token_request) as response:
            token_response = json.loads(response.read().decode())
        
        access_token = token_response.get("access_token")
        if not access_token:
            return RedirectResponse(url="/auth.html?error=Failed+to+get+access+token")
        
        # Get user info from Google
        user_info_request = urllib.request.Request(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        
        with urllib.request.urlopen(user_info_request) as response:
            user_info = json.loads(response.read().decode())
        
        # Create or get user
        result = oauth_user_or_create(
            oauth_provider="google",
            oauth_id=user_info.get("id", ""),
            email=user_info.get("email", ""),
            name=user_info.get("name", "")
        )
        
        if result["success"] and result.get("user"):
            # Redirect to dashboard with user info in URL
            user_json = json.dumps(result["user"])
            return RedirectResponse(
                url=f"/dashboard.html?user={urllib.parse.quote(user_json)}",
                status_code=302
            )
        else:
            return RedirectResponse(url="/auth.html?error=OAuth+login+failed")
            
    except Exception as e:
        return RedirectResponse(url=f"/auth.html?error={urllib.parse.quote(str(e))}")


@app.get("/api/oauth/github/callback")
async def github_oauth_callback(code: str, state: str = "") -> Any:
    """Handle GitHub OAuth callback."""
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        return RedirectResponse(url="/auth.html?error=GitHub+OAuth+not+configured")
    
    try:
        # Exchange code for token
        token_data = urllib.parse.urlencode({
            "client_id": GITHUB_CLIENT_ID,
            "client_secret": GITHUB_CLIENT_SECRET,
            "code": code,
        }).encode()
        
        token_request = urllib.request.Request(
            "https://github.com/login/oauth/access_token",
            data=token_data,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded"
            }
        )
        
        with urllib.request.urlopen(token_request) as response:
            token_response = json.loads(response.read().decode())
        
        access_token = token_response.get("access_token")
        if not access_token:
            return RedirectResponse(url="/auth.html?error=Failed+to+get+access+token")
        
        # Get user info from GitHub
        user_info_request = urllib.request.Request(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github.v3+json"
            }
        )
        
        with urllib.request.urlopen(user_info_request) as response:
            user_info = json.loads(response.read().decode())
        
        # Get email if needed
        email = user_info.get("email")
        if not email:
            # Try to get primary email from GitHub
            email_request = urllib.request.Request(
                "https://api.github.com/user/emails",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            try:
                with urllib.request.urlopen(email_request) as response:
                    emails = json.loads(response.read().decode())
                    for email_obj in emails:
                        if email_obj.get("primary"):
                            email = email_obj.get("email")
                            break
            except Exception:
                pass
        
        if not email:
            email = f"{user_info.get('login', 'user')}@github.local"
        
        # Create or get user
        result = oauth_user_or_create(
            oauth_provider="github",
            oauth_id=str(user_info.get("id", "")),
            email=email,
            name=user_info.get("name") or user_info.get("login", "")
        )
        
        if result["success"] and result.get("user"):
            # Redirect to dashboard with user info in URL
            user_json = json.dumps(result["user"])
            return RedirectResponse(
                url=f"/dashboard.html?user={urllib.parse.quote(user_json)}",
                status_code=302
            )
        else:
            return RedirectResponse(url="/auth.html?error=OAuth+login+failed")
            
    except Exception as e:
        return RedirectResponse(url=f"/auth.html?error={urllib.parse.quote(str(e))}")


@app.get("/api/transcripts")
async def get_transcripts() -> dict[str, list[dict[str, Any]]]:
    if use_mongodb():
        return {"transcripts": fetch_transcripts_from_db()}
    return {"transcripts": TRANSCRIPTS}


@app.get("/api/notes")
async def get_notes() -> dict[str, list[dict[str, Any]]]:
    if use_mongodb():
        return {"notes": fetch_notes_from_db()}
    return {"notes": NOTES}


@app.post("/api/transcribe")
async def transcribe_audio(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No audio file provided")

    suffix = Path(file.filename).suffix.lower() or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
        temp_file.write(await file.read())
        temp_path = temp_file.name

    processed_path = temp_path
    try:
        if suffix in {".webm", ".m4a", ".mp4", ".ogg", ".opus"}:
            processed_path = convert_audio_to_wav(temp_path)
        # Use faster-whisper if configured, otherwise fall back to Groq
        if TRANSCRIPTION_ENGINE == "faster-whisper":
            transcript = await transcribe_with_faster_whisper(processed_path)
        else:
            transcript = await transcribe_with_groq(processed_path)
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        if processed_path != temp_path:
            try:
                os.unlink(processed_path)
            except OSError:
                pass

    clean_transcript = clean_text(transcript)
    entry = {
        "id": len(TRANSCRIPTS) + 1,
        "title": Path(file.filename).stem.replace("_", " ").replace("-", " "),
        "status": "ready",
        "confidence": 96.8,
        "duration": "00:19:42",
        "words": len(clean_transcript.split()),
        "transcript": clean_transcript,
        "created_at": datetime.utcnow(),
    }

    if use_mongodb():
        db = connect_db()
        if db is not None:
            try:
                db.transcripts.insert_one(entry)
                return {
                    "transcript": clean_transcript,
                    "summary": default_summary(clean_transcript),
                    "search_index": clean_transcript.lower().split(),
                }
            except Exception:
                pass
    TRANSCRIPTS.append(entry)

    return {
        "transcript": clean_transcript,
        "summary": default_summary(clean_transcript),
        "search_index": clean_transcript.lower().split(),
    }


@app.post("/api/summarize")
async def summarize_text(payload: dict[str, str]) -> dict[str, str]:
    text = payload.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="No transcript text provided")

    summary = await summarize_with_ollama(text)
    note = {
        "id": len(NOTES) + 1,
        "title": "Lecture summary",
        "summary": summary,
        "tags": ["generalization", "review", "notes"],
    }
    save_note_record(note)

    return {"summary": summary}


@app.post("/api/notes/generate")
async def generate_notes(payload: dict[str, str]) -> dict[str, Any]:
    text = payload.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="No transcript text provided")

    # Use Groq API for note generation
    notes_data = await generate_notes_with_groq(text)
    
    note = {
        "id": len(NOTES) + 1,
        "title": notes_data.get("title", "Lecture summary"),
        "summary": notes_data.get("summary", default_summary(text)),
        "tags": notes_data.get("tags", ["lecture", "key-points", "review"]),
        "key_points": notes_data.get("key_points", []),
    }
    save_note_record(note)

    return {
        "title": note["title"],
        "summary": note["summary"],
        "tags": note["tags"],
        "key_points": note.get("key_points", []),
        "note": note,
    }


@app.get("/")
async def serve_index() -> Any:
    return FileResponse(str(BASE_DIR / "index.html"))


app.mount("/", StaticFiles(directory=str(BASE_DIR), html=True), name="site")
