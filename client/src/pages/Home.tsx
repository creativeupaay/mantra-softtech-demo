import React from 'react';
import { usePipecatClientTransportState, usePipecatClientMicControl, VoiceVisualizer } from '@pipecat-ai/client-react';
import type { PipecatClient } from '@pipecat-ai/client-js';
import { SpinLoader } from '@pipecat-ai/voice-ui-kit';
import { Mic, MicOff, Phone, PhoneOff } from 'lucide-react';

interface HomeProps {
  client: PipecatClient;
  handleConnect?: () => void | Promise<void>;
  handleDisconnect?: () => void | Promise<void>;
}

export const Home: React.FC<HomeProps> = ({ handleConnect, handleDisconnect }) => {
  const transportState = usePipecatClientTransportState();
  const { isMicEnabled, enableMic } = usePipecatClientMicControl();

  const isConnected = transportState === 'connected' || transportState === 'ready';
  const isConnecting = transportState === 'connecting';

  return (
    <div className="flex flex-col items-center justify-between w-full h-full min-h-screen bg-gradient-to-b from-[#0a0a0a] via-[#0f1419] to-[#0a0a0a] text-white p-6 relative overflow-hidden">

      <div className="absolute inset-0 opacity-30 pointer-events-none">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-purple-500/20 rounded-full blur-3xl animate-[pulse_8s_ease-in-out_infinite]" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-cyan-500/20 rounded-full blur-3xl animate-[pulse_10s_ease-in-out_infinite]" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-gradient-radial from-pink-500/10 via-transparent to-transparent blur-2xl" />
      </div>

      {/* Subtle grid overlay */}
      <div className="absolute inset-0 opacity-[0.03] pointer-events-none bg-[linear-gradient(rgba(255,255,255,0.1)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.1)_1px,transparent_1px)] bg-[size:50px_50px]" />

      {/* Subtle mesh background to keep it from looking pure black */}
      <div className="absolute inset-0 opacity-20 pointer-events-none">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(120,119,198,0.15),transparent_70%)]" />
      </div>

      {/* Header */}
      <div className="w-full flex items-center justify-center pt-8 px-4 z-10 relative">
        <div className="text-[10px] tracking-[0.2em] uppercase text-zinc-400 font-medium absolute top-8">
          Creative Upaay
        </div>
      </div>

      {/* Main Center Area for Visualizer */}
      <div className="flex-1 w-full flex flex-col items-center justify-center relative z-10">

        {/* Agent Name above Orb */}
        <div className="absolute top-16 left-0 right-0 flex items-center justify-center z-10 pointer-events-none">
          <h2 className="text-2xl font-light text-white/90 tracking-wide text-center">Mantra Softtech Agent</h2>
        </div>

        {isConnected ? (
          <div className="relative flex items-center justify-center w-64 h-64 mt-10">
            {/* Glowing outer aura */}
            <div className="absolute inset-0 rounded-full bg-gradient-to-tr from-cyan-500/20 via-purple-500/20 to-pink-500/20 blur-3xl animate-[pulse_3s_ease-in-out_infinite]" />

            {/* Geometry Ring 1 (Spinning slowly clock-wise) */}
            <div className="absolute inset-2 mix-blend-screen opacity-60 bg-gradient-to-tr from-cyan-400 to-purple-500 animate-[spin_8s_linear_infinite]"
              style={{ borderRadius: '40% 60% 60% 40% / 40% 40% 60% 60%' }} />

            {/* Geometry Ring 2 (Spinning counter clock-wise) */}
            <div className="absolute inset-4 mix-blend-screen opacity-60 bg-gradient-to-bl from-pink-500 to-purple-400 animate-[spin_12s_linear_infinite_reverse]"
              style={{ borderRadius: '60% 40% 40% 60% / 60% 60% 40% 40%' }} />

            {/* Geometry Ring 3 */}
            <div className="absolute inset-6 mix-blend-screen opacity-50 bg-gradient-to-r from-blue-400 to-cyan-300 animate-[spin_10s_linear_infinite]"
              style={{ borderRadius: '50% 50% 30% 70% / 60% 40% 60% 40%' }} />

            {/* Inner Core that holds the actual pipecat visualizer */}
            <div className="absolute inset-10 rounded-full bg-[#09090b] shadow-[inset_0_0_30px_rgba(168,85,247,0.3)] z-10 flex items-center justify-center overflow-hidden border border-white/5 backdrop-blur-md">
              <div className="scale-90 opacity-90">
                <VoiceVisualizer
                  participantType="bot"
                  barColor="#fff"
                  backgroundColor="transparent"
                  barWidth={3}
                  barGap={3}
                  barCount={20}
                  barMaxHeight={60}
                />
              </div>
            </div>
          </div>
        ) : isConnecting ? (
          <div className="flex flex-col items-center gap-6 mt-10">
            <SpinLoader />
            <p className="text-zinc-500 text-sm tracking-wide">Connecting...</p>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-64 mt-10">
            {/* Kept totally empty until connected */}
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="w-full max-w-sm pb-12 flex items-center justify-center gap-6 z-10">
        {isConnected ? (
          <>
            <button
              onClick={() => enableMic(!isMicEnabled)}
              className={`w-14 h-14 rounded-full flex items-center justify-center backdrop-blur-xl transition-all shadow-lg ${isMicEnabled
                ? 'bg-zinc-800/80 text-white border border-zinc-700/50'
                : 'bg-white text-zinc-900 border border-white'
                }`}
            >
              {isMicEnabled ? <Mic className="w-5 h-5" strokeWidth={2} /> : <MicOff className="w-5 h-5" strokeWidth={2} />}
            </button>

            <button
              onClick={handleDisconnect}
              className="w-14 h-14 rounded-full flex items-center justify-center bg-red-500/90 hover:bg-red-500 text-white transition-all shadow-lg border border-red-400/20"
            >
              <PhoneOff className="w-5 h-5" strokeWidth={2} />
            </button>
          </>
        ) : (
          <button
            onClick={handleConnect}
            disabled={isConnecting}
            className="w-16 h-16 rounded-full flex items-center justify-center bg-emerald-500/90 hover:bg-emerald-500 text-white transition-all shadow-[0_0_30px_rgba(16,185,129,0.3)] hover:shadow-[0_0_40px_rgba(16,185,129,0.5)] border border-emerald-400/20 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Phone className="w-6 h-6" strokeWidth={2} />
          </button>
        )}
      </div>

      {/* Home indicator */}
      <div className="absolute bottom-2 left-1/2 -translate-x-1/2 w-32 h-1 bg-white/20 rounded-full z-10"></div>
    </div>
  );
};