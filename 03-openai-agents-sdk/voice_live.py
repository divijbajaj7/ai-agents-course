"""Live microphone demo for the voice concierge.

    pip install -r requirements.txt sounddevice
    python3 voice_live.py              # speak for 6 seconds after the beep
    python3 voice_live.py --file q.wav # or feed a recorded WAV instead of the mic

Records from the default mic, runs the same VoicePipeline as notebook 03, and plays the
reply through the speakers. Keys are read from week11/.env.
"""
import argparse
import asyncio
import json
import sys
import wave
from pathlib import Path

import numpy as np

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from agents import Agent, function_tool
from agents.voice import (AudioInput, SingleAgentVoiceWorkflow, TTSModelSettings,
                          VoicePipeline, VoicePipelineConfig)

RATE = 24_000
FLIGHTS = [
    {"id": "6E-512", "from": "BLR", "to": "GOI", "date": "2026-10-02", "depart": "07:10", "airline": "IndiGo", "price_inr": 4180},
    {"id": "AI-887", "from": "BLR", "to": "GOI", "date": "2026-10-02", "depart": "13:45", "airline": "Air India", "price_inr": 5620},
    {"id": "QP-1375", "from": "BLR", "to": "GOI", "date": "2026-10-02", "depart": "18:30", "airline": "Akasa Air", "price_inr": 3890},
]


@function_tool
def search_flights(origin: str, destination: str, date: str) -> str:
    """Search flights between two airports (IATA codes) on a date (YYYY-MM-DD), cheapest first."""
    hits = sorted((f for f in FLIGHTS if f["from"] == origin.upper() and f["to"] == destination.upper()
                   and f["date"] == date), key=lambda f: f["price_inr"])
    return json.dumps(hits) if hits else "No flights found."


AGENT = Agent(
    name="Voice Concierge",
    model="gpt-4.1-mini",
    tools=[search_flights],
    instructions=("You are a travel concierge on a phone call. The year is 2026. Always search before "
                  "quoting. At most two short sentences. No lists, markdown or symbols. Say prices and "
                  "times the way a person would speak them."),
)


def record(seconds: float) -> np.ndarray:
    import sounddevice as sd
    print(f"Recording {seconds:.0f}s — speak now...")
    audio = sd.rec(int(seconds * RATE), samplerate=RATE, channels=1, dtype="int16")
    sd.wait()
    return audio.reshape(-1)


def load_wav(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            sys.exit("Need a mono 16-bit WAV.")
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16), w.getframerate()


async def main(args):
    if args.file:
        pcm, rate = load_wav(args.file)
    else:
        pcm, rate = record(args.seconds), RATE

    pipeline = VoicePipeline(workflow=SingleAgentVoiceWorkflow(AGENT),
                             config=VoicePipelineConfig(tts_settings=TTSModelSettings(voice="nova"),
                                                        tracing_disabled=True))
    result = await pipeline.run(AudioInput(buffer=pcm, frame_rate=rate))
    chunks = [e.data async for e in result.stream() if e.type == "voice_stream_event_audio"]
    reply = np.concatenate(chunks).astype(np.int16)

    out = Path(args.out)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(reply.tobytes())
    print(f"Reply: {len(reply) / RATE:.1f}s -> {out}")

    if not args.no_play:
        try:
            import sounddevice as sd
            sd.play(reply, RATE); sd.wait()
        except Exception as exc:   # no audio device (e.g. a server): the WAV is still saved
            print(f"(couldn't play audio: {exc})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="use a recorded mono 16-bit WAV instead of the mic")
    ap.add_argument("--seconds", type=float, default=6)
    ap.add_argument("--out", default="reply.wav")
    ap.add_argument("--no-play", action="store_true")
    asyncio.run(main(ap.parse_args()))
