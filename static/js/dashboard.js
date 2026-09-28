(() => {
    "use strict";

    const NS = "http://www.w3.org/2000/svg";

    function readData(id) {
        const node = document.getElementById(id);
        if (!node) return null;
        try {
            return JSON.parse(node.textContent);
        } catch (_) {
            return null;
        }
    }

    function hasValues(data) {
        return Boolean(
            data &&
            Array.isArray(data.labels) &&
            data.labels.length &&
            Array.isArray(data.series) &&
            data.series.some((serie) =>
                Array.isArray(serie.values) &&
                serie.values.some((value) => Number(value) !== 0)
            )
        );
    }

    function empty(container) {
        container.classList.add("is-empty");
        container.setAttribute("role", "status");
        container.textContent = "Nessun dato disponibile per il periodo selezionato.";
    }

    function maxValue(data) {
        return Math.max(
            1,
            ...data.series.flatMap((serie) =>
                serie.values.map((value) => Number(value) || 0)
            )
        );
    }

    function createSvg(tag, attrs = {}) {
        const el = document.createElementNS(NS, tag);
        Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, value));
        return el;
    }

    function renderLine(container, data) {
        if (!hasValues(data)) return empty(container);

        const width = 760;
        const height = 280;
        const left = 38;
        const right = 18;
        const top = 18;
        const bottom = 34;
        const chartW = width - left - right;
        const chartH = height - top - bottom;
        const max = maxValue(data);
        const values = data.series[0].values.map((v) => Number(v) || 0);
        const count = Math.max(values.length - 1, 1);

        const chartTitle = data.series[0].label || "Andamento dati";
        const svg = createSvg("svg", {
            viewBox: `0 0 ${width} ${height}`,
            role: "img",
            class: "chart-svg",
        });
        const titleId = `chart-title-${Math.random().toString(36).slice(2)}`;
        const descId = `chart-desc-${Math.random().toString(36).slice(2)}`;
        const titleNode = createSvg("title", { id: titleId });
        titleNode.textContent = chartTitle;
        const descNode = createSvg("desc", { id: descId });
        descNode.textContent = data.labels.map((label, index) =>
            `${label}: ${values[index]} ore`
        ).join("; ");
        svg.setAttribute("aria-labelledby", `${titleId} ${descId}`);
        svg.append(titleNode, descNode);

        [0, 0.25, 0.5, 0.75, 1].forEach((ratio) => {
            const y = top + chartH * ratio;
            svg.appendChild(createSvg("line", {
                x1: left,
                x2: width - right,
                y1: y,
                y2: y,
                class: "chart-grid-line",
            }));
            const label = createSvg("text", {
                x: left - 8,
                y: y + 4,
                "text-anchor": "end",
                class: "chart-axis-label",
            });
            label.textContent = Math.round(max * (1 - ratio));
            svg.appendChild(label);
        });

        const points = values.map((value, index) => {
            const x = left + (chartW * index) / count;
            const y = top + chartH - (value / max) * chartH;
            return { x, y, value, index };
        });

        const areaPoints = [
            `${points[0].x},${top + chartH}`,
            ...points.map((point) => `${point.x},${point.y}`),
            `${points[points.length - 1].x},${top + chartH}`,
        ].join(" ");
        svg.appendChild(createSvg("polygon", {
            points: areaPoints,
            class: "chart-area",
        }));

        svg.appendChild(createSvg("polyline", {
            points: points.map((point) => `${point.x},${point.y}`).join(" "),
            class: "chart-line",
        }));

        const labelStep = Math.max(1, Math.ceil(data.labels.length / 8));
        points.forEach((point, index) => {
            if (point.value > 0) {
                const circle = createSvg("circle", {
                    cx: point.x,
                    cy: point.y,
                    r: 4,
                    class: "chart-point",
                });
                const title = createSvg("title");
                title.textContent = `${data.labels[index]}: ${point.value} ore`;
                circle.appendChild(title);
                svg.appendChild(circle);
            }

            if (index % labelStep === 0 || index === points.length - 1) {
                const text = createSvg("text", {
                    x: point.x,
                    y: height - 10,
                    "text-anchor": "middle",
                    class: "chart-axis-label",
                });
                text.textContent = data.labels[index];
                svg.appendChild(text);
            }
        });

        container.replaceChildren(svg);
    }

    function makeBarTrack(value, max) {
        const track = document.createElement("div");
        track.className = "bar-track";
        track.setAttribute("aria-hidden", "true");
        const fill = document.createElement("div");
        fill.className = "bar-fill";
        fill.style.width = `${(value / max) * 100}%`;
        track.appendChild(fill);
        return track;
    }

    function renderBar(container, data) {
        if (!hasValues(data)) return empty(container);
        const max = maxValue(data);
        const root = document.createElement("div");
        root.setAttribute("role", "group");
        root.setAttribute("aria-label", data.series.map((serie) => serie.label).join(" e ") || "Grafico a barre");

        if (data.series.length === 1) {
            root.className = "bar-chart";
            data.labels.forEach((label, index) => {
                const value = Number(data.series[0].values[index]) || 0;
                const row = document.createElement("div");
                row.className = "bar-row";

                const labelNode = document.createElement("span");
                labelNode.className = "bar-label";
                labelNode.title = String(label);
                labelNode.textContent = String(label);

                const valueNode = document.createElement("strong");
                valueNode.className = "bar-value";
                valueNode.textContent = String(value);

                row.append(labelNode, makeBarTrack(value, max), valueNode);
                root.appendChild(row);
            });
        } else {
            root.className = "grouped-bars";
            data.labels.forEach((label, index) => {
                const group = document.createElement("div");
                group.className = "grouped-row";

                const heading = document.createElement("div");
                heading.className = "grouped-label";
                heading.textContent = String(label);
                group.appendChild(heading);

                const seriesRoot = document.createElement("div");
                seriesRoot.className = "grouped-series";
                data.series.forEach((serie) => {
                    const value = Number(serie.values[index]) || 0;
                    const row = document.createElement("div");
                    row.className = "grouped-series-row";

                    const name = document.createElement("span");
                    name.className = "grouped-series-name";
                    name.textContent = serie.label;

                    const valueNode = document.createElement("strong");
                    valueNode.className = "grouped-series-value";
                    valueNode.textContent = String(value);

                    row.append(name, makeBarTrack(value, max), valueNode);
                    seriesRoot.appendChild(row);
                });
                group.appendChild(seriesRoot);
                root.appendChild(group);
            });
        }
        container.replaceChildren(root);
    }

    document.querySelectorAll("[data-dashboard-chart]").forEach((container) => {
        const data = readData(container.dataset.source);
        const type = container.dataset.chartType || "bar";
        if (type === "line") renderLine(container, data);
        else renderBar(container, data);
    });
})();
