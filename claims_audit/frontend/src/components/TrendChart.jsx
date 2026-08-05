import React from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

const ORANGE = "#f3781f";
const BLACK = "#1a1a1a";

/**
 * §6: "Trend/time-series views: flag rate, exposure, and volume over
 * time (weekly/monthly), not just static category snapshots."
 */
export default function TrendChart({ data }) {
  return (
    <div className="card">
      <h3 style={{ marginBottom: 16 }}>Flag Volume Over Time</h3>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data}>
          <XAxis dataKey="period" tick={{ fontSize: 11, fill: BLACK }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fontSize: 11, fill: BLACK }} axisLine={false} tickLine={false} />
          <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid #e6e6e6", fontSize: 12 }} />
          <Line
            type="monotone"
            dataKey="flagCount"
            stroke={ORANGE}
            strokeWidth={2.5}
            dot={{ r: 3, fill: ORANGE }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
