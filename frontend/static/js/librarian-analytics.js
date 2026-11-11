(() => {
  const root = document.querySelector("[data-librarian-analytics]");
  if (!(root instanceof HTMLElement)) return;

  const endpoint = root.dataset.endpoint;
  const status = root.querySelector("[data-analytics-status]");
  const results = root.querySelector("[data-analytics-results]");
  const visuals = root.querySelector("[data-analytics-visuals]");
  const empty = root.querySelector("[data-analytics-empty]");
  const retry = root.querySelector("[data-analytics-retry]");
  const rangeButtons = [...root.querySelectorAll("[data-analytics-range]")];
  const activityChart = root.querySelector("[data-analytics-activity]");
  const genreChart = root.querySelector("[data-analytics-genres]");
  let selectedRange = "30d";
  let activeRequest = 0;

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

  const drawSparkline = (svg, values, label, color) => {
    svg.replaceChildren();
    svg.setAttribute("aria-label", label);
    if (!values.length) return;
    const width = 160;
    const height = 36;
    const max = Math.max(1, ...values);
    const min = Math.min(0, ...values);
    const spread = Math.max(1, max - min);
    const points = values.map((value, index) => {
      const x = values.length === 1 ? width / 2 : (index / (values.length - 1)) * width;
      const y = height - 3 - ((value - min) / spread) * (height - 6);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    svg.append(svgElement("polyline", {
      points: points.join(" "),
      fill: "none",
      stroke: color,
      "stroke-width": "2.5",
      "stroke-linecap": "round",
      "stroke-linejoin": "round",
    }));
  };

  const formatDate = (value) => {
    const day = new Date(`${value}T00:00:00`);
    return day.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  };

  const drawActivity = (svg, series) => {
    svg.replaceChildren();
    if (!series.length) return;
    const width = 720;
    const left = 48;
    const right = 704;
    const top = 18;
    const bottom = 216;
    const maximum = Math.max(1, ...series.flatMap((point) => [point.loans, point.returns]));
    const xAt = (index) => series.length === 1
      ? (left + right) / 2
      : left + (index / (series.length - 1)) * (right - left);
    const yAt = (value) => bottom - (value / maximum) * (bottom - top);

    for (let tick = 0; tick <= 3; tick += 1) {
      const value = Math.round((maximum * tick) / 3);
      const y = yAt(value);
      svg.append(svgElement("line", {
        x1: left, x2: right, y1: y, y2: y, class: "chart-grid",
      }));
      svgText(svg, left - 10, y + 4, String(value), { "text-anchor": "end" });
    }

    [
      ["loans", "chart-loans"],
      ["returns", "chart-returns"],
    ].forEach(([key, className]) => {
      const points = series.map((point, index) => `${xAt(index).toFixed(1)},${yAt(point[key]).toFixed(1)}`);
      svg.append(svgElement("polyline", { points: points.join(" "), class: `chart-line ${className}` }));
    });

    const labelCount = Math.min(5, series.length);
    for (let tick = 0; tick < labelCount; tick += 1) {
      const index = labelCount === 1
        ? 0
        : Math.round((tick / (labelCount - 1)) * (series.length - 1));
      svgText(svg, xAt(index), 244, formatDate(series[index].date), { "text-anchor": "middle" });
    }
    svg.setAttribute("viewBox", `0 0 ${width} 260`);
    svg.setAttribute("aria-label", `Daily loans and returns from ${formatDate(series[0].date)} to ${formatDate(series[series.length - 1].date)}`);
  };

  const drawGenres = (svg, genres) => {
    svg.replaceChildren();
    const display = genres.length > 9
      ? [
        ...genres.slice(0, 8),
        { genre: "Other", loans: genres.slice(8).reduce((sum, item) => sum + item.loans, 0) },
      ]
      : genres;
    if (!display.length) {
      svg.setAttribute("viewBox", "0 0 640 64");
      svgText(svg, 12, 34, "No genre loan data in this date range.");
      svg.setAttribute("aria-label", "No genre loan data in this date range");
      return;
    }

    const rowHeight = 38;
    const height = display.length * rowHeight + 16;
    const barStart = 174;
    const barWidth = 350;
    const max = Math.max(1, ...display.map((item) => item.loans));
    const palette = ["#426c55", "#d3874b", "#537e8b", "#99734c", "#7772a5", "#548e7c", "#bd725e", "#6d8294", "#87944d"];
    display.forEach((item, index) => {
      const y = index * rowHeight + 20;
      const label = item.genre.length > 22 ? `${item.genre.slice(0, 20)}…` : item.genre;
      svgText(svg, 8, y + 4, label);
      svg.append(svgElement("rect", {
        x: barStart,
        y: y - 10,
        width: barWidth,
        height: 16,
        rx: 8,
        fill: "#eff0e9",
      }));
      svg.append(svgElement("rect", {
        x: barStart,
        y: y - 10,
        width: Math.max(item.loans > 0 ? 2 : 0, (item.loans / max) * barWidth),
        height: 16,
        rx: 8,
        fill: palette[index % palette.length],
      }));
      svgText(svg, barStart + barWidth + 12, y + 4, String(item.loans));
    });
    svg.setAttribute("viewBox", `0 0 640 ${height}`);
    svg.setAttribute("aria-label", `Loans by genre: ${display.map((item) => `${item.genre}, ${item.loans}`).join("; ")}`);
  };

  const setLoading = () => {
    root.setAttribute("aria-busy", "true");
    status.textContent = "Loading analytics…";
    status.classList.remove("analytics-error");
    results.hidden = true;
    retry.hidden = true;
  };

  const loadAnalytics = async () => {
    if (!endpoint) return;
    const requestId = ++activeRequest;
    setLoading();
    rangeButtons.forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.analyticsRange === selectedRange));
    });
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

      const loans = data.series.map((point) => Number(point.loans) || 0);
      const returns = data.series.map((point) => Number(point.returns) || 0);
      root.querySelector('[data-analytics-total="loans"]').textContent = String(data.totals.loans);
      root.querySelector('[data-analytics-total="returns"]').textContent = String(data.totals.returns);
      drawSparkline(root.querySelector('[data-analytics-sparkline="loans"]'), loans, "Daily loans trend", "#426c55");
      drawSparkline(root.querySelector('[data-analytics-sparkline="returns"]'), returns, "Daily returns trend", "#d3874b");
      drawActivity(activityChart, data.series);
      drawGenres(genreChart, data.genres);
      const hasActivity = data.totals.loans > 0 || data.totals.returns > 0;
      visuals.hidden = !hasActivity;
      empty.hidden = hasActivity;
      results.hidden = false;
      status.textContent = `${data.totals.loans} loans and ${data.totals.returns} returns from ${data.start} to ${data.end}.`;
      root.setAttribute("aria-busy", "false");
    } catch (error) {
      if (requestId !== activeRequest) return;
      status.textContent = error instanceof Error ? error.message : "Analytics could not be loaded.";
      status.classList.add("analytics-error");
      retry.hidden = false;
      root.setAttribute("aria-busy", "false");
    }
  };

  rangeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      selectedRange = button.dataset.analyticsRange;
      loadAnalytics();
    });
  });
  retry.addEventListener("click", loadAnalytics);
  loadAnalytics();
})();
