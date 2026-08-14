import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { useAudioData, visualizeAudio } from "@remotion/media-utils";
import { resolveAsset } from "../lib/resolveAsset";

// Animated SVG cartoon host: audio-driven mouth, blinking, idle bob, gestures.
// Rendered as an overlay layer (Layer 3.5) between captions and audio.

type AvatarHostProps = {
  narrationSrc: string;
  size?: number;
  position?: "bottom-center" | "bottom-right";
  entrance?: { from?: number; duration?: number };
};

const TAU = Math.PI * 2;

const BLINK_EVERY_FRAMES = 150; // ~5s at 30fps
const BLINK_DURATION = 6;
const GESTURE_EVERY_FRAMES = 240; // ~8s
const GESTURE_DURATION = 45;

function val(f: number, phase: number, period: number): number {
  return Math.sin((f / period) * TAU + phase);
}

// SVG character, everything scaled by `s` (px).
// `mouth` 0..1 (open), `blink` 0..1 (0 = closed), `armRaise` 0..1.
const Character: React.FC<{
  s: number;
  mouth: number;
  blink: number;
  armRaise: number;
  bobY: number;
  tilt: number;
  accent: string;
}> = ({ s, mouth, blink, armRaise, bobY, tilt, accent }) => {
  const o = Math.max(0, 1 - blink); // eye openness

  return (
    <svg
      width={s}
      height={s * 1.05}
      viewBox="0 0 260 273"
      style={{ transform: `translateY(${bobY}px) rotate(${tilt}deg)` }}
    >
      {/* Shadow */}
      <ellipse cx="130" cy="262" rx="82" ry="10" fill="rgba(0,0,0,0.28)" />
      {/* Back arm */}
      <g>
        <g transform="rotate(-38 204 108)">
          <rect x="198" y="70" width="13" height="78" rx="6.5" fill="#BDC3CE" />
          <circle cx="204.5" cy="152" r="11" fill="#E2914D" />
        </g>
      </g>
      {/* Torso */}
      <rect x="72" y="112" width="116" height="112" rx="40" fill="#3B4252" />
      {/* Tech badge */}
      <rect x="102" y="140" width="56" height="26" rx="13" fill={accent} opacity="0.9" />
      <circle cx="116" cy="153" r="2.6" fill="#0B1220" />
      <rect x="124" y="149.5" width="26" height="4" rx="2" fill="#0B1220" />
      <rect x="124" y="156.5" width="18" height="4" rx="2" fill="#0B1220" />
      <rect x="124" y="163.5" width="22" height="4" rx="2" fill="#0B1220" />
      {/* Neck */}
      <rect x="116" y="94" width="28" height="26" rx="10" fill="#E2914D" />
      {/* Head */}
      <rect x="82" y="14" width="96" height="92" rx="40" fill="#F6C99C" />
      {/* Ears */}
      <rect x="70" y="46" width="10" height="22" rx="5" fill="#F6C99C" />
      <rect x="180" y="46" width="10" height="22" rx="5" fill="#F6C99C" />
      {/* Eyebrows */}
      <rect
        x="100"
        y="38"
        width="24"
        height="5"
        rx="2.5"
        fill="#4A3B2F"
        transform={`rotate(${-6 + armRaise * 4} 112 40)`}
      />
      <rect
        x="136"
        y="38"
        width="24"
        height="5"
        rx="2.5"
        fill="#4A3B2F"
        transform={`rotate(${6 - armRaise * 4} 148 40)`}
      />
      {/* Eyes */}
      <g>
        <ellipse cx="112" cy="58" rx="9.5" ry={9.5 * o} fill="#1E2A3A" />
        <circle
          cx="115"
          cy={58 - 3 * o + 1.4}
          r={2.6 * o}
          fill="#FFFFFF"
        />
      </g>
      <g>
        <ellipse cx="148" cy="58" rx="9.5" ry={9.5 * o} fill="#1E2A3A" />
        <circle
          cx="151"
          cy={58 - 3 * o + 1.4}
          r={2.6 * o}
          fill="#FFFFFF"
        />
      </g>
      {/* Mouth (driven by audio amplitude) */}
      <ellipse
        cx="130"
        cy={84 + (1 - mouth) * 2}
        rx={10 + mouth * 6}
        ry={2.5 + mouth * 9}
        fill="#8C5A3F"
      />
      {/* Front arm — raises periodically */}
      <g transform={`rotate(${-20 - armRaise * 70} 130 150)`}>
        <rect x="156" y="104" width="22" height="82" rx="11" fill="#5B6472" />
        <circle cx="167" cy="150" r="0" fill="none" />
        {armRaise > 0.01 && (
          <circle cx={167 - 44 * armRaise} cy={150 - 46 * armRaise} r="12" fill="rgba(255,255,255,0.16)" />
        )}
      </g>
      <circle cx="167" cy="190" r="13" fill="#F6C99C" />
      {/* Headphones (tech host look) */}
      <path
        d="M84 30 A52 40 0 0 1 176 30"
        fill="none"
        stroke="#E8D498"
        strokeWidth="8"
        strokeLinecap="round"
      />
      <rect x="66" y="40" width="20" height="48" rx="8" fill="#E8D498" />
      <rect x="174" y="40" width="20" height="48" rx="8" fill="#E8D498" />
      <rect x="60" y="34" width="10" height="16" rx="4" fill="#E8D498" />
      <rect x="190" y="34" width="10" height="16" rx="4" fill="#E8D498" />
    </svg>
  );
};

export const AvatarHost: React.FC<AvatarHostProps> = ({
  narrationSrc,
  size = 430,
  position = "bottom-center",
  entrance = { from: 36, duration: 22 },
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const audioData = useAudioData(resolveAsset(narrationSrc));

  // Entrance
  const enter = spring({
    frame: frame - (entrance.from ?? 36),
    fps,
    config: { damping: 17, stiffness: 110 },
  });
  const exitFrom = Math.max(0, durationInFrames - 15);
  const opacity = frame < exitFrom ? enter : enter * (1 - (frame - exitFrom) / 15);

  // Mouth: loudness-driven via visualizeAudio, smoothed
  let mouth = 0;
  if (audioData && frame > 0) {
    const samples = visualizeAudio({
      audioData,
      frame,
      fps,
      numberOfSamples: 32,
    });
    const avg =
      samples.reduce((a, b) => a + Math.max(0, b), 0) / Math.max(1, samples.length);
    mouth = interpolate(avg, [0, 0.055], [0.08, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  }

  // Blink cadence
  const blinkPhase = Math.floor(frame / BLINK_EVERY_FRAMES);
  const blinkLocal = frame - blinkPhase * BLINK_EVERY_FRAMES;
  const blinking = blinkLocal < BLINK_DURATION && blinkLocal >= 0;
  const blinkK = blinking
    ? Math.sin((blinkLocal / BLINK_DURATION) * Math.PI)
    : 0;

  // Gesture cadence (raise arm briefly)
  const gesturePhase = Math.floor(frame / GESTURE_EVERY_FRAMES);
  const gestureLocal = frame - gesturePhase * GESTURE_EVERY_FRAMES;
  const gestureK =
    gestureLocal < GESTURE_DURATION
      ? Math.sin((gestureLocal / GESTURE_DURATION) * Math.PI)
      : 0;

  // Idle bob + head bob with speech
  const bobY = Math.sin((frame / 34) * TAU) * 3 + mouth * 2.5;
  const tilt = Math.sin((frame / 47) * TAU) * 0.9 + mouth * 1.6;

  const computedMouth = Math.min(1, mouth + gestureK * 0.12);

  // AbsoluteFill is a column flex: justifyContent = vertical, alignItems = horizontal
  const vertical = "flex-end";
  const horizontal = position === "bottom-right" ? "flex-end" : "center";

  return (
    <AbsoluteFill
      style={{
        justifyContent: vertical,
        alignItems: horizontal,
        paddingBottom: 40,
        pointerEvents: "none",
      }}
    >
      <div style={{ opacity, transform: `scale(${enter})` }}>
        <Character
          s={size}
          mouth={computedMouth}
          blink={blinkK}
          armRaise={gestureK}
          bobY={bobY}
          tilt={tilt}
          accent="#F59E0B"
        />
      </div>
    </AbsoluteFill>
  );
};