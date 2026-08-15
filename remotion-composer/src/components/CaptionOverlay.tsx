import {
  AbsoluteFill,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

// Word-level caption for TikTok/Shorts-style highlight display
export interface WordCaption {
  word: string;
  startMs: number;
  endMs: number;
  emphasize?: boolean;
}

type CaptionOverlayProps = {
  words: WordCaption[];
  // How many words to show at once in a "page"
  wordsPerPage?: number;
  fontSize?: number;
  color?: string;
  highlightColor?: string;
  emphasisColor?: string;
  backgroundColor?: string;
  fontFamily?: string;
  paddingBottom?: number;
};

interface CaptionPage {
  words: WordCaption[];
  startMs: number;
  endMs: number;
}

// Connectors that open a new phrase. We break BEFORE these so phrases like
// "than the speed of light" or "over the moon" stay on one line.
const PHRASE_OPENERS = new Set([
  "and", "but", "or", "so", "because", "that", "which", "when", "while",
  "then", "than", "with", "from", "into", "before", "after", "if", "as",
  "the", "a", "an", "this", "these", "those", "it", "they", "we", "you",
]);

// Phrase-aware pagination: chunks of 2-4 words, breaking at punctuation or
// before phrase openers, never mid-phrase, never leaving a 1-word orphan.
function buildPages(words: WordCaption[], maxChunk: number): CaptionPage[] {
  const pages: CaptionPage[] = [];
  let cur: WordCaption[] = [];
  const flush = () => {
    if (cur.length === 0) return;
    // avoid a 1-word orphan: steal a word from the previous page
    if (cur.length === 1 && pages.length > 0) {
      const prev = pages[pages.length - 1];
      if (prev.words.length < maxChunk + 1) {
        prev.words.push(cur[0]);
        cur = [];
      }
    }
    if (cur.length) {
      pages.push({
        words: cur,
        startMs: cur[0].startMs,
        endMs: cur[cur.length - 1].endMs,
      });
      cur = [];
    }
  };

  for (let i = 0; i < words.length; i++) {
    const w = words[i];
    cur.push(w);
    const isPunct = /[.,!?;:]$/.test(w.word);
    const next = words[i + 1];
    const nextOpens = !!next && PHRASE_OPENERS.has(next.word.toLowerCase());
    const done = i === words.length - 1;
    if (done) {
      flush();
    } else if (isPunct && cur.length >= 2) {
      flush();
    } else if (nextOpens && cur.length >= 2 && cur.length <= maxChunk) {
      flush();
    } else if (cur.length >= maxChunk) {
      flush();
    }
  }
  return pages;
}

const PageRenderer: React.FC<{
  page: CaptionPage;
  fontSize: number;
  color: string;
  highlightColor: string;
  emphasisColor: string;
  fontFamily: string;
  paddingBottom: number;
}> = ({ page, fontSize, color, highlightColor, emphasisColor, fontFamily, paddingBottom }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const currentMs = page.startMs + (frame / fps) * 1000;

  // Pop entrance (pattern interrupt), MrBeast-style
  const entrance = spring({
    frame,
    fps,
    config: { damping: 12, stiffness: 170 },
  });
  const scale = interpolate(entrance, [0, 1], [0.86, 1]);
  const y = interpolate(entrance, [0, 1], [18, 0]);

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom,
      }}
    >
      <div
        style={{
          opacity: entrance,
          transform: `translateY(${y}px) scale(${scale})`,
          maxWidth: "88%",
          textAlign: "center",
          lineHeight: 1.22,
        }}
      >
        {page.words.map((w, i) => {
          const isActive = w.startMs <= currentMs && w.endMs > currentMs;
          const isPast = w.endMs <= currentMs;
          const isEmph = !!w.emphasize;
          const emphScale = isActive && isEmph ? 1.12 : 1;
          const activeColor = isEmph ? emphasisColor : highlightColor;
          const restColor = isEmph ? emphasisColor : color;
          return (
            <span
              key={`${w.startMs}-${i}`}
              style={{
                color: isActive ? activeColor : isPast ? restColor : `${restColor}88`,
                transform: `scale(${emphScale})`,
                display: "inline-block",
                fontFamily,
                fontWeight: 800,
                fontSize,
                marginRight: "0.22em",
                letterSpacing: "0.02em",
                // Heavy black stroke keeps it readable over any footage
                WebkitTextStroke: "10px rgba(0,0,0,0.9)",
                paintOrder: "stroke fill",
                textShadow:
                  isActive && isEmph
                    ? `0 0 26px ${emphasisColor}66, 0 4px 10px rgba(0,0,0,0.55)`
                    : "0 4px 10px rgba(0,0,0,0.55)",
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

export const CaptionOverlay: React.FC<CaptionOverlayProps> = ({
  words,
  wordsPerPage = 4,
  fontSize = 60,
  color = "#FFFFFF",
  highlightColor = "#22D3EE",
  emphasisColor = "#FACC15",
  fontFamily = "Space Grotesk, Inter, system-ui, sans-serif",
  paddingBottom = 300,
}) => {
  const { fps } = useVideoConfig();
  const pages = buildPages(words, wordsPerPage);

  return (
    <AbsoluteFill>
      {pages.map((page, i) => {
        const fromFrame = Math.round((page.startMs / 1000) * fps);
        const nextStart = pages[i + 1]?.startMs ?? page.endMs + 500;
        const duration = Math.max(
          1,
          Math.round(((nextStart - page.startMs) / 1000) * fps)
        );

        return (
          <Sequence key={i} from={fromFrame} durationInFrames={duration}>
            <PageRenderer
              page={page}
              fontSize={fontSize}
              color={color}
              highlightColor={highlightColor}
              emphasisColor={emphasisColor}
              fontFamily={fontFamily}
              paddingBottom={paddingBottom}
            />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};