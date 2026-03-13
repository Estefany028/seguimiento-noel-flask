const tbodyExterno = document.querySelector("#tabla tbody");
const contSolicitudes = document.getElementById("contenedorSolicitudes");

let personas = [];
let ADMIN_TOKEN = "";

// ============================
// BADGES
// ============================

function badge(text) {

  const t = (text || "").toUpperCase().trim();

  if (t === "VIGENTE" || t === "CUMPLE") {
    return `<span class="badge ok">🟢 ${text}</span>`;
  }

  if (t === "REVISAR" || t === "SIN REGISTRO") {
    return `<span class="badge warn">🟡 ${text}</span>`;
  }

  if (t === "VENCIDA" || t === "BLOQUEADO") {
    return `<span class="badge bad">🔴 ${text}</span>`;
  }

  return `<span class="badge">${text}</span>`;
}

// ============================
// MODAL EXTERNO
// ============================

window.mostrarDetalle = function (motivo) {

  const texto = motivo || "";

  document.getElementById("modalMotivo").innerHTML = texto;

  document.getElementById("modal").style.display = "block";
};

window.cerrarModal = function () {
  document.getElementById("modal").style.display = "none";
};

// ============================
// EXTERNO
// ============================

function normalizarEmpresa(s) {

  return String(s || "").trim();

}

function construirOpcionesEmpresaExterno(data) {

  const select = document.getElementById("filtroEmpresa");

  if (!select) return;

  const empresas = Array.from(
    new Set(
      data.map(p => normalizarEmpresa(p.empresa)).filter(Boolean)
    )
  ).sort((a, b) => a.localeCompare(b, "es"));

  const prev = select.value;

  select.innerHTML =
    `<option value="">Todas las empresas</option>` +
    empresas.map(e => `<option value="${e}">${e}</option>`).join("");

  if (empresas.includes(prev)) {
    select.value = prev;
  }

}

function aplicarFiltrosExterno() {

  const q = (document.getElementById("buscador")?.value || "").trim();

  const empresa =
    (document.getElementById("filtroEmpresa")?.value || "").trim();

  let data = personas.slice();

  if (empresa) {

    data = data.filter(p =>
      normalizarEmpresa(p.empresa) === empresa
    );

  }

  if (q) {

    data = data.filter(p =>
      String(p.cedula || "").includes(q)
    );

  }

  renderTablaExterno(data);
  actualizarStats(data);

}

function renderTablaExterno(data) {

  tbodyExterno.innerHTML = "";

  data.forEach(p => {

    const tr = document.createElement("tr");

    tr.innerHTML = `
      <td>${p.nombre || ""}</td>
      <td>${p.cedula || ""}</td>
      <td>${p.empresa || ""}</td>
      <td>${badge(p.induccion)}</td>
      <td>${badge(p.seguridadSocial)}</td>
      <td>
        ${
          p.estado === "REVISAR" || p.estado === "BLOQUEADO"
            ? `<span class="badge warn btnDetalle" style="cursor:pointer">REVISAR</span>`
          : p.estado === "BLOQUEADO"
            ? `<span class="badge bad">BLOQUEADO</span>`
            : `<span class="badge ok">CUMPLE</span>`
        }
      </td>
    `;

    // guardar el motivo como atributo seguro
    if (p.estado === "REVISAR" || p.estado === "BLOQUEADO") {

      const btn = tr.querySelector(".btnDetalle");

      if (btn) {

        btn.dataset.motivo = p.motivo || "";

        btn.addEventListener("click", function () {

          mostrarDetalle(this.dataset.motivo);

        });

      }

    }

    tbodyExterno.appendChild(tr);

  });

}

// ============================
// CARGAR EXTERNO
// ============================

async function cargarExterno() {

  const r = await fetch("/api/external");

  const data = await r.json();

  personas = data;

  construirOpcionesEmpresaExterno(personas);

  aplicarFiltrosExterno();

  const now = new Date();

  setUpdatePill(`Actualizado: ${now.toLocaleTimeString()}`);

}

// ============================
// LISTENERS
// ============================

const buscador = document.getElementById("buscador");

if (buscador) {
  buscador.addEventListener("input", aplicarFiltrosExterno);
}

const filtroEmpresa = document.getElementById("filtroEmpresa");

if (filtroEmpresa) {
  filtroEmpresa.addEventListener("change", aplicarFiltrosExterno);
}

// ============================
// ADMIN
// ============================

async function cargarAdmin() {

  const r = await fetch("/api/admin/solicitudes", {
    headers: { "X-ADMIN-TOKEN": ADMIN_TOKEN }
  });

  if (r.status === 403) {

    document.getElementById("modo").innerText =
      "⛔ Token inválido";

    return false;

  }

  if (!r.ok) {

    document.getElementById("modo").innerText =
      "⛔ Error cargando admin";

    return false;

  }

  const solicitudes = await r.json();

  document.getElementById("modo").innerText = "✅ Modo Admin";

  document
    .getElementById("vistaExterno")
    .classList.add("hidden");

  document
    .getElementById("vistaAdmin")
    .classList.remove("hidden");

  document
    .getElementById("btnSalirAdmin")
    .classList.remove("hidden");

  renderSolicitudesAdmin(solicitudes);

  return true;

}

function renderSolicitudesAdmin(solicitudes) {

  contSolicitudes.innerHTML = "";

  if (!solicitudes || solicitudes.length === 0) {
    contSolicitudes.innerHTML = `
      <div class="card open">
        <div class="cardHeader">
          <strong>No hay solicitudes activas.</strong>
        </div>
      </div>
    `;
    return;
  }

  solicitudes.forEach(sol => {

    const card = document.createElement("div");
    card.className = "card";

    const personasRows = (sol.personas || []).map(p => {

      return `
        <tr>
          <td>${p.nombre || ""}</td>
          <td>${p.cedula || ""}</td>
          <td>${badge(p.induccion)}</td>
          <td>${badge(p.seguridadSocial)}</td>
          <td>${badge(p.estado)}</td>
          <td>${p.motivo || ""}</td>
          <td>
            <input
              class="consecutivoInput"
              data-row="${p.row}"
              value="${(p.consecutivo || "").trim()}"
              placeholder="Ej: 3553"
            />
          </td>
        </tr>
      `;

    }).join("");

    let cumple = 0;
let revisar = 0;

(sol.personas || []).forEach(p => {

  if ((p.estado || "").toUpperCase() === "CUMPLE") {
    cumple++;
  } else {
    revisar++;
  }

});

let semaforoEmpresa = "🟢";

if (revisar > 0) {
  semaforoEmpresa = "🟡";
}

if (revisar === sol.personas.length) {
  semaforoEmpresa = "🔴";
}

    card.innerHTML = `
      <div class="cardHeader">
        <div>
          <strong>${semaforoEmpresa} ${sol.empresa || ""}</strong> · NIT: ${sol.nit || ""}
          <br>
          👥 ${sol.personas.length} personas ·
          🟢 ${cumple} cumplen ·
          🟡 ${revisar} revisar
          <div class="meta">
            🕒 ${sol.horaIngreso || ""} - ${sol.horaSalida || ""} ·
            📅 ${sol.fechaInicio || ""} → ${sol.fechaFin || ""} ·
            👷 ${sol.interventor || ""} ·
            🔁 Turno: ${sol.turno || ""}             
          </div>
        </div>
        <div class="arrow">▶</div>
      </div>

      <div class="cardBody">

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
            ${personasRows}
          </tbody>
        </table>

      </div>
    `;

    card.querySelector(".cardHeader").addEventListener("click", () => {
      card.classList.toggle("open");
    });

    contSolicitudes.appendChild(card);

  });

}

// ============================
// BOTONES ADMIN
// ============================

document
  .getElementById("btnEntrarAdmin")
  .addEventListener("click", async () => {

    ADMIN_TOKEN =
      document.getElementById("adminToken").value.trim();

    if (!ADMIN_TOKEN) {
      return alert("Ingresa la contraseña de Administrador");
    }

    await cargarAdmin();

  });

document
  .getElementById("btnSalirAdmin")
  .addEventListener("click", async () => {

    ADMIN_TOKEN = "";

    document.getElementById("adminToken").value = "";

    document.getElementById("modo").innerText = "";

    document
      .getElementById("vistaAdmin")
      .classList.add("hidden");

    document
      .getElementById("vistaExterno")
      .classList.remove("hidden");

    document
      .getElementById("btnSalirAdmin")
      .classList.add("hidden");

  });

// ============================
// STATS
// ============================

function actualizarStats(data) {

  const elTotal = document.getElementById("statTotal");

  const elCumple = document.getElementById("statCumple");

  const elRevisar = document.getElementById("statRevisar");

  if (!elTotal) return;

  elTotal.innerText = data.length;

  const cumple =
    data.filter(p =>
      (p.estado || "").toUpperCase() === "CUMPLE"
    ).length;

  const revisar =
    data.filter(p =>
      (p.estado || "").toUpperCase() === "REVISAR"
    ).length;

  elCumple.innerText = cumple;

  elRevisar.innerText = revisar;

}

// ============================
// UPDATE PILL
// ============================

function setUpdatePill(text) {

  const el = document.getElementById("pillUpdate");

  if (el) el.innerText = text;

}

// ============================
// INIT
// ============================

(async function init() {

  await cargarExterno();

  setInterval(cargarExterno, 30000);

})();

