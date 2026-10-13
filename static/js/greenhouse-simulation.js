(() => {
  "use strict";
  const root = document.getElementById("gh-live-simulation");
  if (!root) return;
  const $ = (id) => document.getElementById(id);
  const houseSelect = $("gh-chart-house");
  const metricSelect = $("gh-chart-metric");
  const esc = (s) => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  let snapshot = null;
  const metricNames = {temperature:"Temperatura",humidity:"Humedad",soil_moisture:"Humedad del suelo",tank_level:"Nivel del tanque",light_lux:"Luminosidad"};
  const units = {temperature:"°C",humidity:"%",soil_moisture:"%",tank_level:"%",light_lux:"lux"};
  const num = (v,unit="") => v === null || v === undefined ? "—" : esc(v) + (unit ? " " + unit : "");
  function render() {
    if (!snapshot) return;
    const houses = snapshot.greenhouses || [];
    $("gh-total").textContent = houses.length;
    $("gh-average").textContent = houses.length ? (houses.reduce((s,h)=>s+h.current.temperature,0)/houses.length).toFixed(1)+" °C" : "—";
    $("gh-alert-count").textContent = houses.reduce((s,h)=>s+h.alerts.length,0);
    const cards = $("gh-sim-cards");
    cards.innerHTML = houses.map((h,i) => {
      const v=h.current;
      const alert=h.alerts.length ? '<p class="gh-alert">⚠ '+h.alerts.map(esc).join(" · ")+' (simulado)</p>':"";
      return '<article class="gh-card"><div class="gh-card-head"><div><small>'+esc(h.code)+'</small><h2>Invernadero '+String(i+1).padStart(2,"0")+'</h2></div><span class="gh-status gh-demo">SIMULACIÓN</span></div><p class="muted small">Cultivo de ejemplo: '+esc(h.crop)+'</p>'+alert+'<div class="gh-metrics">'+[
        ["Temperatura",num(v.temperature,"°C")],["Humedad ambiente",num(v.humidity,"%")],["Humedad del suelo",num(v.soil_moisture,"%")],
        ["Luz",num(v.light_lux,"lux")],["Tanque",num(v.tank_level,"%")],
        ["Riego / Ventilación",(v.irrigation_on?"ON":"OFF")+" / "+(v.ventilation_on?"ON":"OFF")]
      ].map(([name,value])=>'<div><span>'+name+'</span><strong>'+value+'</strong></div>').join("")+'</div><div class="gh-card-foot">Valores sintéticos · No hay equipo conectado</div></article>';
    }).join("");
    drawChart();
  }
  function drawChart() {
    if (!snapshot) return;
    const selected=snapshot.greenhouses.find(h=>h.code===houseSelect.value)||snapshot.greenhouses[0];
    const svg=$("gh-trend-svg"),metric=metricSelect.value;
    if(!selected){svg.replaceChildren();return;}
    const pts=selected.history.map(p=>Number(p[metric]));
    let low=Math.min(...pts), high=Math.max(...pts);
    if(high-low<1){high+=1;low-=1;}
    const pad=(high-low)*0.16;high+=pad;low-=pad;
    const left=57,right=872,top=26,bottom=230;
    const x=i=>left+i/(pts.length-1)*(right-left);
    const y=v=>bottom-(v-low)/(high-low)*(bottom-top);
    const path=pts.map((v,i)=>(i?"L":"M")+x(i).toFixed(1)+" "+y(v).toFixed(1)).join(" ");
    const lines=[0,1,2,3,4].map(i=>{const yy=top+(bottom-top)*i/4;const value=high-(high-low)*i/4;return '<line x1="'+left+'" y1="'+yy+'" x2="'+right+'" y2="'+yy+'" stroke="#e1eae2"/><text x="47" y="'+(yy+4)+'" text-anchor="end" fill="#668071" font-size="12">'+value.toFixed(metric==="light_lux"?0:1)+'</text>';}).join("");
    const ticks=[0,24,48,72,96].map(i=>'<text x="'+x(i)+'" y="254" text-anchor="middle" font-size="12" fill="#718477">'+new Date(selected.history[i].at).toLocaleTimeString("es-MX",{hour:"2-digit",minute:"2-digit"})+'</text>').join("");
    svg.innerHTML=lines+ticks+'<path d="'+path+'" fill="none" stroke="#267548" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/><circle cx="'+x(pts.length-1)+'" cy="'+y(pts[pts.length-1])+'" r="5" fill="#267548"/>';
    const avg=pts.reduce((a,b)=>a+b,0)/pts.length;
    const stat=(label,value)=>'<div><small>'+label+'</small><strong>'+value+'</strong></div>';
    $("gh-stats").innerHTML=stat("Mínimo",num(Math.min(...pts).toFixed(1),units[metric]))+stat("Máximo",num(Math.max(...pts).toFixed(1),units[metric]))+stat("Promedio",num(avg.toFixed(1),units[metric]))+stat("Lecturas simuladas",pts.length);
  }
  async function load() {
    try {
      const res=await fetch(root.dataset.api,{credentials:"same-origin",cache:"no-store"});
      if(!res.ok) throw new Error("HTTP "+res.status);
      const data=await res.json();
      if(data.mode!=="simulation") throw new Error("Origen de datos inesperado");
      snapshot=data;
      $("gh-updated").textContent="Actualizado "+new Date(data.generated_at).toLocaleTimeString("es-MX",{hour:"2-digit",minute:"2-digit",second:"2-digit"});
      render();
    }catch(e){$("gh-updated").textContent="Sin actualización: "+e.message;}
  }
  houseSelect.addEventListener("change",drawChart);
  metricSelect.addEventListener("change",drawChart);
  $("gh-refresh").addEventListener("click",load);
  load();
  const timer=setInterval(()=>{if(!document.hidden) load();},30000);
  window.addEventListener("pagehide",()=>clearInterval(timer),{once:true});
})();
