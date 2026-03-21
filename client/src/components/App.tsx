import { useEffect } from 'react';

import type { PipecatBaseChildProps } from '@pipecat-ai/voice-ui-kit';
import {
  ConnectButton,
  ConversationPanel,
  EventsPanel,
  UserAudioControl,
} from '@pipecat-ai/voice-ui-kit';

import type { TransportType } from '../config';
import { TransportSelect } from './TransportSelect';

interface AppProps extends PipecatBaseChildProps {
  transportType: TransportType;
  onTransportChange: (type: TransportType) => void;
  availableTransports: TransportType[];
}

export const App = ({
  client,
  handleConnect,
  handleDisconnect,
  transportType,
  onTransportChange,
  availableTransports,
}: AppProps) => {
  useEffect(() => {
    if (!client) return;

    // Customize browser-level audio processing before device init.
    // - echoCancellation: ON — critical to prevent the bot from hearing its own
    //   TTS output through the speaker and triggering a feedback loop.
    // - noiseSuppression: ON — helps reject distant/background voices so only
    //   the primary (close-mic) speaker triggers VAD.
    // - autoGainControl: OFF — AGC is tuned for English phonemes and can
    //   distort Hindi/Hinglish speech; disabling it gives Deepgram cleaner audio.
    const originalGetUserMedia = navigator.mediaDevices.getUserMedia.bind(
      navigator.mediaDevices
    );
    navigator.mediaDevices.getUserMedia = async (constraints) => {
      if (constraints?.audio) {
        const audioBase =
          typeof constraints.audio === 'object' ? constraints.audio : {};
        constraints = {
          ...constraints,
          audio: {
            ...audioBase,
            noiseSuppression: false,
            echoCancellation: true,
            autoGainControl: false,
          },
        };
      }
      return originalGetUserMedia(constraints);
    };

    client.initDevices();
  }, [client]);

  const showTransportSelector = availableTransports.length > 1;

  return (
    <div className="flex flex-col w-full h-full">
      <div className="flex items-center justify-between gap-4 p-4">
        {showTransportSelector ? (
          <TransportSelect
            transportType={transportType}
            onTransportChange={onTransportChange}
            availableTransports={availableTransports}
          />
        ) : (
          <div /> /* Spacer */
        )}
        <div className="flex items-center gap-4">
          <UserAudioControl size="lg" />
          <ConnectButton
            size="lg"
            onConnect={handleConnect}
            onDisconnect={handleDisconnect}
          />
        </div>
      </div>
      <div className="flex-1 overflow-hidden px-4">
        <div className="h-full overflow-hidden">
          <ConversationPanel />
        </div>
      </div>
      <div className="h-96 overflow-hidden px-4 pb-4">
        <EventsPanel />
      </div>
    </div>
  );
};
