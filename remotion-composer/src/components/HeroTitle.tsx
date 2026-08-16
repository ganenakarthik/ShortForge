import { AbsoluteFill } from "remotion";

// Instant hook frame — the mute-test first frame.
// The full hook text is visible and readable at frame 0, completely static:
// no char-by-char typing, no entrance wait. First words accented. This is
// exactly what the 5,000-Shorts study found: viral Shorts show big single
// line high-contrast text before 0.6s, and the eye reads stillness as death
// only AFTER 1.5s — an instantly-readable static hook frame is the win.

type HeroTitleProps = {
  title: string;
  subtitle?: string;
};

const EMPHASIS_WORD_LIMIT = 3;

export const HeroTitle: React.FC<HeroTitleProps> = ({ title, subtitle }) => {
  const words = title.split(/\s+/).filter(Boolean);

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        paddingBottom: 120,
        background:
          "radial-gradient(ellipse at center, rgba(15,23,42,0.35) 0%, rgba(15,23,42,0.55) 100%)",
      }}
    >
      <div style={{ textAlign: "center", maxWidth: "86%" }}>
        <div
          style={{
            fontSize: 88,
            fontWeight: 900,
            fontFamily: "Space Grotesk, Inter, system-ui, sans-serif",
            lineHeight: 1.16,
            letterSpacing: "0.01em",
            display: "flex",
            justifyContent: "center",
            flexWrap: "wrap",
            columnGap: "0.3em",
            textShadow: "0 6px 30px rgba(0,0,0,0.55)",
          }}
        >
          {words.map((word, wi) => {
            const accent = wi < EMPHASIS_WORD_LIMIT;
            return (
              <span
                key={wi}
                style={{
                  color: accent ? "#22D3EE" : "#FFFFFF",
                  textShadow: accent
                    ? "0 0 30px rgba(34,211,238,0.55)"
                    : undefined,
                }}
              >
                {word}
              </span>
            );
          })}
        </div>

        {subtitle && (
          <div
            style={{
              marginTop: 22,
              fontSize: 30,
              fontWeight: 600,
              color: "#A78BFA",
              fontFamily: "Space Grotesk, Inter, system-ui, sans-serif",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
            }}
          >
            {subtitle}
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};