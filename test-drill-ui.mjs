import { chromium } from 'playwright';

(async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    await page.goto('http://localhost:8090', { waitUntil: 'networkidle' });
    await page.waitForTimeout(3000);

    // Drill 모드 진입
    await page.click('button[data-tool="drill"]');
    await page.waitForTimeout(2000);

    // 반지름 10으로 변경
    await page.$eval('#drill-radius', el => {
        el.value = 10;
        el.dispatchEvent(new Event('input'));
    });

    // 마우스를 모델 위로 이동
    const canvas = await page.$('#canvas-container canvas');
    const box = await canvas.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.waitForTimeout(500);

    // 스크린샷
    await page.screenshot({ path: 'test-drill-result.png' });

    // 프리뷰 구성 확인
    const info = await page.evaluate(() => {
        const children = drillPreview.children.length;
        const wire = drillPreview.children[0];
        return {
            childCount: children,
            wireColor: wire.material.color.getHex().toString(16),
            wireOpacity: wire.material.opacity,
            wireframe: wire.material.wireframe,
            visible: drillPreview.visible
        };
    });

    console.log(`프리뷰 구성: 자식=${info.childCount}개 (와이어프레임만)`);
    console.log(`와이어: color=0x${info.wireColor}, opacity=${info.wireOpacity}, wireframe=${info.wireframe}`);
    console.log(`표시: ${info.visible}`);
    console.log('스크린샷: test-drill-result.png');

    await browser.close();
})();
