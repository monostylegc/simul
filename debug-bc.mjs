import { chromium } from '@playwright/test';

(async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    const logs = [];
    page.on('console', msg => logs.push('[' + msg.type() + '] ' + msg.text()));
    page.on('pageerror', err => logs.push('[PAGE_ERROR] ' + err.message));

    await page.goto('http://localhost:8080', { waitUntil: 'networkidle' });
    await page.waitForTimeout(3000);

    // Brush Select 활성화
    await page.click('button[data-menu="preprocess"]');
    await page.waitForTimeout(200);
    await page.click('#mi-select-faces');
    await page.waitForTimeout(4000); // 복셀 초기화 대기

    // 내부 상태 덤프
    await page.evaluate(() => {
        console.log('=== BC Debug (before click) ===');
        console.log('currentTool:', currentTool);
        console.log('preProcessor:', !!preProcessor);
        console.log('isDrillInitialized:', isDrillInitialized);
        console.log('voxelGrids keys:', JSON.stringify(Object.keys(voxelGrids)));
        console.log('voxelMeshes keys:', JSON.stringify(Object.keys(voxelMeshes)));
        if (preProcessor) {
            console.log('brushSelection count:', preProcessor.getBrushSelectionCount());
            console.log('voxelGrids in pre:', JSON.stringify(Object.keys(preProcessor.voxelGrids)));
        }
    });

    // 캔버스 좌표
    const box = await page.locator('#canvas-container').boundingBox();
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;

    // 마우스 호버 - intersection 확인
    await page.mouse.move(cx, cy);
    await page.waitForTimeout(500);
    await page.evaluate(() => {
        raycaster.setFromCamera(mouse, camera);
        const objs = isDrillInitialized ? Object.values(voxelMeshes) : Object.values(meshes);
        console.log('raycaster objects count:', objs.length);
        const hits = raycaster.intersectObjects(objs);
        console.log('intersection hits:', hits.length);
        if (hits.length > 0) {
            const p = hits[0].point;
            console.log('hit point:', p.x.toFixed(2), p.y.toFixed(2), p.z.toFixed(2));
            console.log('hit object:', hits[0].object.name);
        } else {
            console.log('NO INTERSECTION - 모델을 벗어난 위치');
        }
        console.log('drillPreview visible:', drillPreview.visible);
        console.log('bcBrushHighlight:', !!bcBrushHighlight, bcBrushHighlight ? 'count=' + bcBrushHighlight.count : '');
    });

    // 좌클릭
    console.log('--- Clicking at', cx.toFixed(0), cy.toFixed(0), '---');
    await page.mouse.click(cx, cy);
    await page.waitForTimeout(500);

    await page.evaluate(() => {
        console.log('=== After click ===');
        console.log('brushSelection count:', preProcessor ? preProcessor.getBrushSelectionCount() : 'no pre');
        console.log('UI bc-selection-count:', document.getElementById('bc-selection-count')?.textContent);
        console.log('bcSelectionHighlight exists:', !!bcSelectionHighlight);
        if (bcSelectionHighlight) {
            console.log('  visible:', bcSelectionHighlight.visible !== false);
            console.log('  count:', bcSelectionHighlight.count);
            console.log('  in scene:', scene.children.includes(bcSelectionHighlight));
        }
    });

    // 다른 위치 시도 (모델이 확실히 있는 곳)
    // 여러 위치에서 클릭 시도
    for (let dx = -100; dx <= 100; dx += 50) {
        await page.mouse.move(cx + dx, cy);
        await page.waitForTimeout(100);
        const hasHit = await page.evaluate(() => {
            raycaster.setFromCamera(mouse, camera);
            const objs = isDrillInitialized ? Object.values(voxelMeshes) : Object.values(meshes);
            return raycaster.intersectObjects(objs).length > 0;
        });
        if (hasHit) {
            console.log(`  Hit at offset dx=${dx}`);
            await page.mouse.click(cx + dx, cy);
            await page.waitForTimeout(200);
            const count = await page.evaluate(() => preProcessor.getBrushSelectionCount());
            console.log(`  After click: selection=${count}`);
            break;
        }
    }

    // 최종 상태
    await page.evaluate(() => {
        console.log('=== Final state ===');
        console.log('total selection:', preProcessor ? preProcessor.getBrushSelectionCount() : 0);
    });

    // 스크린샷
    await page.screenshot({ path: 'debug-bc-screenshot.png' });

    console.log('\n=== Collected logs ===');
    logs.forEach(l => console.log(l));

    await browser.close();
})();
