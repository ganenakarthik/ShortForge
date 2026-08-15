import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

type HeroTitleProps = {
  title: string;
  subtitle?: string;
};

const EMPHASIS_WORD_LIMIT = 3;

export const HeroTitle: React.FC<HeroTitleProps> = ({ title, subtitle }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

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
        {/* Main title, word-safe (letters never break mid-word), first words accented */}
        <div
          style={{
            fontSize: 88,
            fontWeight: 800,
            fontFamily: "Space Grotesk, Inter, system-ui, sans-serif",
            lineHeight: 1.18,
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
                  display: "inline-flex",
                }}
              >
                {word.split("").map((char, ci) => {
                  const delay = (wi * 6 + ci) * 1.1;
                  const cs = spring({
                    frame: frame - delay,
                    fps,
                    config: { damping: 12, stiffness: 150 },
                  });
                  return (
                    <span
                      key={ci}
                      style={{
                        display: "inline-block",
                        opacity: cs,
                        transform: `translateY(${interpolate(cs, [0, 1], [34, 0])}px)`,
                        textShadow: accent
                          ? `0 0 30px rgba(34,211,238,0.55)`
                          : undefined,
                      }}
                    >
                      {char}
                    </span>
                  );
                })}
              </span>
            );
          })}
        </div>

        {/* Subtitle */}
        {subtitle && (
          <div
            style={{
              marginTop: 22,
              opacity: spring({
                frame: frame - words.length * 6 * 1.1 - 5,
                fps,
                config: { damping: 20 },
              }),
              fontSize: 30,
              fontWeight: 400,
              color: "#A78BFA",
              fontFamily: "Space Grotesk, Inter, system-ui, sans-serif",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
            }}
          >
            {subtitle}
          </div>
        )}

        {/* Animated underline */}
        <div
          style={{
            margin: "26px auto 0",
            height: 3,
            backgroundColor: "#22D3EE",
            borderRadius: 2,
            width: interpolate(
              spring({
                frame: frame - 15,
                fps,
                config: { damping: 15, stiffness: 60 },
              }),
              [0, 1],
              [0, 420]
            ),
          }}
        />
      </div>
    </AbsoluteFill>
  );
};