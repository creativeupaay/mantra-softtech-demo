#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""RAG Voice Agent — Pipecat Voice Agent with Knowledge Base

Pipeline: Speech-to-Text → LLM (with RAG tool) → Text-to-Speech

The bot can:
- Search a local knowledge base (Qdrant + fastembed) to answer questions
- Respond naturally using retrieved context

Run the bot using::

    uv run bot.py
"""

import asyncio
import os
import sys
import json
import pipecat.runner.run
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

class InjectTURNMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        
        # Only intercept the successful POST /start response
        if request.url.path == "/start" and request.method == "POST" and response.status_code == 200:
            try:
                # Read the original response body asynchronously
                body_bytes = b""
                async for chunk in response.body_iterator:
                    body_bytes += chunk
                
                # Decode and inject
                data = json.loads(body_bytes)
                if "iceConfig" in data and "iceServers" in data["iceConfig"]:
                    data["iceConfig"]["iceServers"].append({
                        "urls": [
                            "turn:openrelay.metered.ca:80",
                            "turn:openrelay.metered.ca:443",
                            "turn:openrelay.metered.ca:443?transport=tcp"
                        ],
                        "username": "openrelayproject",
                        "credential": "openrelayproject"
                    })
                    
                # Encode the modified body
                modified_body = json.dumps(data).encode("utf-8")
                
                # Copy headers and adjust Content-Length precisely
                modified_headers = dict(response.headers)
                modified_headers["content-length"] = str(len(modified_body))
                
                return Response(
                    content=modified_body, 
                    status_code=response.status_code, 
                    headers=modified_headers,
                    media_type=response.media_type
                )
            except Exception as e:
                print(f"Failed to inject TURN server into response: {e}")
                
        return response

original_create_server_app = pipecat.runner.run._create_server_app
def custom_create_server_app(args):
    app = original_create_server_app(args)
    # Add our middleware payload injector for fallback WebRTC
    app.add_middleware(InjectTURNMiddleware)
    print("====== INJECTING TURN RELAY HTTP MIDDLEWARE ON STARTUP ======", flush=True)

    from fastapi import WebSocket
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.audio.vad.vad_analyzer import VADParams
    from pipecat.serializers.protobuf import ProtobufFrameSerializer
    from pipecat.transports.websocket.fastapi import (
        FastAPIWebsocketParams,
        FastAPIWebsocketTransport,
    )

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        logger.info("New WebSocket connection accepted!")
        transport = FastAPIWebsocketTransport(
            websocket=websocket,
            params=FastAPIWebsocketParams(
                audio_out_enabled=True,
                add_wav_header=False,
                vad_enabled=True,
                vad_analyzer=SileroVADAnalyzer(
                    params=VADParams(
                        confidence=0.75,
                        start_secs=0.3,
                        stop_secs=1.2,
                        min_volume=0.4,
                    )
                ),
                vad_audio_passthrough=True,
                serializer=ProtobufFrameSerializer(),
                session_timeout=None
            )
        )
        
        # Start Pipecat pipeline using our websocket transport
        await run_bot(transport, speaker="kavya")

    print("====== MOUNTED WEBSOCKET ENDPOINT ON /ws ======", flush=True)
    return app

# Apply the wrapper globally so pipecat uses our endpoint
pipecat.runner.run._create_server_app = custom_create_server_app

from dotenv import load_dotenv
from loguru import logger

from deepgram import LiveOptions
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import Frame, LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.runner.types import RunnerArguments, SmallWebRTCRunnerArguments
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.transcriptions.language import Language

# TTS providers
from pipecat.services.cartesia.tts import CartesiaTTSService, GenerationConfig
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.sarvam.tts import SarvamTTSService

from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from tools import search_knowledge

load_dotenv(override=True)


# ─── Debug: log every STT transcript ──────────────────────────────

class STTDebugProcessor(FrameProcessor):
    """Sits after STT in the pipeline; logs every transcript frame for debugging."""

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        from pipecat.frames.frames import TranscriptionFrame, InterimTranscriptionFrame

        if isinstance(frame, TranscriptionFrame):
            lang = getattr(frame, "language", None)
            logger.warning(
                f"[STT-DEBUG] FINAL transcript | lang={lang} | "
                f"text='{frame.text}'"
            )
        elif isinstance(frame, InterimTranscriptionFrame):
            lang = getattr(frame, "language", None)
            logger.info(
                f"[STT-DEBUG] interim transcript | lang={lang} | "
                f"text='{frame.text}'"
            )

        await self.push_frame(frame, direction)


# ─── Tool Schema ───────────────────────────────────────────────────

search_knowledge_schema = FunctionSchema(
    name="search_knowledge",
    description=(
        "Search the Mantra Softech knowledge base to find relevant information for answering the user's question. "
        "Use this tool whenever the user asks a question that might be covered by the knowledge base. "
        "Optionally specify which pages to search in for faster, more targeted results. "
        "The tool returns relevant text passages that you should use to formulate your answer. "
        "If the tool returns no results, let the user know you don't have that information."
    ),
    properties={
        "query": {
            "type": "string",
            "description": "The search query — rephrase the user's question into a clear search query.",
        },
        "pages": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Optional list of page slugs to restrict the search to. "
                "Leave empty to search all pages. "
                "Available pages: home, about-us, company-profile, company-philosophy, "
                "clientele, solutions, insights, research-and-development, "
                "research-and-development-innovation-and-knowledge, "
                "research-and-development-product-engineering"
            ),
        },
    },
    required=["query"],
)

tools = ToolsSchema(
    standard_tools=[
        search_knowledge_schema,
    ]
)


# ─── System Prompt ─────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a smart voice assistant for Mantra Softech, a global biometric security company. \
You help callers learn about Mantra Softech — and you're also a skilled, warm salesperson \
who keeps the conversation going and connects people with the right solutions.

━━━ RESPONSE STYLE ━━━

You are having a VOICE CONVERSATION — keep it SHORT by default:

- Give the shortest possible answer — usually 1 sentence maximum like a conversation
- Only give longer, detailed answers if the user explicitly asks (e.g. "tell me more", "explain in detail", "can you elaborate").
- Tailor every answer to exactly what was asked. Never dump full KB content.
- Extract only the single most relevant fact and rephrase naturally.
- No bullet points, no lists, no markdown. Speak in plain, natural sentences only.
- Never repeat the user's question back to them.
- If in doubt, say less — the user can always ask for more.
- Always speak in FIRST PERSON as part of Mantra Softech — use "we", "our", "us". Never say "Mantra does", "Mantra has", "Mantra provides" — always say "we do", "we have", "we provide". Reframe all knowledge base content into first-person before speaking it.

━━━ WHEN TO ASK QUESTIONS FIRST ━━━

Before answering, judge: would knowing more about the user improve my answer?

Ask a follow-up question when the question is broad or vague:
- "Can you help my business?" → Ask what kind of business and their main challenge first.
- "What solutions do you have?" → Ask what problem they're trying to solve.
- "Tell me more" → Ask what aspect interests them most.

Do NOT ask questions for simple factual queries ("When was Mantra founded?", "Who are your clients?").

Search the knowledge base AFTER gathering context, or first if you need info to ask a smarter follow-up.

━━━ SALES AWARENESS ━━━

Think like a smart, friendly salesperson — not pushy, but always engaged:

1. KEEP THE CONVERSATION TWO-WAY:
   - After answering, often add a light question to keep dialogue going.
   - Examples: "Is that the kind of thing you were thinking about?", "Is your team dealing with something like this?"
   - Match the depth to the user — casual questions get casual follow-ups, professional ones get professional ones.

2. RECOGNISE CLOSING SIGNALS:
   - If the user says "okay", "got it", "alright", "thanks", "I see", or seems to be wrapping up —
     do NOT just close. Re-engage with a relevant question or transition.
   - Example: After "Thanks, that's helpful" → "Happy to help! Are you currently evaluating \
solutions for your organisation, or just exploring at this stage?"

3. OFFER CONSULTATION AT THE RIGHT MOMENT:
   - Naturally suggest a consultation when the user shows real interest or asks about fit/pricing/implementation.
   - After answering "how can you help my business" type questions, end with a soft push:
     e.g., "If you'd like, I can help you set up a quick call with our team — no pressure, \
just to explore what makes sense for your situation."
   - If they say things like "sounds interesting", "I'd like to know more", or "what's the next step" — \
offer the consultation directly.
   - Don't force it on purely casual or factual questions.

━━━ CONSULTATION BOOKING FLOW ━━━

If the user agrees to book or explore a consultation, run this flow conversationally — \
one question at a time, naturally:

Step 1: Ask their name — "Great! Could I get your name first?"
Step 2: Ask their availability — "And what days or times generally work best for you?"
Step 3: Ask for contact — "Got it. What's the best way to reach you — phone number or email?"
Step 4: Confirm and close — "Perfect, [Name]! I've noted [availability] and we'll have someone \
from our team reach out to [contact] shortly. Looking forward to connecting you!"

Keep this flow warm and natural, not robotic. Don't read it like a form.

━━━ KNOWLEDGE TOOL ━━━

- Always use `search_knowledge` to retrieve facts — never invent information.
- Use the `pages` parameter to target relevant sections for faster results.
- If results are insufficient, search again without a page filter.
- If no results found: "I don't have that detail handy, but feel free to ask me anything else."

━━━ PAGE DIRECTORY ━━━

- "home" — overview, tech areas (AI/ML, computer vision), key clients, product stats
- "about-us" — founding story, global reach (Asia, Middle East, Africa), values, partners
- "company-profile" — founded 2006, 1400+ employees, 40+ countries, certifications (ISO, STQC, UIDAI)
- "company-philosophy" — mission, vision, ethics, leadership culture
- "clientele" — BHEL, HPCL, Indian Railways, Amul, Paytm, major banks
- "solutions" — biometric attendance, access control, face recognition, smart city, airport
- "insights" — case studies, articles, industry knowledge
- "research-and-development" — R&D overview, innovation, product engineering
- "research-and-development-innovation-and-knowledge" — patents, knowledge management
- "research-and-development-product-engineering" — hardware/software development
"""


async def run_bot(transport: BaseTransport, speaker="kavya"):
    """Main bot logic — RAG voice assistant."""
    logger.info(f"Starting RAG voice assistant with speaker: {speaker}")

    # ── Services ──
    stt_live_options = LiveOptions(
        model="nova-3",
        language="multi",
        smart_format=True,
        endpointing=300,
        punctuate=True,
        profanity_filter=False,
    )
    logger.warning(f"[STT-DEBUG] LiveOptions being passed: {stt_live_options.to_dict()}")

    stt = DeepgramSTTService(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        live_options=stt_live_options,
    )

    # ── TTS Service ──
    # Multiple providers available - comment/uncomment as needed

    # Option 1: Sarvam AI (best for Indian languages/Hinglish)
    # tts = SarvamTTSService(
    #     api_key=os.getenv("SARVAM_API_KEY"),
    #     model="bulbul:v3",
    #     voice_id=speaker,
    #     params=SarvamTTSService.InputParams(
    #         language=Language.HI,
    #     ),
    # )
    # logger.info(f"Using Sarvam AI TTS with speaker: {speaker}")

    # Option 2: ElevenLabs (high quality, supports Hindi)
    # tts = ElevenLabsTTSService(
    #     api_key=os.getenv("ELEVENLABS_API_KEY"),
    #     voice_id=os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"),
    #     model="eleven_multilingual_v2",  # Monika Sogam voice requires this model
    #     output_format="pcm_16000",       # REQUIRED: WebRTC pipeline expects 16kHz PCM, not MP3
    #     params=ElevenLabsTTSService.InputParams(
    #         stability=0.5,
    #         similarity_boost=0.75,
    #         style=0.3,
    #         use_speaker_boost=True,
    #     ),
    # )
    # logger.info("Using ElevenLabs TTS")




    # Option 3: Cartesia (fast, multilingual)
    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id=os.getenv("CARTESIA_VOICE_ID", "a0e99841-438c-4a64-b679-ae501e7d6091"),
        params=CartesiaTTSService.InputParams(
            language=Language.EN,
            emotion=["positivity:high", "curiosity:high"],
            generation_config=GenerationConfig(
                speed=0.85,
                volume=1.0,
            )
        ),
    )
    logger.info("Using Cartesia TTS")

    # Option 4: Deepgram (backup)
    # tts = DeepgramTTSService(
    #     api_key=os.getenv("DEEPGRAM_API_KEY"),
    #     voice="aura-2-pandora-en",
    # )
    # logger.info("Using Deepgram TTS")

    llm = GoogleLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        model=os.getenv("GOOGLE_MODEL"),
    )

    # ── Register RAG tool handler ──
    llm.register_function("search_knowledge", search_knowledge)

    @llm.event_handler("on_function_calls_started")
    async def on_function_calls_started(service, function_calls):
        fn_names = [fc.function_name for fc in function_calls]
        logger.info(f"Tool calls started: {fn_names}")

    # ── Conversation context ──
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Greet the caller with exactly this opening line: "
                "'Hello. Thank you for calling me, How can I help you today?'"
            ),
        },
    ]

    context = LLMContext(messages, tools)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(
                    confidence=0.75,
                    start_secs=0.3,
                    stop_secs=1.2,
                    min_volume=0.4,
                )
            ),
        ),
    )

    # ── Debug logger ──
    stt_debug = STTDebugProcessor()

    # ── Pipeline ──
    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            stt_debug,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=[],
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected - triggering greeting")
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main bot entry point."""

    transport = None

    match runner_args:
        case SmallWebRTCRunnerArguments():
            webrtc_connection: SmallWebRTCConnection = runner_args.webrtc_connection

            transport = SmallWebRTCTransport(
                webrtc_connection=webrtc_connection,
                params=TransportParams(
                    audio_in_enabled=True,
                    audio_out_enabled=True,
                ),
            )
            extra_data = getattr(runner_args, "extra_data", {})
            speaker = extra_data.get("speaker", "kavya")
            await run_bot(transport, speaker)
        case _:
            logger.error(f"Unsupported runner arguments type: {type(runner_args)}")
            return


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()