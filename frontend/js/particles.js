/**
 * 钢子出击 - 粒子背景动画
 * Canvas 粒子漂浮 + 近距离连线
 * 手机端自动关闭连线（O(n^2) 太耗电），减少粒子数到 15 个
 * 支持 localStorage 手动开关：gangzi_particles = "off" 禁用
 */

let particlesArray = [];
let particleCanvas, particleCtx;
let particleAnimId;
let _isMobile = false;

export function initParticles() {
    // 用户手动关闭粒子（设置页可控）
    if (localStorage.getItem('gangzi_particles') === 'off') return;

    // 手机端 + 低性能设备检测
    _isMobile = window.innerWidth < 768 ||
        /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent);

    // 尊重系统减少动画偏好
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    particleCanvas = document.getElementById('particleCanvas');
    if (!particleCanvas) return;

    particleCtx = particleCanvas.getContext('2d');
    resizeParticleCanvas();
    window.addEventListener('resize', resizeParticleCanvas);

    // 手机端大幅减少粒子数
    const count = _isMobile ? 15 : 60;

    particlesArray = [];
    for (let i = 0; i < count; i++) {
        particlesArray.push(createParticle());
    }

    animateParticles();
}

function resizeParticleCanvas() {
    if (!particleCanvas) return;
    particleCanvas.width = window.innerWidth;
    particleCanvas.height = window.innerHeight;
}

function createParticle() {
    return {
        x: Math.random() * (particleCanvas?.width || 1920),
        y: Math.random() * (particleCanvas?.height || 1080),
        size: Math.random() * 1.5 + 0.5,
        speedX: (Math.random() - 0.5) * 0.3,
        speedY: (Math.random() - 0.5) * 0.3,
        opacity: Math.random() * 0.4 + 0.1,
        color: Math.random() > 0.5 ? '0, 212, 255' : '6, 182, 212',
    };
}

function animateParticles() {
    if (!particleCtx || !particleCanvas) return;

    particleCtx.clearRect(0, 0, particleCanvas.width, particleCanvas.height);

    // 更新和绘制粒子
    particlesArray.forEach(p => {
        p.x += p.speedX;
        p.y += p.speedY;

        if (p.x < 0 || p.x > particleCanvas.width) p.speedX *= -1;
        if (p.y < 0 || p.y > particleCanvas.height) p.speedY *= -1;

        particleCtx.beginPath();
        particleCtx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        particleCtx.fillStyle = `rgba(${p.color}, ${p.opacity})`;
        particleCtx.fill();
    });

    // 手机端跳过连线（O(n^2) 算法太耗电）
    if (!_isMobile) {
        const maxDist = 100;
        const maxDist2 = maxDist * maxDist;
        for (let i = 0; i < particlesArray.length; i++) {
            for (let j = i + 1; j < particlesArray.length; j++) {
                const dx = particlesArray[i].x - particlesArray[j].x;
                const dy = particlesArray[i].y - particlesArray[j].y;
                const dist2 = dx * dx + dy * dy;
                if (dist2 > maxDist2) continue;

                const dist = Math.sqrt(dist2);
                const alpha = 0.08 * (1 - dist / maxDist);
                particleCtx.strokeStyle = `rgba(0, 212, 255, ${alpha})`;
                particleCtx.lineWidth = 0.5;
                particleCtx.beginPath();
                particleCtx.moveTo(particlesArray[i].x, particlesArray[i].y);
                particleCtx.lineTo(particlesArray[j].x, particlesArray[j].y);
                particleCtx.stroke();
            }
        }
    }

    particleAnimId = requestAnimationFrame(animateParticles);
}

// 停止粒子动画
export function stopParticles() {
    if (particleAnimId) {
        cancelAnimationFrame(particleAnimId);
        particleAnimId = null;
    }
    if (particleCtx && particleCanvas) {
        particleCtx.clearRect(0, 0, particleCanvas.width, particleCanvas.height);
    }
}

// 后台暂停动画节省电量
let particlesPaused = false;
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        if (particleAnimId) {
            cancelAnimationFrame(particleAnimId);
            particleAnimId = null;
            particlesPaused = true;
        }
    } else if (particlesPaused) {
        particlesPaused = false;
        animateParticles();
    }
});

// 保持 window 全局引用（其他非模块文件可能通过 GangziApp 调用）
window.GangziApp = window.GangziApp || {};
window.GangziApp.initParticles = initParticles;
window.GangziApp.stopParticles = stopParticles;
