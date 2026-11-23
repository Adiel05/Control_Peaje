(function () {
  const sseBadge = document.getElementById("sse-estado");
  const tbody = document.getElementById("tabla-pasos-body");
  const kpiPasos = document.getElementById("kpi-pasos");
  const kpiRec = document.getElementById("kpi-recaudacion");
  const kpiAlertas = document.getElementById("kpi-alertas");
  const listaAlertas = document.getElementById("lista-alertas");
  const toasts = document.getElementById("toast-container");

  function badgeEstado(estado) {
    if (estado === "OK") return '<span class="badge badge-ok">OK</span>';
    if (estado === "SIN_SALDO") return '<span class="badge badge-warn">SIN_SALDO</span>';
    return '<span class="badge badge-err">' + (estado || "NO_REGISTRADA") + "</span>";
  }

  function escapar(txt) {
    const div = document.createElement("div");
    div.textContent = txt == null ? "" : String(txt);
    return div.innerHTML;
  }

  function mostrarToast(texto) {
    if (!toasts) return;
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = texto;
    toasts.appendChild(el);
    setTimeout(() => el.remove(), 7000);
  }

  const es = new EventSource("/eventos");
  es.onopen = function () {
    if (sseBadge) {
      sseBadge.textContent = "En vivo (SSE)";
      sseBadge.className = "badge badge-ok";
    }
  };
  es.onerror = function () {
    if (sseBadge) {
      sseBadge.textContent = "Reconectando SSE...";
      sseBadge.className = "badge badge-warn";
    }
  };

  es.addEventListener("paso", function (ev) {
    if (!tbody) return;
    const p = JSON.parse(ev.data);
    const vacio = document.getElementById("fila-vacia");
    if (vacio) vacio.remove();

    const tr = document.createElement("tr");
    const imgHtml = p.imagen_url
      ? '<a href="' + escapar(p.imagen_url) + '" target="_blank"><img class="thumb" src="' + escapar(p.imagen_url) + '" alt="Evidencia"></a>'
      : '<span class="badge badge-muted">Sin img</span>';

    tr.innerHTML =
      "<td>" + imgHtml + "</td>" +
      "<td><strong>" + escapar(p.placa_normalizada) + "</strong></td>" +
      "<td>" + escapar(p.categoria_detectada || "-") + "</td>" +
      "<td>" + escapar(p.ejes_detectados ?? "-") + "</td>" +
      "<td>" + escapar(p.pasajeros ?? "-") + "</td>" +
      "<td>Bs " + Number(p.monto || 0).toFixed(2) + "</td>" +
      "<td>" + escapar(p.caseta_nombre || p.caseta_id) + "</td>" +
      "<td>" + badgeEstado(p.estado) + "</td>" +
      "<td>" + escapar(p.fecha_legible) + "</td>";

    tbody.prepend(tr);
    while (tbody.rows.length > 20) {
      tbody.deleteRow(tbody.rows.length - 1);
    }
  });

  es.addEventListener("contadores", function (ev) {
    const c = JSON.parse(ev.data);
    if (kpiPasos) kpiPasos.textContent = c.pasos_hoy;
    if (kpiRec) kpiRec.textContent = "Bs " + Number(c.recaudacion_hoy || 0).toFixed(2);
    if (kpiAlertas) kpiAlertas.textContent = c.alertas_pendientes;
  });

  es.addEventListener("alerta", function (ev) {
    const a = JSON.parse(ev.data);
    mostrarToast("ALERTA " + a.tipo + ": placa " + a.placa + " en " + a.caseta);
    if (listaAlertas) {
      const li = document.createElement("li");
      li.style.marginBottom = "0.4rem";
      li.innerHTML =
        '<span class="badge badge-err">' + escapar(a.tipo) + "</span> " +
        "<strong>" + escapar(a.placa) + "</strong> · " +
        escapar(a.caseta) + " · " + escapar(a.fecha_legible);
      listaAlertas.prepend(li);
    }
  });
})();
