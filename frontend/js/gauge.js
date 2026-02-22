/**
 * 钢子出击 - AI 信心仪表盘（Canvas 转速表）
 * 半圆仪表盘、0-100 刻度、渐变色、弹簧指针动画
 * #21 修复：增加动画取消机制，避免新旧动画同时在 Canvas 上绘制
 */

let _gaugeAnimId = null; // 当前 gauge 动画 rAF ID

export function drawGauge(canvas, value, options = {}) {
    if (!canvas) return;
    // #21 修复：取消旧动画
    if (_gaugeAnimId) { cancelAnimationFrame(_gaugeAnimId); _gaugeAnimId = null; }

    const ctx = canvas.getContext('2d');
    const W = canvas.width;
    const H = canvas.height;
    const centerX = W / 2;
    const centerY = H - 10;
    const radius = Math.min(W / 2 - 10, H - 20);

    const {
        animate = true,
        duration = 800,
    } = options;

    const startAngle = Math.PI;
    const endAngle = 2 * Math.PI;
    const targetAngle = startAngle + (value / 100) * Math.PI;

    let currentAngle = startAngle;
    let startTime = null;

    function easeOutBack(t) {
        const c1 = 1.70158;
        const c3 = c1 + 1;
        return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
    }

    function render(angle) {
        ctx.clearRect(0, 0, W, H);

        // 背景弧
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, startAngle, endAngle);
        ctx.lineWidth = 8;
        ctx.strokeStyle = 'rgba(35, 42, 54, 0.8)';
        ctx.stroke();

        // 渐变弧（红->黄->绿）
        const gradient = ctx.createLinearGradient(centerX - radius, centerY, centerX + radius, centerY);
        gradient.addColorStop(0, '#ff4757');
        gradient.addColorStop(0.35, '#ffc107');
        gradient.addColorStop(0.65, '#ffc107');
        gradient.addColorStop(1, '#00d68f');

        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, startAngle, angle);
        ctx.lineWidth = 8;
        ctx.lineCap = 'round';
        ctx.strokeStyle = gradient;
        ctx.stroke();

        // 刻度线
        for (let i = 0; i <= 10; i++) {
            const a = startAngle + (i / 10) * Math.PI;
            const isMain = i % 5 === 0;
            const inner = radius - (isMain ? 16 : 10);
            const outer = radius - 2;

            ctx.beginPath();
            ctx.moveTo(centerX + inner * Math.cos(a), centerY + inner * Math.sin(a));
            ctx.lineTo(centerX + outer * Math.cos(a), centerY + outer * Math.sin(a));
            ctx.lineWidth = isMain ? 2 : 1;
            ctx.strokeStyle = 'rgba(107, 117, 133, 0.5)';
            ctx.stroke();
        }

        // 指针
        const pointerLen = radius - 22;
        const pointerX = centerX + pointerLen * Math.cos(angle);
        const pointerY = centerY + pointerLen * Math.sin(angle);

        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.lineTo(pointerX, pointerY);
        ctx.lineWidth = 2.5;
        ctx.lineCap = 'round';
        ctx.strokeStyle = '#e8ecf1';
        ctx.stroke();

        // 中心圆点
        ctx.beginPath();
        ctx.arc(centerX, centerY, 5, 0, Math.PI * 2);
        ctx.fillStyle = '#3b82f6';
        ctx.fill();

        // 中间数字
        ctx.font = 'bold 18px -apple-system, sans-serif';
        ctx.fillStyle = '#e8ecf1';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'bottom';
        ctx.fillText(`${Math.round(value)}%`, centerX, centerY - 10);
    }

    if (animate) {
        function step(timestamp) {
            if (!startTime) startTime = timestamp;
            const elapsed = timestamp - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const easedProgress = easeOutBack(progress);

            currentAngle = startAngle + easedProgress * (targetAngle - startAngle);
            render(currentAngle);

            if (progress < 1) {
                _gaugeAnimId = requestAnimationFrame(step);
            } else {
                _gaugeAnimId = null;
            }
        }
        _gaugeAnimId = requestAnimationFrame(step);
    } else {
        render(targetAngle);
    }
}

// 保持 window 全局引用（其他非模块文件可能通过 GangziApp.drawGauge 调用）
window.GangziApp = window.GangziApp || {};
window.GangziApp.drawGauge = drawGauge;
