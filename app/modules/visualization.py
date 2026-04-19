from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>New Bot Dashboard</title>
    <!-- Use stable version 4.1.1 -->
    <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        body {
            margin: 0;
            padding: 0;
            background-color: #0d1117;
            color: #c9d1d9;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            height: 100vh;
        }
        
        #toolbar {
            height: 50px;
            background-color: #161b22;
            border-bottom: 1px solid #30363d;
            display: flex;
            align-items: center;
            padding: 0 20px;
            gap: 15px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.3);
            z-index: 1000; /* Higher than panels */
            position: relative;
        }
        
        .tool-btn {
            background-color: #21262d;
            border: 1px solid #363b42;
            color: #c9d1d9;
            padding: 5px 12px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            transition: all 0.2s;
            user-select: none;
        }
        
        .tool-btn:hover {
            background-color: #30363d;
            border-color: #8b949e;
        }
        
        #chart-container {
            flex-grow: 1;
            position: relative;
            background-color: #0d1117;
        }
        
        #loading-overlay {
            position: absolute;
            top: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(22, 27, 34, 0.9);
            padding: 8px 20px;
            border-radius: 20px;
            border: 1px solid #58a6ff;
            font-size: 12px;
            display: none;
            z-index: 1000;
            box-shadow: 0 4px 15px rgba(0,0,0,0.5);
        }

        /* Premium Scrollbar */
        ::-webkit-scrollbar { width: 8px; height: 8px; }
        ::-webkit-scrollbar-track { background: #0d1117; }
        ::-webkit-scrollbar-thumb { background: #30363d; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #484f58; }

        /* Dropdown */
        .dropdown {
            position: relative;
            display: inline-block;
        }
        .dropdown-content {
            display: none;
            position: absolute;
            background-color: #161b22;
            min-width: 160px;
            box-shadow: 0px 8px 16px 0px rgba(0,0,0,0.5);
            z-index: 200;
            border: 1px solid #30363d;
            border-radius: 6px;
            top: 100%;
            margin-top: 5px;
            overflow: hidden;
        }
        .dropdown-content a {
            color: #c9d1d9;
            padding: 12px 16px;
            text-decoration: none;
            display: block;
            font-size: 13px;
        }
        .dropdown-content a:hover {
            background-color: #21262d;
            color: #58a6ff;
            cursor: pointer;
        }
        .show { display: block; }

        /* Modal */
        .modal-overlay {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.6);
            backdrop-filter: blur(3px);
            align-items: center;
            justify-content: center;
        }
        .modal-box {
            background-color: #0d1117;
            border: 1px solid #30363d;
            border-radius: 10px;
            width: 400px;
            max-width: 90%;
            box-shadow: 0 10px 30px rgba(0,0,0,0.8);
            display: flex;
            flex-direction: column;
            animation: modalFadeIn 0.2s ease;
        }
        .modal-header {
            padding: 15px 20px;
            border-bottom: 1px solid #30363d;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-weight: bold;
            color: #58a6ff;
        }
        .modal-close {
            color: #8b949e;
            cursor: pointer;
            font-size: 18px;
            line-height: 1;
        }
        .modal-close:hover { color: #f85149; }
        .modal-body {
            padding: 20px;
            font-size: 14px;
        }
        .modal-footer {
            padding: 15px 20px;
            border-top: 1px solid #30363d;
            display: flex;
            justify-content: flex-end;
            gap: 10px;
        }
        .btn-primary { background-color: #238636; color: white; border: none; }
        .btn-primary:hover { background-color: #2ea043; border-color: transparent; }
        
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 5px; color: #8b949e; }
        .form-control {
            width: 100%; padding: 8px 10px; border-radius: 5px; 
            background: #21262d; border: 1px solid #30363d; color: #c9d1d9;
            box-sizing: border-box;
        }
        .form-control:focus { outline: none; border-color: #58a6ff; }

        /* Position HUD Panel */
        #pos-panel {
            position: absolute;
            top: 10px; left: 10px;
            z-index: 100;
            display: flex; flex-direction: column; gap: 8px;
            pointer-events: none; /* Don't block chart interaction */
        }
        .pos-card {
            background: rgba(13, 17, 23, 0.85);
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 10px 12px;
            min-width: 180px;
            backdrop-filter: blur(8px);
            display: none; /* Shown via JS only when active */
        }
        .pos-card.active { display: block; }
        .pos-header {
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 6px; border-bottom: 1px solid #30363d; padding-bottom: 4px;
        }
        .pos-title { font-size: 11px; font-weight: bold; letter-spacing: 0.5px; }
        .pos-long .pos-title { color: #58a6ff; }
        .pos-short .pos-title { color: #e3b341; }
        .pos-row { display: flex; justify-content: space-between; font-size: 10px; margin-bottom: 2px; color: #8b949e; }
        .pos-val { font-weight: bold; color: #c9d1d9; }
        .pos-pnl { font-size: 12px; margin-top: 4px; font-weight: bold; }
        .pnl-plus { color: #3fb950; }
        .pnl-minus { color: #f85149; }

        /* Analytics Panel Styles - Tall & Narrow Histogram */
        #analytics-panel {
            position: absolute;
            top: 50px; left: 10px; right: 10px;
            height: 180px;
            background: rgba(13, 17, 23, 0.98);
            border: 1px solid #30363d;
            border-radius: 8px;
            z-index: 1000;
            display: none;
            flex-direction: column;
            box-shadow: 0 4px 25px rgba(0,0,0,0.9);
            backdrop-filter: blur(15px);
            animation: panelSlideDown 0.3s ease-out;
        }
        @keyframes panelSlideDown {
            from { opacity: 0; transform: translateY(-10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .analytics-header {
            padding: 8px 15px;
            border-bottom: 1px solid #30363d;
            display: flex; justify-content: space-between; align-items: center;
            font-size: 11px; font-weight: bold; color: #58a6ff;
        }
        .analytics-main {
            flex-grow: 1; display: flex; overflow: hidden;
        }
        .analytics-body {
            flex-grow: 3; padding: 10px 20px;
            display: flex; align-items: flex-end; gap: 6px;
            overflow-x: auto;
            border-right: 1px solid #30363d;
        }
        .analytics-stats-sidebar {
            flex-grow: 1; min-width: 150px; padding: 15px;
            display: flex; flex-direction: column; gap: 10px;
            background: rgba(110, 118, 129, 0.05);
        }
        .stat-item { display: flex; flex-direction: column; gap: 2px; }
        .stat-label { font-size: 10px; color: #8b949e; text-transform: uppercase; }
        .stat-value { font-size: 14px; font-weight: bold; color: #c9d1d9; }
        .stat-value.profit { color: #3fb950; }
        .stat-value.loss { color: #f85149; }
        .bar-container {
            display: flex; flex-direction: column; align-items: center; gap: 4px;
            min-width: 18px; /* Narrower as requested */
            height: 100%; justify-content: flex-end;
        }
        .bar {
            width: 14px; border-radius: 2px 2px 0 0;
            background: #1f6feb; border: 1px solid #58a6ff;
            background: linear-gradient(to top, #0969da, #1f6feb);
            transition: height 0.4s ease-out;
            position: relative;
            opacity: 0.9;
        }
        .bar:hover { opacity: 1; filter: brightness(1.3); }
        .bar-label { font-size: 8px; color: #8b949e; white-space: nowrap; transform: rotate(-45deg); margin-top: 10px; }
        .bar-prob { font-size: 8px; color: #58a6ff; font-weight: bold; margin-bottom: 2px; }
        .bar-value { 
            position: absolute; top: -12px; width: 100%; text-align: center;
            font-size: 8px; font-weight: bold; color: #c9d1d9;
        }
        .analytics-close { cursor: pointer; color: #8b949e; font-size: 18px; }
        .analytics-close:hover { color: #f85149; }

        @keyframes modalFadeIn {
            from { opacity: 0; transform: translateY(-10px); }
            to { opacity: 1; transform: translateY(0); }
        }
    </style>
</head>
<body>
    <div id="toolbar">
        <div style="font-weight: bold; font-size: 16px; margin-right: 10px; color: #58a6ff;">LTC/USDT</div>
        <div class="dropdown">
            <button class="tool-btn dropdown-toggle" id="strategy-btn">Strategia ▼</button>
            <div id="strategy-dropdown" class="dropdown-content">
                <a id="btn-open-settings">⚙️ Ustawienia strategii</a>
                <a id="btn-open-pos-settings">📊 Ustawienia pozycji</a>
                <a id="btn-open-analytics">📈 Analityka</a>
            </div>
        </div>

        <div style="flex-grow: 1;"></div>
        <div id="status-tag" style="font-size: 12px; color: #8b949e;">Live Data Offline (Historical Mode)</div>
    </div>
    
    <div id="chart-container">
        <div id="loading-overlay">Loading historical data...</div>
        
        <!-- Position Panel HUD -->
        <div id="pos-panel">
            <div id="long-pos-card" class="pos-card pos-long">
                <div class="pos-header"><span class="pos-title">LONG POSITION</span></div>
                <div class="pos-row"><span>Uśrednienia:</span> <span class="pos-val" id="l-hud-count">0</span></div>
                <div class="pos-row"><span>Kontrakty:</span> <span class="pos-val" id="l-hud-qty">0.00</span></div>
                <div class="pos-pnl" id="l-hud-pnl">$0.00 (0.00%)</div>
            </div>
            <div id="short-pos-card" class="pos-card pos-short">
                <div class="pos-header"><span class="pos-title">SHORT POSITION</span></div>
                <div class="pos-row"><span>Uśrednienia:</span> <span class="pos-val" id="s-hud-count">0</span></div>
                <div class="pos-row"><span>Kontrakty:</span> <span class="pos-val" id="s-hud-qty">0.00</span></div>
                <div class="pos-pnl" id="s-hud-pnl">$0.00 (0.00%)</div>
            </div>
        </div>
        
        <!-- Analytics Panel Container -->
        <div id="analytics-panel">
            <div class="analytics-header">
                <div>ANALIZA STATYSTYCZNA UŚREDNIEŃ (DCA) <span id="analytics-total-count" style="margin-left: 20px; color: #8b949e; opacity: 0.7;"></span></div>
                <span class="analytics-close" id="close-analytics-btn">&times;</span>
            </div>
            <div class="analytics-main">
                <div class="analytics-body" id="analytics-bars-container"></div>
                <div class="analytics-stats-sidebar">
                    <div class="stat-item">
                        <span class="stat-label">Całkowity PNL</span>
                        <span class="stat-value" id="stats-total-pnl">0.00</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Średni PNL</span>
                        <span class="stat-value" id="stats-avg-pnl">0.00</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Najwyższy PNL</span>
                        <span class="stat-value profit" id="stats-max-pnl">0.00</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Najniższy PNL</span>
                        <span class="stat-value loss" id="stats-min-pnl">0.00</span>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Strategy Settings Modal -->
    <div id="settings-modal" class="modal-overlay">
        <div class="modal-box">
            <div class="modal-header">
                Ustawienia Strategii
                <div class="modal-close" id="close-modal-btn">&times;</div>
            </div>
            <div class="modal-body">
                <div class="form-group">
                    <label for="trend-period">Szerokość badana (ilość świec high/low)</label>
                    <input type="number" id="trend-period" class="form-control" value="100" min="10" max="1000">
                </div>
                <div class="form-group">
                    <label for="weight-factor">Współczynnik wagi (zmniejszanie o)</label>
                    <input type="number" id="weight-factor" class="form-control" value="0.87" step="0.01" min="0.1" max="1.0">
                </div>
                <div class="form-group">
                    <label for="multiplier-value">Mnożnik wyniku końcowego</label>
                    <input type="number" id="multiplier-value" class="form-control" value="1.0" step="0.1" min="0.1">
                </div>
                <div class="form-group">
                    <label for="min-profit">Minimalny zysk do zamknięcia (%)</label>
                    <input type="number" id="min-profit" class="form-control" value="0.2" step="0.05" min="0.01">
                </div>
                <div style="margin-top: 20px; padding: 15px; background: #161b22; border-radius: 6px; border: 1px solid #30363d;">
                    <div style="color: #8b949e; font-size: 12px; margin-bottom: 5px;">Aktualny wynik z <span id="calc-candles-count">100</span> świec:</div>
                    <div id="strategy-result" style="font-size: 24px; font-weight: bold; color: #58a6ff;">0.0000</div>
                </div>
            </div>
            <div class="modal-footer">
                <button class="tool-btn" id="cancel-settings-btn">Anuluj</button>
                <button class="tool-btn btn-primary" id="save-settings-btn">Zapisz</button>
            </div>
        </div>
    </div>

    <!-- Position Settings Modal -->
    <div id="pos-settings-modal" class="modal-overlay">
        <div class="modal-box">
            <div class="modal-header">
                Ustawienia Pozycji
                <div class="modal-close" id="close-pos-modal-btn">&times;</div>
            </div>
            <div class="modal-body">
                <div class="form-group">
                    <label for="initial-qty">Ilość kontraktów początkowych</label>
                    <input type="number" id="initial-qty" class="form-control" value="1.0" step="0.1" min="0.001">
                </div>
                <div class="form-group">
                    <label for="contract-size">Wielkość kontraktu (w LTC)</label>
                    <input type="number" id="contract-size" class="form-control" value="0.01" step="0.0001" min="0.00001">
                    <div style="font-size: 10px; color: #8b949e; margin-top: 5px;">
                        * Dla LTC często 1 kontrakt = 0.01 LTC
                    </div>
                </div>
            </div>
            <div class="modal-footer">
                <button class="tool-btn" id="cancel-pos-btn">Anuluj</button>
                <button class="tool-btn btn-primary" id="save-pos-btn">Zapisz</button>
            </div>
        </div>
    </div>

    <script>
        const chartContainer = document.getElementById('chart-container');
        const loadingOverlay = document.getElementById('loading-overlay');
        const statusTag = document.getElementById('status-tag');
        
        let mainChart, candleSeries, renkoSeries;
        let earliestTimestamp = null;
        let lastTimestamp = null;
        let isLoading = false;
        let allDataLoaded = false;
        
        let histLongAvgSeries = null;
        let histLongTargetSeries = null;
        let histShortAvgSeries = null;
        let histShortTargetSeries = null;

        // Modal Elements
        const strategyBtn = document.getElementById('strategy-btn');
        const strategyDropdown = document.getElementById('strategy-dropdown');
        const btnOpenSettings = document.getElementById('btn-open-settings');
        const settingsModal = document.getElementById('settings-modal');
        const closeModalBtn = document.getElementById('close-modal-btn');
        const cancelSettingsBtn = document.getElementById('cancel-settings-btn');
        const saveSettingsBtn = document.getElementById('save-settings-btn');
        
        const btnOpenPosSettings = document.getElementById('btn-open-pos-settings');
        const posSettingsModal = document.getElementById('pos-settings-modal');
        const closePosModalBtn = document.getElementById('close-pos-modal-btn');
        const cancelPosBtn = document.getElementById('cancel-pos-btn');
        const savePosBtn = document.getElementById('save-pos-btn');
        const initialQtyInput = document.getElementById('initial-qty');
        const contractSizeInput = document.getElementById('contract-size');
        
        const analyticsPanel = document.getElementById('analytics-panel');
        const btnOpenAnalytics = document.getElementById('btn-open-analytics');
        const closeAnalyticsBtn = document.getElementById('close-analytics-btn');
        const barsContainer = document.getElementById('analytics-bars-container');
        const analyticsTotalCount = document.getElementById('analytics-total-count');

        // Dropdown Logic
        strategyBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            strategyDropdown.classList.toggle('show');
        });

        btnOpenPosSettings.addEventListener('click', () => {
            posSettingsModal.style.display = 'flex';
            strategyDropdown.classList.remove('show');
        });
        closePosModalBtn.addEventListener('click', () => posSettingsModal.style.display = 'none');
        cancelPosBtn.addEventListener('click', () => posSettingsModal.style.display = 'none');

        initialQtyInput.addEventListener('input', () => {}); // No immediate calc needed
        contractSizeInput.addEventListener('input', () => {});

        async function saveSettings() {
            const period = trendPeriodInput.value;
            const factor = weightFactorInput.value;
            const multiplier = multiplierInput.value;
            const minProfit = minProfitInput.value;
            const iQty = initialQtyInput.value;
            const cSize = contractSizeInput.value;
            
            try {
                await fetch('/api/settings', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        settings: {
                            "trend_period": period,
                            "weight_factor": factor,
                            "multiplier": multiplier,
                            "min_profit": minProfit,
                            "initial_qty": iQty,
                            "contract_size": cSize
                        }
                    })
                });
                calculateTrend();
                fetchRenko();
                simulateStrategy();
            } catch (err) {
                console.error("Błąd zapisu ustawień", err);
            }
        }

        saveSettingsBtn.addEventListener('click', async () => {
            await saveSettings();
            settingsModal.style.display = 'none';
        });

        savePosBtn.addEventListener('click', async () => {
            await saveSettings();
            posSettingsModal.style.display = 'none';
        });

        document.addEventListener('click', (e) => {
            if (strategyDropdown.classList.contains('show')) {
                strategyDropdown.classList.remove('show');
            }
        });
        
        // Strategy Calculation Logic - declared before loadSettings to avoid reference errors
        const trendPeriodInput = document.getElementById('trend-period');
        const weightFactorInput = document.getElementById('weight-factor');
        const multiplierInput = document.getElementById('multiplier-value');
        const minProfitInput = document.getElementById('min-profit');
        const strategyResult = document.getElementById('strategy-result');
        const calcCandlesCount = document.getElementById('calc-candles-count');

        // Persistent Settings Fetch Payload
        async function loadSettings() {
            try {
                const res = await fetch('/api/settings');
                const data = await res.json();
                
                if (data["trend_period"]) trendPeriodInput.value = data["trend_period"];
                if (data["weight_factor"]) weightFactorInput.value = data["weight_factor"];
                if (data["multiplier"]) multiplierInput.value = data["multiplier"];
                if (data["min_profit"]) minProfitInput.value = data["min_profit"];
                if (data["initial_qty"]) initialQtyInput.value = data["initial_qty"];
                if (data["contract_size"]) contractSizeInput.value = data["contract_size"];
                
                calculateTrend();
                simulateStrategy();
            } catch (err) {
                console.error("Nie udało się pobrać ustawień:", err);
            }
        }

        async function calculateTrend() {
            const period = parseInt(trendPeriodInput.value) || 100;
            const factor = parseFloat(weightFactorInput.value) || 0.87;
            const multiplier = parseFloat(multiplierInput.value) || 1.0;
            
            calcCandlesCount.innerText = period;

            try {
                const res = await fetch(`/api/strategy/trend?period=${period}&weight_factor=${factor}&multiplier=${multiplier}`);
                const data = await res.json();
                
                if (data && data.value !== undefined) {
                    strategyResult.innerText = parseFloat(data.value).toFixed(4);
                }
            } catch (err) {
                console.error("Strategy calculataion error:", err);
                strategyResult.innerText = "Error";
            }
        }

        async function fetchRenko() {
            const period = parseInt(trendPeriodInput.value) || 100;
            const factor = parseFloat(weightFactorInput.value) || 0.87;
            const multiplier = parseFloat(multiplierInput.value) || 1.0;

            try {
                const res = await fetch(`/api/strategy/renko?period=${period}&weight_factor=${factor}&multiplier=${multiplier}`);
                const data = await res.json();
                
                if (!renkoSeries) return; // Should be initialized
                
                renkoSeries.applyOptions({ visible: true });
                if (data.bricks && data.bricks.length > 0) {
                    renkoSeries.setData(data.bricks);
                }
            } catch (e) {
                console.error("Renko fetch error:", e);
            }
        }

        trendPeriodInput.addEventListener('input', calculateTrend);
        weightFactorInput.addEventListener('input', calculateTrend);
        multiplierInput.addEventListener('input', calculateTrend);
        minProfitInput.addEventListener('input', calculateTrend);

        // Analytics Logic - Discrete Probability Histogram
        function updateAnalytics(signals) {
            if (!signals || signals.length === 0) return;
            
            const avgCounts = {};
            const pnlList = [];
            let longAvgs = 0, shortAvgs = 0;
            let longActive = false, shortActive = false;

            signals.forEach(s => {
                if (s.signal === 'open_long') { longActive = true; longAvgs = 0; }
                else if (s.signal === 'average_long') { longAvgs++; }
                else if (s.signal === 'close_long') { 
                    avgCounts[longAvgs] = (avgCounts[longAvgs] || 0) + 1;
                    if (s.pnl !== undefined) pnlList.push(s.pnl);
                    longActive = false;
                }
                
                if (s.signal === 'open_short') { shortActive = true; shortAvgs = 0; }
                else if (s.signal === 'average_short') { shortAvgs++; }
                else if (s.signal === 'close_short') {
                    avgCounts[shortAvgs] = (avgCounts[shortAvgs] || 0) + 1;
                    if (s.pnl !== undefined) pnlList.push(s.pnl);
                    shortActive = false;
                }
            });

            // Update PNL Stats
            if (pnlList.length > 0) {
                const totalPnl = pnlList.reduce((a, b) => a + b, 0);
                const maxPnl = Math.max(...pnlList);
                const minPnl = Math.min(...pnlList);
                const avgPnl = totalPnl / pnlList.length;

                const setStat = (id, val, colorize = true) => {
                    const el = document.getElementById(id);
                    el.innerText = val.toFixed(2);
                    if (colorize) {
                        el.className = 'stat-value' + (val >= 0 ? ' profit' : ' loss');
                    }
                };

                setStat('stats-total-pnl', totalPnl);
                setStat('stats-avg-pnl', avgPnl);
                setStat('stats-max-pnl', maxPnl);
                setStat('stats-min-pnl', minPnl);
            }

            barsContainer.innerHTML = '';
            const allKeys = Object.keys(avgCounts).map(Number);
            const maxCounts = allKeys.length > 0 ? Math.max(...allKeys, 5) : 5;
            const totalPositions = Object.values(avgCounts).reduce((a, b) => a + b, 0);
            
            if (analyticsTotalCount) {
                analyticsTotalCount.innerText = `| ŁĄCZNIE: ${totalPositions}`;
            }

            // Calculate conditional completion for each step
            for (let i = 0; i <= maxCounts; i++) {
                const freq = avgCounts[i] || 0;
                
                // Calculate how many positions reached this level (i and above)
                let totalReachedLevel = 0;
                for (let k = i; k <= maxCounts; k++) {
                    totalReachedLevel += (avgCounts[k] || 0);
                }

                // Probability: Out of those who reached i, how many closed at i?
                const prob = totalReachedLevel > 0 ? (freq / totalReachedLevel * 100) : 0;
                const heightPct = prob; 
                
                const barHtml = `
                    <div class="bar-container">
                        <div class="bar-prob">${prob.toFixed(1)}%</div>
                        <div class="bar" style="height: ${Math.max(heightPct, 2)}%;">
                            <div class="bar-value">${freq}</div>
                        </div>
                        <div class="bar-label">${i} uśr.</div>
                    </div>
                `;
                barsContainer.innerHTML += barHtml;
            }
        }

        btnOpenAnalytics.addEventListener('click', () => {
            analyticsPanel.style.display = 'flex';
        });
        closeAnalyticsBtn.addEventListener('click', () => {
            analyticsPanel.style.display = 'none';
        });

        function updatePositionHUD(data) {
            const lCard = document.getElementById('long-pos-card');
            const sCard = document.getElementById('short-pos-card');

            if (data.current_long_active) {
                lCard.classList.add('active');
                document.getElementById('l-hud-count').innerText = data.long_count;
                document.getElementById('l-hud-qty').innerText = data.long_qty;
                const pnlEl = document.getElementById('l-hud-pnl');
                pnlEl.innerText = `$${data.long_pnl} (${data.long_pnl_pct}%)`;
                pnlEl.className = 'pos-pnl ' + (data.long_pnl >= 0 ? 'pnl-plus' : 'pnl-minus');
            } else {
                lCard.classList.remove('active');
            }

            if (data.current_short_active) {
                sCard.classList.add('active');
                document.getElementById('s-hud-count').innerText = data.short_count;
                document.getElementById('s-hud-qty').innerText = data.short_qty;
                const pnlEl = document.getElementById('s-hud-pnl');
                pnlEl.innerText = `$${data.short_pnl} (${data.short_pnl_pct}%)`;
                pnlEl.className = 'pos-pnl ' + (data.short_pnl >= 0 ? 'pnl-plus' : 'pnl-minus');
            } else {
                sCard.classList.remove('active');
            }
        }

        async function simulateStrategy() {
            const period = parseInt(trendPeriodInput.value) || 100;
            const factor = parseFloat(weightFactorInput.value) || 0.87;
            const multiplier = parseFloat(multiplierInput.value) || 1.0;
            const minProfit = parseFloat(minProfitInput.value) || 0.2;
            const iQty = parseFloat(initialQtyInput.value) || 1.0;
            const cSize = parseFloat(contractSizeInput.value) || 0.01;

            try {
                const res = await fetch(`/api/strategy/simulate?period=${period}&weight_factor=${factor}&multiplier=${multiplier}&min_profit_pct=${minProfit}&initial_qty=${iQty}&contract_size=${cSize}`);
                const data = await res.json();
                
                updateAnalytics(data.signals);
                updatePositionHUD(data);

                // Handle Historical and Active Lines (Segmented)
                // hist series are pre-initialized in initChart

                if (data.history_lines && data.history_lines.length > 0) {
                    const lAvg = [], lTp = [], sAvg = [], sTp = [];
                    data.history_lines.forEach(h => {
                        const val = h.avg || 0;
                        const tval = h.target || 0;
                        if (h.type === 'long') { 
                            lAvg.push({ time: h.time, value: val }); 
                            lTp.push({ time: h.time, value: tval }); 
                        } else { 
                            sAvg.push({ time: h.time, value: val }); 
                            sTp.push({ time: h.time, value: tval }); 
                        }
                    });
                    histLongAvgSeries.setData(lAvg);
                    histLongTargetSeries.setData(lTp);
                    histShortAvgSeries.setData(sAvg);
                    histShortTargetSeries.setData(sTp);
                }

                if (!data.signals || data.signals.length === 0) {
                    candleSeries.setMarkers([]);
                    return;
                }

                const markerConfig = {
                    open_long:     { position: 'belowBar', color: '#00ffcc', shape: 'arrowUp',   text: 'OPEN LONG' },
                    average_long:  { position: 'belowBar', color: '#00ccff', shape: 'circle',    text: 'AVG LONG' },
                    close_long:    { position: 'aboveBar', color: '#ff00ff', shape: 'arrowDown', text: 'CLOSE LONG' },
                    open_short:    { position: 'aboveBar', color: '#ff3300', shape: 'arrowDown', text: 'OPEN SHORT' },
                    average_short: { position: 'aboveBar', color: '#ffcc00', shape: 'circle',    text: 'AVG SHORT' },
                    close_short:   { position: 'belowBar', color: '#ff00ff', shape: 'arrowUp',   text: 'CLOSE SHORT' },
                };

                const markers = data.signals
                    .filter(s => markerConfig[s.signal])
                    .map(s => {
                        const m = markerConfig[s.signal];
                        let label = m.text;
                        if (s.signal.includes('average')) {
                            label = `AVG (${s.counter})`;
                        }
                        return { 
                            time: s.time, 
                            position: m.position, 
                            color: m.color, 
                            shape: m.shape, 
                            text: label,
                            size: 2 // Some browser versions support this, others ignore
                        };
                    })
                    .sort((a, b) => a.time - b.time);

                console.log(`Strategy: setting ${markers.length} markers`);
                try {
                    candleSeries.setMarkers(markers);
                    console.log("setMarkers OK");
                    // Zoom out to show all signals
                    mainChart.timeScale().fitContent();
                } catch(markerErr) {
                    console.error("setMarkers FAILED:", markerErr);
                }
            } catch (e) {
                console.error("Strategy simulate error:", e);
            }
        }

        // Modal Logic
        function openModal() { 
            settingsModal.style.display = 'flex'; 
            calculateTrend();
        }
        function closeModal() { settingsModal.style.display = 'none'; }

        btnOpenSettings.addEventListener('click', openModal);
        closeModalBtn.addEventListener('click', closeModal);
        cancelSettingsBtn.addEventListener('click', closeModal);
        
        saveSettingsBtn.addEventListener('click', async () => {
            await saveSettings();
        });

        function initChart() {
            const width = chartContainer.clientWidth;
            const height = chartContainer.clientHeight;
            
            const chartOptions = {
                width: width, height: height,
                layout: { background: { type: 'solid', color: '#0d1117' }, textColor: '#c9d1d9' },
                grid: { vertLines: { color: '#161b22' }, horzLines: { color: '#161b22' } },
                timeScale: { borderColor: '#30363d', timeVisible: true }
            };

            mainChart = LightweightCharts.createChart(chartContainer, chartOptions);
            
            // 1. Candlesticks (Base)
            candleSeries = mainChart.addCandlestickSeries({
                upColor: '#26a69a', downColor: '#ef5350', borderVisible: false,
                wickUpColor: '#26a69a', wickDownColor: '#ef5350',
            });

            // 2. Performance Lines (Middle)
            const lineOptions = (color, title, dashed = false) => ({
                color: color,
                lineWidth: 1,
                lineStyle: dashed ? LightweightCharts.LineStyle.Dashed : LightweightCharts.LineStyle.Solid,
                lastValueVisible: true,
                priceLineVisible: false,
                title: title
            });
            histLongAvgSeries = mainChart.addLineSeries(lineOptions('#58a6ff', 'AVG L'));
            histLongTargetSeries = mainChart.addLineSeries(lineOptions('#26a69a', 'TP L', true));
            histShortAvgSeries = mainChart.addLineSeries(lineOptions('#e3b341', 'AVG S'));
            histShortTargetSeries = mainChart.addLineSeries(lineOptions('#f85149', 'TP S', true));

            // 3. Renko Bricks (Top-most semi-transparent)
            renkoSeries = mainChart.addCandlestickSeries({
                upColor: 'rgba(88, 166, 255, 0.4)', 
                downColor: 'rgba(248, 81, 73, 0.4)', 
                borderVisible: false,
                wickVisible: false
            });

            setTimeout(() => {
                loadSettings();
                fetchHistory(null, 5000).then(() => {
                    fetchRenko();
                    setTimeout(() => simulateStrategy(), 500);
                });
                startLiveUpdates();
            }, 100);

            // Lazy Loading Logic
            mainChart.timeScale().subscribeVisibleTimeRangeChange((range) => {
                if (!range || isLoading || allDataLoaded || !earliestTimestamp) return;
                if (range.from < (earliestTimestamp / 1000) + 60) {
                    fetchHistory(earliestTimestamp, 500);
                }
            });

            window.addEventListener('resize', () => {
                mainChart.applyOptions({ width: chartContainer.clientWidth, height: chartContainer.clientHeight });
            });
        }

        async function fetchHistory(before = null, limit = 1000) {
            if (isLoading || (before && allDataLoaded)) return;
            isLoading = true;
            if (before) loadingOverlay.style.display = 'block';
            
            try {
                let url = `/api/candles?limit=${limit}`;
                if (before) url += `&before=${before}`;
                
                const response = await fetch(url);
                const data = await response.json();
                
                if (data.candles && data.candles.length > 0) {
                    const sortedCandles = data.candles;
                    if (before) {
                        const currentData = candleSeries.data();
                        candleSeries.setData([...sortedCandles, ...currentData]);
                    } else {
                        candleSeries.setData(sortedCandles);
                        lastTimestamp = sortedCandles[sortedCandles.length - 1].time * 1000;
                        setTimeout(() => mainChart.timeScale().fitContent(), 50);
                    }
                    earliestTimestamp = sortedCandles[0].time * 1000;
                } else if (before) {
                    allDataLoaded = true;
                }
            } catch (err) { console.error("Fetch failed:", err); }
            finally { isLoading = false; loadingOverlay.style.display = 'none'; }
        }

        async function startLiveUpdates() {
            // 1. Polling Status Tag
            setInterval(async () => {
                try {
                    const res = await fetch('/api/status');
                    const data = await res.json();
                    statusTag.innerText = `Monitoring: ${data.status} (${data.extra})`;
                    statusTag.style.color = data.status === "Live" ? "#26a69a" : "#e3b341";
                } catch (e) {}
            }, 3000);

            // 2. Polling Latest Data
            setInterval(async () => {
                try {
                    const res = await fetch('/api/candles?limit=10');
                    const data = await res.json();
                    if (data.candles && data.candles.length > 0) {
                        let updated = false;
                        data.candles.forEach(c => {
                            if (!lastTimestamp || c.time * 1000 >= lastTimestamp) {
                                candleSeries.update(c);
                                lastTimestamp = Math.max(lastTimestamp || 0, c.time * 1000);
                                updated = true;
                            }
                        });
                        
                        // Recalculate dynamic trend if modal is open and data changed
                        if (updated && settingsModal.style.display === 'flex') {
                            calculateTrend();
                        }
                    }
                } catch (e) {}
            }, 5000);
        }

        if (document.readyState === 'complete') initChart();
        else window.addEventListener('load', initChart);
    </script>
</body>
</html>
    """
