const tbodyExterno = document.querySelector("#tabla tbody");
const contSolicitudes = document.getElementById("contenedorSolicitudes");

let personas = [];
let ADMIN_TOKEN = "";

let EMPRESA_SELECTED = ""; // filtro empresa externo

// ===== badges =====
function badge(text) {
  if (text === "VIGENTE" || text === "CUMPLE" || text === "LISTO") {
    return `<span class="badge ok">${text}</span>`;
  }
  if (text === "VENCIDA" || text === "NO CUMPLE") {
    return `<span class="badge bad">${text}</span>`;
  }
  return `<span class="badge warn">${text || ""}</span>`;
}

// ===== modal externo =====
window.mostrarDetalle = function (motivo) {
  document.getElementById("modalMotivo").innerText = "❌ " + (motivo || "");
  document.getElementById("modal").style.display = "block";
};

window.cerrarModal = function () {
  document.getElementById("modal").style.display = "none";
};

// ============================
// EXTERNO: filtro + render
// ============================
function normalizarEmpresa(s) {
  return String(s || "").trim();
}

function construirOpcionesEmpresaExterno(dataVisibleActiva) {
  const select = document.getElementById("filtroEmpresa");
  if (!select) return;

  // empresas solo de lo ACTIVO que llega (/api/external ya filtra activos)
  const empresas = Array.from(
    new Set(dataVisibleActiva.map(p => normalizarEmpresa(p.empresa)).filter(Boolean))
  ).sort((a, b) => a.localeCompare(b, "es"));

  const prev = select.value;
  select.innerHTML = `<option value="">Todas las empresas</option>` +
    empresas.map(e => `<option value="${e}">${e}</option>`).join("");

  // mantener selección si aún existe
  if (empresas.includes(prev)) select.value = prev;
}

function aplicarFiltrosExterno() {
  const q = (document.getElementById("buscador")?.value || "").trim();
  const emp = (document.getElementById("filtroEmpresa")?.value || "").trim();

  let data = personas.slice();

  // filtro empresa
  if (emp) data = data.filter(p => normalizarEmpresa(p.empresa) === emp);

  // filtro cédula (solo afecta la vista, no el dataset base)
  if (q) data = data.filter(p => String(p.cedula || "").includes(q));

  renderTablaExterno(data);
}

function renderTablaExterno(data) {
  tbodyExterno.innerHTML = "";

  data.forEach(p => {
    const tr = document.createElement("tr");
    const motivoSafe = (p.motivo || "").replace(/'/g, "\\'");

    tr.innerHTML = `
      <td>${p.nombre || ""}</td>
      <td>${p.cedula || ""}</td>
      <td>${p.empresa || ""}</td>
      <td>${badge(p.induccion)}</td>
      <td>${badge(p.seguridadSocial)}</td>
      <td>
        ${p.estado === "REVISAR"
          ? `<span class="badge warn" style="cursor:pointer"
              onclick="mostrarDetalle('${motivoSafe}')">REVISAR</span>`
          : `<span class="badge ok">CUMPLE</span>`
        }
      </td>
    `;
    tbodyExterno.appendChild(tr);
  });
}

async function cargarExterno() {
  const r = await fetch("/api/external");
  const data = await r.json();

  personas = data;

  construirOpcionesEmpresaExterno(personas);
  aplicarFiltrosExterno();

  const now = new Date();
  setUpdatePill(`Actualizado: ${now.toLocaleTimeString()}`);
}

// listeners externo
document.getElementById("filtroEmpresa")?.addEventListener("change", aplicarFiltrosExterno);
document.getElementById("filtroEmpresa").addEventListener("change", aplicarFiltrosExterno);

// ============================
// ADMIN: render con “Guardar cambios” por solicitud
// ============================

// guarda cambios por solicitud: { keySolicitud: Map(row -> consecutivo) }
const pendingBySolicitud = new Map();

function getSolicitudKey(sol) {
  // debe coincidir con lo que llega del backend como agrupación.
  // si tu backend no envía "key", usamos combinación estable.
  return [
    sol.empresa || "",
    sol.nit || "",
    sol.horaIngreso || "",
    sol.horaSalida || "",
    sol.tipoTrabajo || "",
    sol.extension || "",
    sol.interventor || "",
    sol.turno || "",
    sol.fechaInicio || "",
    sol.fechaFin || ""
  ].join("|");
}

function setPending(solKey, row, value) {
  if (!pendingBySolicitud.has(solKey)) pendingBySolicitud.set(solKey, new Map());
  pendingBySolicitud.get(solKey).set(row, value);
}

function countPending(solKey) {
  return pendingBySolicitud.has(solKey) ? pendingBySolicitud.get(solKey).size : 0;
}

function renderSolicitudesAdmin(solicitudes) {
  contSolicitudes.innerHTML = "";

  if (!solicitudes || solicitudes.length === 0) {
    contSolicitudes.innerHTML = `<div class="card open"><div class="cardHeader">
      <strong>No hay solicitudes activas.</strong></div></div>`;
    return;
  }

  solicitudes.forEach(sol => {
    const solKey = getSolicitudKey(sol);

    const card = document.createElement("div");
    card.className = "card";
    card.dataset.solkey = solKey;

    card.innerHTML = `
      <div class="cardHeader">
        <div>
          <strong>${sol.empresa || ""}</strong> · NIT: ${sol.nit || ""}
          <div class="meta">
            🕒 ${sol.horaIngreso || ""} - ${sol.horaSalida || ""} ·
            🧩 ${sol.tipoTrabajo || ""} ·
            📞 Ext: ${sol.extension || ""} ·
            👷 ${sol.interventor || ""} ·
            🔁 Turno: ${sol.turno || ""} ·
            📅 ${sol.fechaInicio || ""} → ${sol.fechaFin || ""}
          </div>
        </div>
        <div class="arrow">▶</div>
      </div>

      <div class="cardBody">

        <!-- Barra de acciones por solicitud -->
        <div class="admin-actions" style="display:flex; gap:10px; align-items:center; margin-bottom:10px;">
          <button class="btnSmall" data-action="saveSolicitud">💾 Guardar cambios</button>
          <span class="pending" style="font-size:12px; color:#555;">
            ${countPending(solKey) ? `✳️ ${countPending(solKey)} cambios pendientes` : "— Sin cambios"}
          </span>
          <span class="saveStatus" style="font-size:12px; color:#137333;"></span>
        </div>

        <table class="adminTable">
          <thead>
            <tr>
              <th>Nombre</th>
              <th>CC</th>
              <th>Ind.</th>
              <th>SS</th>
              <th>Estado</th>
              <th>Motivo</th>
              <th>Consecutivo</th>
            </tr>
          </thead>
          <tbody>
            ${(sol.personas || []).map(p => `
              <tr>
                <td>${p.nombre || ""}</td>
                <td>${p.cedula || ""}</td>
                <td>${badge(p.induccion)}</td>
                <td>${badge(p.seguridadSocial)}</td>
                <td>${badge(p.estado)}</td>
                <td>${p.motivo || ""}</td>
                <td>
                  <input class="consecutivoInput"
                    data-row="${p.row}"
                    data-original="${(p.consecutivo || "").trim()}"
                    value="${(p.consecutivo || "").trim()}"
                    placeholder="Ej: 3553" />
                </td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;

    // Toggle card
    card.querySelector(".cardHeader").addEventListener("click", () => {
      card.classList.toggle("open");
    });

    // track cambios en inputs
    card.querySelectorAll(".consecutivoInput").forEach(inp => {
      inp.addEventListener("input", () => {
        const row = Number(inp.dataset.row);
        const original = (inp.dataset.original || "").trim();
        const val = (inp.value || "").trim();

        const statusEl = card.querySelector(".saveStatus");
        if (statusEl) statusEl.textContent = "";

        if (val && val !== original) {
          setPending(solKey, row, val);
        } else {
          // si volvió al original o quedó vacío, lo quitamos de pendientes
          if (pendingBySolicitud.has(solKey)) {
            pendingBySolicitud.get(solKey).delete(row);
            if (pendingBySolicitud.get(solKey).size === 0) pendingBySolicitud.delete(solKey);
          }
        }

        const pendingEl = card.querySelector(".pending");
        const n = countPending(solKey);
        if (pendingEl) pendingEl.textContent = n ? `✳️ ${n} cambios pendientes` : "— Sin cambios";
      });
    });

    // botón guardar cambios (por solicitud)
    card.querySelector('[data-action="saveSolicitud"]').addEventListener("click", async (e) => {
      e.stopPropagation();

      const map = pendingBySolicitud.get(solKey);
      const btn = e.currentTarget;
      const pendingEl = card.querySelector(".pending");
      const statusEl = card.querySelector(".saveStatus");

      if (!map || map.size === 0) {
        if (statusEl) statusEl.textContent = "No hay cambios";
        return;
      }

      const changes = Array.from(map.entries()).map(([row, consecutivo]) => ({ row, consecutivo }));

      btn.disabled = true;
      if (statusEl) statusEl.textContent = "Guardando...";

      const r = await fetch("/api/admin/consecutivos/batch", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-ADMIN-TOKEN": ADMIN_TOKEN
        },
        body: JSON.stringify({ changes })
      });

      btn.disabled = false;

      if (!r.ok) {
        if (statusEl) statusEl.style.color = "#b71c1c";
        if (statusEl) statusEl.textContent = "Error al guardar";
        return;
      }

      // marcar como guardado: actualizar originales y limpiar pendientes
      changes.forEach(ch => {
        const input = card.querySelector(`.consecutivoInput[data-row="${ch.row}"]`);
        if (input) input.dataset.original = String(ch.consecutivo).trim();
      });

      pendingBySolicitud.delete(solKey);

      if (pendingEl) pendingEl.textContent = "— Sin cambios";
      if (statusEl) statusEl.style.color = "#137333";
      if (statusEl) statusEl.textContent = "✅ Cambios guardados";
    });

    contSolicitudes.appendChild(card);
  });
}

async function cargarAdmin() {
  const r = await fetch("/api/admin/solicitudes", {
    headers: { "X-ADMIN-TOKEN": ADMIN_TOKEN }
  });

  if (r.status === 403) {
    document.getElementById("modo").innerText = "⛔ Token inválido";
    return false;
  }

  if (!r.ok) {
    document.getElementById("modo").innerText = "⛔ Error cargando admin";
    return false;
  }

  const solicitudes = await r.json();

  document.getElementById("modo").innerText = "✅ Modo Admin";
  document.getElementById("vistaExterno").classList.add("hidden");
  document.getElementById("vistaAdmin").classList.remove("hidden");
  document.getElementById("btnSalirAdmin").classList.remove("hidden");

  renderSolicitudesAdmin(solicitudes);
  return true;
}

// botones admin
document.getElementById("btnEntrarAdmin").addEventListener("click", async () => {
  ADMIN_TOKEN = document.getElementById("adminToken").value.trim();
  if (!ADMIN_TOKEN) return alert("Ingresa el token admin");
  await cargarAdmin();
});

document.getElementById("btnSalirAdmin").addEventListener("click", async () => {
  ADMIN_TOKEN = "";
  document.getElementById("adminToken").value = "";
  document.getElementById("modo").innerText = "";
  document.getElementById("vistaAdmin").classList.add("hidden");
  document.getElementById("vistaExterno").classList.remove("hidden");
  document.getElementById("btnSalirAdmin").classList.add("hidden");
});

// init
(async function init() {
  await cargarExterno();
  setInterval(cargarExterno, 30000);
})();

function setUpdatePill(text) {
  const el = document.getElementById("pillUpdate");
  if (el) el.innerText = text;
}

function actualizarStats(data) {
  const elTotal = document.getElementById("statTotal");
  const elCumple = document.getElementById("statCumple");
  const elRevisar = document.getElementById("statRevisar");
  if (!elTotal || !elCumple || !elRevisar) return;

  // "Activos" = los que estás mostrando (ya vienen activos desde backend)
  elTotal.innerText = data.length;

  const cumple = data.filter(p => (p.estado || "").toUpperCase() === "CUMPLE").length;
  const revisar = data.filter(p => (p.estado || "").toUpperCase() === "REVISAR").length;

  elCumple.innerText = cumple;
  elRevisar.innerText = revisar;
}

function construirOpcionesEmpresaExterno(data) {
  const sel = document.getElementById("filtroEmpresa");
  if (!sel) return;

  // empresas SOLO del listado actual (activos)
  const empresas = Array.from(
    new Set((data || []).map(p => (p.empresa || "").trim()).filter(Boolean))
  ).sort((a, b) => a.localeCompare(b, "es"));

  const prev = sel.value;

  sel.innerHTML = `<option value="">Todas las empresas</option>` +
    empresas.map(e => `<option value="${e}">${e}</option>`).join("");

  // conservar selección si aún existe
  if ([...sel.options].some(o => o.value === prev)) sel.value = prev;
}

function aplicarFiltrosExterno() {
  const q = (document.getElementById("buscador")?.value || "").trim();
  const sel = document.getElementById("filtroEmpresa");
  const empresa = (sel?.value || "").trim();

  let data = personas.slice();

  if (empresa) {
    data = data.filter(p => (p.empresa || "").trim() === empresa);
  }

  if (q) {
    data = data.filter(p => String(p.cedula || "").includes(q));
  }

  renderTablaExterno(data);
  actualizarStats(data);
}
