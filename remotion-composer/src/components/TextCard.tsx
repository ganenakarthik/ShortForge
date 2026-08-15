import { AbsoluteFill, spring, useCurrentFrame, useVideoConfig } from "remotion";

interface TextCardProps {
  text: string;
  fontSize?: number;
  color?: string;
  backgroundColor?: string;
  accentColor?: string;
  emphasis?: string[];
}

// Balanced, controlled line breaks: max words per line, rebalanced so the last
// line never holds a single orphan word. Renders each line as its own centered
// block — no more ragged flex-wrap alignment.
function toLines(text: string, maxWordsPerLine: number): string[][] {
  const words = text.split(/\s+/).filter(Boolean);
  const lines: string[][] = [];
  for (let i = 0; i < words.length; i += maxWordsPerLine) {
    lines.push(words.slice(i, i + maxWordsPerLine));
  }
  // rebalance: if the last line has exactly 1 word, move one word from the
  // previous line to even it out
  if (lines.length > 1 && lines[lines.length - 1].length === 1) {
    const last = lines.pop()!;
    const prev = lines[lines.length - 1];
    prev.push(last[0]);
  }
  return lines;
}

function fitFontSize(text: string, base: number, maxLines: number): number {
  // longest word run in any line drives the width; shrink until it fits
  const words = text.split(/\s+/);
  const maxLineChars = Math.max(
    ...words
      .map((_, i, arr) => arr.slice(i, i + 7).join(" ").length)
      .filter((n, i, a) => i % 7 === 0 || a.length === 1)
  );
  const perLine = Math.ceil(words.length / maxLines);
  const longest = Math.max(maxLineChars, Math.max(...words.map((w) => w.length)));
  const cap = 1160; // px of width available at fontSize 1 inside an 84%-wide card
  return Math.max(34, Math.min(base, Math.floor(cap / longest)));
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
    from: 0.94,
    to: 1,
  });

  const emph = new Set(emphasis.map((w) => w.toLowerCase().replace(/[.,!?]+$/, "")));
  const size = fitFontSize(text, fontSize, 4);
  const lines = toLines(text, 7);

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        background: backgroundColor,
        padding: "180px 60px 320px",
      }}
    >
      <div
        style={{
          opacity,
          transform: `scale(${scale})`,
          fontFamily: "Inter, system-ui, sans-serif",
          fontWeight: 800,
          textAlign: "center",
          width: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
        }}
      >
        {lines.map((line, li) => (
          <div
            key={li}
            style={{
              fontSize: size,
              color,
              lineHeight: 1.18,
              letterSpacing: "0.01em",
              textShadow: "0 4px 24px rgba(0,0,0,0.6)",
              whiteSpace: "nowrap",
              margin: "0.04em 0",
            }}
          >
            {line.map((word, wi) => {
              const key = word.toLowerCase().replace(/[.,!?]+$/, "");
              const isEmph = emph.has(key);
              return (
                <span
                  key={wi}
                  style={{
                    color: isEmph ? accentColor : color,
                    textShadow: isEmph ? `0 0 26px ${accentColor}88` : undefined,
                    marginRight: "0.3em",
                  }}
                >
                  {word}
                </span>
              );
            })}
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};