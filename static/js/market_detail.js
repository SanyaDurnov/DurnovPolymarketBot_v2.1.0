// Durnov Polybot V2 - Market Detail JavaScript

// Cached orderbook data for quick buy orders
let cachedOrderbook = null;

// Tab switching functionality (defined globally for onclick handlers)
function showMarketDetailTab(tabName) {
    console.log('Switching to tab:', tabName);

    // Hide all tabs
    const tabs = document.querySelectorAll('.tab-content');
    console.log('Found tabs:', tabs.length);
    tabs.forEach(tab => {
        tab.style.display = 'none';
        console.log('Hid tab:', tab.id);
    });

    // Remove active class from all buttons
    const buttons = document.querySelectorAll('.tab-btn');
    buttons.forEach(btn => btn.classList.remove('active'));

    // Show selected tab
    const selectedTab = document.getElementById(tabName + '-tab');
    console.log('Selected tab element:', selectedTab);
    if (selectedTab) {
        selectedTab.style.display = 'block';
        console.log('Showed tab:', tabName + '-tab');
    } else {
        console.error('Tab not found:', tabName + '-tab');
    }

    // Add active class to clicked button
    const activeButton = document.querySelector(`[onclick="showMarketDetailTab('${tabName}')"]`);
    if (activeButton) {
        activeButton.classList.add('active');
        console.log('Activated button for:', tabName);
    } else {
        console.error('Button not found for:', tabName);
    }

    // Load positions if positions tab is selected
    if (tabName === 'positions') {
        console.log('Loading positions...');
        loadMarketPositions();
    }
}

document.addEventListener('DOMContentLoaded', function() {
    // Get market ID from URL
    const urlParams = new URLSearchParams(window.location.search);
    const marketId = window.location.pathname.split('/').pop();

    console.log('Market Detail Page Loaded');
    console.log('Current URL:', window.location.href);
    console.log('Extracted marketId:', marketId);

    if (marketId) {
        loadMarketData(marketId);

        // Автообновление данных каждые 15 секунд (данные кэшируются каждую секунду)
        setInterval(() => {
            loadMarketData(marketId, false); // false = тихое обновление без loading
        }, 15000);

        console.log('Auto-refresh enabled: every 15 seconds (cached data updates every 1 second)');
    } else {
        console.error('No marketId found in URL');
        showError();
    }
});

// Load market data from API
async function loadMarketData(marketId, showLoading = true) {
    const loadingDiv = document.getElementById('loading');
    const contentDiv = document.getElementById('market-content');
    const errorDiv = document.getElementById('error');

    console.log('Starting to load market data for marketId:', marketId, showLoading ? '(with loading)' : '(silent update)');

    try {
        if (showLoading) {
            loadingDiv.style.display = 'block';
            contentDiv.style.display = 'none';
            errorDiv.style.display = 'none';
        }

        const apiUrl = `/api/market/${marketId}`;
        console.log('Making API request to:', apiUrl);

        const response = await fetch(apiUrl);
        console.log('API response status:', response.status);
        console.log('API response ok:', response.ok);

        if (response.ok) {
            const data = await response.json();
            console.log('Received market data:', data);
            displayMarketData(data);
        } else {
            const errorText = await response.text();
            console.error('API request failed with status:', response.status);
            console.error('Error response:', errorText);

            // Специальная обработка для 404 (рынок не найден)
            if (response.status === 404) {
                throw new Error(`Market ${marketId} not found or inactive. Please check the market ID.`);
            } else {
                throw new Error(`API request failed: ${response.status} ${response.statusText}`);
            }
        }
    } catch (error) {
        console.error('Error loading market data:', error);
        console.error('Error details:', {
            name: error.name,
            message: error.message,
            stack: error.stack
        });
        showError(error.message);
    }
}

// Display market data in the UI
function displayMarketData(data) {
    const loadingDiv = document.getElementById('loading');
    const contentDiv = document.getElementById('market-content');

    // Update page title
    document.title = `${data.title} - Durnov Polybot V2`;

    // Market header
    document.getElementById('market-title').textContent = data.title;
    document.getElementById('market-id').textContent = data.market_id;
    document.getElementById('market-symbol').textContent = data.symbol || 'N/A';

    const statusElement = document.getElementById('market-status');
    const isActive = data.status !== 'inactive' && data.status !== 'error';
    statusElement.textContent = isActive ? 'Active' : 'Inactive';
    statusElement.className = `value status ${isActive ? 'active' : 'inactive'}`;

    // Price to Beat & Deviation
    document.getElementById('price-to-beat').textContent = `$${data.price_to_beat?.toFixed(2) || '0.00'}`;
    document.getElementById('current-price').textContent = `$${data.current_price?.toFixed(2) || '0.00'}`;

    const deviationElement = document.getElementById('deviation');
    const deviation = data.deviation || {};
    deviationElement.textContent = `${deviation.deviation_pct?.toFixed(2) || '0.00'}%`;
    deviationElement.className = `metric-value ${deviation.position === 'UP' ? 'price-up' : deviation.position === 'DOWN' ? 'price-down' : ''}`;

    document.getElementById('position').textContent = deviation.description || 'N/A';

    // Orderbook - проверяем статус рынка
    const orderbook = data.orderbook || {};
    cachedOrderbook = orderbook;
    if (data.status === "inactive" || orderbook.message === "Market is inactive") {
        // Для неактивных рынков показываем сообщение
        document.getElementById('up-bid').textContent = "N/A";
        document.getElementById('up-ask').textContent = "N/A";
        document.getElementById('up-spread').textContent = "N/A";
        document.getElementById('down-bid').textContent = "N/A";
        document.getElementById('down-ask').textContent = "N/A";
        document.getElementById('down-spread').textContent = "N/A";

        // Показываем сообщение о неактивности
        const inactiveMessage = document.createElement('div');
        inactiveMessage.className = 'inactive-message';
        inactiveMessage.textContent = data.message || "Market is inactive";
        inactiveMessage.style.cssText = `
            grid-column: 1 / -1;
            text-align: center;
            color: #ff6b6b;
            font-weight: bold;
            padding: 20px;
            background: #ffebee;
            border-radius: 8px;
            margin-top: 10px;
        `;

        // Добавляем сообщение в orderbook секцию
        const orderbookSection = document.querySelector('.orderbook-section');
        if (orderbookSection) {
            // Удаляем предыдущее сообщение если есть
            const existingMessage = orderbookSection.querySelector('.inactive-message');
            if (existingMessage) {
                existingMessage.remove();
            }
            orderbookSection.appendChild(inactiveMessage);
        }
    } else {
        // Для активных рынков показываем orderbook
        document.getElementById('up-bid').textContent = (orderbook.up_bid || 0).toFixed(4);
        document.getElementById('up-ask').textContent = (orderbook.up_ask || 0).toFixed(4);
        document.getElementById('up-spread').textContent = (orderbook.up_spread || 0).toFixed(4);
        document.getElementById('down-bid').textContent = (orderbook.down_bid || 0).toFixed(4);
        document.getElementById('down-ask').textContent = (orderbook.down_ask || 0).toFixed(4);
        document.getElementById('down-spread').textContent = (orderbook.down_spread || 0).toFixed(4);

        // Удаляем сообщение о неактивности если есть
        const orderbookSection = document.querySelector('.orderbook-section');
        if (orderbookSection) {
            const existingMessage = orderbookSection.querySelector('.inactive-message');
            if (existingMessage) {
                existingMessage.remove();
            }
        }
    }

    // Probabilities
    const probabilities = data.probabilities || {};
    document.getElementById('up-edge').textContent = `${((probabilities.up?.edge || 0) * 100).toFixed(1)}%`;
    document.getElementById('down-edge').textContent = `${((probabilities.down?.edge || 0) * 100).toFixed(1)}%`;
    document.getElementById('up-prob').textContent = `${((probabilities.up?.reach_probability || 0) * 100).toFixed(1)}%`;
    document.getElementById('down-prob').textContent = `${((probabilities.down?.reach_probability || 0) * 100).toFixed(1)}%`;

    // Absorption Probabilities
    const absorptionProbabilities = data.absorption_probabilities || {};
    document.getElementById('up-absorption-prob').textContent = `${((absorptionProbabilities.up?.absorption_prob || 0) * 100).toFixed(1)}%`;
    document.getElementById('down-absorption-prob').textContent = `${((absorptionProbabilities.down?.absorption_prob || 0) * 100).toFixed(1)}%`;

    document.getElementById('kf-score').textContent = (probabilities.up?.kf || 0).toFixed(2);
    document.getElementById('z-score').textContent = (probabilities.up?.z_score || 0).toFixed(2);

    // Probability Formula
    const formula = probabilities.up?.formula || {};
    document.getElementById('formula-equation').textContent = formula.formula || 'P = 1 - Φ(z)';
    document.getElementById('formula-explanation').textContent = formula.explanation || 'z = price_move_pct / std_dev_pct';
    document.getElementById('vol-used').textContent = `${((formula.volatility_used || 0) * 100).toFixed(2)}%`;
    document.getElementById('time-remaining-var').textContent = `${(formula.time_remaining_minutes || 0).toFixed(1)} min`;
    document.getElementById('price-move-pct').textContent = `${(probabilities.up?.price_move_pct || 0).toFixed(2)}%`;
    document.getElementById('std-dev-pct').textContent = `${(probabilities.up?.std_dev_pct || 0).toFixed(2)}%`;
    document.getElementById('z-score-var').textContent = (probabilities.up?.z_score || 0).toFixed(2);
    document.getElementById('market-direction').textContent = data.direction || 'UNKNOWN';

    // Std Dev Calculation
    const stdDevCalc = formula.std_dev_calculation || {};
    document.getElementById('std-dev-vol-pct').textContent = (stdDevCalc.volatility_pct || 0).toFixed(4);
    document.getElementById('std-dev-time-remaining').textContent = (stdDevCalc.time_remaining_minutes || 0).toFixed(1);
    document.getElementById('std-dev-vol-period').textContent = (stdDevCalc.vol_period_minutes || 0).toFixed(1);
    document.getElementById('std-dev-time-ratio').textContent = (stdDevCalc.sqrt_term || 0).toFixed(4);
    document.getElementById('std-dev-sqrt').textContent = Math.sqrt(stdDevCalc.sqrt_term || 0).toFixed(4);
    document.getElementById('std-dev-result').textContent = `${(stdDevCalc.std_dev_pct || 0).toFixed(4)}%`;

    // Time metrics - используем данные из formula или значения по умолчанию
    const timeMetrics = formula || {};
    document.getElementById('time-remaining').textContent = `${(timeMetrics.time_remaining_minutes || 0).toFixed(1)} min`;
    document.getElementById('market-duration').textContent = `${(timeMetrics.market_duration_minutes || 0).toFixed(1)} min`;
    document.getElementById('time-since-open').textContent = `${(timeMetrics.minutes_since_open || 0).toFixed(1)} min`;

    // Volatility
    const volatility = data.volatility || {};
    document.getElementById('vol-5m').textContent = `${((volatility['5m'] || 0) * 100).toFixed(2)}%`;
    document.getElementById('vol-15m').textContent = `${((volatility['15m'] || 0) * 100).toFixed(2)}%`;
    document.getElementById('vol-1h').textContent = `${((volatility['1h'] || 0) * 100).toFixed(2)}%`;

    // Update entry buttons based on market status
    updateEntryButtons(data);

    // Show content
    loadingDiv.style.display = 'none';
    contentDiv.style.display = 'block';
}



// Load market positions
async function loadMarketPositions() {
    const marketId = window.location.pathname.split('/').pop();
    const positionsLoading = document.getElementById('positions-loading');
    const positionsList = document.getElementById('positions-list');
    const positionsError = document.getElementById('positions-error');

    if (!marketId) {
        console.error('No marketId found for positions');
        return;
    }

    try {
        positionsLoading.style.display = 'block';
        positionsList.style.display = 'none';
        positionsError.style.display = 'none';

        const response = await fetch('/api/positions');
        if (response.ok) {
            const data = await response.json();
            displayMarketPositions(data, marketId);
        } else {
            throw new Error(`API request failed: ${response.status}`);
        }
    } catch (error) {
        console.error('Error loading positions:', error);
        positionsLoading.style.display = 'none';
        positionsError.style.display = 'block';
        document.getElementById('positions-error').querySelector('p').textContent =
            'Failed to load positions. Please try again later.';
    }
}

// Display market positions
function displayMarketPositions(data, marketId) {
    const positionsLoading = document.getElementById('positions-loading');
    const positionsList = document.getElementById('positions-list');

    console.log('Displaying positions for market:', marketId);
    console.log('Open positions:', data.open.length);
    console.log('Closed positions:', data.closed.length);

    // Filter positions for this market
    const marketPositions = data.open.filter(pos => pos.market_id === marketId);

    console.log('Positions for this market:', marketPositions.length);

    if (marketPositions.length === 0) {
        positionsList.innerHTML = '<p style="text-align: center; color: #666; padding: 20px;">No open positions for this market.</p>';
    } else {
        let html = '<div class="positions-table">';

        marketPositions.forEach(pos => {
            const pnlClass = pos.pnl_usd >= 0 ? 'positive' : 'negative';
            const pnlSign = pos.pnl_usd >= 0 ? '+' : '';

            html += `
                <div class="position-card">
                    <div class="position-header">
                        <span class="position-id">${pos.position_id}</span>
                        <span class="position-side ${pos.side?.toLowerCase()}">${pos.side || 'UNKNOWN'}</span>
                    </div>
                    <div class="position-details">
                        <div class="detail-item">
                            <span class="label">Market:</span>
                            <span class="value">${pos.market_title || 'Unknown'}</span>
                        </div>
                        <div class="detail-item">
                            <span class="label">Symbol:</span>
                            <span class="value">${pos.symbol || 'N/A'}</span>
                        </div>
                        <div class="detail-item">
                            <span class="label">Entry Price:</span>
                            <span class="value">$${pos.entry_price_avg?.toFixed(4) || '0.0000'}</span>
                        </div>
                        <div class="detail-item">
                            <span class="label">Volume:</span>
                            <span class="value">${pos.total_volume?.toFixed(6) || '0.000000'}</span>
                        </div>
                        <div class="detail-item">
                            <span class="label">Total Cost:</span>
                            <span class="value">$${pos.total_cost_usd?.toFixed(2) || '0.00'}</span>
                        </div>
                        <div class="detail-item">
                            <span class="label">Entry Time:</span>
                            <span class="value">${pos.entry_time ? new Date(pos.entry_time).toLocaleString() : 'N/A'}</span>
                        </div>
                        <div class="detail-item">
                            <span class="label">Reason:</span>
                            <span class="value">${pos.entry_reason || 'N/A'}</span>
                        </div>
                        <div class="detail-item">
                            <span class="label">Status:</span>
                            <span class="value">${pos.status || 'UNKNOWN'}</span>
                        </div>
                        ${pos.pnl_usd !== undefined ? `
                        <div class="detail-item">
                            <span class="label">P&L USD:</span>
                            <span class="value ${pnlClass}">${pnlSign}$${pos.pnl_usd?.toFixed(2) || '0.00'}</span>
                        </div>
                        <div class="detail-item">
                            <span class="label">P&L %:</span>
                            <span class="value ${pnlClass}">${pnlSign}${pos.pnl_pct?.toFixed(2) || '0.00'}%</span>
                        </div>
                        ` : ''}
                    </div>
                </div>
            `;
        });

        html += '</div>';
        positionsList.innerHTML = html;
    }

    positionsLoading.style.display = 'none';
    positionsList.style.display = 'block';
}

// Manual market entry function
async function manualEnterMarket(side) {
    const marketId = window.location.pathname.split('/').pop();
    const statusElement = document.getElementById('entry-status');
    const upBtn = document.getElementById('enter-up-btn');
    const downBtn = document.getElementById('enter-down-btn');

    if (!marketId) {
        console.error('No marketId found');
        statusElement.textContent = '❌ Ошибка: ID рынка не найден';
        statusElement.style.color = 'var(--danger-color)';
        return;
    }

    try {
        // Disable buttons during request
        upBtn.disabled = true;
        downBtn.disabled = true;
        statusElement.textContent = '⏳ Запуск процесса входа...';
        statusElement.style.color = 'var(--warning-color)';

        console.log(`Starting manual entry for market ${marketId} on ${side} side`);

        const response = await fetch(`/api/market/${marketId}/enter?side=${side}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });

        const result = await response.json();

        if (response.ok) {
            console.log('Entry process started successfully:', result);
            statusElement.textContent = `✅ ${result.message || 'Процесс входа запущен'}`;
            statusElement.style.color = 'var(--success-color)';

            // Обновляем позиции через 5 секунд
            setTimeout(() => {
                loadMarketPositions();
                loadSystemStatus(); // Обновляем баланс и статистику
            }, 5000);

        } else {
            console.error('Entry failed:', result);
            statusElement.textContent = `❌ Ошибка: ${result.detail || 'Не удалось запустить процесс входа'}`;
            statusElement.style.color = 'var(--danger-color)';
        }

    } catch (error) {
        console.error('Error during manual entry:', error);
        statusElement.textContent = '❌ Ошибка сети при запуске входа';
        statusElement.style.color = 'var(--danger-color)';
    } finally {
        // Re-enable buttons
        upBtn.disabled = false;
        downBtn.disabled = false;
    }
}

// Update entry buttons based on market status
function updateEntryButtons(data) {
    const upBtn = document.getElementById('enter-up-btn');
    const downBtn = document.getElementById('enter-down-btn');
    const statusElement = document.getElementById('entry-status');
    const buyUpBtn = document.getElementById('buy-up-btn');
    const buyDownBtn = document.getElementById('buy-down-btn');

    const isActive = data.status !== 'inactive' && data.status !== 'error';
    const hasOrderbook = data.orderbook && data.orderbook.message !== "Market is inactive";

    if (isActive && hasOrderbook) {
        // Enable buttons for active markets
        upBtn.disabled = false;
        downBtn.disabled = false;
        if (buyUpBtn) buyUpBtn.disabled = false;
        if (buyDownBtn) buyDownBtn.disabled = false;
        statusElement.textContent = 'Готов к входу в рынок';
        statusElement.style.color = 'var(--success-color)';
    } else {
        // Disable buttons for inactive markets
        upBtn.disabled = true;
        downBtn.disabled = true;
        if (buyUpBtn) buyUpBtn.disabled = true;
        if (buyDownBtn) buyDownBtn.disabled = true;
        statusElement.textContent = data.message || 'Рынок неактивен - вход невозможен';
        statusElement.style.color = 'var(--danger-color)';
    }
}

// Quick buy order - places REAL order via test_buy endpoint (bypasses SIM_MODE)
async function quickBuyOrder(side) {
    const marketId = window.location.pathname.split('/').pop();
    const statusElement = document.getElementById('buy-order-status');
    const buyUpBtn = document.getElementById('buy-up-btn');
    const buyDownBtn = document.getElementById('buy-down-btn');

    if (!marketId) {
        statusElement.textContent = '❌ Ошибка: ID рынка не найден';
        statusElement.style.color = 'var(--danger-color)';
        return;
    }

    if (!cachedOrderbook) {
        statusElement.textContent = '❌ Ошибка: данные orderbook не загружены';
        statusElement.style.color = 'var(--danger-color)';
        return;
    }

    // Get current ask price for the selected side
    const currentAsk = side === 'UP' ? cachedOrderbook.up_ask : cachedOrderbook.down_ask;
    if (!currentAsk || currentAsk <= 0) {
        statusElement.textContent = `❌ Ошибка: нет цены ask для ${side}`;
        statusElement.style.color = 'var(--danger-color)';
        return;
    }

    // Calculate limit price: -5% from current ask, rounded to 2 decimals
    const limitPrice = Math.round(currentAsk * 0.95 * 100) / 100;
    const amount = 1; // $1 test order

    // Confirm before placing real order
    const confirmed = confirm(
        `⚠️ REAL ORDER (bypasses SIM mode)\n\n` +
        `BUY ${side} for $${amount}\n` +
        `Current ask: ${currentAsk.toFixed(4)}\n` +
        `Limit price: ${limitPrice.toFixed(2)} (-5%)\n\n` +
        `Proceed?`
    );

    if (!confirmed) {
        statusElement.textContent = 'Отменено пользователем';
        statusElement.style.color = 'var(--gray-color)';
        return;
    }

    try {
        buyUpBtn.disabled = true;
        buyDownBtn.disabled = true;
        statusElement.textContent = '⏳ Отправка ордера...';
        statusElement.style.color = 'var(--warning-color)';

        const params = new URLSearchParams({
            market_id: marketId,
            side: side,
            amount: amount.toString(),
            price: limitPrice.toString(),
        });

        const response = await fetch(`/api/order/test_buy?${params}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });

        const result = await response.json();

        if (response.ok && result.success) {
            statusElement.textContent = `✅ BUY ${side} $${amount} @ ${limitPrice.toFixed(2)} - ордер размещён!`;
            statusElement.style.color = 'var(--success-color)';
            console.log('Test buy order result:', result);
        } else {
            statusElement.textContent = `❌ Ошибка: ${result.detail || 'Не удалось разместить ордер'}`;
            statusElement.style.color = 'var(--danger-color)';
            console.error('Test buy order failed:', result);
        }

    } catch (error) {
        console.error('Error placing test buy order:', error);
        statusElement.textContent = '❌ Ошибка сети';
        statusElement.style.color = 'var(--danger-color)';
    } finally {
        buyUpBtn.disabled = false;
        buyDownBtn.disabled = false;
    }
}

// Show error message
function showError(errorMessage = 'Failed to load market data. Please try again.') {
    const loadingDiv = document.getElementById('loading');
    const errorDiv = document.getElementById('error');

    console.log('Showing error message:', errorMessage);

    // Update error message in the DOM
    const errorTextElement = document.getElementById('error-message');
    if (errorTextElement) {
        errorTextElement.textContent = errorMessage;
    }

    loadingDiv.style.display = 'none';
    errorDiv.style.display = 'block';
}
