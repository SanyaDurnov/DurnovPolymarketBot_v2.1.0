// Durnov Polybot V2 - Main JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Load markets, indicators, top markets and system status when page loads
    loadMarkets();
    loadMarketIndicators();
    loadTopEntryMarkets();
    loadSystemStatus();
});

// Load markets and display them
async function loadMarkets() {
    const loadingDiv = document.getElementById('markets-loading');
    const marketsDiv = document.getElementById('markets-list');
    const errorDiv = document.getElementById('markets-error');

    console.log('Starting to load markets from main page');

    try {
        loadingDiv.style.display = 'block';
        marketsDiv.style.display = 'none';
        errorDiv.style.display = 'none';

        const apiUrl = '/api/markets?limit=20';
        console.log('Making API request to:', window.location.origin + apiUrl);

        const response = await fetch(apiUrl);
        console.log('Markets API response status:', response.status);
        console.log('Markets API response ok:', response.ok);

        if (response.ok) {
            const data = await response.json();
            console.log('Received markets data:', data);
            console.log('Number of markets received:', data.markets ? data.markets.length : 0);
            displayMarkets(data.markets);
        } else {
            const errorText = await response.text();
            console.error('Markets API request failed with status:', response.status);
            console.error('Markets API error response:', errorText);
            throw new Error(`Markets API request failed: ${response.status} ${response.statusText}`);
        }
    } catch (error) {
        console.error('Error loading markets:', error);
        console.error('Error details:', {
            name: error.name,
            message: error.message,
            stack: error.stack
        });
        loadingDiv.style.display = 'none';
        errorDiv.style.display = 'block';
    }
}

// Display markets in grid
function displayMarkets(markets) {
    const loadingDiv = document.getElementById('markets-loading');
    const marketsDiv = document.getElementById('markets-list');

    loadingDiv.style.display = 'none';
    marketsDiv.style.display = 'grid';

    if (markets && markets.length > 0) {
        marketsDiv.innerHTML = markets.map(market => `
            <a href="/market/${market.id}" target="_blank" class="market-card">
                <span class="market-title">${market.title}</span>
                <span class="market-id">ID: ${market.id}</span>
                <span class="market-status ${market.active ? 'active' : 'inactive'}">
                    ${market.active ? 'Active' : 'Inactive'}
                </span>
            </a>
        `).join('');
    } else {
        marketsDiv.innerHTML = '<p>No markets available</p>';
    }
}

// Load system status information
async function loadSystemStatus() {
    const refreshBtn = document.getElementById('refresh-btn');
    const originalText = refreshBtn.textContent;
    refreshBtn.textContent = '⏳ Refreshing...';
    refreshBtn.disabled = true;

    try {
        // Load config
        const configResponse = await fetch('/api/config');
        if (configResponse.ok) {
            const config = await configResponse.json();
            document.getElementById('sim-mode').textContent = config.sim_mode ? 'Simulation' : 'Live Trading';
        }

        // Load positions
        const positionsResponse = await fetch('/api/positions');
        if (positionsResponse.ok) {
            const positions = await positionsResponse.json();
            document.getElementById('positions').textContent = positions.open.length;
        }

        // Load collector status
        const collectorResponse = await fetch('/api/collector/status');
        if (collectorResponse.ok) {
            const collectorData = await collectorResponse.json();
            const status = collectorData.status;
            const isRunning = collectorData.is_running;
            const dataFresh = collectorData.data_fresh;

            let statusText = "Unknown";
            let statusColor = "var(--gray-color)";

            if (status === "healthy") {
                statusText = "✅ Healthy";
                statusColor = "var(--success-color)";
            } else if (status === "stopped") {
                statusText = "❌ Stopped";
                statusColor = "var(--danger-color)";
            } else if (status === "stale_data") {
                statusText = "⚠️ Stale Data";
                statusColor = "var(--warning-color)";
            } else {
                statusText = "❓ " + status;
            }

            const collectorElement = document.getElementById('collector-status');
            collectorElement.textContent = statusText;
            collectorElement.style.color = statusColor;
        } else {
            document.getElementById('collector-status').textContent = '❌ Error';
            document.getElementById('collector-status').style.color = 'var(--danger-color)';
        }

        // Load balance
        const balanceResponse = await fetch('/api/balance?' + Date.now()); // Add timestamp to avoid cache
        console.log('Balance API response status:', balanceResponse.status);
        if (balanceResponse.ok) {
            const balanceData = await balanceResponse.json();
            console.log('Balance data received:', balanceData);
            console.log('Total balance from API:', balanceData.total_balance);
            console.log('Balances array:', balanceData.balances);
            const balances = balanceData.balances || [];
            const totalBalance = balanceData.total_balance || 0;
            const mode = balanceData.mode || 'UNKNOWN';

            // Update total balance
            const totalBalanceElement = document.getElementById('total-balance');
            console.log('Total balance element found:', !!totalBalanceElement);
            if (totalBalanceElement) {
                totalBalanceElement.textContent = `$${totalBalance.toFixed(2)} (${mode})`;
                console.log('Updated total balance to:', totalBalanceElement.textContent);
            }

            // Update individual account balances
            balances.forEach(account => {
                const accountId = account.account;
                const balanceElement = document.getElementById(`account-${accountId}-balance`);
                console.log(`Account ${accountId} balance element found:`, !!balanceElement);
                if (balanceElement) {
                    const typeLabel = account.type === 'web3' ? 'Web3' : 'Poly';
                    balanceElement.textContent = `$${account.balance.toFixed(2)} (${typeLabel})`;
                    console.log(`Updated account ${accountId} balance to:`, balanceElement.textContent);
                } else {
                    console.error(`Element account-${accountId}-balance not found!`);
                }
            });

            // Update API status based on balance response
            document.getElementById('api-status').textContent = '✅ Connected';
            document.getElementById('api-status').style.color = 'var(--success-color)';
        } else {
            console.error('Balance API failed with status:', balanceResponse.status);
            document.getElementById('total-balance').textContent = 'Error';
            document.getElementById('account-1-balance').textContent = 'Error';
            document.getElementById('account-2-balance').textContent = 'Error';
            document.getElementById('api-status').textContent = '❌ Failed';
            document.getElementById('api-status').style.color = 'var(--error-color)';
        }

        // Update last update time
        const now = new Date();
        document.getElementById('last-update').textContent = now.toLocaleTimeString();

    } catch (error) {
        console.error('Error loading system status:', error);
        // Set default values
        document.getElementById('sim-mode').textContent = 'Loading failed';
        document.getElementById('balance').textContent = 'Loading failed';
        document.getElementById('positions').textContent = 'Loading failed';
        document.getElementById('api-status').textContent = '❌ Error';
        document.getElementById('api-status').style.color = 'var(--error-color)';
    } finally {
        // Reset button
        refreshBtn.textContent = originalText;
        refreshBtn.disabled = false;
    }
}

// Load market indicators and display them
async function loadMarketIndicators() {
    const loadingDiv = document.getElementById('indicators-loading');
    const indicatorsDiv = document.getElementById('indicators-list');
    const errorDiv = document.getElementById('indicators-error');

    console.log('Starting to load market indicators');

    try {
        loadingDiv.style.display = 'block';
        indicatorsDiv.style.display = 'none';
        errorDiv.style.display = 'none';

        const apiUrl = '/api/market-indicators';
        console.log('Making API request to:', apiUrl);

        const response = await fetch(apiUrl);
        console.log('Indicators API response status:', response.status);

        if (response.ok) {
            const data = await response.json();
            console.log('Received indicators data:', data);
            displayMarketIndicators(data);
        } else {
            const errorText = await response.text();
            console.error('Indicators API request failed with status:', response.status);
            console.error('Indicators API error response:', errorText);
            throw new Error(`Indicators API request failed: ${response.status} ${response.statusText}`);
        }
    } catch (error) {
        console.error('Error loading market indicators:', error);
        loadingDiv.style.display = 'none';
        errorDiv.style.display = 'block';
    }
}

// Display market indicators in grid
function displayMarketIndicators(indicators) {
    const loadingDiv = document.getElementById('indicators-loading');
    const indicatorsDiv = document.getElementById('indicators-list');

    loadingDiv.style.display = 'none';
    indicatorsDiv.style.display = 'grid';

    const symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'];
    const cards = symbols.map(symbol => {
        const data = indicators[symbol];
        if (!data) {
            return `
                <div class="indicator-card">
                    <div class="indicator-header">
                        <span class="indicator-symbol">${symbol.replace('USDT', '')}</span>
                        <span class="indicator-price">N/A</span>
                    </div>
                    <p style="color: var(--gray-color); text-align: center;">No data available</p>
                </div>
            `;
        }

        const price = data.price ? `$${data.price.toFixed(2)}` : 'N/A';
        const momentum = data.momentum || {};
        const volatility = data.volatility || {};

        // Format momentum items
        const momentumItems = Object.entries(momentum)
            .filter(([key, value]) => value !== null)
            .map(([key, value]) => {
                const className = value > 0 ? 'positive' : value < 0 ? 'negative' : 'neutral';
                return `
                    <div class="indicator-item">
                        <span class="indicator-label">${key}</span>
                        <span class="indicator-value ${className}">${value?.toFixed(3)}%</span>
                    </div>
                `;
            }).join('');

        // Format volatility items
        const volatilityItems = Object.entries(volatility)
            .filter(([key, value]) => value !== null)
            .map(([key, value]) => `
                <div class="indicator-item">
                    <span class="indicator-label">${key}</span>
                    <span class="indicator-value neutral">${value?.toFixed(3)}%</span>
                </div>
            `).join('');

        return `
            <div class="indicator-card">
                <div class="indicator-header">
                    <span class="indicator-symbol">${symbol.replace('USDT', '')}</span>
                    <span class="indicator-price">${price}</span>
                </div>

                <div class="indicator-section">
                    <h4>Momentum</h4>
                    <div class="indicator-grid">
                        ${momentumItems || '<p style="color: var(--gray-color); font-size: 0.8rem;">No momentum data</p>'}
                    </div>
                </div>

                <div class="indicator-section">
                    <h4>Volatility</h4>
                    <div class="indicator-grid">
                        ${volatilityItems || '<p style="color: var(--gray-color); font-size: 0.8rem;">No volatility data</p>'}
                    </div>
                </div>
            </div>
        `;
    }).join('');

    indicatorsDiv.innerHTML = cards;
}

// Load top entry markets and display them
async function loadTopEntryMarkets() {
    const loadingDiv = document.getElementById('top-markets-loading');
    const errorDiv = document.getElementById('top-markets-error');

    console.log('Starting to load top entry markets');

    try {
        loadingDiv.style.display = 'block';
        errorDiv.style.display = 'none';

        const apiUrl = '/api/top-entry-markets';
        console.log('Making API request to:', apiUrl);

        const response = await fetch(apiUrl);
        console.log('Top markets API response status:', response.status);

        if (response.ok) {
            const data = await response.json();
            console.log('Received top markets data:', data);
            displayTopEntryMarkets(data);
        } else {
            const errorText = await response.text();
            console.error('Top markets API request failed with status:', response.status);
            console.error('Top markets API error response:', errorText);
            throw new Error(`Top markets API request failed: ${response.status} ${response.statusText}`);
        }
    } catch (error) {
        console.error('Error loading top entry markets:', error);
        loadingDiv.style.display = 'none';
        errorDiv.style.display = 'block';
    }
}

// Display top entry markets in grid with tabs
function displayTopEntryMarkets(data) {
    const loadingDiv = document.getElementById('top-markets-loading');
    const errorDiv = document.getElementById('top-markets-error');

    loadingDiv.style.display = 'none';
    errorDiv.style.display = 'none';

    // Display markets for each category
    displayMarketsForTab(data['15m_markets'] || [], '15m');
    displayMarketsForTab(data['1h_markets'] || [], '1h');
    displayMarketsForTab(data['all_markets'] || [], 'all');

    // Show the default active tab (15m)
    showMarketTab('15m');
}

// Display markets for a specific tab
function displayMarketsForTab(markets, tabType) {
    const container = document.getElementById(`top-markets-${tabType}`);

    if (markets.length === 0) {
        container.innerHTML = `
            <div class="top-market-card" style="text-align: center; padding: 40px;">
                <p style="color: var(--gray-color); font-size: 1.1rem;">No ${tabType === '15m' ? '15-minute' : tabType === '1h' ? '1-hour' : ''} markets starting soon with good momentum conditions</p>
                <p style="color: var(--gray-color); font-size: 0.9rem; margin-top: 10px;">Markets will appear here when they meet the entry criteria</p>
            </div>
        `;
        return;
    }

    const cards = markets.map(market => {
        const trendClass = market.trend_direction?.toLowerCase() || 'neutral';
        const momentumData = market.momentum_data || {};

        // Get best momentum value for display
        const momentumValues = Object.values(momentumData).filter(v => v !== null);
        const bestMomentum = momentumValues.length > 0 ? Math.max(...momentumValues) : 0;

        return `
            <div class="top-market-card">
                <div class="top-market-header">
                    <div class="top-market-title">${market.title}</div>
                    <div class="top-market-meta">
                        <div class="top-market-symbol">${market.symbol}</div>
                        <div class="top-market-score">Score: ${market.momentum_score}</div>
                    </div>
                </div>

                <div class="top-market-stats">
                    <div class="top-market-stat">
                        <span class="top-market-stat-label">Starts in</span>
                        <span class="top-market-stat-value">${market.minutes_until_start} min</span>
                    </div>
                    <div class="top-market-stat">
                        <span class="top-market-stat-label">Best Momentum</span>
                        <span class="top-market-stat-value ${bestMomentum > 0 ? 'positive' : bestMomentum < 0 ? 'negative' : 'neutral'}">
                            ${bestMomentum?.toFixed(2)}%
                        </span>
                    </div>
                </div>

                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <span class="top-market-trend ${trendClass}">${market.trend_direction}</span>
                        <span class="recommended-side ${market.recommended_side?.toLowerCase() || 'hold'}">
                            ${market.recommended_side === 'UP' ? '⬆️ UP' :
                              market.recommended_side === 'DOWN' ? '⬇️ DOWN' : '⏸️ HOLD'}
                        </span>
                    </div>
                    <span style="font-size: 0.9rem; color: var(--gray-color);">
                        Current: $${market.current_price?.toFixed(2) || 'N/A'}
                    </span>
                </div>

                <div class="top-market-action">
                    <button onclick="window.open('/market/${market.market_id}', '_blank')">
                        View Market Details
                    </button>
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = cards;
}

// Show specific market tab
function showMarketTab(tabType) {
    // Hide all tab contents
    const allTabs = ['15m', '1h', 'all'];
    allTabs.forEach(type => {
        const container = document.getElementById(`top-markets-${type}`);
        const button = document.querySelector(`.tab-btn[onclick="showMarketTab('${type}')"]`);
        if (container) container.style.display = 'none';
        if (button) button.classList.remove('active');
    });

    // Show selected tab
    const selectedContainer = document.getElementById(`top-markets-${tabType}`);
    const selectedButton = document.querySelector(`.tab-btn[onclick="showMarketTab('${tabType}')"]`);
    if (selectedContainer) selectedContainer.style.display = 'grid';
    if (selectedButton) selectedButton.classList.add('active');
}

// Refresh system status periodically
setInterval(loadSystemStatus, 30000); // Refresh every 30 seconds

// Refresh market indicators periodically
setInterval(loadMarketIndicators, 10000); // Refresh every 10 seconds

// Refresh top entry markets periodically
setInterval(loadTopEntryMarkets, 30000); // Refresh every 30 seconds
