(function () {
  const sseBadge = document.getElementById("sse-estado");
  const motorBadge = document.getElementById("motor-badge");
  const tbody = document.getElementById("tabla-pasos-body");
  const kpiPasos = document.getElementById("kpi-pasos");
  const kpiRec = document.getElementById("kpi-recaudacion");
  const kpiAlertas = document.getElementById("kpi-alertas");
  const listaAlertas = document.getElementById("lista-alertas");
  const toasts = document.getElementById("toast-container");

  const vivoImagen = document.getElementById("vivo-imagen");
  const vivoPlaceholder = document.getElementById("vivo-placeholder");
  const vivoCaseta = document.getElementById("vivo-caseta");
  const vivoAviso = document.getElementById("vivo-aviso");
  const vivoPlaca = document.getElementById("vivo-placa");
  const vivoCat = document.getElementById("vivo-cat");
  const vivoEjes = document.getElementById("vivo-ejes");
  const vivoPas = document.getElementById("vivo-pas");
  const vivoLat = document.getElementById("vivo-lat");

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

  function mostrarToast(texto, ok) {
    if (!toasts) return;
    const el = document.createElement("div");
    el.className = "toast";
    if (ok) el.style.background = "#166534";
    el.textContent = texto;
    toasts.appendChild(el);
    setTimeout(() => el.remove(), 6500);
  }

  function actualizarMonitorVivo(d) {
    const srcImg = d.imagen_anotada || d.imagen_url;
    if (srcImg && vivoImagen) {
      vivoImagen.src = srcImg;
      vivoImagen.style.display = "block";
      if (vivoPlaceholder) vivoPlaceholder.style.display = "none";
    }
    if (vivoCaseta && (d.caseta || d.caseta_nombre)) {
      vivoCaseta.textContent = d.caseta || d.caseta_nombre;
      vivoCaseta.className = "badge badge-info";
    }
    if (vivoPlaca) vivoPlaca.textContent = d.placa || d.placa_normalizada || "Buscando...";
    if (vivoCat) vivoCat.textContent = d.categoria || d.categoria_detectada || "---";
    if (vivoEjes) {
      const ej = d.ejes ?? d.ejes_detectados;
      vivoEjes.textContent = ej != null ? ej + (d.ruedas != null ? " (" + d.ruedas + " ruedas)" : "") : "-";
    }
    if (vivoPas) vivoPas.textContent = d.pasajeros != null ? d.pasajeros : "-";
    if (vivoLat) vivoLat.textContent = d.latencia_ms != null ? d.latencia_ms + " ms" : "-";

    if (motorBadge) {
      if (d.mock) {
        motorBadge.textContent = "Respaldo Mock";
        motorBadge.className = "badge badge-warn";
      } else if (d.modo_m1_local) {
        motorBadge.textContent = "M1 Local (Colab apagado)";
        motorBadge.className = "badge badge-warn";
      } else {
        motorBadge.textContent = "IA Colab GPU Activa";
        motorBadge.className = "badge badge-ok";
      }
    }

    if (vivoAviso) {
      if (d.aviso) {
        vivoAviso.textContent = d.aviso;
        vivoAviso.style.display = "block";
      } else {
        vivoAviso.style.display = "none";
      }
    }
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

  es.addEventListener("deteccion_vivo", function (ev) {
    actualizarMonitorVivo(JSON.parse(ev.data));
  });

  es.addEventListener("paso", function (ev) {
    const p = JSON.parse(ev.data);
    actualizarMonitorVivo(p);
    mostrarToast("Vehículo registrado: " + p.placa_normalizada + " (" + p.estado + " · Bs " + Number(p.monto || 0).toFixed(2) + ")", p.estado === "OK");

    if (!tbody) return;
    const vacio = document.getElementById("fila-vacia");
    if (vacio) vacio.remove();

    const tr = document.createElement("tr");
    tr.className = "row-flash";
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
    mostrarToast("ALERTA " + a.tipo + ": placa " + a.placa + " en " + a.caseta, false);
    if (listaAlertas) {
      const vacia = document.getElementById("alertas-vacia");
      if (vacia) vacia.remove();
      const li = document.createElement("li");
      li.style.marginBottom = "0.4rem";
      li.innerHTML =
        '<span class="badge badge-err">' + escapar(a.tipo) + "</span> " +
        "<strong>" + escapar(a.placa) + "</strong> · " +
        escapar(a.caseta) + " · " + escapar(a.fecha_legible);
      listaAlertas.prepend(li);
    }
  });

  // Simulador / Analizador directo desde Web (foto o cámara PC)
  const formWeb = document.getElementById("form-probar-web");
  const btnProbar = document.getElementById("btn-probar-web");
  const resWeb = document.getElementById("web-resultado");

  async function enviarBlobFrame(archivoOBlob, nombreArchivo) {
    const casetaSel = document.getElementById("web-caseta");
    if (!casetaSel) return;
    const fd = new FormData();
    fd.append("caseta_id", casetaSel.value);
    fd.append("imagen", archivoOBlob, nombreArchivo || "captura.jpg");

    if (btnProbar) btnProbar.disabled = true;
    if (resWeb) resWeb.innerHTML = '<span style="color:var(--muted);">Analizando imagen con M1 + M2 + M3 + Pasajeros...</span>';
    try {
      const r = await fetch("/panel/probar-frame", { method: "POST", body: fd });
      const d = await r.json();
      if (!r.ok) {
        if (resWeb) resWeb.innerHTML = '<div class="flash flash-err">Error: ' + escapar(d.detail || r.statusText) + "</div>";
        return;
      }
      actualizarMonitorVivo(d);
      if (d.registrado) {
        resWeb.innerHTML =
          '<div class="flash flash-ok">Paso registrado: <strong>' + escapar(d.placa) +
          "</strong> · Tipo: " + escapar(d.categoria) +
          " · Ejes: " + escapar(d.ejes) +
          " · Tarifa: Bs " + Number(d.monto || 0).toFixed(2) +
          " (" + escapar(d.estado) + ")</div>";
      } else {
        resWeb.innerHTML =
          '<div class="flash" style="background:var(--info-bg);color:var(--info-fg);">Resultado: <strong>' +
          escapar(d.motivo) + "</strong>" + (d.placa ? " · Placa leída: " + escapar(d.placa) : "") + "</div>";
      }
    } catch (err) {
      if (resWeb) resWeb.innerHTML = '<div class="flash flash-err">Error de red: ' + escapar(err) + "</div>";
    } finally {
      if (btnProbar) btnProbar.disabled = false;
    }
  }

  if (formWeb) {
    formWeb.addEventListener("submit", function (e) {
      e.preventDefault();
      const inp = document.getElementById("web-imagen");
      if (!inp || !inp.files || !inp.files[0]) return;
      enviarBlobFrame(inp.files[0], inp.files[0].name);
    });
  }

  const btnCamPc = document.getElementById("btn-camara-pc");
  const boxCamPc = document.getElementById("box-camara-pc");
  const videoPc = document.getElementById("video-pc");
  const btnCapPc = document.getElementById("btn-capturar-pc");
  const btnCerPc = document.getElementById("btn-cerrar-pc");
  let streamPc = null;

  if (btnCamPc) {
    btnCamPc.onclick = async function () {
      try {
        streamPc = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
        videoPc.srcObject = streamPc;
        boxCamPc.style.display = "block";
      } catch (err) {
        alert("No se pudo acceder a la cámara del navegador: " + err);
      }
    };
  }
  if (btnCerPc) {
    btnCerPc.onclick = function () {
      if (streamPc) streamPc.getTracks().forEach((t) => t.stop());
      streamPc = null;
      boxCamPc.style.display = "none";
    };
  }
  if (btnCapPc) {
    btnCapPc.onclick = function () {
      if (!videoPc || !videoPc.videoWidth) return;
      const canvas = document.createElement("canvas");
      canvas.width = videoPc.videoWidth;
      canvas.height = videoPc.videoHeight;
      canvas.getContext("2d").drawImage(videoPc, 0, 0);
      canvas.toBlob(function (blob) {
        if (blob) enviarBlobFrame(blob, "webcam.jpg");
      }, "image/jpeg", 0.85);
    };
  }
})();
