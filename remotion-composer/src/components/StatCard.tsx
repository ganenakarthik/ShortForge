import { AbsoluteFill, spring, useCurrentFrame, useVideoConfig } from "remotion";

interface StatCardProps {
  stat: string;
  subtitle?: string;
  statFontSize?: number;
  subtitleFontSize?: number;
  color?: string;
  accentColor?: string;
  backgroundColor?: string;
}

export const StatCard: React.FC<StatCardProps> = ({
  stat,
  subtitle,
  statFontSize = 170,
  subtitleFontSize = 46,
  color = "#FFFFFF",
  accentColor = "#F59E0B",
  backgroundColor = "rgba(15, 23, 42, 0.88)",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const scale = spring({
    frame,
    fps,
    config: { damping: 12, stiffness: 120 },
    from: 0.8,
    to: 1,
  });

  const subtitleOpacity = spring({
    frame: frame - 8,
    fps,
    config: { damping: 20 },
  });

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        background: backgroundColor,
      }}
    >
      <div style={{ textAlign: "center" }}>
          <div
            style={{
              transform: `scale(${scale})`,
              fontSize: statFontSize,
              color: accentColor,
              fontFamily: "Inter, system-ui, sans-serif",
              fontWeight: 800,
              lineHeight: 1.1,
              textShadow: "0 4px 24px rgba(0,0,0,0.55)",
            }}
          >
            {stat}
          </div>
          {subtitle && (
            <div
              style={{
                opacity: subtitleOpacity,
                fontSize: subtitleFontSize,
                color,
                fontFamily: "Inter, system-ui, sans-serif",
                fontWeight: 700,
                marginTop: 20,
                textShadow: "0 2px 12px rgba(0,0,0,0.5)",
              }}
            >
            {subtitle}
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};
