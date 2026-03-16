const tbodyExterno = document.querySelector("#tabla tbody");
const contSolicitudes = document.getElementById("contenedorSolicitudes");
let personas = [];
let ADMIN_TOKEN = "";
let solicitudesAdmin = [];
let filtroAdminActual = "todos";

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
          p.estado === "REVISAR"
            ? `<span class="badge warn btnDetalle" style="cursor:pointer">REVISAR</span>`
          : p.estado === "BLOQUEADO"
            ? `<span class="badge bad btnDetalle" style="cursor:pointer">BLOQUEADO</span>`
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
  solicitudesAdmin = solicitudes;

  const modo = document.getElementById("modo");
    if (modo) modo.innerText = "✅ Modo Admin";

    const vistaExterno = document.getElementById("vistaExterno");
    if (vistaExterno) vistaExterno.classList.add("hidden");

    const vistaAdmin = document.getElementById("vistaAdmin");
    if (vistaAdmin) vistaAdmin.classList.remove("hidden");

    const btnSalirAdmin = document.getElementById("btnSalirAdmin");
    if (btnSalirAdmin) btnSalirAdmin.classList.remove("hidden");

    document.querySelector("#statTotal").parentElement.addEventListener("click", () => {
    filtrarSolicitudesAdmin("todos");
    });

    document.querySelector("#statCumple").parentElement.addEventListener("click", () => {
      filtrarSolicitudesAdmin("cumple");
    });

    document.querySelector("#statRevisar").parentElement.addEventListener("click", () => {
      filtrarSolicitudesAdmin("revisar");
    });

    document.getElementById("buscadorAdmin")?.addEventListener("input", buscarEnSolicitudes);

  filtrarSolicitudesAdmin(filtroAdminActual);

  const now = new Date();
  setUpdatePill("Actualizado: " + now.toLocaleTimeString());

  return true;

}

function renderSolicitudesAdmin(solicitudes) {

  const contSolicitudes = document.getElementById("contenedorSolicitudes");

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
            style="width:90px;"
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

      <div class="adminActions">
        <button class="guardarEmpresa">Guardar cambios</button>
        <span class="estadoCambios">Sin cambios</span>
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
            ${personasRows}
          </tbody>
        </table>

      </div>
    `;

    card.querySelector(".cardHeader").addEventListener("click", () => {
      card.classList.toggle("open");
    });

    contSolicitudes.appendChild(card);

    const btnGuardar = card.querySelector(".guardarEmpresa");

    btnGuardar.addEventListener("click", async () => {

      const inputs = card.querySelectorAll(".consecutivoInput");

      const changes = [];

      inputs.forEach(input => {

        const consecutivo = input.value.trim();
        const row = input.dataset.row;

        if(consecutivo){
          changes.push({
            row: row,
            consecutivo: consecutivo
          });
        }

      });

      if(changes.length === 0){
        alert("No hay consecutivos para guardar");
        return;
      }

      const r = await fetch("/api/admin/consecutivos/batch",{
        method:"POST",
        headers:{
          "Content-Type":"application/json",
          "X-ADMIN-TOKEN": ADMIN_TOKEN
        },
        body: JSON.stringify({
          changes: changes
        })
      });

      const res = await r.json();

      if(res.ok){
        card.querySelector(".estadoCambios").innerText = "✓ Cambios guardados";
      }else{
        alert("Error guardando consecutivos");
      }

    });

    });

}

function filtrarSolicitudesAdmin(tipo) {

  // quitar activo a todos
  document.querySelectorAll(".chip").forEach(c => c.classList.remove("active"));

  if(tipo === "todos"){
    document.querySelector("#statTotal").parentElement.classList.add("active");
  }

  if(tipo === "cumple"){
    document.querySelector("#statCumple").parentElement.classList.add("active");
  }

  if(tipo === "revisar"){
    document.querySelector("#statRevisar").parentElement.classList.add("active");
  }

  filtroAdminActual = tipo;

  if (!solicitudesAdmin || solicitudesAdmin.length === 0) return;

  let filtradas;

  if (tipo === "todos") {
    filtradas = solicitudesAdmin;
  } else {

    filtradas = solicitudesAdmin.map(sol => {

      const personasFiltradas = (sol.personas || []).filter(p => {

        const estado = (p.estado || "").toUpperCase();

        if (tipo === "cumple") return estado === "CUMPLE";

        if (tipo === "revisar") return estado !== "CUMPLE";

      });

      return {
        ...sol,
        personas: personasFiltradas
      };

    }).filter(sol => sol.personas.length > 0);

  }

  renderSolicitudesAdmin(filtradas);

}

function buscarEnSolicitudes(){

  const q = document.getElementById("buscadorAdmin")?.value.trim();

  if(!q){
    filtrarSolicitudesAdmin(filtroAdminActual);
    return;
  }

  const filtradas = solicitudesAdmin.map(sol=>{

    const personas = (sol.personas || []).filter(p=>{
      return String(p.cedula || "").includes(q);
    });

    return {
      ...sol,
      personas
    };

  }).filter(sol=>sol.personas.length>0);

  renderSolicitudesAdmin(filtradas);

}

// ============================
// BOTONES ADMIN
// ============================

const btnEntrarAdmin = document.getElementById("btnEntrarAdmin");

if (btnEntrarAdmin) {
  btnEntrarAdmin.addEventListener("click", async () => {

    ADMIN_TOKEN =
      document.getElementById("adminToken").value.trim();

    if (!ADMIN_TOKEN) {
      return alert("Ingresa la contraseña de Administrador");
    }

    await cargarAdmin();

  });
}

const btnSalirAdmin = document.getElementById("btnSalirAdmin");

if (btnSalirAdmin) {
  btnSalirAdmin.addEventListener("click", async () => {

    ADMIN_TOKEN = "";

    document.getElementById("adminToken").value = "";

    document.getElementById("modo").innerText = "";

    document
      .getElementById("vistaAdmin")
      .classList.add("hidden");

    document
      .getElementById("vistaExterno")
      .classList.remove("hidden");

    btnSalirAdmin.classList.add("hidden");

  });
}
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

  if (window.__MODE__ === "admin") {

    ADMIN_TOKEN = "admin"; // si no usas token visual
    await cargarAdmin();

  } else {

    await cargarExterno();
    setInterval(cargarExterno, 30000);

  }

})();;

