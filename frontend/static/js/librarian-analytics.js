(() => {
  const root = document.querySelector("[data-librarian-analytics]");
  if (!(root instanceof HTMLElement)) return;

  const endpoint = root.dataset.endpoint;
  const status = root.querySelector("[data-analytics-status]");
  const loading = root.querySelector("[data-analytics-loading]");
  const results = root.querySelector("[data-analytics-results]");
  const visuals = root.querySelector("[data-analytics-visuals]");
  const empty = root.querySelector("[data-analytics-empty]");
  const errorState = root.querySelector("[data-analytics-error]");
  const errorMessage = root.querySelector("[data-analytics-error-message]");
  const retry = root.querySelector("[data-analytics-retry]");
  const ranges = root.querySelector(".analytics-ranges");
  const rangeButtons = [...root.querySelectorAll("[data-analytics-range]")];
  const activityChart = root.querySelector("[data-analytics-activity]");
  const activityFrame = root.querySelector("[data-analytics-activity-frame]");
  const tooltip = root.querySelector("[data-analytics-tooltip]");
  const genreChart = root.querySelector("[data-analytics-genres]");
  const genreLegend = root.querySelector("[data-genre-legend]");
  const tableBody = root.querySelector("[data-analytics-table] tbody");
  const genreTableBody = root.querySelector("[data-genre-table] tbody");
  const numberFormat = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });
  let selectedRange = "30d";
  let activeRequest = 0;
  let activityState = null;
  let selectedIndex = 0;
  const seriesEnabled = { loans: true, returns: true, overdue: true };

  const svgElement = (name, attributes = {}) => {
    const element = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
    return element;
  };

  const svgText = (svg, x, y, value, attributes = {}) => {
    const text = svgElement("text", { x, y, ...attributes });
    text.textContent = value;
    svg.append(text);
    return text;
  };

  const safeNumber = (value) => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? Math.max(0, parsed) : 0;
  };

  const formatDate = (value, options = { month: "short", day: "numeric" }) => {
    const day = new Date(`${value}T00:00:00`);
    return Number.isNaN(day.getTime()) ? String(value) : day.toLocaleDateString(undefined, options);
  };

  const formatCompact = (value) => new Intl.NumberFormat(undefined, {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);

  const smoothPath = (points) => {
    if (!points.length) return "";
    if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;

    const slopes = [];
    for (let index = 0; index < points.length - 1; index += 1) {
      const dx = points[index + 1].x - points[index].x;
      slopes.push(dx ? (points[index + 1].y - points[index].y) / dx : 0);
    }

    const tangents = points.map((_, index) => {
      if (index === 0) return slopes[0];
      if (index === points.length - 1) return slopes[slopes.length - 1];
      const before = slopes[index - 1];
      const after = slopes[index];
      if (before === 0 || after === 0 || Math.sign(before) !== Math.sign(after)) return 0;
      return (2 * before * after) / (before + after);
    });

    let path = `M ${points[0].x} ${points[0].y}`;
    for (let index = 0; index < points.length - 1; index += 1) {
      const start = points[index];
      const end = points[index + 1];
      const dx = (end.x - start.x) / 3;
      const low = Math.min(start.y, end.y);
      const high = Math.max(start.y, end.y);
      const control1 = Math.min(high, Math.max(low, start.y + tangents[index] * dx));
      const control2 = Math.min(high, Math.max(low, end.y - tangents[index + 1] * dx));
      path += ` C ${start.x + dx} ${control1}, ${end.x - dx} ${control2}, ${end.x} ${end.y}`;
    }
    return path;
  };

  const areaPath = (points, bottom) => {
    if (!points.length) return "";
    if (points.length === 1) {
      return `M ${points[0].x - 8} ${bottom} L ${points[0].x - 8} ${points[0].y} L ${points[0].x} ${points[0].y} L ${points[0].x} ${bottom} Z`;
    }
    return `${smoothPath(points)} L ${points[points.length - 1].x} ${bottom} L ${points[0].x} ${bottom} Z`;
  };

  const niceStep = (maximum) => {
    const rough = Math.max(1, maximum / 4);
    const power = 10 ** Math.floor(Math.log10(rough));
    const fraction = rough / power;
    const multiplier = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
    return multiplier * power;
  };

  const makeText = (svg, width, x, y, value, attributes = {}) => {
    const text = svgText(svg, x, y, value, attributes);
    text.style.fontSize = `${11 * (width / Math.max(1, svg.getBoundingClientRect().width))}px`;
    return text;
  };

  const drawSparkline = (svg, values, key, colorName) => {
    svg.replaceChildren();
    const width = 180;
    const height = 42;
    const inset = 4;
    const points = values.map((value, index) => ({
      x: values.length === 1
        ? width - inset
        : inset + (index / (values.length - 1)) * (width - inset * 2),
      y: height - inset - (Math.min(1, safeNumber(value) / Math.max(1, ...values.map(safeNumber))) * (height - inset * 2)),
    }));
    const plotPoints = points.length === 1
      ? [{ x: points[0].x - 18, y: points[0].y }, points[0]]
      : points;
    const gradient = svgElement("linearGradient", {
      id: `analytics-spark-${key}`,
      x1: "0",
      x2: "0",
      y1: "0",
      y2: "1",
    });
    gradient.append(
      svgElement("stop", { offset: "0%", "stop-color": `var(--${colorName})`, "stop-opacity": "0.28" }),
      svgElement("stop", { offset: "100%", "stop-color": `var(--${colorName})`, "stop-opacity": "0" }),
    );
    const defs = svgElement("defs");
    defs.append(gradient);
    svg.append(defs);
    svg.append(svgElement("path", {
      class: "analytics-spark-area",
      d: areaPath(plotPoints, height - inset),
      fill: `url(#analytics-spark-${key})`,
    }));
    svg.append(svgElement("path", {
      class: "analytics-spark-line",
      d: smoothPath(plotPoints),
      stroke: `var(--${colorName})`,
    }));
    svg.append(svgElement("circle", {
      class: "analytics-spark-dot",
      cx: points[points.length - 1].x,
      cy: points[points.length - 1].y,
      r: "3.5",
      fill: `var(--${colorName})`,
    }));
  };

  const setSeriesVisible = (name, visible) => {
    seriesEnabled[name] = visible;
    const group = activityChart.querySelector(`[data-series-group="${name}"]`);
    if (group) group.setAttribute("display", visible ? "" : "none");
    const button = root.querySelector(`[data-series-toggle="${name}"]`);
    button?.setAttribute("aria-pressed", String(visible));
    if (activityState) showActivityPoint(selectedIndex);
  };

  const showActivityPoint = (index) => {
    if (!activityState) return;
    selectedIndex = Math.max(0, Math.min(activityState.points.length - 1, index));
    const point = activityState.points[selectedIndex];
    const crosshair = activityChart.querySelector(".chart-crosshair");
    crosshair?.setAttribute("x1", String(point.x));
    crosshair?.setAttribute("x2", String(point.x));
    crosshair?.classList.add("is-selected");
    ["loans", "returns", "overdue"].forEach((name) => {
      const marker = activityChart.querySelector(`[data-selected-point="${name}"]`);
      if (!marker) return;
      const value = activityState.values[name][selectedIndex];
      marker.setAttribute("cx", String(point.x));
      marker.setAttribute("cy", String(activityState.yAt(value)));
      marker.classList.toggle("is-selected", seriesEnabled[name]);
    });
    root.querySelector("[data-tooltip-date]").textContent = formatDate(
      point.date,
      { weekday: "short", month: "short", day: "numeric", year: "numeric" },
    );
    root.querySelector("[data-tooltip-loans]").textContent = numberFormat.format(activityState.values.loans[selectedIndex]);
    root.querySelector("[data-tooltip-returns]").textContent = numberFormat.format(activityState.values.returns[selectedIndex]);
    root.querySelector("[data-tooltip-overdue]").textContent = numberFormat.format(activityState.values.overdue[selectedIndex]);
    const frameRect = activityFrame.getBoundingClientRect();
    const chartRect = activityChart.getBoundingClientRect();
    const chartX = chartRect.left - frameRect.left + (point.x / activityState.width) * chartRect.width;
    const safeX = Math.max(78, Math.min(frameRect.width - 78, chartX));
    tooltip.style.left = `${safeX}px`;
    tooltip.hidden = false;
  };

  const hideActivityPoint = () => {
    if (activityChart.contains(document.activeElement)) return;
    activityChart.querySelector(".chart-crosshair")?.classList.remove("is-selected");
    activityChart.querySelectorAll(".analytics-point").forEach((point) => point.classList.remove("is-selected"));
    tooltip.hidden = true;
  };

  const drawActivity = (svg, series, overdueNow) => {
    svg.replaceChildren();
    if (!series.length) return;

    const width = 720;
    const height = 300;
    const left = 54;
    const right = 706;
    const top = 24;
    const bottom = 254;
    const values = {
      loans: series.map((point) => safeNumber(point.loans)),
      returns: series.map((point) => safeNumber(point.returns)),
      overdue: series.map((point) => point.overdue === undefined ? overdueNow : safeNumber(point.overdue)),
    };
    const maximum = Math.max(1, ...Object.values(values).flat());
    const step = niceStep(maximum);
    const yMaximum = Math.ceil(maximum / step) * step;
    const xAt = (index) => series.length === 1
      ? (left + right) / 2
      : left + (index / (series.length - 1)) * (right - left);
    const yAt = (value) => bottom - (safeNumber(value) / yMaximum) * (bottom - top);
    const points = series.map((point, index) => ({ x: xAt(index), date: point.date }));
    const defs = svgElement("defs");
    [
      ["analytics-loans-gradient", "var(--green)"],
      ["analytics-returns-gradient", "var(--rust)"],
    ].forEach(([id, color]) => {
      const gradient = svgElement("linearGradient", { id, x1: "0", x2: "0", y1: "0", y2: "1" });
      gradient.append(
        svgElement("stop", { offset: "0%", "stop-color": color, "stop-opacity": "0.25" }),
        svgElement("stop", { offset: "100%", "stop-color": color, "stop-opacity": "0" }),
      );
      defs.append(gradient);
    });
    svg.append(defs);

    for (let value = 0; value <= yMaximum; value += step) {
      const y = yAt(value);
      svg.append(svgElement("line", {
        x1: left, x2: right, y1: y, y2: y, class: "chart-grid",
      }));
      makeText(svg, width, left - 10, y + 4, formatCompact(value), { "text-anchor": "end" });
    }

    [
      ["loans", "series-loans"],
      ["returns", "series-returns"],
      ["overdue", "series-overdue"],
    ].forEach(([name, className]) => {
      const plotted = values[name].map((value, index) => ({ x: xAt(index), y: yAt(value) }));
      const group = svgElement("g", {
        class: className,
        "data-series-group": name,
      });
      if (name !== "overdue") {
        group.append(svgElement("path", {
          class: "analytics-area",
          d: areaPath(plotted, bottom),
        }));
      }
      group.append(svgElement("path", {
        class: "analytics-line",
        pathLength: "1",
        d: smoothPath(plotted),
      }));
      group.append(svgElement("circle", {
        class: "analytics-point",
        "data-selected-point": name,
        r: "4",
      }));
      svg.append(group);
    });

    const crosshair = svgElement("line", {
      class: "chart-crosshair",
      x1: left,
      x2: left,
      y1: top,
      y2: bottom,
    });
    svg.append(crosshair);

    const renderedWidth = svg.getBoundingClientRect().width || width;
    const labelCount = Math.min(series.length, Math.max(2, Math.floor(renderedWidth / 115)), 5);
    for (let tick = 0; tick < labelCount; tick += 1) {
      const index = labelCount === 1
        ? 0
        : Math.round((tick / (labelCount - 1)) * (series.length - 1));
      makeText(svg, width, xAt(index), 284, formatDate(series[index].date), { "text-anchor": "middle" });
    }

    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    const totals = series.reduce((sum, point) => sum + safeNumber(point.loans) + safeNumber(point.returns), 0);
    svg.setAttribute(
      "aria-label",
      `${numberFormat.format(totals)} borrow and return events from ${formatDate(series[0].date)} to ${formatDate(series[series.length - 1].date)}. Current overdue count: ${numberFormat.format(overdueNow)}.`,
    );
    activityState = { points, values, yAt, width };
    seriesEnabled.loans = true;
    seriesEnabled.returns = true;
    seriesEnabled.overdue = true;
    root.querySelectorAll("[data-series-toggle]").forEach((button) => {
      button.setAttribute("aria-pressed", "true");
    });
    svg.classList.remove("is-ready");
    requestAnimationFrame(() => svg.classList.add("is-ready"));
  };

  const drawGenres = (svg, genres) => {
    svg.replaceChildren();
    genreLegend.replaceChildren();
    genreTableBody.replaceChildren();
    const ordered = [...genres]
      .map((item) => ({ genre: String(item.genre), loans: safeNumber(item.loans) }))
      .sort((left, right) => right.loans - left.loans);
    const display = ordered.length > 6
      ? [
        ...ordered.slice(0, 6),
        { genre: "Other", loans: ordered.slice(6).reduce((sum, item) => sum + item.loans, 0) },
      ]
      : ordered;
    const total = display.reduce((sum, item) => sum + item.loans, 0);
    const width = 640;
    const rowHeight = 34;
    const height = Math.max(52, display.length * rowHeight + 8);
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    if (!display.length) {
      const text = makeText(svg, width, 10, 28, "No genre loan data for this range.");
      text.classList.add("analytics-empty-chart-label");
      svg.setAttribute("aria-label", "No genre loan data for the selected range.");
      return;
    }

    const barStart = 250;
    const barWidth = 250;
    const max = Math.max(1, ...display.map((item) => item.loans));
    const renderedWidth = svg.getBoundingClientRect().width || width;
    display.forEach((item, index) => {
      const y = index * rowHeight + 18;
      const percent = total ? (item.loans / total) * 100 : 0;
      const group = svgElement("g", {
        class: `genre-row color-${index % 7}`,
        "data-genre-row": String(index),
      });
      group.append(
        svgElement("rect", {
          class: "genre-track",
          x: barStart,
          y: y - 10,
          width: barWidth,
          height: 12,
          rx: 6,
        }),
        svgElement("rect", {
          class: "genre-bar",
          x: barStart,
          y: y - 10,
          width: Math.max(item.loans ? 2 : 0, (item.loans / max) * barWidth),
          height: 12,
          rx: 6,
        }),
      );
      const label = item.genre.length > 21 ? `${item.genre.slice(0, 20)}…` : item.genre;
      makeText(svg, width, 8, y, label);
      makeText(
        svg,
        width,
        632,
        y,
        `${formatCompact(item.loans)} · ${percent.toFixed(1)}%`,
        { "text-anchor": "end" },
      );
      svg.append(group);

      const button = document.createElement("button");
      button.type = "button";
      button.className = `analytics-genre-item color-${index % 7}`;
      button.dataset.genreIndex = String(index);
      button.innerHTML = `<span class="analytics-genre-name"><span class="analytics-genre-dot" aria-hidden="true"></span><span class="analytics-genre-label"></span></span><span class="analytics-genre-value"></span>`;
      button.querySelector(".analytics-genre-label").textContent = item.genre;
      button.querySelector(".analytics-genre-value").textContent =
        `${numberFormat.format(item.loans)} · ${percent.toFixed(1)}%`;
      const highlight = (active) => {
        button.classList.toggle("is-highlighted", active);
        group.classList.toggle("is-highlighted", active);
      };
      group.addEventListener("pointerenter", () => highlight(true));
      group.addEventListener("pointerleave", () => highlight(false));
      button.addEventListener("pointerenter", () => highlight(true));
      button.addEventListener("pointerleave", () => highlight(false));
      button.addEventListener("focus", () => highlight(true));
      button.addEventListener("blur", () => highlight(false));
      genreLegend.append(button);
    });
    svg.setAttribute(
      "aria-label",
      `Loans by genre, ${numberFormat.format(total)} total: ${display.map((item) => `${item.genre}, ${numberFormat.format(item.loans)}, ${total ? ((item.loans / total) * 100).toFixed(1) : "0.0"} percent`).join("; ")}.`,
    );
    display.forEach((item) => {
      const row = document.createElement("tr");
      [
        item.genre,
        numberFormat.format(item.loans),
        `${total ? ((item.loans / total) * 100).toFixed(1) : "0.0"}%`,
      ].forEach((value) => {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.append(cell);
      });
      genreTableBody.append(row);
    });
    svg.classList.remove("is-ready");
    requestAnimationFrame(() => svg.classList.add("is-ready"));
    svg.style.setProperty("--genre-chart-scale", String(width / Math.max(1, renderedWidth)));
  };

  const populateTable = (series, overdueNow) => {
    tableBody.replaceChildren();
    series.forEach((point) => {
      const row = document.createElement("tr");
      [
        formatDate(point.date, { year: "numeric", month: "long", day: "numeric" }),
        numberFormat.format(safeNumber(point.loans)),
        numberFormat.format(safeNumber(point.returns)),
        numberFormat.format(point.overdue === undefined ? overdueNow : safeNumber(point.overdue)),
      ].forEach((value) => {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.append(cell);
      });
      tableBody.append(row);
    });
  };

  const updateKpis = (data) => {
    const metrics = {
      "on-loan": { value: safeNumber(root.dataset.onLoan), format: numberFormat, series: [safeNumber(root.dataset.onLoan)], color: "green" },
      overdue: { value: safeNumber(root.dataset.overdue), format: numberFormat, series: [safeNumber(root.dataset.overdue)], color: "rust" },
      "fees-collected": {
        value: safeNumber(root.dataset.feesCollected),
        format: {
          format: (value) => `₱${new Intl.NumberFormat(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
          }).format(value)}`,
        },
        series: [safeNumber(root.dataset.feesCollected)],
        color: "green",
      },
      "members-with-fees": {
        value: safeNumber(root.dataset.membersWithFees),
        format: numberFormat,
        series: [safeNumber(root.dataset.membersWithFees)],
        color: "rust",
      },
    };
    Object.entries(metrics).forEach(([key, metric]) => {
      root.querySelector(`[data-kpi-value="${key}"]`).textContent = metric.format.format(metric.value);
      drawSparkline(root.querySelector(`[data-kpi-sparkline="${key}"]`), metric.series, key, metric.color);
    });

    const previous = data.previous;
    if (!previous || typeof previous !== "object") return;
    const previousKeys = {
      "on-loan": "on_loan",
      overdue: "overdue",
      "fees-collected": "fees_collected",
      "members-with-fees": "members_with_fees",
    };
    Object.entries(metrics).forEach(([key, metric]) => {
      const previousValue = Number(previous[previousKeys[key]]);
      if (!Number.isFinite(previousValue) || previousValue <= 0) return;
      const change = ((metric.value - previousValue) / previousValue) * 100;
      const chip = root.querySelector(`[data-analytics-kpi="${key}"] [data-analytics-trend]`);
      const direction = change >= 0 ? "▲" : "▼";
      chip.textContent = `${direction} ${Math.abs(change).toFixed(0)}% vs previous period`;
      chip.classList.toggle("is-down", change < 0);
      chip.hidden = false;
    });
  };

  const setLoading = () => {
    root.setAttribute("aria-busy", "true");
    status.textContent = "Loading library activity…";
    status.classList.remove("analytics-error");
    loading.hidden = false;
    results.hidden = true;
    errorState.hidden = true;
    retry.hidden = true;
  };

  const setError = (error) => {
    const message = error instanceof Error ? error.message : "Analytics could not be loaded.";
    status.textContent = "Analytics are unavailable.";
    status.classList.add("analytics-error");
    errorMessage.textContent = message;
    loading.hidden = true;
    results.hidden = true;
    errorState.hidden = false;
    retry.hidden = false;
    root.setAttribute("aria-busy", "false");
  };

  const loadAnalytics = async () => {
    if (!endpoint) {
      setError(new Error("The analytics endpoint is not configured."));
      return;
    }
    const requestId = ++activeRequest;
    setLoading();
    ranges.style.setProperty("--active-index", String(rangeButtons.indexOf(
      rangeButtons.find((button) => button.dataset.analyticsRange === selectedRange),
    )));
    rangeButtons.forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.analyticsRange === selectedRange));
    });
    const rangeLabels = { "7d": "7 days", "30d": "30 days", "12w": "12 weeks" };
    root.querySelector("[data-analytics-subtitle]").textContent =
      `Showing activity for the last ${rangeLabels[selectedRange]}.`;

    try {
      const url = new URL(endpoint, window.location.href);
      url.searchParams.set("range", selectedRange);
      const response = await fetch(url, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      const data = await response.json();
      if (requestId !== activeRequest) return;
      if (!response.ok) throw new Error(data.error || "Analytics could not be loaded.");
      if (!Array.isArray(data.series) || !Array.isArray(data.genres) || !data.totals) {
        throw new Error("Analytics data was not in the expected format.");
      }

      const normalizedSeries = data.series.map((point) => ({
        ...point,
        loans: safeNumber(point.loans),
        returns: safeNumber(point.returns),
      }));
      const overdueNow = safeNumber(root.dataset.overdue);
      const totalLoans = safeNumber(data.totals.loans);
      const totalReturns = safeNumber(data.totals.returns);
      const hasActivity = totalLoans > 0 || totalReturns > 0;

      results.hidden = false;
      visuals.hidden = false;
      empty.hidden = true;
      activityChart.getBoundingClientRect();
      updateKpis(data);
      drawActivity(activityChart, normalizedSeries, overdueNow);
      drawGenres(genreChart, data.genres);
      populateTable(normalizedSeries, overdueNow);
      visuals.hidden = !hasActivity;
      empty.hidden = hasActivity;
      results.hidden = false;
      loading.hidden = true;
      status.textContent = `${numberFormat.format(totalLoans)} borrowed and ${numberFormat.format(totalReturns)} returned from ${formatDate(data.start)} to ${formatDate(data.end)}.`;
      root.setAttribute("aria-busy", "false");
    } catch (error) {
      if (requestId !== activeRequest) return;
      setError(error);
    }
  };

  activityChart.addEventListener("pointermove", (event) => {
    if (!activityState) return;
    const point = activityChart.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const matrix = activityChart.getScreenCTM();
    if (!matrix) return;
    const chartPoint = point.matrixTransform(matrix.inverse());
    const plotWidth = 706 - 54;
    const index = activityState.points.length === 1
      ? 0
      : Math.round(((chartPoint.x - 54) / plotWidth) * (activityState.points.length - 1));
    showActivityPoint(index);
  });
  activityChart.addEventListener("pointerup", (event) => {
    if (event.pointerType === "touch" && activityState) {
      const point = activityChart.createSVGPoint();
      point.x = event.clientX;
      point.y = event.clientY;
      const matrix = activityChart.getScreenCTM();
      if (!matrix) return;
      const chartPoint = point.matrixTransform(matrix.inverse());
      const index = Math.round(((chartPoint.x - 54) / (706 - 54)) * (activityState.points.length - 1));
      showActivityPoint(index);
    }
  });
  activityChart.addEventListener("pointerleave", hideActivityPoint);
  activityChart.addEventListener("focus", () => showActivityPoint(selectedIndex));
  activityChart.addEventListener("blur", hideActivityPoint);
  activityChart.addEventListener("keydown", (event) => {
    if (!activityState || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    if (event.key === "Home") selectedIndex = 0;
    else if (event.key === "End") selectedIndex = activityState.points.length - 1;
    else selectedIndex += event.key === "ArrowLeft" ? -1 : 1;
    showActivityPoint(selectedIndex);
  });

  root.querySelectorAll("[data-series-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const name = button.dataset.seriesToggle;
      setSeriesVisible(name, !seriesEnabled[name]);
    });
  });
  rangeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      selectedRange = button.dataset.analyticsRange;
      loadAnalytics();
    });
  });
  retry.addEventListener("click", loadAnalytics);
  loadAnalytics();
})();
