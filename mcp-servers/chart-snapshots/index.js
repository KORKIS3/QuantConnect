#!/usr/bin/env node
/**
 * chart-snapshots MCP server
 *
 * Exposes tools to list and read YM chart snapshot images from
 * C:\Users\Administrator\Desktop\IB_Live\charts (configurable via
 * CHARTS_DIR env var), so an LLM can pull and view specific snapshots
 * on demand without the user manually attaching files.
 *
 * Filenames look like:
 *   YM_2026-07-01_1400_algo_snapshot.jpg
 *   YM_2026-07-01_1400_ib_snapshot.jpg
 *   YM_2026-04-21_1000_snapshot.jpg   (older files, no kind suffix)
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import fs from "node:fs";
import path from "node:path";

const CHARTS_DIR =
  process.env.CHARTS_DIR ||
  "C:\\Users\\Administrator\\Desktop\\IB_Live\\charts";

// YM_<date>_<hhmm|full>_[<kind>_]snapshot.<ext>
const FILE_RE =
  /^YM_(\d{4}-\d{2}-\d{2})_(\d{3,4}|full)_(?:(algo|ib)_)?snapshot\.(jpg|jpeg|png)$/i;

function parseFileName(name) {
  const m = FILE_RE.exec(name);
  if (!m) return null;
  return {
    date: m[1],
    hour: m[2],
    kind: m[3] ? m[3].toLowerCase() : "plain",
    ext: m[4].toLowerCase(),
  };
}

function listSnapshotFiles() {
  let entries;
  try {
    entries = fs.readdirSync(CHARTS_DIR, { withFileTypes: true });
  } catch (err) {
    throw new Error(`Cannot read charts directory "${CHARTS_DIR}": ${err.message}`);
  }
  const files = [];
  for (const e of entries) {
    if (!e.isFile()) continue;
    const parsed = parseFileName(e.name);
    if (!parsed) continue;
    files.push({ file: e.name, ...parsed });
  }
  return files;
}

function mimeForExt(ext) {
  if (ext === "png") return "image/png";
  return "image/jpeg";
}

const server = new Server(
  { name: "chart-snapshots", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "list_snapshots",
      description:
        "List available YM chart snapshot files in the charts directory, optionally filtered by date (YYYY-MM-DD) and/or kind (algo, ib, plain). Returns file names, dates, hours (HHMM) and kinds so you can pick which to load with get_snapshot.",
      inputSchema: {
        type: "object",
        properties: {
          date: {
            type: "string",
            description: "Filter by date, format YYYY-MM-DD (e.g. 2026-07-01). Omit to list all dates.",
          },
          kind: {
            type: "string",
            enum: ["algo", "ib", "plain", "any"],
            description: "Filter by snapshot kind. 'plain' = older files with no kind suffix. Defaults to 'any'.",
          },
        },
      },
    },
    {
      name: "get_snapshot",
      description:
        "Load a specific YM chart snapshot image as image content so it can be visually analyzed. Requires date and hour; kind defaults to 'algo'.",
      inputSchema: {
        type: "object",
        properties: {
          date: {
            type: "string",
            description: "Date of the snapshot, format YYYY-MM-DD (e.g. 2026-07-01).",
          },
          hour: {
            type: "string",
            description: "Hour label as it appears in the filename, e.g. '1400'.",
          },
          kind: {
            type: "string",
            enum: ["algo", "ib", "plain"],
            description: "Which snapshot variant to load. Defaults to 'algo'.",
          },
        },
        required: ["date", "hour"],
      },
    },
    {
      name: "get_latest_snapshot",
      description:
        "Load the most recent YM chart snapshot image (by date+hour) as image content, optionally filtered by kind (algo, ib, plain). Useful for 'show me the latest chart' requests.",
      inputSchema: {
        type: "object",
        properties: {
          kind: {
            type: "string",
            enum: ["algo", "ib", "plain"],
            description: "Which snapshot variant to load. Defaults to 'algo'.",
          },
        },
      },
    },
  ],
}));

function sortKey(f) {
  // hour may be 3 or 4 digits (e.g. "930" or "1400") -> normalize to int minutes-of-day-ish
  return `${f.date}_${f.hour.padStart(4, "0")}`;
}

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args = {} } = request.params;

  if (name === "list_snapshots") {
    const { date, kind = "any" } = args;
    let files = listSnapshotFiles();
    if (date) files = files.filter((f) => f.date === date);
    if (kind && kind !== "any") files = files.filter((f) => f.kind === kind);
    files.sort((a, b) => sortKey(a).localeCompare(sortKey(b)));

    if (files.length === 0) {
      return {
        content: [
          {
            type: "text",
            text: `No snapshot files found in "${CHARTS_DIR}" matching date=${date ?? "*"} kind=${kind}.`,
          },
        ],
      };
    }

    const lines = files.map(
      (f) => `${f.file}  (date=${f.date}, hour=${f.hour}, kind=${f.kind})`
    );
    return {
      content: [
        {
          type: "text",
          text: `Found ${files.length} snapshot(s):\n${lines.join("\n")}`,
        },
      ],
    };
  }

  if (name === "get_snapshot" || name === "get_latest_snapshot") {
    let target;

    if (name === "get_latest_snapshot") {
      const kind = args.kind || "algo";
      const files = listSnapshotFiles().filter((f) => f.kind === kind);
      if (files.length === 0) {
        return {
          content: [
            { type: "text", text: `No snapshots found for kind="${kind}" in "${CHARTS_DIR}".` },
          ],
          isError: true,
        };
      }
      files.sort((a, b) => sortKey(b).localeCompare(sortKey(a))); // descending
      target = files[0];
    } else {
      const { date, hour, kind = "algo" } = args;
      if (!date || !hour) {
        return {
          content: [{ type: "text", text: "Both 'date' and 'hour' are required." }],
          isError: true,
        };
      }
      const files = listSnapshotFiles().filter(
        (f) => f.date === date && f.hour === String(hour) && f.kind === kind
      );
      if (files.length === 0) {
        return {
          content: [
            {
              type: "text",
              text: `No snapshot found for date=${date} hour=${hour} kind=${kind} in "${CHARTS_DIR}". Use list_snapshots to see what's available.`,
            },
          ],
          isError: true,
        };
      }
      target = files[0];
    }

    const fullPath = path.join(CHARTS_DIR, target.file);
    let data;
    try {
      data = fs.readFileSync(fullPath);
    } catch (err) {
      return {
        content: [{ type: "text", text: `Failed to read "${fullPath}": ${err.message}` }],
        isError: true,
      };
    }

    return {
      content: [
        {
          type: "text",
          text: `Loaded ${target.file} (date=${target.date}, hour=${target.hour}, kind=${target.kind})`,
        },
        {
          type: "image",
          data: data.toString("base64"),
          mimeType: mimeForExt(target.ext),
        },
      ],
    };
  }

  throw new Error(`Unknown tool: ${name}`);
});

const transport = new StdioServerTransport();
await server.connect(transport);
