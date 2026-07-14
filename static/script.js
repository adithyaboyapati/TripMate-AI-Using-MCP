// =========================================================
//  TripMate AI — Script v2
// =========================================================

let currentThreadId = localStorage.getItem("travel_thread_id") || null;
let latestAnswerMarkdown = "";
let latestFlightData = "";
let latestHotelData = "";
let latestItineraryData = "";
let loadingTimer = null;
let currentStageIndex = 0;

const STAGES = [
    { id: "flight",    msg: "✈️  Searching live flights...",           dur: 4000 },
    { id: "hotel",     msg: "🏨  Finding best hotels...",              dur: 4000 },
    { id: "itinerary", msg: "📝  Crafting your itinerary...",          dur: 5000 },
    { id: "final",     msg: "✨  Formatting your travel plan...",      dur: 4000 },
];

// ---- Star canvas background ----
(function initStars() {
    const canvas = document.getElementById("starCanvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    let W, H, stars = [];
    function resize() { W = canvas.width = window.innerWidth; H = canvas.height = window.innerHeight; }
    function makeStar() { return { x: Math.random()*W, y: Math.random()*H, r: Math.random()*1.2+0.2, a: Math.random()*0.6+0.1, vx: (Math.random()-0.5)*0.12, vy: (Math.random()-0.5)*0.12 }; }
    resize();
    for (let i = 0; i < 100; i++) stars.push(makeStar());
    window.addEventListener("resize", resize);
    function draw() {
        ctx.clearRect(0, 0, W, H);
        stars.forEach(s => {
            s.x += s.vx; s.y += s.vy;
            if (s.x < 0) s.x = W; if (s.x > W) s.x = 0;
            if (s.y < 0) s.y = H; if (s.y > H) s.y = 0;
            ctx.beginPath();
            ctx.arc(s.x, s.y, s.r, 0, Math.PI*2);
            ctx.fillStyle = `rgba(180,200,255,${s.a})`;
            ctx.fill();
        });
        requestAnimationFrame(draw);
    }
    draw();
})();

// ---- DOM ready ----
document.addEventListener("DOMContentLoaded", function () {
    const ta = document.getElementById("userInput");
    const cc = document.getElementById("charCount");
    const cw = document.querySelector(".char-counter");
    if (ta && cc) {
        ta.addEventListener("input", function () {
            const len = this.value.length;
            cc.textContent = len;
            if (cw) { cw.classList.toggle("warning", len > 750); cw.classList.toggle("danger", len > 900); }
            this.style.height = "auto";
            this.style.height = Math.max(155, this.scrollHeight) + "px";
        });
    }
    renderHistory();
});

// ---- Quick prompt ----
function setPrompt(text) {
    const ta = document.getElementById("userInput");
    ta.value = text;
    ta.dispatchEvent(new Event("input"));
    ta.focus();
}

// ---- Status ----
function setStatus(state) {
    const pill = document.getElementById("statusPill");
    const dot  = document.getElementById("statusDot");
    const txt  = document.getElementById("statusText");
    if (!pill) return;
    if (state === "busy") { pill.classList.add("busy"); if (txt) txt.textContent = "Working..."; }
    else { pill.classList.remove("busy"); if (txt) txt.textContent = "Ready"; }
}

// ---- Loading ----
function setLoading(isLoading) {
    const btn     = document.getElementById("sendBtn");
    const btnTxt  = document.getElementById("btnText");
    const btnIcon = document.getElementById("btnIcon");
    const btnArr  = document.getElementById("btnArrow");
    const loader  = document.getElementById("btnLoader");
    const idle    = document.getElementById("agentsIdle");
    const stepper = document.getElementById("agentStepper");
    const quick   = document.getElementById("quickPromptsSection");

    btn.disabled = isLoading;

    if (isLoading) {
        btnTxt.classList.add("hidden");
        if (btnIcon) btnIcon.classList.add("hidden");
        if (btnArr)  btnArr.classList.add("hidden");
        loader.classList.remove("hidden");
        if (idle)    idle.classList.add("hidden");
        if (stepper) stepper.classList.remove("hidden");
        if (quick)   quick.classList.add("hidden");
        setStatus("busy");
        startStages();
    } else {
        btnTxt.classList.remove("hidden");
        if (btnIcon) btnIcon.classList.remove("hidden");
        if (btnArr)  btnArr.classList.remove("hidden");
        loader.classList.add("hidden");
        if (idle)    idle.classList.remove("hidden");
        if (stepper) stepper.classList.add("hidden");
        if (quick)   quick.classList.remove("hidden");
        setStatus("idle");
        stopStages();
        resetStages();
    }
}

function resetStages() {
    STAGES.forEach(s => {
        const el = document.getElementById("step-" + s.id);
        if (el) el.classList.remove("active", "done");
        const st = document.getElementById("status-" + s.id);
        if (st) st.textContent = "Waiting...";
        const bg = document.getElementById("badge-" + s.id);
        if (bg) bg.textContent = "·";
    });
    const msg = document.getElementById("loadingMsg");
    if (msg) msg.textContent = "Initializing pipeline...";
    currentStageIndex = 0;
}

function startStages() { currentStageIndex = 0; runStage(); }

function runStage() {
    if (currentStageIndex >= STAGES.length) return;
    const s = STAGES[currentStageIndex];

    // Mark previous done
    if (currentStageIndex > 0) {
        const prev = STAGES[currentStageIndex - 1];
        const pEl = document.getElementById("step-" + prev.id);
        if (pEl) { pEl.classList.remove("active"); pEl.classList.add("done"); }
        const pSt = document.getElementById("status-" + prev.id);
        if (pSt) pSt.textContent = "Done ✓";
        const pBg = document.getElementById("badge-" + prev.id);
        if (pBg) pBg.textContent = "✓";
    }

    // Mark current active
    const el = document.getElementById("step-" + s.id);
    if (el) el.classList.add("active");
    const st = document.getElementById("status-" + s.id);
    if (st) st.textContent = "Running...";

    // Loading message
    const msg = document.getElementById("loadingMsg");
    if (msg) { msg.style.animation = "none"; void msg.offsetWidth; msg.style.animation = "fpop 0.4s ease"; msg.textContent = s.msg; }

    currentStageIndex++;
    loadingTimer = setTimeout(runStage, s.dur);
}

function stopStages() { if (loadingTimer) { clearTimeout(loadingTimer); loadingTimer = null; } }

// ---- Error ----
function showError(msg) {
    const box = document.getElementById("errorBox");
    box.innerHTML = `<strong>⚠️</strong> ${msg}`;
    box.classList.remove("hidden");
}
function hideError() {
    const box = document.getElementById("errorBox");
    box.classList.add("hidden");
    box.textContent = "";
}

// ---- Tab switching ----
function switchTab(name) {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.toggle("hidden", p.id !== "tab-" + name));
}

// ---- Show results ----
function showResult(answer, flightData, hotelData, itineraryData, threadId, llmCalls) {
    latestAnswerMarkdown = answer || "";
    latestFlightData     = flightData || "";
    latestHotelData      = hotelData || "";
    latestItineraryData  = itineraryData || "";

    function renderMd(id, content) {
        const el = document.getElementById(id);
        if (!el) return;
        const text = content != null ? String(content).trim() : "";
        if (text) {
            el.innerHTML = (typeof marked !== "undefined") ? marked.parse(text) : text;
        } else {
            el.innerHTML = `<p style="color:#4b5a72;font-style:italic;">No data available for this section.</p>`;
        }
    }

    renderMd("resultBox",    answer);
    renderMd("flightBox",    flightData);
    renderMd("hotelBox",     hotelData);
    renderMd("itineraryBox", itineraryData);

    const ti = document.getElementById("threadInfo");
    const li = document.getElementById("llmCallsInfo");
    if (ti) ti.textContent = `Thread: ${threadId || "—"}`;
    if (li) li.textContent = `Agents: ${llmCalls || 4} calls`;

    const rs = document.getElementById("resultSection");
    rs.classList.remove("hidden");
    switchTab("full");
    setTimeout(() => rs.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
}

// ---- Send message ----
async function sendMessage() {
    hideError();
    const input = document.getElementById("userInput");
    const message = input.value.trim();
    if (!message) { showError("Please enter your travel request first."); return; }

    setLoading(true);
    try {
        const res = await fetch("/api/travel", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message, thread_id: currentThreadId })
        });
        const data = await res.json();
        if (!res.ok || !data.success) throw new Error(data.error || "Something went wrong. Please try again.");
        currentThreadId = data.thread_id;
        localStorage.setItem("travel_thread_id", currentThreadId);
        showResult(data.answer, data.flight_results, data.hotel_results, data.itinerary, data.thread_id, data.llm_calls);
        addToHistory(message);
    } catch (err) {
        showError(err.message);
    } finally {
        setLoading(false);
    }
}

// ---- New trip ----
function newTrip() {
    document.getElementById("resultSection").classList.add("hidden");
    const ta = document.getElementById("userInput");
    ta.value = "";
    ta.dispatchEvent(new Event("input"));
    ta.focus();
    hideError();
    currentThreadId = null;
    localStorage.removeItem("travel_thread_id");
    window.scrollTo({ top: 0, behavior: "smooth" });
}

// ---- Copy ----
function copyResult() {
    const text = latestAnswerMarkdown || document.getElementById("resultBox").innerText;
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => {
        const btn = document.getElementById("copyBtn");
        const old = btn.innerHTML;
        btn.innerHTML = "✅ Copied!";
        setTimeout(() => btn.innerHTML = old, 1500);
    }).catch(() => showError("Could not copy to clipboard."));
}

// ---- Share ----
function shareResult() {
    const summary = latestAnswerMarkdown.substring(0, 280) + "...";
    const text = `🗺️ My AI Travel Plan from TripMate AI:\n\n${summary}\n\nGenerate yours at TripMate AI!`;
    if (navigator.share) {
        navigator.share({ title: "TripMate AI Travel Plan", text }).catch(() => {});
    } else {
        navigator.clipboard.writeText(text).then(() => {
            const btn = document.getElementById("shareBtn");
            const old = btn.innerHTML;
            btn.innerHTML = "✅ Copied!";
            setTimeout(() => btn.innerHTML = old, 1500);
        });
    }
}

// ---- PDF ----
function downloadPDF() {
    const content = document.getElementById("pdfContent");
    if (!latestAnswerMarkdown || !content) { showError("No travel plan to download."); return; }
    const btn = document.getElementById("downloadBtn");
    const old = btn.innerHTML;
    btn.innerHTML = "⏳ Preparing...";
    btn.disabled = true;
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("hidden"));
    const opts = {
        margin: 0.5,
        filename: `tripmate-plan-${Date.now()}.pdf`,
        image: { type: "jpeg", quality: 0.98 },
        html2canvas: { scale: 2, useCORS: true, backgroundColor: "#ffffff" },
        jsPDF: { unit: "in", format: "a4", orientation: "portrait" },
        pagebreak: { mode: ["avoid-all","css","legacy"] }
    };
    html2pdf().set(opts).from(content).save()
        .then(() => { btn.innerHTML = old; btn.disabled = false; switchTab("full"); })
        .catch(() => { btn.innerHTML = old; btn.disabled = false; switchTab("full"); showError("Could not generate PDF."); });
}

// ---- History ----
function getHistory() { try { return JSON.parse(localStorage.getItem("tripmate_history") || "[]"); } catch { return []; } }
function saveHistory(h) { localStorage.setItem("tripmate_history", JSON.stringify(h.slice(0, 10))); }
function addToHistory(query) { const h = getHistory(); h.unshift({ query, time: Date.now() }); saveHistory(h); renderHistory(); }
function clearHistory() { localStorage.removeItem("tripmate_history"); renderHistory(); }

function renderHistory() {
    const list = document.getElementById("historyList");
    const h = getHistory();
    if (!list) return;
    if (!h.length) { list.innerHTML = `<div class="history-empty">Your recent trip searches will appear here.</div>`; return; }
    list.innerHTML = h.map(item => `
        <div class="history-item" onclick="setPrompt(${JSON.stringify(item.query)})" title="${item.query}">
            <span class="history-item-text">✈️ ${item.query}</span>
            <span class="history-item-time">${timeAgo(item.time)}</span>
        </div>`).join("");
}

function timeAgo(ts) {
    const m = Math.floor((Date.now() - ts) / 60000);
    if (m < 1) return "Just now";
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
}

// ---- Keyboard ----
document.addEventListener("keydown", e => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); sendMessage(); }
});
