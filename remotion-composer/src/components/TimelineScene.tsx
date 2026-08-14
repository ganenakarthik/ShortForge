import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

interface Milestone {
  label: string;
  sub?: string;
  color?: string;
}

export type { Milestone };

interface TimelineSceneProps {
  title?: string;
  milestones: Milestone[];
  accentColor?: string;
  backgroundColor?: string;
  textColor?: string;
}

/**
 * Horizontal animated timeline: line draws left->right, milestone dots pop in
 * sequence, labels fade up. Timing is spread evenly across the scene duration
 * so it reads as a story beat, not a static chart.
 */
export const TimelineScene: React.FC<TimelineSceneProps> = ({
  title,
  milestones,
  accentColor = "#22D3EE",
  backgroundColor = "rgba(15, 23, 42, 0.88)",
  textColor = "#F8FAFC",
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const startFade = Math.min(14, Math.max(6, durationInFrames * 0.12));
  const titleOpacity = interpolate(frame, [0, startFade], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const lineProgress = interpolate(
    frame,
    [startFade, Math.max(startFade + 6, durationInFrames * 0.4)],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return (
    <AbsoluteFill
      style={{
        background: backgroundColor,
        justifyContent: "center",
        alignItems: "center",
        padding: "70px 90px",
        fontFamily: "Space Grotesk, Inter, sans-serif",
      }}
    >
      {title && (
        <div
          style={{
            position: "absolute",
            top: 110,
            fontSize: 46,
            fontWeight: 700,
            color: textColor,
            opacity: titleOpacity,
            textAlign: "center",
            width: "100%",
            padding: "0 80px",
          }}
        >
          {title}
        </div>
      )}

      <div style={{ width: "100%", maxWidth: 900 }}>
        {/* track */}
        <div
          style={{
            position: "relative",
            height: 8,
            borderRadius: 4,
            background: "rgba(148,163,184,0.25)",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              position: "absolute",
              inset: 0,
              width: `${lineProgress * 100}%`,
              background: `linear-gradient(90deg, ${accentColor}88, ${accentColor})`,
              borderRadius: 4,
            }}
          />
        </div>

        {/* milestones */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            marginTop: 18,
          }}
        >
          {milestones.map((m, i) => {
            const appear = Math.round(
              startFade + (i / Math.max(1, milestones.length - 1)) * (durationInFrames - startFade) * 0.55
            );
            const inFrame = frame >= appear;
            const pop = spring({
              frame: Math.max(0, frame - appear),
              fps,
              config: { damping: 11, stiffness: 130 },
            });
            const color = m.color || (i % 2 === 0 ? accentColor : "#F59E0B");
            const labelOpacity = interpolate(frame, [appear, appear + 8], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            return (
              <div
                key={i}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  width: "22%",
                  opacity: inFrame ? 1 : 0.25,
                }}
              >
                <div
                  style={{
                    width: 26,
                    height: 26,
                    borderRadius: 13,
                    background: color,
                    transform: `scale(${pop})`,
                    boxShadow: `0 0 18px ${color}66`,
                    border: "3px solid rgba(255,255,255,0.85)",
                  }}
                />
                <div
                  style={{
                    marginTop: 14,
                    fontSize: 30,
                    fontWeight: 700,
                    color: textColor,
                    textAlign: "center",
                    opacity: labelOpacity,
                    lineHeight: 1.25,
                  }}
                >
                  {m.label}
                </div>
                {m.sub && (
                  <div
                    style={{
                      marginTop: 6,
                      fontSize: 22,
                      color: `${textColor}aa`,
                      textAlign: "center",
                      opacity: labelOpacity,
                      lineHeight: 1.3,
                    }}
                  >
                    {m.sub}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};
