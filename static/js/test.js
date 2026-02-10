// Polymarket Bot V2 - Test Page JavaScript

async function analyzeRandomMarket() {
    const resultDiv = document.getElementById('result');
    const btn = document.getElementById('analyzeBtn');

    // Update button state
    btn.disabled = true;
    btn.innerHTML = '<span class="loading"></span>Анализируем...';

    try {
        const response = await fetch('/api/market/random');
        const data = await response.json();

        if (response.ok) {
            displayAnalysis(data);
            resultDiv.classList.remove('hidden');
        } else {
            displayError(data.detail || 'Неизвестная ошибка');
        }
    } catch (error) {
        displayError(error.message);
    } finally {
        // Reset button state
        btn.disabled = false;
        btn.innerHTML = '🎯 Проанализировать случайный рынок';
    }
}

function displayAnalysis(data) {
    const resultDiv = document.getElementById('result');

    const priceToBeat = data.price_to_beat || 0;
    const currentPrice = data.current_price || 0;
    const deviation = data.deviation || {};

    let html = `
        <div class="result-card">
            <h3>🎯 ${data.title}</h3>
            <p><strong>ID:</strong> ${data.market_id}</p>
            <p><strong>Символ:</strong> ${data.symbol}</p>

            <h4>💰 PRICE TO BEAT & DEVIATION</h4>
            <p><strong>Price to Beat:</strong> <span class="price-up">$${priceToBeat.toFixed(2)}</span></p>
            <p><strong>Текущая цена:</strong> $${currentPrice.toFixed(2)}</p>
            <p><strong>Deviation:</strong> <span class="${deviation.position === 'UP' ? 'price-up' : deviation.position === 'DOWN' ? 'price-down' : 'neutral'}">${deviation.deviation_pct?.toFixed(2)}%</span></p>
            <p><strong>Позиция:</strong> ${deviation.description || 'N/A'}</p>

            <h4>💰 ORDERBOOK</h4>
            <div class="metrics-grid">
                <div class="metric">UP Bid: $${(data.orderbook?.up_bid || 0).toFixed(4)}</div>
                <div class="metric">UP Ask: $${(data.orderbook?.up_ask || 0).toFixed(4)}</div>
                <div class="metric">UP Spread: $${(data.orderbook?.up_spread || 0).toFixed(4)}</div>
                <div class="metric">DOWN Bid: $${(data.orderbook?.down_bid || 0).toFixed(4)}</div>
                <div class="metric">DOWN Ask: $${(data.orderbook?.down_ask || 0).toFixed(4)}</div>
                <div class="metric">DOWN Spread: $${(data.orderbook?.down_spread || 0).toFixed(4)}</div>
            </div>

            <h4>🎲 КОЭФФИЦИЕНТЫ</h4>
            <div class="metrics-grid">
                <div class="metric">UP Edge: ${(data.probabilities?.up?.edge * 100 || 0).toFixed(1)}%</div>
                <div class="metric">DOWN Edge: ${(data.probabilities?.down?.edge * 100 || 0).toFixed(1)}%</div>
                <div class="metric">UP Prob: ${(data.probabilities?.up?.math_prob * 100 || 0).toFixed(1)}%</div>
                <div class="metric">DOWN Prob: ${(data.probabilities?.down?.math_prob * 100 || 0).toFixed(1)}%</div>
                <div class="metric">KF: ${(data.probabilities?.up?.kf || 0).toFixed(2)}</div>
                <div class="metric">Z-Score: ${(data.probabilities?.up?.z_score || 0).toFixed(2)}</div>
            </div>

            <h4>📊 РЕКОМЕНДАЦИЯ</h4>
            <p><strong>Действие:</strong> ${data.recommendation?.action || 'N/A'}</p>
            <p><strong>Уверенность:</strong> ${(data.recommendation?.confidence * 100 || 0).toFixed(0)}%</p>
            <p><strong>Причина:</strong> ${data.recommendation?.reason || 'N/A'}</p>

            <h4>⏰ ВРЕМЕННЫЕ МЕТРИКИ</h4>
            <div class="metrics-grid">
                <div class="metric">Осталось: ${(data.time_metrics?.time_remaining_minutes || 0).toFixed(1)} мин</div>
                <div class="metric">Длительность: ${(data.time_metrics?.market_duration_minutes || 0).toFixed(1)} мин</div>
                <div class="metric">Прошло: ${(data.time_metrics?.minutes_since_open || 0).toFixed(1)} мин</div>
            </div>

            <h4>📈 ВОЛАТИЛЬНОСТЬ</h4>
            <div class="metrics-grid">
                <div class="metric">15m: ${(data.volatility?.['15m'] * 100 || 0).toFixed(2)}%</div>
                <div class="metric">1h: ${(data.volatility?.['1h'] * 100 || 0).toFixed(2)}%</div>
                <div class="metric">5m: ${(data.volatility?.['5m'] * 100 || 0).toFixed(2)}%</div>
            </div>
        </div>
    `;

    resultDiv.innerHTML = html;
}

function displayError(errorMessage) {
    const resultDiv = document.getElementById('result');

    const html = `
        <div class="error-result">
            <h3>❌ Ошибка</h3>
            <p>${errorMessage}</p>
        </div>
    `;

    resultDiv.innerHTML = html;
    resultDiv.classList.remove('hidden');
}