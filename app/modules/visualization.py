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
            z-index: 100;
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

        @keyframes modalFadeIn {
            from { opacity: 0; transform: translateY(-10px); }
            to { opacity: 1; transform: translateY(0); }
        }
    </style>
</head>
<body>
    <div id="toolbar">
        <div style="font-weight: bold; font-size: 16px; margin-right: 10px; color: #58a6ff;">LTC/USDT</div>
        <button class="tool-btn">1m</button>
        <button class="tool-btn">Indicators</button>
        
        <div class="dropdown">
            <button class="tool-btn" id="strategy-btn">Strategia ▼</button>
            <div id="strategy-dropdown" class="dropdown-content">
                <a id="btn-open-settings">⚙️ Ustawienia strategii</a>
            </div>
        </div>

        <div style="flex-grow: 1;"></div>
        <div id="status-tag" style="font-size: 12px; color: #8b949e;">Live Data Offline (Historical Mode)</div>
    </div>
    
    <div id="chart-container">
        <div id="loading-overlay">Loading historical data...</div>
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

    <script>
        const chartContainer = document.getElementById('chart-container');
        const loadingOverlay = document.getElementById('loading-overlay');
        const statusTag = document.getElementById('status-tag');
        
        let mainChart, candleSeries, renkoSeries;
        let earliestTimestamp = null;
        let lastTimestamp = null;
        let isLoading = false;
        let allDataLoaded = false;

        // Modal Elements
        const strategyBtn = document.getElementById('strategy-btn');
        const strategyDropdown = document.getElementById('strategy-dropdown');
        const btnOpenSettings = document.getElementById('btn-open-settings');
        const settingsModal = document.getElementById('settings-modal');
        const closeModalBtn = document.getElementById('close-modal-btn');
        const cancelSettingsBtn = document.getElementById('cancel-settings-btn');
        const saveSettingsBtn = document.getElementById('save-settings-btn');

        // Dropdown Logic
        strategyBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            strategyDropdown.classList.toggle('show');
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
                
                calculateTrend();
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
                
                if (!renkoSeries) {
                    // Overlay style: semi-transparent solid bricks, removing wicks
                    renkoSeries = mainChart.addCandlestickSeries({
                        upColor: 'rgba(88, 166, 255, 0.4)', 
                        downColor: 'rgba(248, 81, 73, 0.4)', 
                        borderVisible: false,
                        wickVisible: false
                    });
                }
                
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

        async function simulateStrategy() {
            const period = parseInt(trendPeriodInput.value) || 100;
            const factor = parseFloat(weightFactorInput.value) || 0.87;
            const multiplier = parseFloat(multiplierInput.value) || 1.0;
            const minProfit = parseFloat(minProfitInput.value) || 0.2;

            try {
                const res = await fetch(`/api/strategy/simulate?period=${period}&weight_factor=${factor}&multiplier=${multiplier}&min_profit_pct=${minProfit}`);
                const data = await res.json();
                if (!data.signals || data.signals.length === 0) return;

                const markerConfig = {
                    open_long:     { position: 'belowBar', color: '#26a69a', shape: 'arrowUp',   text: 'L+' },
                    average_long:  { position: 'belowBar', color: '#58a6ff', shape: 'circle',    text: 'LA' },
                    close_long:    { position: 'aboveBar', color: '#26a69a', shape: 'arrowDown', text: 'LX' },
                    open_short:    { position: 'aboveBar', color: '#f85149', shape: 'arrowDown', text: 'S+' },
                    average_short: { position: 'aboveBar', color: '#e3b341', shape: 'circle',    text: 'SA' },
                    close_short:   { position: 'belowBar', color: '#f85149', shape: 'arrowUp',   text: 'SX' },
                };

                const markers = data.signals
                    .filter(s => markerConfig[s.signal])
                    .map(s => ({ time: s.time, ...markerConfig[s.signal] }))
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
            const period = trendPeriodInput.value;
            const factor = weightFactorInput.value;
            const multiplier = multiplierInput.value;
            const minProfit = minProfitInput.value;
            
            try {
                await fetch('/api/settings', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        settings: {
                            "trend_period": period,
                            "weight_factor": factor,
                            "multiplier": multiplier,
                            "min_profit": minProfit
                        }
                    })
                });
                calculateTrend();
                fetchRenko();
                simulateStrategy();
            } catch (err) {
                console.error("Błąd zapisu ustawień", err);
            }
            
            closeModal();
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
            candleSeries = mainChart.addCandlestickSeries({
                upColor: '#26a69a', downColor: '#ef5350', borderVisible: false,
                wickUpColor: '#26a69a', wickDownColor: '#ef5350',
            });

            setTimeout(() => {
                loadSettings();
                fetchHistory(null, 5000).then(() => {
                    // After history is loaded, overlay Renko and strategy signals
                    fetchRenko();
                    // Delay signals to ensure candleSeries is fully rendered
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
