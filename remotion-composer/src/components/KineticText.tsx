import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

// Word-level kinetic typography — the winning Shorts format.
//
// The words ARE the video: big, centered, one word popping at a time exactly
// with the voice (captions LEAD the audio by leadMs), past words dim, keyword
// anchors (emphasize) pop in accent color + scale. Never more than
// maxVisibleWords on screen (1-2 lines). No cards, no boxes.
//
// `instant` mode (hook + loop frames): the full text is visible at frame 0,
// completely static — the mute-test frame. This is what makes the hook
// readable before the brain even decides to scroll.

export interface KineticWord {
  word: string;
  startMs: number;
  endMs: number;
  emphasize?: boolean;
}

type KineticTextProps = {
  words: KineticWord[];
  instant?: boolean;
  /** Absolute start time (ms) of this scene — words are timed on the global timeline. */
  startMs?: number;
  fontSize?: number;
  accentColor?: string;
  dimOpacity?: number;
  paddingBottom?: number;
  maxVisibleWords?: number;
  /** Captions lead the spoken word by this many ms. */
  leadMs?: number;
};

const DEFAULT_ACCENT = "#FACC15";

export const KineticText: React.FC<KineticTextProps> = ({
  words,
  instant = false,
  startMs = 0,
  fontSize = 82,
  accentColor = DEFAULT_ACCENT,
  dimOpacity = 0.42,
  paddingBottom = 280,
  maxVisibleWords = 12,
  leadMs = 150,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const nowMs = startMs + (frame / fps) * 1000;

  if (instant) {
    return (
      <AbsoluteFill
        style={{
          justifyContent: "center",
          alignItems: "center",
          paddingBottom,
        }}
      >
        <div
          style={{
            maxWidth: "88%",
            textAlign: "center",
            lineHeight: 1.18,
          }}
        >
          {words.map((w, i) => (
            <span
              key={i}
              style={{
                color: w.emphasize ? accentColor : "#FFFFFF",
                display: "inline-block",
                fontFamily: "Space Grotesk, Inter, system-ui, sans-serif",
                fontWeight: 900,
                fontSize,
                marginRight: "0.24em",
                letterSpacing: "0.01em",
                textShadow: w.emphasize
                  ? `0 0 30px ${accentColor}66, 0 4px 10px rgba(0,0,0,0.6)`
                  : "0 4px 10px rgba(0,0,0,0.6)",
                WebkitTextStroke: "8px rgba(0,0,0,0.85)",
                paintOrder: "stroke fill",
              }}
            >
              {w.word}
            </span>
          ))}
        </div>
      </AbsoluteFill>
    );
  }

  // Kinetic mode: show only the words that have been SPOKEN so far (leading
  // by leadMs), keep a rolling window, pop each word on activation.
  const visible: Array<{ w: KineticWord; i: number; pop: number }> = [];
  for (let i = 0; i < words.length; i++) {
    const w = words[i];
    const actMs = w.startMs - leadMs;
    if (actMs > nowMs) break; // words are time-ordered; stop at first future word
    const actFrame = Math.max(0, actMs / 1000) * fps;
    const pop = spring({
      frame: frame - actFrame,
      fps,
      config: { damping: 11, stiffness: 210 },
    });
    visible.push({ w, i, pop });
  }
  const windowed = visible.slice(-maxVisibleWords);

  let activeIdx = -1;
  for (let i = 0; i < words.length; i++) {
    const w = words[i];
    if (w.startMs - leadMs <= nowMs && w.endMs - leadMs > nowMs) {
      activeIdx = i;
      break;
    }
  }

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        paddingBottom,
      }}
    >
      <div
        style={{
          maxWidth: "88%",
          textAlign: "center",
          lineHeight: 1.18,
        }}
      >
        {windowed.map(({ w, i, pop }) => {
          const isActive = i === activeIdx;
          const emph = !!w.emphasize;
          const emphScale = isActive && emph ? 1.14 : 1;
          const scale = interpolate(pop, [0, 1], [0.82, 1]) * emphScale;
          const y = interpolate(pop, [0, 1], [14, 0]);
          // Words dim shortly after they finish speaking (read-along: only
          // the live word is full-bright; past words stay as a faint trail).
          const settledFrames = Math.max(
            0,
            frame - (Math.max(0, (w.endMs - leadMs) / 1000) * fps + 6)
          );
          const wordOpacity = isActive
            ? 1
            : interpolate(
                Math.min(1, settledFrames / 8),
                [0, 1],
                [1, dimOpacity]
              );
          return (
            <span
              key={`${i}-${w.word}`}
              style={{
                display: "inline-block",
                transform: `translateY(${y}px) scale(${scale})`,
                opacity: wordOpacity,
                color: isActive
                  ? emph
                    ? accentColor
                    : "#FFFFFF"
                  : emph
                  ? accentColor
                  : "#FFFFFF",
                fontFamily: "Space Grotesk, Inter, system-ui, sans-serif",
                fontWeight: 900,
                fontSize,
                marginRight: "0.24em",
                letterSpacing: "0.01em",
                textShadow: isActive && emph
                  ? `0 0 32px ${accentColor}77, 0 4px 10px rgba(0,0,0,0.6)`
                  : "0 4px 10px rgba(0,0,0,0.6)",
                WebkitTextStroke: "8px rgba(0,0,0,0.85)",
                paintOrder: "stroke fill",
                willChange: "transform, opacity",
              }}
            >
              {w.word}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};