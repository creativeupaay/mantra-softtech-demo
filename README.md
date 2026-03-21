# Mantra Softech Voice Agent

A Pipecat-powered RAG voice agent that answers questions about Mantra Softech, a global leader in biometric security.

## Features

-   **Knowledge-Aware**: Uses RAG (Retrieval-Augmented Generation) to search internal company documents for accurate answers.
-   **Sales-Driven**: Naturally transitions factual queries into consultation bookings.
-   **Consultation Booking**: Built-in conversational flow to capture potential leads' names, availability, and contact details.
-   **Multi-Voice Support**: Optimized for natural, helpful voice interactions.

## Technical Specifications

-   **Transport**: SmallWebRTC (Web-based voice)
-   **Speech-to-Text (STT)**: Deepgram (nova-3 model)
-   **Large Language Model (LLM)**: Google Gemini
-   **Text-to-Speech (TTS)**: Cartesia (optimized for speed and quality)
-   **Framework**: [Pipecat AI](https://docs.pipecat.ai/)

## Setup

### Server

1. **Navigate to server directory**:

   ```bash
   cd server
   ```

2. **Install dependencies**:

   ```bash
   uv sync
   ```

3. **Configure environment variables**:

   ```bash
   cp .env.example .env
   # Edit .env and add your API keys:
   # DEEPGRAM_API_KEY, GOOGLE_API_KEY, CARTESIA_API_KEY, etc.
   ```

4. **Run the bot**:

   ```bash
   uv run bot.py
   ```

### Client (Web UI)

1. **Navigate to client directory**:

   ```bash
   cd client
   ```

2. **Install dependencies**:

   ```bash
   npm install
   ```

3. **Configure environment variables**:

   ```bash
   cp env.example .env.local
   # Edit .env.local to point to your bot server:
   # VITE_BOT_START_URL=http://localhost:7860/start
   ```

   > **Note:** Environment variables in Vite are bundled into the client and exposed in the browser. For production applications that require secret protection, consider implementing a backend proxy server to handle API requests and manage sensitive credentials securely.

4. **Run development server**:

   ```bash
   npm run dev
   ```

5. **Open browser**:
   Visit `http://localhost:5173` to start the voice interaction.

## Project Structure

```
mantra-tec-voice-agent/
├── server/              # Python RAG bot server
│   ├── bot.py           # Main Pipecat implementation
│   ├── knowledge/       # Knowledge base source documents
│   ├── tools.py         # Search & retrieval logic
│   ├── pyproject.toml   # uv dependencies
│   └── ...
├── client/              # React/Vite application
│   ├── src/             # Frontend source code
│   ├── package.json     # Node dependencies
│   └── ...
├── .gitignore           # Root-level ignore rules
└── README.md            # This file
```

## Learn More

- [Pipecat Documentation](https://docs.pipecat.ai/)
- [Voice UI Kit](https://voiceuikit.pipecat.ai/)
- [Daily.co](https://www.daily.co/)