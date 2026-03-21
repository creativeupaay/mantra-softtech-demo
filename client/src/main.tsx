import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';

import { ThemeProvider } from '@pipecat-ai/voice-ui-kit';

import type { PipecatBaseChildProps } from '@pipecat-ai/voice-ui-kit';
import {
  ErrorCard,
  FullScreenContainer,
  PipecatAppBase,
  SpinLoader,
} from '@pipecat-ai/voice-ui-kit';

import { App as DefaultApp } from './components/App';
import { Home } from './pages/Home';
import {
  AVAILABLE_TRANSPORTS,
  DEFAULT_TRANSPORT,
  TRANSPORT_CONFIG,
} from './config';
import type { TransportType } from './config';
import './index.css';

export const Main = () => {
  const [transportType, setTransportType] =
    useState<TransportType>(DEFAULT_TRANSPORT);

  const connectParams = TRANSPORT_CONFIG[transportType];

  return (
    <ThemeProvider defaultTheme="terminal" disableStorage>
      <FullScreenContainer>
        <PipecatAppBase
          connectParams={connectParams}
          transportType={transportType}>
          {({
            client,
            handleConnect,
            handleDisconnect,
            error,
          }: PipecatBaseChildProps) =>
            !client ? (
              <SpinLoader />
            ) : error ? (
              <ErrorCard>{error}</ErrorCard>
            ) : (
              <BrowserRouter>
                <Routes>
                  <Route 
                    path="/default" 
                    element={
                      <DefaultApp
                        client={client}
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
                        client={client}
                        handleConnect={handleConnect}
                        handleDisconnect={handleDisconnect}
                      />
                    } 
                  />
                </Routes>
              </BrowserRouter>
            )
          }
        </PipecatAppBase>
      </FullScreenContainer>
    </ThemeProvider>
  );
};

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Main />
  </StrictMode>
);
