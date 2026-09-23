(function () {
  "use strict";

  const byId = (id) => document.getElementById(id);
  const root = byId("graph-component");
  const container = byId("network");
  const number = new Intl.NumberFormat("kk-KZ", { maximumFractionDigits: 0 });
  const money = new Intl.NumberFormat("kk-KZ", { maximumFractionDigits: 2 });
  let network = null;
  let nodeData = null;
  let records = new Map();
  let currentViewKey = "";
  let selectedId = "";
  let topologyKey = "";
  let freezeTimer = null;
  let heightTimer = null;
  let lastHeight = 0;
  let nonce = 0;
  let renderGeneration = 0;
  let physicsRunning = false;

  function post(type, fields) {
    window.parent.postMessage(Object.assign({ isStreamlitMessage: true, type: type }, fields || {}), "*");
  }

  function sendHeight() {
    window.clearTimeout(heightTimer);
    heightTimer = window.setTimeout(function () {
      const height = Math.ceil(root.getBoundingClientRect().height) + 3;
      if (height !== lastHeight) {
        lastHeight = height;
        post("streamlit:setFrameHeight", { height: height });
      }
    }, 30);
  }

  function numeric(value, fallback) {
    return typeof value === "number" && Number.isFinite(value) ? value : fallback;
  }

  function textElement(tag, text, className) {
    const element = document.createElement(tag);
    element.textContent = String(text == null ? "" : text);
    if (className) element.className = className;
    return element;
  }

  function safeColor(value, fallback) {
    return typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value) ? value : fallback;
  }

  function tooltip(lines) {
    const element = document.createElement("div");
    lines.forEach(function (line, index) {
      element.appendChild(textElement("div", line, index === 0 ? "tooltip-title" : "tooltip-line"));
    });
    return element;
  }

  function nodeTooltip(node) {
    const lines = [
      "gid: " + node.id,
      (node.role_label || node.role || "Рөл анықталмаған") + " · Кластер " + node.cluster_id,
      "Кіріс: " + money.format(numeric(node.in_kzt, 0)) + " ₸ · Шығыс: " + money.format(numeric(node.out_kzt, 0)) + " ₸",
      "Жіберуші: " + number.format(numeric(node.in_deg, 0)) + " · Алушы: " + number.format(numeric(node.out_deg, 0)),
      "Басымдық: " + numeric(node.priority_score, 0).toFixed(3),
      node.evidence || ""
    ];
    if (node.is_seed) lines.push("Seed: бастапқы клиент; кірісі толық көрінбейді.");
    if (node.depth === 4) lines.push("Depth=4: кейінгі шығыс бақылауы шектелген.");
    return tooltip(lines.filter(Boolean));
  }

  function edgeTooltip(edge) {
    return tooltip([
      edge.from + " → " + edge.to,
      "Сома: " + money.format(numeric(edge.sum_kzt, 0)) + " ₸",
      "Операциялар: " + number.format(numeric(edge.n_tx, 0))
    ]);
  }

  function visibleLabel(node) {
    const isSelected = node.id === selectedId;
    if (records.size <= 120 || isSelected || node.is_seed || numeric(node.priority_score, 0) >= 0.75) {
      return "…" + node.id.slice(-6);
    }
    return "";
  }

  function selectionStyle(node) {
    const isSelected = node.id === selectedId;
    const baseColor = safeColor(node.color, "#64899d");
    return {
      id: node.id,
      label: visibleLabel(node),
      borderWidth: isSelected ? 4 : (node.is_seed ? 2 : 1),
      borderWidthSelected: 4,
      color: {
        background: baseColor,
        border: isSelected ? "#082b40" : "#496677",
        highlight: { background: baseColor, border: "#082b40" },
        hover: { background: baseColor, border: "#082b40" }
      },
      font: { color: "#193c50", size: isSelected ? 13 : 10, strokeWidth: 3, strokeColor: "#ffffff" },
      shapeProperties: { borderDashes: node.depth === 4 ? [5, 3] : false }
    };
  }

  function showCard(gid) {
    const node = records.get(gid);
    const card = byId("selected-card");
    card.hidden = !node;
    if (node) {
      byId("selected-id").textContent = "gid: " + node.id;
      byId("selected-role").textContent = (node.role_label || node.role || "") + " · Кластер " + node.cluster_id + " · Басымдық " + numeric(node.priority_score, 0).toFixed(3);
      byId("selected-flows").textContent = "Кіріс " + money.format(numeric(node.in_kzt, 0)) + " ₸ · Шығыс " + money.format(numeric(node.out_kzt, 0)) + " ₸ · Жіберуші " + numeric(node.in_deg, 0) + " · Алушы " + numeric(node.out_deg, 0);
      byId("selected-evidence").textContent = node.evidence || "";
    }
    byId("node-select").value = node ? gid : "";
    sendHeight();
  }

  function selectNode(gid, notifyParent) {
    if (typeof gid !== "string" || !records.has(gid)) return;
    const oldId = selectedId;
    selectedId = gid;
    if (nodeData) {
      const updates = [];
      if (records.has(oldId)) updates.push(selectionStyle(records.get(oldId)));
      updates.push(selectionStyle(records.get(gid)));
      nodeData.update(updates);
    }
    if (network) network.selectNodes([gid], false);
    showCard(gid);
    if (notifyParent && gid !== oldId) {
      nonce += 1;
      post("streamlit:setComponentValue", { dataType: "json", value: { gid: gid, view_key: currentViewKey, nonce: String(Date.now()) + "-" + nonce } });
    }
  }

  function freezePhysics(generation) {
    if (generation !== renderGeneration || !network || !physicsRunning) return;
    window.clearTimeout(freezeTimer);
    physicsRunning = false;
    network.stopSimulation();
    network.setOptions({ physics: { enabled: false } });
    byId("freeze-graph").disabled = true;
    byId("graph-loading").hidden = true;
    byId("physics-status").textContent = "Орналасу бекітілді · жылжытуға болады";
    sendHeight();
  }

  function showError(message) {
    byId("graph-error").textContent = message;
    byId("graph-error").hidden = false;
    byId("graph-loading").hidden = true;
    byId("physics-status").textContent = "";
    byId("freeze-graph").disabled = true;
    sendHeight();
  }

  function buildLegend(payload) {
    const legend = byId("legend");
    legend.replaceChildren();
    const legends = payload.legend || {};
    const colorBy = (payload.summary || {}).color_by || "role";
    const category = colorBy === "cluster" ? "clusters" : (colorBy === "depth" ? "depths" : "roles");
    const titles = { roles: "Түстер — рөл гипотезалары", clusters: "Түстер — құрылымдық кластерлер", depths: "Түстер — бастапқы клиенттен қадам саны" };
    const entries = Array.isArray(legends[category]) ? legends[category] : [];
    const counts = new Map();
    records.forEach(function (node) {
      const key = String(category === "clusters" ? node.cluster_id : (category === "depths" ? node.depth : node.role));
      counts.set(key, (counts.get(key) || 0) + 1);
    });
    let items = legend;
    if (category === "clusters") {
      const disclosure = document.createElement("details");
      disclosure.className = "cluster-legend";
      disclosure.appendChild(textElement("summary", titles[category] + " · көрінетін " + counts.size + " кластер"));
      disclosure.appendChild(textElement("p", "Нақты кластер нөмірі түйінге меңзерді апарғанда және клиент мәліметінде көрсетіледі.", "graph-help"));
      items = document.createElement("div");
      items.className = "legend-items";
      disclosure.appendChild(items);
      disclosure.addEventListener("toggle", sendHeight);
      legend.appendChild(disclosure);
    } else {
      legend.appendChild(textElement("span", titles[category], "legend-title"));
    }
    entries.forEach(function (entry) {
      const count = counts.get(String(entry.key)) || 0;
      if (!count) return;
      const item = document.createElement("span");
      item.className = "legend-item";
      const swatch = document.createElement("span");
      swatch.className = "legend-color";
      swatch.style.backgroundColor = safeColor(entry.color, "#64899d");
      swatch.setAttribute("aria-hidden", "true");
      item.append(swatch, textElement("span", (entry.label || entry.key) + " · " + number.format(count)));
      items.appendChild(item);
    });
  }

  function updateSelectionList() {
    const select = byId("node-select");
    const fragment = document.createDocumentFragment();
    const placeholder = textElement("option", "Клиентті таңдаңыз");
    placeholder.value = "";
    fragment.appendChild(placeholder);
    records.forEach(function (node) {
      const option = textElement("option", node.id + " · " + (node.role_label || node.role || ""));
      option.value = node.id;
      fragment.appendChild(option);
    });
    select.replaceChildren(fragment);
    select.disabled = !records.size;
  }

  function signature(payload) {
    return JSON.stringify([
      payload.nodes.map(function (node) { return [node.id, node.color, node.size, node.shape, node.depth, node.is_seed]; }),
      payload.edges.map(function (edge) { return [edge.id, edge.from, edge.to, edge.width, edge.sum_kzt, edge.n_tx]; }),
      (payload.summary || {}).mode,
      (payload.summary || {}).color_by
    ]);
  }

  function render(args) {
    const payload = args.payload;
    currentViewKey = typeof args.view_key === "string" ? args.view_key : "";
    if (!payload || !Array.isArray(payload.nodes) || !Array.isArray(payload.edges)) {
      showError("Граф деректері келмеді. Жоғарыдағы есептеу қадамын қайталаңыз.");
      return;
    }
    if (!payload.nodes.every(function (node) { return typeof node.id === "string"; }) || !payload.edges.every(function (edge) { return typeof edge.from === "string" && typeof edge.to === "string"; })) {
      showError("Клиент идентификаторлары мәтін түрінде берілуі керек. Граф көрсетілмеді.");
      return;
    }
    records = new Map(payload.nodes.map(function (node) { return [node.id, node]; }));
    const summary = payload.summary || {};
    byId("graph-stats").textContent = "Клиенттер: " + number.format(records.size) + " / " + number.format(numeric(summary.total_nodes, records.size)) + " · Байланыстар: " + number.format(payload.edges.length) + " / " + number.format(numeric(summary.total_edges, payload.edges.length));
    const note = byId("scope-note");
    note.hidden = !summary.focus_outside_filter;
    note.textContent = summary.focus_outside_filter ? "Карта ортасындағы клиент сүзгіден тыс болса да, оның контекстін сақтау үшін көрсетілді." : "";
    byId("graph-error").hidden = true;
    byId("search-feedback").textContent = "";
    buildLegend(payload);
    const nextSignature = signature(payload);
    const nextSelected = typeof payload.selected_gid === "string" && records.has(payload.selected_gid) ? payload.selected_gid : "";
    if (network && nextSignature === topologyKey) {
      const oldSelected = selectedId;
      if (nextSelected) selectNode(nextSelected, false);
      else {
        selectedId = "";
        if (records.has(oldSelected)) nodeData.update(selectionStyle(records.get(oldSelected)));
        network.unselectAll();
        showCard("");
      }
      sendHeight();
      return;
    }
    renderGeneration += 1;
    const generation = renderGeneration;
    window.clearTimeout(freezeTimer);
    if (network) network.destroy();
    network = null;
    nodeData = null;
    topologyKey = nextSignature;
    selectedId = nextSelected;
    updateSelectionList();
    showCard(selectedId);
    if (!records.size) {
      showError("Бұл көріністе клиент жоқ. Сүзгілерді кеңейтіңіз немесе басқа gid таңдаңыз.");
      return;
    }
    if (!window.vis || typeof window.vis.Network !== "function" || typeof window.vis.DataSet !== "function") {
      showError("Жергілікті граф кітапханасы жүктелмеді. Бетті жаңартыңыз; клиенттер тізімін қолдануға болады.");
      return;
    }
    try {
      nodeData = new window.vis.DataSet(payload.nodes.map(function (node) {
        return Object.assign(selectionStyle(node), {
          shape: node.is_seed ? "diamond" : "dot",
          size: Math.max(5, Math.min(42, numeric(node.size, 12))),
          title: nodeTooltip(node)
        });
      }));
      const directedPairs = new Set(payload.edges.map(function (edge) {
        return edge.from + "\u0000" + edge.to;
      }));
      const edges = new window.vis.DataSet(payload.edges.map(function (edge, index) {
        const reciprocal = edge.from !== edge.to && directedPairs.has(edge.to + "\u0000" + edge.from);
        return {
          id: typeof edge.id === "string" ? edge.id : "edge-" + index,
          from: edge.from,
          to: edge.to,
          width: Math.max(0.5, Math.min(12, numeric(edge.width, 1))),
          arrows: { to: { enabled: true, scaleFactor: 0.45 } },
          color: { color: "#8aa8b8", highlight: "#136f83", hover: "#136f83", opacity: 0.5 },
          title: edgeTooltip(edge),
          // The same clockwise orientation bends reversed directions onto
          // opposite sides; one-way transfers stay straight, loops unchanged.
          smooth: reciprocal ? { enabled: true, type: "curvedCW", roundness: 0.12 } : false
        };
      }));
      byId("graph-loading").hidden = false;
      byId("physics-status").textContent = "Орналастыру жүріп жатыр…";
      byId("freeze-graph").disabled = false;
      physicsRunning = true;
      network = new window.vis.Network(container, { nodes: nodeData, edges: edges }, {
        autoResize: true,
        width: "100%",
        height: "100%",
        layout: { randomSeed: 42, improvedLayout: records.size < 150 },
        nodes: { chosen: true, shadow: false, scaling: { label: { enabled: false } } },
        edges: { selectionWidth: 1.5, hoverWidth: 1.5 },
        interaction: { hover: true, tooltipDelay: 160, multiselect: false, selectConnectedEdges: true, hideEdgesOnDrag: records.size > 250, hideEdgesOnZoom: records.size > 250, keyboard: { enabled: true, bindToWindow: false }, zoomView: true, dragView: true, dragNodes: true },
        physics: {
          enabled: true,
          solver: "barnesHut",
          barnesHut: { gravitationalConstant: -6500, centralGravity: 0.15, springLength: 125, springConstant: 0.025, damping: 0.35, avoidOverlap: 0.1 },
          stabilization: { enabled: true, iterations: records.size > 500 ? 180 : 250, updateInterval: 25, fit: true },
          minVelocity: 0.8,
          maxVelocity: 35,
          timestep: 0.5,
          adaptiveTimestep: true
        }
      });
      network.on("click", function (parameters) {
        if (parameters.nodes.length === 1 && typeof parameters.nodes[0] === "string") selectNode(parameters.nodes[0], true);
      });
      network.on("stabilizationProgress", function (parameters) {
        if (generation !== renderGeneration || !physicsRunning) return;
        byId("graph-loading").textContent = "Түйіндер орналастырылуда… " + Math.min(99, Math.round(parameters.iterations / parameters.total * 100)) + "%";
      });
      network.once("stabilizationIterationsDone", function () { freezePhysics(generation); });
      network.once("stabilized", function () { freezePhysics(generation); });
      freezeTimer = window.setTimeout(function () { freezePhysics(generation); }, 5500);
      if (selectedId) network.selectNodes([selectedId], false);
      sendHeight();
    } catch (error) {
      if (network) network.destroy();
      network = null;
      showError("Графты көрсету мүмкін болмады. Бетті жаңартыңыз немесе клиенттер тізімін қолданыңыз.");
    }
  }

  byId("zoom-in").addEventListener("click", function () {
    if (network) network.moveTo({ scale: Math.min(network.getScale() * 1.35, 5), animation: { duration: 180 } });
  });
  byId("zoom-out").addEventListener("click", function () {
    if (network) network.moveTo({ scale: Math.max(network.getScale() / 1.35, 0.015), animation: { duration: 180 } });
  });
  byId("fit-graph").addEventListener("click", function () {
    if (network) network.fit({ animation: { duration: 220 } });
  });
  byId("freeze-graph").addEventListener("click", function () { freezePhysics(renderGeneration); });
  byId("node-select").addEventListener("change", function (event) { selectNode(event.target.value, true); });
  byId("gid-search").addEventListener("submit", function (event) {
    event.preventDefault();
    const gid = byId("gid-input").value.trim();
    if (records.has(gid)) {
      selectNode(gid, true);
      byId("search-feedback").textContent = "Клиент таңдалды: " + gid + ". Толық мәлімет төменде.";
    } else {
      byId("search-feedback").textContent = "Бұл gid ағымдағы көріністе жоқ. Жоғарыдағы іздеуді немесе сүзгілерді қолданыңыз.";
    }
    sendHeight();
  });
  window.addEventListener("message", function (event) {
    if (event.source !== window.parent || !event.data || event.data.type !== "streamlit:render") return;
    try { render(event.data.args || {}); }
    catch (error) { showError("Граф деректерін көрсету мүмкін болмады. Есепті қайта жасаңыз."); }
  });
  if (typeof ResizeObserver === "function") new ResizeObserver(sendHeight).observe(root);
  window.addEventListener("resize", sendHeight);
  post("streamlit:componentReady", { apiVersion: 1 });
  sendHeight();
}());
