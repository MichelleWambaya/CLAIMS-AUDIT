import React from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from "recharts";

const ORANGE = "#f3781f";
const BLACK = "#1a1a1a";

/**
 * Clicking a bar filters every other visual on the page (§6). The
 * currently-selected category is rendered in solid orange; everything
 * else dims to signal "this chart is filtered, click again to clear."
 */
export default function CategoryChart({ data, selectedCategory, onSelectCategory }) {
  return (
    <div className="card">
      <h3 style={{ marginBottom: 16 }}>Flags by Category</h3>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data} layout="vertical" margin={{ left: 24 }}>
          <XAxis type="number" tick={{ fontSize: 12, fill: BLACK }} axisLine={false} tickLine={false} />
          <YAxis
            type="category"
            dataKey="category"
            tick={{ fontSize: 12, fill: BLACK }}
            axisLine={false}
            tickLine={false}
            width={110}
          />
          <Tooltip
            cursor={{ fill: "#f2f2f2" }}
            contentStyle={{ borderRadius: 8, border: "1px solid #e6e6e6", fontSize: 12 }}
          />
          <Bar
            dataKey="count"
            radius={[0, 6, 6, 0]}
            onClick={(entry) =>
              onSelectCategory(selectedCategory === entry.category ? null : entry.category)
            }
            cursor="pointer"
          >
            {data.map((entry) => (
              <Cell
                key={entry.category}
                fill={
                  !selectedCategory || selectedCategory === entry.category ? ORANGE : "#f0d9c4"
                }
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
