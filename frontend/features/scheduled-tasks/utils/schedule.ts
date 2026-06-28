export type SchedulePreset =
  "interval" | "daily" | "weekly" | "monthly" | "cron";
export type IntervalUnit = "minute" | "hour";

export interface InferredSchedule {
  preset: SchedulePreset;
  cron: string;
  interval?: {
    value: number;
    unit: IntervalUnit;
  };
  time?: {
    hour: number;
    minute: number;
  };
  weekDays?: number[]; // 0 (Sun) - 6 (Sat)
  dayOfMonth?: number; // 1 - 31
}

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

function isIntInRange(value: number, min: number, max: number): boolean {
  return Number.isInteger(value) && value >= min && value <= max;
}

function parseCronParts(expr: string): string[] | null {
  const parts = (expr || "").trim().split(/\s+/).filter(Boolean);
  return parts.length === 5 ? parts : null;
}

function parseStep(value: string): number | null {
  const match = value.match(/^\*\/(\d+)$/);
  if (!match) return null;
  const parsed = Number.parseInt(match[1], 10);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseNumber(value: string): number | null {
  if (!/^\d+$/.test(value)) return null;
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseDayOfWeekList(value: string): number[] | null {
  if (!value || value === "*") return null;
  const items = value.split(",").map((v) => v.trim());
  if (items.length === 0) return null;
  const out: number[] = [];
  for (const item of items) {
    const n = parseNumber(item);
    if (n === null) return null;
    const normalized = n === 7 ? 0 : n;
    if (!isIntInRange(normalized, 0, 6)) return null;
    out.push(normalized);
  }
  // Deduplicate while preserving order.
  return Array.from(new Set(out));
}

export function inferScheduleFromCron(cronExpr: string): InferredSchedule {
  const cron = (cronExpr || "").trim();
  const parts = parseCronParts(cron);
  if (!parts) {
    return { preset: "cron", cron };
  }

  const [min, hour, dom, mon, dow] = parts;

  const minuteStep = parseStep(min);
  if (
    minuteStep !== null &&
    hour === "*" &&
    dom === "*" &&
    mon === "*" &&
    dow === "*"
  ) {
    return {
      preset: "interval",
      cron,
      interval: { value: minuteStep, unit: "minute" },
    };
  }

  const fixedMinute = parseNumber(min);
  const hourStep = parseStep(hour);
  if (
    fixedMinute !== null &&
    hourStep !== null &&
    dom === "*" &&
    mon === "*" &&
    dow === "*"
  ) {
    return {
      preset: "interval",
      cron,
      interval: { value: hourStep, unit: "hour" },
      time: { hour: 0, minute: fixedMinute },
    };
  }

  const fixedHour = parseNumber(hour);
  if (
    fixedMinute !== null &&
    fixedHour !== null &&
    dom === "*" &&
    mon === "*" &&
    dow === "*"
  ) {
    return {
      preset: "daily",
      cron,
      time: { hour: fixedHour, minute: fixedMinute },
    };
  }

  const weekDays = parseDayOfWeekList(dow);
  if (
    fixedMinute !== null &&
    fixedHour !== null &&
    dom === "*" &&
    mon === "*" &&
    weekDays &&
    weekDays.length > 0
  ) {
    return {
      preset: "weekly",
      cron,
      time: { hour: fixedHour, minute: fixedMinute },
      weekDays,
    };
  }

  const dayOfMonth = parseNumber(dom);
  if (
    fixedMinute !== null &&
    fixedHour !== null &&
    dayOfMonth !== null &&
    mon === "*" &&
    dow === "*"
  ) {
    return {
      preset: "monthly",
      cron,
      time: { hour: fixedHour, minute: fixedMinute },
      dayOfMonth,
    };
  }

  return { preset: "cron", cron };
}

export function buildCronFromPreset(input: {
  preset: Exclude<SchedulePreset, "cron">;
  interval?: { value: number; unit: IntervalUnit };
  time?: { hour: number; minute: number };
  weekDays?: number[];
  dayOfMonth?: number;
}): string {
  if (input.preset === "interval") {
    const unit = input.interval?.unit ?? "minute";
    const value = input.interval?.value ?? 5;
    const safeValue = Math.max(1, Math.floor(value));
    if (unit === "hour") {
      return `0 */${safeValue} * * *`;
    }
    return `*/${safeValue} * * * *`;
  }

  const hour = input.time?.hour ?? 0;
  const minute = input.time?.minute ?? 0;
  const safeHour = Math.min(23, Math.max(0, Math.floor(hour)));
  const safeMinute = Math.min(59, Math.max(0, Math.floor(minute)));

  if (input.preset === "daily") {
    return `${safeMinute} ${safeHour} * * *`;
  }

  if (input.preset === "weekly") {
    const days = (input.weekDays || [])
      .map((d) => (d === 7 ? 0 : d))
      .filter((d) => Number.isInteger(d) && d >= 0 && d <= 6);
    const safeDays = Array.from(new Set(days));
    return `${safeMinute} ${safeHour} * * ${safeDays.length > 0 ? safeDays.join(",") : "1"}`;
  }

  const day = input.dayOfMonth ?? 1;
  const safeDay = Math.min(31, Math.max(1, Math.floor(day)));
  return `${safeMinute} ${safeHour} ${safeDay} * *`;
}

export function formatScheduleSummary(
  inferred: InferredSchedule,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  if (inferred.preset === "interval") {
    const value = inferred.interval?.value ?? 5;
    const unit = inferred.interval?.unit ?? "minute";
    return unit === "hour"
      ? t("library.scheduledTasks.schedule.summary.intervalHours", {
          count: value,
        })
      : t("library.scheduledTasks.schedule.summary.intervalMinutes", {
          count: value,
        });
  }

  if (inferred.preset === "daily") {
    const hour = inferred.time?.hour ?? 0;
    const minute = inferred.time?.minute ?? 0;
    return t("library.scheduledTasks.schedule.summary.daily", {
      time: `${pad2(hour)}:${pad2(minute)}`,
    });
  }

  if (inferred.preset === "weekly") {
    const hour = inferred.time?.hour ?? 0;
    const minute = inferred.time?.minute ?? 0;
    const days = inferred.weekDays || [];
    const order = [1, 2, 3, 4, 5, 6, 0];
    const sorted = order.filter((d) => days.includes(d));
    const labels = sorted.map((d) =>
      t(`library.scheduledTasks.schedule.weekdays.short.${d}`),
    );
    return t("library.scheduledTasks.schedule.summary.weekly", {
      days: labels.join(" "),
      time: `${pad2(hour)}:${pad2(minute)}`,
    });
  }

  if (inferred.preset === "monthly") {
    const hour = inferred.time?.hour ?? 0;
    const minute = inferred.time?.minute ?? 0;
    const day = inferred.dayOfMonth ?? 1;
    return t("library.scheduledTasks.schedule.summary.monthly", {
      day,
      time: `${pad2(hour)}:${pad2(minute)}`,
    });
  }

  return t("library.scheduledTasks.schedule.summary.cron", {
    cron: inferred.cron || "* * * * *",
  });
}
