import { StrictMode, useState, useMemo, useCallback } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';

import { ThemeProvider } from '@pipecat-ai/voice-ui-kit';
import { FullScreenContainer } from '@pipecat-ai/voice-ui-kit';

import { PipecatClient } from '@pipecat-ai/client-js';
import { PipecatClientProvider } from '@pipecat-ai/client-react';
import { WebSocketTransport, ProtobufFrameSerializer } from '@pipecat-ai/websocket-transport';

import { App as DefaultApp } from './components/App';
import { Home } from './pages/Home';
import { AVAILABLE_TRANSPORTS, DEFAULT_TRANSPORT } from './config';
import type { TransportType } from './config';
import './index.css';

export const Main = () => {
  const [transportType, setTransportType] = useState<TransportType>(DEFAULT_TRANSPORT);

  const voiceClient = useMemo(() => {
    // Determine the Websocket URL robustly, fallback to localhost:7860
    let urlString = import.meta.env.VITE_BOT_START_URL || 'http://localhost:7860/start';
    if (urlString.startsWith('/')) {
        urlString = window.location.origin + urlString;
    }
    const wsUrl = new URL(urlString);
    wsUrl.protocol = wsUrl.protocol === 'https:' ? 'wss:' : 'ws:';
    wsUrl.pathname = '/ws';

    const transport = new WebSocketTransport({
      wsUrl: wsUrl.toString(),
      serializer: new ProtobufFrameSerializer(),
    });

    return new PipecatClient({
      transport,
      enableMic: true,
      enableCam: false,
      callbacks: {
        onConnected: () => console.log('[Websocket] User Connected'),
        onDisconnected: () => console.log('[Websocket] User Disconnected'),
        onTransportStateChanged: (state: any) => console.log('[Websocket] Transport state:', state),
      },
    });
  }, []); // single client instance

  const handleConnect = useCallback(async () => {
    try {
      await voiceClient.connect();
    } catch (e) {
      console.error('Failed to connect:', e);
    }
  }, [voiceClient]);

  const handleDisconnect = useCallback(async () => {
    try {
      await voiceClient.disconnect();
    } catch (e) {
      console.error('Failed to disconnect:', e);
    }
  }, [voiceClient]);

  return (
    <ThemeProvider defaultTheme="terminal" disableStorage>
      <FullScreenContainer>
        <PipecatClientProvider client={voiceClient}>
            <BrowserRouter>
              <Routes>
                <Route
                  path="/default"
                  element={
                    <DefaultApp
                      client={voiceClient as any}
                      handleConnect={handleConnect}
                      handleDisconnect={handleDisconnect}
                      transportType={transportType}
                      onTransportChange={setTransportType}
                      availableTransports={AVAILABLE_TRANSPORTS}
                    />
                  }
                />
                <Route
                  path="/"
                  element={
                    <Home
                      client={voiceClient as any}
                      handleConnect={handleConnect}
                      handleDisconnect={handleDisconnect}
                    />
                  }
                />
              </Routes>
            </BrowserRouter>
        </PipecatClientProvider>
      </FullScreenContainer>
    </ThemeProvider>
  );
};

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Main />
  </StrictMode>
);
