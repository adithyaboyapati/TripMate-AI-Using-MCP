// =========================================================
//  TripMate AI — Script v3
//  Feature 5: SSE Streaming (real-time agent updates)
//  Feature 6: Logout support
// =========================================================

let currentThreadId      = localStorage.getItem("travel_thread_id") || null;
let latestAnswerMarkdown = "";
let latestFlightData     = "";
let latestHotelData      = "";
let latestWeatherData    = "";
let latestRestaurantData = "";
let latestCurrencyData   = "";
let latestItineraryData  = "";

// Feature 3: Track which route was chosen by the router
let currentRoute = "full_trip";

// All 8 stepper stages — now driven by REAL SSE events (no fake timers)
const STAGES = [
    { id: "router",     name: "Query Router"      },
    { id: "flight",     name: "Flight Search"      },
    { id: "hotel",      name: "Hotel Search"       },
    { id: "weather",    name: "Weather Check"      },
    { id: "restaurant", name: "Restaurant Finder"  },
    { id: "currency",   name: "Currency Advisor"   },
    { id: "itinerary",  name: "Itinerary Agent"    },
    { id: "final",      name: "Formatter Agent"    },
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


// ---- Status pill ----
function setStatus(state) {
    const pill = document.getElementById("statusPill");
    const dot  = document.getElementById("statusDot");
    const txt  = document.getElementById("statusText");
    if (!pill) return;
    if (state === "busy") { pill.classList.add("busy"); if (txt) txt.textContent = "Working..."; }
    else { pill.classList.remove("busy"); if (txt) txt.textContent = "Ready"; }
}


// ---- Loading state ----
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
    } else {
        btnTxt.classList.remove("hidden");
        if (btnIcon) btnIcon.classList.remove("hidden");
        if (btnArr)  btnArr.classList.remove("hidden");
        loader.classList.add("hidden");
        if (idle)    idle.classList.remove("hidden");
        if (stepper) stepper.classList.add("hidden");
        if (quick)   quick.classList.remove("hidden");
        setStatus("idle");
    }
}


// ---- Stepper helpers ----

function resetStages() {
    STAGES.forEach(s => {
        const el = document.getElementById("step-"   + s.id);
        if (el) el.classList.remove("active", "done", "skipped");
        const st = document.getElementById("status-" + s.id);
        if (st) st.textContent = "Waiting...";
        const bg = document.getElementById("badge-"  + s.id);
        if (bg) bg.textContent = "·";
    });
    const msg = document.getElementById("loadingMsg");
    if (msg) msg.textContent = "Initializing pipeline...";
    currentRoute = "full_trip";
}

function markStepActive(id) {
    const el = document.getElementById("step-" + id);
    if (el) { el.classList.remove("done", "skipped"); el.classList.add("active"); }
    const st = document.getElementById("status-" + id);
    if (st) st.textContent = "Running...";
}

function markStepDone(id) {
    const el = document.getElementById("step-" + id);
    if (el) { el.classList.remove("active", "skipped"); el.classList.add("done"); }
    const st = document.getElementById("status-" + id);
    if (st) st.textContent = "Done ✓";
    const bg = document.getElementById("badge-" + id);
    if (bg) bg.textContent = "✓";
}

function markStepSkipped(id) {
    const el = document.getElementById("step-" + id);
    if (el) { el.classList.remove("active"); el.classList.add("skipped"); }
    const st = document.getElementById("status-" + id);
    if (st) st.textContent = "Skipped";
    const bg = document.getElementById("badge-" + id);
    if (bg) bg.textContent = "–";
}

function setLoadingMsg(text) {
    const msg = document.getElementById("loadingMsg");
    if (!msg) return;
    msg.style.animation = "none";
    void msg.offsetWidth;
    msg.style.animation = "fadeUp 0.4s ease";
    msg.textContent = text;
}


// ---- Feature 5: SSE Event Handler ----
// Called for each SSE event from /api/travel/stream
// Advances the stepper in REAL TIME as each agent finishes.

function handleSSEEvent(data) {

    if (data.event === "start") {
        markStepActive("router");
        setLoadingMsg("🧭 Analyzing your request...");
    }

    else if (data.event === "router_done") {
        currentRoute = data.route || "full_trip";
        markStepDone("router");

        if (currentRoute === "hotels_only") {
            markStepSkipped("flight");
            markStepActive("hotel");
            setLoadingMsg("🏨 Finding best hotels...");
        } else if (currentRoute === "weather_only") {
            markStepSkipped("flight");
            markStepSkipped("hotel");
            markStepActive("weather");
            setLoadingMsg("🌤️ Checking weather...");
        } else {
            // full_trip or flights_only
            markStepActive("flight");
            setLoadingMsg("✈️ Searching live flights...");
        }

        // Update route badge
        const ri = document.getElementById("routeInfo");
        if (ri) ri.textContent = `Route: ${currentRoute.replace("_", " ")}`;
    }

    else if (data.event === "flight_done") {
        markStepDone("flight");
        if (currentRoute === "full_trip") {
            markStepActive("hotel");
            setLoadingMsg("🏨 Finding best hotels...");
        } else {
            // flights_only → skip to final
            markStepSkipped("hotel");
            markStepSkipped("weather");
            markStepSkipped("restaurant");
            markStepSkipped("currency");
            markStepSkipped("itinerary");
            markStepActive("final");
            setLoadingMsg("✨ Formatting your plan...");
        }
    }

    else if (data.event === "hotel_done") {
        markStepDone("hotel");
        if (currentRoute === "full_trip") {
            markStepActive("weather");
            setLoadingMsg("🌤️ Checking weather...");
        } else {
            // hotels_only → skip to final
            markStepSkipped("weather");
            markStepSkipped("restaurant");
            markStepSkipped("currency");
            markStepSkipped("itinerary");
            markStepActive("final");
            setLoadingMsg("✨ Formatting your plan...");
        }
    }

    else if (data.event === "weather_done") {
        markStepDone("weather");
        if (currentRoute === "full_trip") {
            markStepActive("restaurant");
            setLoadingMsg("🍽️ Finding local restaurants...");
        } else {
            // weather_only → skip to final
            markStepSkipped("restaurant");
            markStepSkipped("currency");
            markStepSkipped("itinerary");
            markStepActive("final");
            setLoadingMsg("✨ Formatting your plan...");
        }
    }

    else if (data.event === "restaurant_done") {
        markStepDone("restaurant");
        markStepActive("currency");
        setLoadingMsg("💱 Converting currency...");
    }

    else if (data.event === "currency_done") {
        markStepDone("currency");
        markStepActive("itinerary");
        setLoadingMsg("📝 Crafting your itinerary...");
    }

    else if (data.event === "itinerary_done") {
        markStepDone("itinerary");
        markStepActive("final");
        setLoadingMsg("✨ Formatting your travel plan...");
    }

    else if (data.event === "final_done") {
        markStepDone("final");
        setLoadingMsg("✅ Your travel plan is ready!");
    }
}


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
function showResult(answer, flightData, hotelData, weatherData, restaurantData, currencyData, itineraryData, threadId, llmCalls) {
    latestAnswerMarkdown = answer      || "";
    latestFlightData     = flightData  || "";
    latestHotelData      = hotelData   || "";
    latestWeatherData    = weatherData || "";
    latestRestaurantData = restaurantData || "";
    latestCurrencyData   = currencyData   || "";
    latestItineraryData  = itineraryData  || "";

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

    renderMd("resultBox",     answer);
    renderMd("flightBox",     flightData);
    renderMd("hotelBox",      hotelData);
    renderMd("weatherBox",    weatherData);
    renderMd("restaurantBox", restaurantData);
    renderMd("currencyBox",   currencyData);
    renderMd("itineraryBox",  itineraryData);

    const ti = document.getElementById("threadInfo");
    const li = document.getElementById("llmCallsInfo");
    if (ti) ti.textContent = `Thread: ${threadId  || "—"}`;
    if (li) li.textContent = `Agents: ${llmCalls  || 0} calls`;

    const rs = document.getElementById("resultSection");
    rs.classList.remove("hidden");
    switchTab("full");
    setTimeout(() => rs.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
}


// ---- Feature 5: Main SSE streaming send ----
// Uses fetch() + ReadableStream instead of a single JSON response.
// The /api/travel/stream endpoint sends one SSE event per agent.

async function sendMessage() {
    hideError();
    const input   = document.getElementById("userInput");
    const message = input.value.trim();
    if (!message) { showError("Please enter your travel request first."); return; }

    setLoading(true);
    resetStages();

    // Accumulate data from SSE events
    let accFlightData     = "";
    let accHotelData      = "";
    let accWeatherData    = "";
    let accRestaurantData = "";
    let accCurrencyData   = "";
    let accItineraryData  = "";
    let accAnswer         = "";
    let accThreadId       = currentThreadId;
    let accLlmCalls       = 0;

    try {
        const response = await fetch("/api/travel/stream", {
            method:  "POST",
            headers: { "Content-Type": "application/json" },
            body:    JSON.stringify({ message, thread_id: currentThreadId })
        });

        if (!response.ok) {
            throw new Error(`Server error (${response.status}). Please try again.`);
        }

        const reader  = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer    = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() || "";   // keep incomplete trailing line

            for (const line of lines) {
                if (!line.startsWith("data: ")) continue;

                let data;
                try {
                    data = JSON.parse(line.slice(6));
                } catch (_) {
                    continue; // skip malformed lines
                }

                // Update stepper UI based on the SSE event
                handleSSEEvent(data);

                // Accumulate data from each agent
                if (data.event === "flight_done")     accFlightData     = data.data || "";
                if (data.event === "hotel_done")      accHotelData      = data.data || "";
                if (data.event === "weather_done")    accWeatherData    = data.data || "";
                if (data.event === "restaurant_done") accRestaurantData = data.data || "";
                if (data.event === "currency_done")   accCurrencyData   = data.data || "";
                if (data.event === "itinerary_done")  accItineraryData  = data.data || "";
                if (data.event === "final_done")      accAnswer         = data.data || "";

                if (data.event === "complete") {
                    accThreadId  = data.thread_id || accThreadId;
                    accLlmCalls  = data.llm_calls || 0;
                }

                if (data.event === "error") {
                    throw new Error(data.message || "Agent pipeline encountered an error.");
                }
            }
        }

        // Persist thread for multi-turn memory
        if (accThreadId) {
            currentThreadId = accThreadId;
            localStorage.setItem("travel_thread_id", currentThreadId);
        }

        showResult(
            accAnswer, accFlightData, accHotelData, accWeatherData,
            accRestaurantData, accCurrencyData, accItineraryData,
            accThreadId, accLlmCalls
        );
        addToHistory(message);

    } catch (err) {
        showError(err.message || "Something went wrong. Please try again.");
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
    btn.disabled  = true;
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("hidden"));
    const opts = {
        margin:     0.5,
        filename:   `tripmate-plan-${Date.now()}.pdf`,
        image:      { type: "jpeg", quality: 0.98 },
        html2canvas:{ scale: 2, useCORS: true, backgroundColor: "#ffffff" },
        jsPDF:      { unit: "in", format: "a4", orientation: "portrait" },
        pagebreak:  { mode: ["avoid-all","css","legacy"] }
    };
    html2pdf().set(opts).from(content).save()
        .then(() => { btn.innerHTML = old; btn.disabled = false; switchTab("full"); })
        .catch(()=> { btn.innerHTML = old; btn.disabled = false; switchTab("full"); showError("Could not generate PDF."); });
}


// ---- Feature 6: Logout ----
async function handleLogout() {
    try {
        await fetch("/api/logout", { method: "POST" });
    } catch (_) {}
    // Clear local state and redirect to login
    localStorage.removeItem("travel_thread_id");
    localStorage.removeItem("tripmate_history");
    window.location.href = "/login";
}


// ---- History ----
function getHistory()  { try { return JSON.parse(localStorage.getItem("tripmate_history") || "[]"); } catch { return []; } }
function saveHistory(h){ localStorage.setItem("tripmate_history", JSON.stringify(h.slice(0, 10))); }
function addToHistory(query) { const h = getHistory(); h.unshift({ query, time: Date.now() }); saveHistory(h); renderHistory(); }
function clearHistory(){ localStorage.removeItem("tripmate_history"); renderHistory(); }

function renderHistory() {
    const list = document.getElementById("historyList");
    const h    = getHistory();
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
    if (m < 1)  return "Just now";
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
}


// ---- Keyboard shortcut ----
document.addEventListener("keydown", e => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); sendMessage(); }
});
