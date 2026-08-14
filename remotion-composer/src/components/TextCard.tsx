import { AbsoluteFill, spring, useCurrentFrame, useVideoConfig } from "remotion";

interface TextCardProps {
  text: string;
  fontSize?: number;
  color?: string;
  backgroundColor?: string;
  accentColor?: string;
  emphasis?: string[];
}

function toWords(text: string): { word: string; ws: boolean }[] {
  const parts: { word: string; ws: boolean }[] = [];
  for (const m of text.matchAll(/\s+|[^\s]+/g)) {
    const tok = m[0];
    parts.push({ word: tok, ws: /^\s+$/.test(tok) });
  }
  return parts;
}

export const TextCard: React.FC<TextCardProps> = ({
  text,
  fontSize = 84,
  color = "#FFFFFF",
  backgroundColor = "rgba(15, 23, 42, 0.88)",
  accentColor = "#22D3EE",
  emphasis = [],
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const opacity = spring({ frame, fps, config: { damping: 20 } });
  const scale = spring({
    frame,
    fps,
    config: { damping: 15, stiffness: 100 },
    from: 0.95,
    to: 1,
  });

  const emph = new Set(emphasis.map((w) => w.toLowerCase().replace(/[.,!?]+$/, "")));
  const words = toWords(text);

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        background: backgroundColor,
        padding: 60,
      }}
    >
      <div
        style={{
          opacity,
          transform: `scale(${scale})`,
          fontSize,
          color,
          fontFamily: "Inter, system-ui, sans-serif",
          fontWeight: 800,
          textAlign: "center",
          maxWidth: "86%",
          lineHeight: 1.3,
          textShadow: "0 4px 24px rgba(0,0,0,0.6)",
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          gap: "0.18em",
        }}
      >
        {words.map((w, i) => {
          if (w.ws) return null;
          const key = w.word.toLowerCase().replace(/[.,!?]+$/, "");
          const isEmph = emph.has(key);
          return (
            <span
              key={i}
              style={{
                color: isEmph ? accentColor : color,
                textShadow: isEmph ? `0 0 26px ${accentColor}88` : undefined,
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
