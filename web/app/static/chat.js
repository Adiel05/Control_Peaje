(function () {
  const caja = document.getElementById("chat-mensajes");
  const form = document.getElementById("form-chat");
  const inputTxt = document.getElementById("chat-texto");
  const inputImg = document.getElementById("chat-imagen");
  const btnEnviar = document.getElementById("btn-enviar");
  const historial = [];

  function agregarBurbuja(rol, texto, sugerencias) {
    const wrap = document.createElement("div");
    wrap.className = "msg " + (rol === "usuario" ? "msg-user" : "msg-bot");
    wrap.textContent = texto;

    if (sugerencias && sugerencias.length > 0) {
      const chips = document.createElement("div");
      chips.className = "chips";
      sugerencias.forEach((s) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "chip";
        btn.textContent = "¿Quisiste decir " + s + "?";
        btn.onclick = () => enviarConsulta("Consultar placa " + s, null);
        chips.appendChild(btn);
      });
      wrap.appendChild(chips);
    }

    caja.appendChild(wrap);
    caja.scrollTop = caja.scrollHeight;
  }

  async function enviarConsulta(texto, archivo) {
    if (!texto && !archivo) return;
    const etiquetaUsuario = texto || ("[Imagen enviada: " + archivo.name + "]");
    agregarBurbuja("usuario", etiquetaUsuario, null);

    const fd = new FormData();
    if (texto) fd.append("mensaje", texto);
    if (archivo) fd.append("imagen", archivo);
    fd.append("historial", JSON.stringify(historial.slice(-6)));

    btnEnviar.disabled = true;
    try {
      const resp = await fetch("/api/v1/agente/chat", { method: "POST", body: fd });
      const data = await resp.json();
      if (!resp.ok) {
        agregarBurbuja("bot", "Error: " + (data.detail || resp.statusText), null);
      } else {
        const meta = data.fuente ? " (" + data.fuente + ")" : "";
        agregarBurbuja("bot", data.respuesta + meta, data.sugerencias || []);
        historial.push({ rol: "usuario", texto: etiquetaUsuario });
        historial.push({ rol: "asistente", texto: data.respuesta });
      }
    } catch (err) {
      agregarBurbuja("bot", "Error de red al consultar el agente.", null);
    } finally {
      btnEnviar.disabled = false;
    }
  }

  if (form) {
    form.addEventListener("submit", async function (ev) {
      ev.preventDefault();
      const texto = inputTxt.value.trim();
      const archivo = inputImg.files && inputImg.files[0] ? inputImg.files[0] : null;
      if (!texto && !archivo) return;
      inputTxt.value = "";
      inputImg.value = "";
      await enviarConsulta(texto, archivo);
    });
  }
})();
